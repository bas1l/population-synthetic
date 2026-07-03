"""Find the VRAM/offload cliff: raise NUM_PARALLEL, watch tok/s until it collapses.

KV cache scales with NUM_PARALLEL. Past the point where weights+KV exceed VRAM, Ollama
offloads layers to CPU and throughput collapses. This locates that cliff per model — the
true fast-path max NUM_PARALLEL (the useful `workers` ceiling), which the main sweep did not
reach (it capped at the server recommendation) and the load probe overshot (RAM offload).

At each NUM_PARALLEL we measure SINGLE-STREAM decode tok/s (one request — already slow once
weights spill, so it detects the cliff cheaply) plus /api/ps size_vram/size (offload = the
mechanism). Early-stops once offloaded + tok/s collapses. Grid capped at the measured load
ceiling (oom_results.json).

    python docs/development/ollama-parallelism-poc/cliff_sweep.py

MUST NOT run while other probes/sweeps are running. Writes cliff_results.json.
"""
from __future__ import annotations

import json
import os
import statistics
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cliff_results.json")
OOM = os.path.join(HERE, "oom_results.json")
CONTROL = "http://192.168.0.19:11435"
INFER = "http://192.168.0.19:11434"

REC = {
    "gemma4:e4b": 12, "llama3.2:3b-instruct-q4_K_M": 10,
    "OpenLLM-France/Lucie-7B-Instruct:latest": 7, "llama3.1:8b-instruct-q4_K_M": 6,
    "mistral-nemo:12b": 4, "qwen3:14b": 4, "deepseek-r1:14b": 2,
    "gemma2:9b": 1, "llama3.3:70b-instruct-q4_K_M": 1, "deepseek-r1:70b": 1,
    "qwen2.5:72b-instruct-q4_K_M": 1,
}
STEPS = [1, 2, 4, 8, 16, 24, 32, 48, 64]


def is_big(model: str) -> bool:
    return ("70b" in model.lower()) or ("72b" in model.lower())


def load_ceiling() -> dict:
    if not os.path.exists(OOM):
        return {}
    return json.load(open(OOM, encoding="utf-8"))


def grid(model: str, max_ok: int | None, rec: int) -> list[int]:
    if is_big(model):
        return [1]  # weights alone exceed VRAM; always offloaded — one point confirms
    cap = max_ok if isinstance(max_ok, int) else 64
    # coarse doubling + fine resolution around the server rec (where the cliff is expected)
    g = [s for s in STEPS if s < cap] + [cap] + [rec - 1, rec, rec + 1, rec + 2]
    return sorted({s for s in g if 1 <= s <= cap})


def single_stream(model: str, timeout: int, num_predict: int = 96) -> float | None:
    payload = {"model": model, "messages": [{"role": "user", "content": "Write two sentences about Stockholm."}],
               "stream": False, "options": {"num_predict": num_predict, "temperature": 0.7}}
    r = requests.post(f"{INFER}/api/chat", json=payload, timeout=timeout)
    r.raise_for_status()
    d = r.json()
    ct, ns = d.get("eval_count") or 0, d.get("eval_duration") or 0
    return round(ct / (ns / 1e9), 1) if ns else None


def ps_offload(model: str) -> dict:
    try:
        for m in requests.get(f"{INFER}/api/ps", timeout=15).json().get("models", []):
            if m.get("model") == model or m.get("name") == model:
                size, vram = m.get("size") or 0, m.get("size_vram") or 0
                frac = round(vram / size, 3) if size else None
                return {"size_gb": round(size / 1e9, 1), "vram_gb": round(vram / 1e9, 1),
                        "vram_frac": frac, "offloaded": (frac is not None and frac < 0.999)}
    except Exception:  # noqa: BLE001
        pass
    return {"vram_frac": None, "offloaded": None}


def point(model: str, npar: int) -> dict:
    big = is_big(model)
    to = 900 if big else 300
    npred = 32 if big else 96
    try:
        requests.post(f"{CONTROL}/reconfigure", json={"model": model, "num_parallel": npar}, timeout=120).raise_for_status()
        single_stream(model, to, npred)  # warm-up (load)
        toks = [single_stream(model, to, npred) for _ in range(2)]
        tok_s = statistics.median([t for t in toks if t]) if any(toks) else None
        return {"np": npar, "loads": True, "tok_s": tok_s, **ps_offload(model)}
    except Exception as e:  # noqa: BLE001
        return {"np": npar, "loads": False, "error": str(e)[:150]}


def sweep_model(model: str, max_ok, rec: int) -> dict:
    g = grid(model, max_ok, rec)
    print(f"\n=== {model}  grid={g} ===", flush=True)
    curve, peak, cliff = [], 0.0, None
    for npar in g:
        p = point(model, npar)
        curve.append(p)
        if not p["loads"]:
            print(f"  np={npar}: load FAIL {p.get('error')}", flush=True)
            cliff = cliff or {"np": npar, "reason": "load failed"}
            break
        ts = p["tok_s"] or 0
        peak = max(peak, ts)
        print(f"  np={npar}: tok/s={ts} vram_frac={p.get('vram_frac')} offloaded={p.get('offloaded')}", flush=True)
        collapsed = p.get("offloaded") is True or (peak and ts < 0.5 * peak)
        if collapsed:
            cliff = {"np": npar, "tok_s": ts, "peak_tok_s": peak,
                     "vram_frac": p.get("vram_frac"), "reason": "offload/collapse"}
            print(f"  -> CLIFF at np={npar} (tok/s {ts} vs peak {peak})", flush=True)
            break
    return {"grid": g, "curve": curve, "cliff": cliff,
            "last_ok_before_cliff": (cliff["np"] - 1 if cliff and cliff.get("np", 0) > 1 else None)}


def main() -> int:
    ceilings = load_ceiling()
    results = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    for model, rec in REC.items():
        if model in results:
            continue
        max_ok = ceilings.get(model, {}).get("max_ok")
        if max_ok is None and not is_big(model):
            max_ok = 64
        results[model] = sweep_model(model, max_ok, rec)
        json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"\nDone -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

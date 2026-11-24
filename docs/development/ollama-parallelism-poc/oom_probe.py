"""Find the REAL NUM_PARALLEL ceiling per model by pushing until it OOMs on load.

The server's /models value is only a *recommendation*. This probe reconfigures each model
at increasing NUM_PARALLEL and issues a warm-up call (the model loads lazily on first call,
so OOM surfaces there). Exponential search up to the first failure, then binary search to
pin the boundary: highest np that loads OK vs first np that OOMs.

    python docs/development/ollama-parallelism-poc/oom_probe.py

MUST NOT run while sweep_matrix.py is running — both restart the shared container.
Writes oom_results.json (consumed by analyze.py). Resumable: models already present are skipped.
"""
from __future__ import annotations

import json
import os
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "oom_results.json")
CONTROL = "http://192.168.0.19:11435"
INFER = "http://192.168.0.19:11434"

# start probing just above the server-recommended value for each model
REC = {
    "gemma4:e4b": 12,
    "llama3.2:3b-instruct-q4_K_M": 10,
    "OpenLLM-France/Lucie-7B-Instruct:latest": 7,
    "llama3.1:8b-instruct-q4_K_M": 6,
    "mistral-nemo:12b": 4,
    "qwen3:14b": 4,
    "deepseek-r1:14b": 2,
    "gemma2:9b": 1,
    "llama3.3:70b-instruct-q4_K_M": 1,
    "deepseek-r1:70b": 1,
    "qwen2.5:72b-instruct-q4_K_M": 1,
}
HARD_CAP = 64  # never probe beyond this


def is_oom(err: str) -> bool:
    e = err.lower()
    return any(k in e for k in ("memory", "oom", "cuda", "allocat", "500", "vram", "out of"))


def loads_ok(model: str, npar: int) -> tuple[bool, str]:
    """Reconfigure at npar, warm-up call; True if the model loads and answers."""
    try:
        r = requests.post(f"{CONTROL}/reconfigure", json={"model": model, "num_parallel": npar}, timeout=120)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        return False, f"reconfigure: {e}"[:200]
    big = ("70b" in model.lower()) or ("72b" in model.lower())
    try:
        resp = requests.post(
            f"{INFER}/api/chat",
            json={"model": model, "messages": [{"role": "user", "content": "Say OK."}],
                  "stream": False, "options": {"num_predict": 8}},
            timeout=900 if big else 600,
        )
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}: {resp.text[:180]}"
        resp.json()["message"]["content"]
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:200]


def probe_model(model: str) -> dict:
    rec = REC[model]
    print(f"\n=== {model} (rec={rec}) ===", flush=True)
    # confirm rec loads (sanity)
    ok, err = loads_ok(model, rec)
    print(f"  np={rec}: {'OK' if ok else 'FAIL '+err}", flush=True)
    if not ok:
        return {"max_ok": None, "min_fail": rec, "error": err, "note": "even server-rec failed"}

    last_ok, first_fail = rec, None
    npar = rec
    # exponential climb until failure or hard cap
    while npar < HARD_CAP:
        npar = min(npar * 2, HARD_CAP)
        ok, err = loads_ok(model, npar)
        print(f"  np={npar}: {'OK' if ok else 'OOM/FAIL '+err[:80]}", flush=True)
        if ok:
            last_ok = npar
            if npar == HARD_CAP:
                return {"max_ok": last_ok, "min_fail": None,
                        "error": f"no OOM up to hard cap {HARD_CAP}", "note": "ceiling above probe range"}
        else:
            first_fail = npar
            break

    # binary search between last_ok and first_fail
    while first_fail - last_ok > 1:
        mid = (last_ok + first_fail) // 2
        ok, err = loads_ok(model, mid)
        print(f"  np={mid}: {'OK' if ok else 'OOM/FAIL '+err[:80]}", flush=True)
        if ok:
            last_ok = mid
        else:
            first_fail, last_err = mid, err
    return {"max_ok": last_ok, "min_fail": first_fail, "error": err}


def main() -> int:
    results = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            results = json.load(f)
        print(f"Resuming — {len(results)} models already probed.")
    t0 = time.perf_counter()
    for model in REC:
        if model in results:
            continue
        results[model] = probe_model(model)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1)
    print(f"\nDone in {time.perf_counter()-t0:.0f}s -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

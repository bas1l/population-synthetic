"""Full parallelism matrix: all local models x num_parallel x in/out token profiles.

For each model we step server-side NUM_PARALLEL (via the :11435 control API, which restarts
the container per level) and, at each level, fire k=NUM_PARALLEL concurrent requests for
three workload profiles that isolate prefill vs decode:

  * short    : tiny input, short output           (baseline)
  * long_in  : ~2.4k padded input, short output   (prefill-heavy)
  * long_out : tiny input, long generation        (decode-heavy)

Throughput is reported as req/s and output-tok/s (rates, so the per-level request count
can vary without biasing the comparison). Speedup at each level is vs NUM_PARALLEL=1 for
the SAME model+profile. The knee = the level past which throughput stops improving.

Results are appended to sweep_results.jsonl (one row per model/np/profile) and the run is
RESUMABLE: rows already present are skipped, so a restart continues where it left off.

Scope caps (documented, not silent):
  * NUM_PARALLEL capped per model at the server's VRAM-recommended max (going past it OOMs
    on load). Models with max=1 (gemma2:9b, all 70B/72B) have no parallelism to measure —
    we still record their single-stream baseline across profiles.
  * 70B/72B use fewer requests + shorter long_out to keep runtime sane.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

CONTROL = "http://192.168.0.19:11435"
INFER = "http://192.168.0.19:11434"
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_results.jsonl")

# (model tag, server-recommended NUM_PARALLEL max = VRAM ceiling)
MODELS: list[tuple[str, int]] = [
    ("llama3.2:3b-instruct-q4_K_M", 10),
    ("OpenLLM-France/Lucie-7B-Instruct:latest", 7),
    ("llama3.1:8b-instruct-q4_K_M", 6),
    ("gemma2:9b", 1),
    ("gemma4:e4b", 12),
    ("mistral-nemo:12b", 4),
    ("qwen3:14b", 4),
    ("deepseek-r1:14b", 2),
    ("llama3.3:70b-instruct-q4_K_M", 1),
    ("deepseek-r1:70b", 1),
    ("qwen2.5:72b-instruct-q4_K_M", 1),
]

# ~3.7 chars/token filler used to pad the prefill-heavy profile.
_FILLER_UNIT = (
    "The respondent is a resident whose demographic record includes age band, sex, "
    "municipality, household composition, educational attainment, employment status, "
    "and income decile drawn from the national statistical register. "
)


def np_levels(cap: int) -> list[int]:
    lv = [x for x in (1, 2, 4, 8) if x <= cap]
    if cap not in lv:
        lv.append(cap)
    return sorted(set(lv))


def _pad_to_tokens(target_tokens: int) -> str:
    if target_tokens <= 0:
        return ""
    target_chars = int(target_tokens * 3.7)
    reps = max(1, target_chars // len(_FILLER_UNIT) + 1)
    return (_FILLER_UNIT * reps)[:target_chars]


def make_prompt(profile: str, big_model: bool) -> tuple[str, int]:
    task_json = (
        "Respond ONLY with a JSON object: name, age, occupation, city, backstory "
        "(two sentences). Realistic for a resident of Stockholm, Sweden."
    )
    if profile == "short":
        return (task_json, 96)
    if profile == "long_in":
        ctx = _pad_to_tokens(1600 if big_model else 2400)
        return (f"Background context (ignore formatting, use for realism):\n{ctx}\n\n{task_json}", 96)
    if profile == "long_out":
        npred = 384 if big_model else 768
        return (
            "Write a long, detailed life story (occupation history, family, health, "
            "daily routine, aspirations) for a realistic resident of Stockholm, Sweden. "
            "Write continuous prose, at least several hundred words.",
            npred,
        )
    raise ValueError(profile)


def reconfigure(model: str, num_parallel: int) -> None:
    r = requests.post(f"{CONTROL}/reconfigure", json={"model": model, "num_parallel": num_parallel}, timeout=120)
    r.raise_for_status()


def one_call(model: str, prompt: str, num_predict: int, timeout: int) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": num_predict, "temperature": 0.8},
    }
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{INFER}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
        d = r.json()
        return {
            "ok": True,
            "latency": time.perf_counter() - t0,
            "in_tok": int(d.get("prompt_eval_count") or 0),
            "out_tok": int(d.get("eval_count") or 0),
        }
    except Exception as e:  # noqa: BLE001 - record and continue
        return {"ok": False, "latency": time.perf_counter() - t0, "in_tok": 0, "out_tok": 0, "err": str(e)[:200]}


def _one_trial(model: str, npar: int, prompt: str, num_predict: int, n_req: int, timeout: int) -> dict:
    def call(_i: int) -> dict:
        return one_call(model, prompt, num_predict, timeout)

    t0 = time.perf_counter()
    if npar == 1:
        res = [call(i) for i in range(n_req)]
    else:
        with ThreadPoolExecutor(max_workers=npar) as ex:
            res = list(ex.map(call, range(n_req)))
    wall = time.perf_counter() - t0
    ok = [r for r in res if r["ok"]]
    out_tok = sum(r["out_tok"] for r in ok)
    return {
        "wall_s": wall,
        "n_ok": len(ok),
        "req_per_s": len(ok) / wall if wall else 0.0,
        "out_tok_per_s": out_tok / wall if wall else 0.0,
        "mean_in_tok": statistics.mean([r["in_tok"] for r in ok]) if ok else 0.0,
        "mean_out_tok": statistics.mean([r["out_tok"] for r in ok]) if ok else 0.0,
        "mean_lat_s": statistics.mean([r["latency"] for r in ok]) if ok else 0.0,
        "errors": [r.get("err") for r in res if not r["ok"]][:2],
    }


def run_config(model: str, npar: int, profile: str, n_req: int, big_model: bool, trials: int) -> dict:
    """Run ``trials`` independent trials of the config; aggregate by MEDIAN (noise-robust)."""
    prompt, num_predict = make_prompt(profile, big_model)
    per_req_timeout = 900 if big_model else 400

    tr = [_one_trial(model, npar, prompt, num_predict, n_req, per_req_timeout) for _ in range(trials)]
    req_rates = [t["req_per_s"] for t in tr]
    tok_rates = [t["out_tok_per_s"] for t in tr]
    errors = [e for t in tr for e in t["errors"]][:3]
    return {
        "model": model,
        "num_parallel": npar,
        "profile": profile,
        "n_req": n_req,
        "trials": trials,
        "n_ok_min": min(t["n_ok"] for t in tr),
        # median across trials is the headline; min/max show run-to-run spread
        "req_per_s": round(statistics.median(req_rates), 3),
        "req_per_s_min": round(min(req_rates), 3),
        "req_per_s_max": round(max(req_rates), 3),
        "out_tok_per_s": round(statistics.median(tok_rates), 1),
        "out_tok_per_s_spread": round(max(tok_rates) - min(tok_rates), 1),
        "mean_in_tok": round(statistics.median([t["mean_in_tok"] for t in tr]), 0),
        "mean_out_tok": round(statistics.median([t["mean_out_tok"] for t in tr]), 0),
        "mean_lat_s": round(statistics.median([t["mean_lat_s"] for t in tr]), 2),
        "per_trial_req_per_s": [round(x, 3) for x in req_rates],
        "errors": errors,
    }


def load_done() -> set[tuple[str, int, str]]:
    done: set[tuple[str, int, str]] = set()
    if os.path.exists(RESULTS):
        with open(RESULTS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                done.add((d["model"], d["num_parallel"], d["profile"]))
    return done


PROFILES = ["short", "long_in", "long_out"]


def plan() -> list[tuple[str, int, int]]:
    rows = []
    for model, cap in MODELS:
        for npar in np_levels(cap):
            rows.append((model, cap, npar))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--trials", type=int, default=3, help="trials per config, median-aggregated (default 3)")
    ap.add_argument("--big-trials", type=int, default=2, help="trials for 70B/72B models (default 2)")
    args = ap.parse_args()

    combos = plan()
    n_rows = len(combos) * len(PROFILES)
    print(f"Plan: {len(MODELS)} models, {len(combos)} (model,np) reconfigures, "
          f"{n_rows} result rows ({len(PROFILES)} profiles each).")
    for model, cap, npar in combos:
        if npar == np_levels(cap)[0]:
            print(f"  {model}: np levels {np_levels(cap)}")
    if args.dry_run:
        return 0

    done = load_done()
    if done:
        print(f"Resuming — {len(done)} rows already recorded, will skip those.")

    t_start = time.perf_counter()
    for model, cap in MODELS:
        big = ("70b" in model.lower()) or ("72b" in model.lower())
        for npar in np_levels(cap):
            pending = [p for p in PROFILES if (model, npar, p) not in done]
            if not pending:
                continue
            print(f"\n[{time.perf_counter() - t_start:6.0f}s] reconfigure {model} np={npar} ...", flush=True)
            try:
                reconfigure(model, npar)
            except Exception as e:  # noqa: BLE001
                print(f"  !! reconfigure failed: {e} — skipping (model,np)", flush=True)
                continue
            # warm-up loads the model after the container restart
            wu = one_call(model, "Say OK.", 8, 900 if big else 400)
            if not wu["ok"]:
                print(f"  !! warm-up failed: {wu.get('err')} — skipping (model,np)", flush=True)
                continue
            n_req = 4 if big else min(16, max(6, 2 * npar))
            trials = args.big_trials if big else args.trials
            for profile in pending:
                row = run_config(model, npar, profile, n_req, big, trials)
                with open(RESULTS, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
                print(
                    f"    {profile:8s} n={row['n_ok_min']}/{row['n_req']} x{trials}tr "
                    f"in~{row['mean_in_tok']:.0f} out~{row['mean_out_tok']:.0f} | "
                    f"req/s={row['req_per_s']:.3f} (min {row['req_per_s_min']}, max {row['req_per_s_max']}) "
                    f"tok/s={row['out_tok_per_s']:.1f} lat={row['mean_lat_s']:.1f}s"
                    + (f" ERR={row['errors']}" if row["errors"] else ""),
                    flush=True,
                )

    print(f"\nDone in {time.perf_counter() - t_start:.0f}s. Rows in {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

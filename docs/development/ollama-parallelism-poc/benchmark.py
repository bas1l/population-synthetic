"""Standalone POC: prove server-side batching (OLLAMA_NUM_PARALLEL) is faster.

Self-contained (stdlib + ``requests`` only) — does NOT import ``population_synthetic``.
Run it directly:

    python docs/development/ollama-parallelism-poc/benchmark.py --model llama3.2:latest

Two modes, selected automatically by control-API health:

* **Full before/after** (control API on :11435 is up) — reconfigures the server to
  ``NUM_PARALLEL=1`` (the *current* system), benchmarks it, then reconfigures to the
  server-recommended ``NUM_PARALLEL=N``, benchmarks that, and prints the speedup.
  The server is the single source of truth for the worker count; the client fires
  exactly that many concurrent requests.

* **Diagnostic only** (control API unreachable) — cannot change ``NUM_PARALLEL``, so it
  sweeps client concurrency against the inference API and reports whether the server is
  *currently* batching. Flat throughput + linearly-growing latency ⇒ ``NUM_PARALLEL=1``.

The claim being tested: aligning client concurrency with server ``NUM_PARALLEL`` yields
~3-4x aggregate throughput at small added per-request latency, vs the serial baseline.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests

DEFAULT_INFERENCE_URL = "http://192.168.0.19:11434"
DEFAULT_CONTROL_URL = "http://192.168.0.19:11435"

# Representative of the identity-generation workload envelope (small context, JSON out).
PROMPT = (
    "You are generating a synthetic person profile. Respond with a JSON object with keys "
    "name, age, occupation, city, and a two-sentence backstory. Make it realistic for a "
    "resident of Stockholm, Sweden. Vary the details each time."
)


# ---------------------------------------------------------------------------
# Control API (:11435) — the service the server team documented.
# ---------------------------------------------------------------------------
class ControlAPI:
    """Thin wrapper over the parallel-control service. Server = source of truth."""

    def __init__(self, base_url: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=8)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def reconfigure(self, model: str, num_parallel: int | None = None) -> int:
        """Restart the server with NUM_PARALLEL for ``model``; return the worker count.

        Response shape isn't pinned in the docs (``reconfigure(...) -> int``), so we parse
        an int directly or the first plausible integer field, and fail loudly otherwise.
        """
        payload: dict[str, object] = {"model": model}
        if num_parallel is not None:
            payload["num_parallel"] = num_parallel
        r = requests.post(f"{self.base_url}/reconfigure", json=payload, timeout=self.timeout)
        r.raise_for_status()
        body = r.json()
        if isinstance(body, int):
            return body
        if isinstance(body, dict):
            for key in ("workers", "num_parallel", "worker_count", "workers_count"):
                if isinstance(body.get(key), int):
                    return body[key]
        raise RuntimeError(f"Unexpected /reconfigure response, cannot find worker count: {body!r}")


# ---------------------------------------------------------------------------
# Benchmark harness (:11434 inference API)
# ---------------------------------------------------------------------------
@dataclass
class TrialResult:
    concurrency: int
    requests: int
    wall_s: float
    out_tokens: int
    latencies: list[float]

    @property
    def agg_tok_s(self) -> float:
        return self.out_tokens / self.wall_s if self.wall_s else 0.0

    @property
    def mean_latency(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0.0

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return sorted(self.latencies)[min(len(self.latencies) - 1, int(0.95 * len(self.latencies)))]


def _one_call(inference_url: str, model: str, idx: int, num_predict: int) -> tuple[float, int]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": f"{PROMPT} (request #{idx})"}],
        "stream": False,
        "format": "json",
        "options": {"num_predict": num_predict, "temperature": 0.8},
    }
    t0 = time.perf_counter()
    r = requests.post(f"{inference_url}/api/chat", json=payload, timeout=600)
    r.raise_for_status()
    dt = time.perf_counter() - t0
    return dt, int(r.json().get("eval_count") or 0)


def benchmark(inference_url: str, model: str, concurrency: int, n_requests: int,
              num_predict: int) -> TrialResult:
    def call(i: int) -> tuple[float, int]:
        return _one_call(inference_url, model, i, num_predict)

    t0 = time.perf_counter()
    if concurrency == 1:
        results = [call(i) for i in range(n_requests)]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            results = list(ex.map(call, range(n_requests)))
    wall = time.perf_counter() - t0
    return TrialResult(
        concurrency=concurrency,
        requests=n_requests,
        wall_s=wall,
        out_tokens=sum(t for _, t in results),
        latencies=[dt for dt, _ in results],
    )


def _print_row(label: str, tr: TrialResult, baseline: TrialResult | None) -> None:
    speedup = f"{baseline.wall_s / tr.wall_s:5.2f}x" if baseline else "  --  "
    print(
        f"{label:<28} | k={tr.concurrency:>2} | wall={tr.wall_s:7.2f}s | "
        f"agg={tr.agg_tok_s:7.1f} tok/s | mean_lat={tr.mean_latency:6.2f}s | "
        f"p95_lat={tr.p95_latency:6.2f}s | speedup={speedup}"
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_full(control: ControlAPI, inference_url: str, model: str, n_requests: int,
             num_predict: int, force_parallel: int | None) -> None:
    print("Control API reachable — running FULL before/after proof.\n")

    # --- Baseline: the current system (server pinned to NUM_PARALLEL=1) ---
    print("Reconfiguring server: NUM_PARALLEL=1 (baseline / current system)...")
    control.reconfigure(model, num_parallel=1)
    print("Warm-up (loads model after restart)...")
    _one_call(inference_url, model, -1, num_predict)
    baseline = benchmark(inference_url, model, 1, n_requests, num_predict)

    # --- Tuned: server decides the worker count ---
    print("Reconfiguring server: server-recommended NUM_PARALLEL...")
    workers = force_parallel if force_parallel is not None else control.reconfigure(model)
    if force_parallel is not None:
        control.reconfigure(model, num_parallel=force_parallel)
    print(f"Server reports {workers} workers. Warm-up...")
    _one_call(inference_url, model, -1, num_predict)
    tuned = benchmark(inference_url, model, workers, n_requests, num_predict)

    print(f"\n=== RESULTS ({model}, {n_requests} requests) ===")
    _print_row("baseline NUM_PARALLEL=1", baseline, None)
    _print_row(f"tuned NUM_PARALLEL={workers}", tuned, baseline)
    print(
        f"\nVerdict: {baseline.wall_s / tuned.wall_s:.2f}x faster wall-clock, "
        f"{tuned.agg_tok_s / baseline.agg_tok_s:.2f}x aggregate throughput."
    )


def run_diagnostic(inference_url: str, model: str, n_requests: int, num_predict: int,
                   levels: list[int]) -> None:
    print("!! Control API UNREACHABLE — cannot change NUM_PARALLEL.")
    print("   Running DIAGNOSTIC sweep against the inference API instead.")
    print("   Flat throughput + linearly-growing latency => server is at NUM_PARALLEL=1.\n")
    print("Warm-up...")
    _one_call(inference_url, model, -1, num_predict)

    print(f"\n=== DIAGNOSTIC SWEEP ({model}, {n_requests} requests per level) ===")
    baseline: TrialResult | None = None
    for k in levels:
        tr = benchmark(inference_url, model, k, n_requests, num_predict)
        _print_row(f"concurrency k={k}", tr, baseline)
        if baseline is None:
            baseline = tr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="llama3.2:latest", help="Ollama model tag (default: the resident llama3.2)")
    ap.add_argument("--requests", type=int, default=16, help="requests per trial (default: 16)")
    ap.add_argument("--num-predict", type=int, default=200, help="max output tokens per call (default: 200)")
    ap.add_argument("--control-url", default=DEFAULT_CONTROL_URL)
    ap.add_argument("--inference-url", default=DEFAULT_INFERENCE_URL)
    ap.add_argument("--force-parallel", type=int, default=None,
                    help="override server-chosen NUM_PARALLEL for the tuned run")
    ap.add_argument("--levels", default="1,2,4,8",
                    help="diagnostic-mode concurrency levels (default: 1,2,4,8)")
    args = ap.parse_args()

    control = ControlAPI(args.control_url)
    print(f"Model={args.model}  requests/trial={args.requests}  num_predict={args.num_predict}")
    print(f"Inference={args.inference_url}  Control={args.control_url}\n")

    if control.health():
        run_full(control, args.inference_url, args.model, args.requests, args.num_predict,
                 args.force_parallel)
    else:
        levels = [int(x) for x in args.levels.split(",") if x.strip()]
        run_diagnostic(args.inference_url, args.model, args.requests, args.num_predict, levels)
    return 0


if __name__ == "__main__":
    sys.exit(main())

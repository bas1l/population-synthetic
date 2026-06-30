"""
Benchmark: One-Shot vs Persistent ClaudeCodeClient latency.

Runs N simple pings through both architectures and reports latency distributions.

Usage:
    python scripts/dev/benchmark_claude_latency.py --n 100 --model haiku --mode both
    python scripts/dev/benchmark_claude_latency.py --n 5 --model haiku --mode both       # quick sanity check
    python scripts/dev/benchmark_claude_latency.py --n 100 --model haiku --mode both --output data/benchmark_results.json
"""

import argparse
import json
import queue
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


PROMPT = "Reply with exactly one word: PONG"


# ---------------------------------------------------------------------------
# One-shot mode: one subprocess.run() per call
# ---------------------------------------------------------------------------

def oneshot_ping(model: str, prompt: str, timeout: int = 60) -> tuple[str, float]:
    cmd = [
        "claude", "-p",
        "--model", model,
        "--no-session-persistence",
        "--output-format", "json",
        "--tools", "",
    ]
    t0 = time.perf_counter()
    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"oneshot failed (exit {result.returncode}): {stderr[:300]}")

    stdout = (result.stdout or "").strip()
    try:
        parsed = json.loads(stdout)
        text = parsed.get("result", stdout).strip()
    except json.JSONDecodeError:
        text = stdout

    return text, latency_ms


# ---------------------------------------------------------------------------
# Persistent mode: one Popen for all calls via NDJSON stream-json protocol
# ---------------------------------------------------------------------------

class PersistentSession:
    def __init__(self, model: str, timeout: int = 60):
        self._model = model
        self._timeout = timeout
        self._proc = None
        self._queue = None
        self._reader = None

    def __enter__(self):
        cmd = [
            "claude",
            "--model", self._model,
            "--no-session-persistence",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--max-turns", "1",
        ]
        self._queue = queue.Queue()
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader.start()
        return self

    def _reader_loop(self):
        try:
            for line in iter(self._proc.stdout.readline, ""):
                self._queue.put(line)
        finally:
            self._queue.put(None)

    def ping(self, prompt: str) -> tuple[str, float]:
        msg = {
            "type": "user",
            "session_id": "",
            "message": {"role": "user", "content": prompt},
            "parent_tool_use_id": None,
        }
        t0 = time.perf_counter()
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()

        skip_types = {"system", "rate_limit_event", "assistant", "stream_event"}
        deadline = time.monotonic() + self._timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"persistent ping timed out after {self._timeout}s")
            try:
                line = self._queue.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(f"persistent ping timed out after {self._timeout}s")

            if line is None:
                raise RuntimeError("claude process terminated unexpectedly")

            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(parsed, dict) or "type" not in parsed:
                continue
            if parsed["type"] in skip_types:
                continue
            if parsed["type"] == "result":
                latency_ms = (time.perf_counter() - t0) * 1000
                if parsed.get("is_error"):
                    raise RuntimeError(f"persistent error: {parsed.get('result') or parsed.get('error')}")
                text = parsed.get("result", "")
                return (text.strip() if isinstance(text, str) else str(text)), latency_ms

    def __exit__(self, *exc):
        if self._proc is None:
            return
        try:
            self._proc.stdin.close()
        except Exception:
            pass
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        if self._reader is not None:
            self._reader.join(timeout=2)


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_oneshot(n: int, model: str) -> list[dict]:
    results = []
    for i in range(n):
        try:
            text, latency_ms = oneshot_ping(model, PROMPT)
            results.append({"i": i, "ok": True, "text": text, "ms": latency_ms})
            print(f"  oneshot [{i+1:3d}/{n}] {latency_ms:7.0f} ms  {text[:40]}")
        except Exception as e:
            results.append({"i": i, "ok": False, "error": str(e), "ms": None})
            print(f"  oneshot [{i+1:3d}/{n}]   ERROR  {e}")
    return results


def run_persistent(n: int, model: str) -> list[dict]:
    results = []
    with PersistentSession(model) as session:
        for i in range(n):
            try:
                text, latency_ms = session.ping(PROMPT)
                results.append({"i": i, "ok": True, "text": text, "ms": latency_ms})
                print(f"  persistent [{i+1:3d}/{n}] {latency_ms:7.0f} ms  {text[:40]}")
            except Exception as e:
                results.append({"i": i, "ok": False, "error": str(e), "ms": None})
                print(f"  persistent [{i+1:3d}/{n}]   ERROR  {e}")
    return results


# ---------------------------------------------------------------------------
# Statistics & reporting
# ---------------------------------------------------------------------------

def compute_stats(name: str, results: list[dict]) -> dict:
    latencies = [r["ms"] for r in results if r["ok"] and r["ms"] is not None]
    errors = sum(1 for r in results if not r["ok"])

    if not latencies:
        return {"name": name, "n": len(results), "errors": errors, "no_data": True}

    latencies_sorted = sorted(latencies)
    total_ms = sum(latencies)

    def percentile(data, p):
        k = (len(data) - 1) * (p / 100)
        f = int(k)
        c = f + 1 if f + 1 < len(data) else f
        d = k - f
        return data[f] + d * (data[c] - data[f])

    return {
        "name": name,
        "n": len(results),
        "ok": len(latencies),
        "errors": errors,
        "total_s": total_ms / 1000,
        "mean_ms": statistics.mean(latencies),
        "median_ms": statistics.median(latencies),
        "min_ms": latencies_sorted[0],
        "max_ms": latencies_sorted[-1],
        "p5_ms": percentile(latencies_sorted, 5),
        "p95_ms": percentile(latencies_sorted, 95),
        "stdev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
        "calls_per_min": len(latencies) / (total_ms / 1000 / 60) if total_ms > 0 else 0,
    }


def print_report(stats_list: list[dict]) -> None:
    print("\n" + "=" * 78)
    print(f"{'METRIC':<22}", end="")
    for s in stats_list:
        print(f"  {s['name']:>24}", end="")
    print()
    print("-" * 78)

    if any(s.get("no_data") for s in stats_list):
        print("  (no successful calls to report)")
        return

    rows = [
        ("Calls (ok/total)", lambda s: f"{s['ok']}/{s['n']}"),
        ("Errors", lambda s: f"{s['errors']}"),
        ("Total time", lambda s: f"{s['total_s']:.1f} s"),
        ("Mean", lambda s: f"{s['mean_ms']:.0f} ms"),
        ("Median", lambda s: f"{s['median_ms']:.0f} ms"),
        ("Min", lambda s: f"{s['min_ms']:.0f} ms"),
        ("Max", lambda s: f"{s['max_ms']:.0f} ms"),
        ("P5", lambda s: f"{s['p5_ms']:.0f} ms"),
        ("P95", lambda s: f"{s['p95_ms']:.0f} ms"),
        ("Std Dev", lambda s: f"{s['stdev_ms']:.0f} ms"),
        ("Calls/min", lambda s: f"{s['calls_per_min']:.1f}"),
    ]
    for label, fn in rows:
        print(f"  {label:<20}", end="")
        for s in stats_list:
            print(f"  {fn(s):>24}", end="")
        print()

    print("=" * 78)

    if len(stats_list) == 2:
        a, b = stats_list
        if not a.get("no_data") and not b.get("no_data"):
            ratio = a["mean_ms"] / b["mean_ms"] if b["mean_ms"] > 0 else float("inf")
            faster = b["name"] if ratio > 1 else a["name"]
            factor = ratio if ratio > 1 else 1 / ratio
            print(f"\n  {faster} is {factor:.2f}x faster per call (mean).")
            total_ratio = a["total_s"] / b["total_s"] if b["total_s"] > 0 else float("inf")
            faster_total = b["name"] if total_ratio > 1 else a["name"]
            factor_total = total_ratio if total_ratio > 1 else 1 / total_ratio
            print(f"  {faster_total} is {factor_total:.2f}x faster total wall time.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Benchmark one-shot vs persistent Claude CLI latency")
    parser.add_argument("--n", type=int, default=10, help="Number of pings per mode (default: 10)")
    parser.add_argument("--model", type=str, default="haiku", help="Model to use (default: haiku)")
    parser.add_argument("--mode", choices=["oneshot", "persistent", "both"], default="both",
                        help="Which mode(s) to benchmark (default: both)")
    parser.add_argument("--output", type=str, default=None,
                        help="Path to write JSON results (default: auto-generated under data/benchmarks/)")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(f"data/benchmarks/{timestamp}_n{args.n}_{args.model}_{args.mode}")
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else run_dir / "results.json"
    if args.output:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Benchmark: {args.n} pings x model={args.model} x mode={args.mode}")
    print(f"Prompt: {PROMPT!r}")
    print(f"Output: {run_dir}\n")

    all_stats = []
    all_results = {}

    if args.mode in ("oneshot", "both"):
        print(f"--- ONE-SHOT ({args.n} calls) ---")
        t0 = time.perf_counter()
        oneshot_results = run_oneshot(args.n, args.model)
        wall_s = time.perf_counter() - t0
        stats = compute_stats("one-shot", oneshot_results)
        stats["wall_s"] = wall_s
        all_stats.append(stats)
        all_results["oneshot"] = oneshot_results
        print(f"  Wall time: {wall_s:.1f}s\n")

    if args.mode in ("persistent", "both"):
        print(f"--- PERSISTENT ({args.n} calls) ---")
        t0 = time.perf_counter()
        persistent_results = run_persistent(args.n, args.model)
        wall_s = time.perf_counter() - t0
        stats = compute_stats("persistent", persistent_results)
        stats["wall_s"] = wall_s
        all_stats.append(stats)
        all_results["persistent"] = persistent_results
        print(f"  Wall time: {wall_s:.1f}s\n")

    print_report(all_stats)

    payload = {
        "config": {"n": args.n, "model": args.model, "prompt": PROMPT, "timestamp": timestamp},
        "stats": {s["name"]: s for s in all_stats},
        "raw": all_results,
    }
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()

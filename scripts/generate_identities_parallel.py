"""
generate_identities_parallel.py -- Generate N persona identities in parallel.

Usage:
    python scripts/generate_identities_parallel.py \
        --mode configurable \
        --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json \
        --strategy config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json \
        --n 100 \
        --workers 8 \
        --output-dir data/identity/config_004_n100

    python scripts/generate_identities_parallel.py \
        --provider claude \
        --mode configurable \
        --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json \
        --strategy config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json \
        --n 100 \
        --workers 8 \
        --output-dir data/identity/config_004_n100_claude
"""

import argparse
import atexit
import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from population_synth.identity.factory_identity_generator import FactoryIdentityGenerator

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_progress_lock = threading.Lock()
_completed = 0
_failed = 0

_active_clients: set = set()
_active_clients_lock = threading.Lock()


def _atexit_cleanup() -> None:
    with _active_clients_lock:
        clients = list(_active_clients)
    for client in clients:
        try:
            client.close()
        except Exception:
            pass


atexit.register(_atexit_cleanup)


def _generate_one(
    index: int,
    total: int,
    mode: str,
    provider: str,
    model: str,
    config_path: str,
    output_dir: Path,
    kwargs: dict,
) -> tuple[int, bool, str]:
    global _completed, _failed

    persona_dir = output_dir / f"persona_{index:05d}"
    out_file = persona_dir / "identity.json"

    if out_file.exists():
        with _progress_lock:
            _completed += 1
            return index, True, "skipped (exists)"

    client = None
    try:
        if provider == "gemini":
            from population_synth.clients.gemini_client import GeminiClient
            client = GeminiClient(model_name=model)
        elif provider == "claude":
            from population_synth.clients.claude_code_client import ClaudeCodeClient
            client = ClaudeCodeClient(model_name=model)
            with _active_clients_lock:
                _active_clients.add(client)
        else:
            raise ValueError(f"Unknown provider: {provider!r}. Expected 'gemini' or 'claude'.")
        generator = FactoryIdentityGenerator.create_generator(mode, client)
        identity_data, _ = generator.generate_identity(config_path, **kwargs)

        persona_dir.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(identity_data, f, indent=2, ensure_ascii=False)

        with _progress_lock:
            _completed += 1
            c, fa = _completed, _failed
        logger.info("[%d/%d] OK  persona_%05d  (failed: %d)", c, total, index, fa)
        return index, True, "ok"

    except Exception as e:
        with _progress_lock:
            _failed += 1
            c, fa = _completed, _failed
        logger.error("[%d/%d] FAIL persona_%05d: %s  (failed: %d)", c, total, index, e, fa)
        return index, False, str(e)

    finally:
        if client is not None and hasattr(client, "close"):
            client.close()
            with _active_clients_lock:
                _active_clients.discard(client)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate N persona identities in parallel")
    parser.add_argument("--mode", required=True, choices=["batch", "configurable"])
    parser.add_argument("--config", required=True, help="Flat schema / prompt config file")
    parser.add_argument("--strategy", default=None, help="Strategy definition file (required for configurable)")
    parser.add_argument("--n", type=int, required=True, help="Number of identities to generate")
    parser.add_argument("--workers", type=int, default=8, help="Max parallel workers (default: 8)")
    parser.add_argument(
        "--provider",
        default="gemini",
        choices=["gemini", "claude"],
        help="LLM provider to use: gemini or claude (default: gemini)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override. Defaults: gemini -> gemini-2.5-flash, claude -> sonnet",
    )
    parser.add_argument("--output-dir", required=True, help="Output directory for persona_XXXXX/ folders")
    args = parser.parse_args()

    if args.mode == "configurable" and not args.strategy:
        logger.error("--strategy is required for configurable mode")
        sys.exit(1)

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    if args.strategy:
        strategy_path = Path(args.strategy)
        if not strategy_path.exists():
            logger.error("Strategy file not found: %s", strategy_path)
            sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model = args.model or ("gemini-2.5-flash" if args.provider == "gemini" else "sonnet")

    kwargs = {}
    if args.strategy:
        kwargs["strategy_file"] = str(Path(args.strategy))

    logger.info("Provider: %s | Mode: %s | Config: %s | Strategy: %s", args.provider, args.mode, args.config, args.strategy)
    logger.info("Model: %s | Generating %d identities with %d workers -> %s", model, args.n, args.workers, output_dir)

    t0 = time.perf_counter()

    futures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for i in range(args.n):
            fut = executor.submit(
                _generate_one,
                index=i,
                total=args.n,
                mode=args.mode,
                provider=args.provider,
                model=model,
                config_path=str(config_path),
                output_dir=output_dir,
                kwargs=kwargs,
            )
            futures.append(fut)

        results = []
        for fut in as_completed(futures):
            results.append(fut.result())

    elapsed = time.perf_counter() - t0
    ok_count = sum(1 for _, ok, _ in results if ok)
    fail_count = sum(1 for _, ok, _ in results if not ok)

    logger.info("Done in %.1fs. Success: %d, Failed: %d, Output: %s", elapsed, ok_count, fail_count, output_dir)


if __name__ == "__main__":
    main()

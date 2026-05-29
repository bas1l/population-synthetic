"""
generate_identities_parallel.py -- Generate N persona identities in parallel.

Usage:
    # Via manifest (recommended):
    python scripts/generate_identities_parallel.py \
        --manifest config/seed_manifests/identity_manifest_014_claude_haiku.yaml

    # Via manifest with CLI overrides:
    python scripts/generate_identities_parallel.py \
        --manifest config/seed_manifests/identity_manifest_014_claude_haiku.yaml \
        --n 10 --workers 4

    # Via axis IDs (composable experiment config):
    python scripts/generate_identities_parallel.py \
        --model-id claude_haiku \
        --strategy-id all_pick \
        --country-id swedish

    # Via axis IDs with overrides and force regeneration:
    python scripts/generate_identities_parallel.py \
        --model-id ollama_llama33_70b \
        --strategy-id all_generate_evaluate_pick \
        --country-id swedish \
        --n 50 \
        --workers 4 \
        --force

    # Via explicit CLI args:
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
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from population_synth.identity.factory_identity_generator import FactoryIdentityGenerator
from population_synth.identity.llm_interaction_log import LLMInteractionCollector
from population_synth.utils import should_process_task

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
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
    log_llm: bool = False,
    base_url: str | None = None,
    api_key_env_var: str | None = None,
    generation_config: dict | None = None,
    force: bool = False,
    retry_until_success: bool = False,
    structured_output: bool = False,
) -> tuple[int, bool, str]:
    global _completed, _failed

    persona_dir = output_dir / f"persona_{index:05d}"
    out_file = persona_dir / "identity.json"

    if not should_process_task(input_paths=config_path, output_paths=out_file, force=force):
        with _progress_lock:
            _completed += 1
            return index, True, "skipped (up-to-date)"

    cfg = generation_config or {}

    client = None
    generator = None
    try:
        if provider == "gemini":
            from population_synth.clients.gemini_client import GeminiClient
            client = GeminiClient(model_name=model, default_config=cfg)
        elif provider == "claude":
            from population_synth.clients.claude_code_client import ClaudeCodeClient
            client = ClaudeCodeClient(model_name=model, default_config=cfg)
            with _active_clients_lock:
                _active_clients.add(client)
        elif provider == "ollama":
            from population_synth.clients.ollama_client import OllamaClient
            client = OllamaClient(model_name=model, base_url=base_url, default_config=cfg)
            with _active_clients_lock:
                _active_clients.add(client)
        elif provider == "openai_compat":
            from population_synth.clients.openai_compat_client import OpenAICompatClient
            if not base_url:
                raise ValueError("base_url is required for provider 'openai_compat'")
            client = OpenAICompatClient(
                model_name=model,
                base_url=base_url,
                api_key_env_var=api_key_env_var or "OPENAI_API_KEY",
                default_config=cfg,
            )
            with _active_clients_lock:
                _active_clients.add(client)
        else:
            raise ValueError(f"Unknown provider: {provider!r}. Expected 'gemini', 'claude', 'ollama', or 'openai_compat'.")
        generator = FactoryIdentityGenerator.create_generator(mode, client)
        generator.retry_until_success = retry_until_success
        generator.use_structured_output = structured_output
        if log_llm:
            generator.interaction_collector = LLMInteractionCollector(
                persona_dir / "llm_interactions.jsonl"
            )

        identity_data, _ = generator.generate_identity(config_path, **kwargs)

        persona_dir.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(identity_data, f, indent=2, ensure_ascii=False)

        with _progress_lock:
            _completed += 1
            c, fa = _completed, _failed
        logger.info("──── ✓ [%d/%d] persona_%05d OK ──── (failed so far: %d)", c, total, index, fa)
        return index, True, "ok"

    except Exception as e:
        with _progress_lock:
            _failed += 1
            c, fa = _completed, _failed
        logger.error("──── ✗ [%d/%d] persona_%05d FAIL ──── %s  (failed so far: %d)", c, total, index, e, fa)
        return index, False, str(e)

    finally:
        if generator is not None and generator.interaction_collector:
            generator.interaction_collector.close()
        if client is not None and hasattr(client, "close"):
            client.close()
            with _active_clients_lock:
                _active_clients.discard(client)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate N persona identities in parallel")
    parser.add_argument("--manifest", default=None, help="Path to a YAML manifest file (replaces all other arguments)")
    parser.add_argument("--model-id", default=None, help="Axis model ID (e.g., 'claude_haiku') — mutually exclusive with --manifest")
    parser.add_argument("--strategy-id", default=None, help="Axis strategy ID (e.g., 'all_pick') — mutually exclusive with --manifest")
    parser.add_argument("--country-id", default=None, help="Axis country ID (e.g., 'swedish') — mutually exclusive with --manifest")
    parser.add_argument("--mode", default=None, choices=["batch", "configurable"])
    parser.add_argument("--config", default=None, help="Flat schema / prompt config file")
    parser.add_argument("--strategy", default=None, help="Strategy definition file (required for configurable)")
    parser.add_argument("--n", type=int, default=None, help="Number of identities to generate")
    parser.add_argument("--workers", type=int, default=None, help="Max parallel workers (default: 8)")
    parser.add_argument(
        "--provider",
        default=None,
        choices=["gemini", "claude", "ollama", "openai_compat"],
        help="LLM provider to use: gemini, claude, ollama, or openai_compat (default: gemini)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override. Defaults: gemini -> gemini-2.5-flash, claude -> sonnet, ollama -> llama3.2, openai_compat -> mistral-large-latest",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base URL for Ollama or OpenAI-compatible provider (overrides manifest)",
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help="Name of the environment variable holding the API key for openai_compat provider (default: OPENAI_API_KEY)",
    )
    parser.add_argument("--output-dir", default=None, help="Output directory for persona_XXXXX/ folders")
    parser.add_argument(
        "--log-llm",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Log all raw LLM interactions (prompt + response) to llm_interactions.json per persona (default: on)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing personas instead of skipping",
    )
    parser.add_argument(
        "--retry-until-success",
        action="store_true",
        default=False,
        help="Retry failed persona slots and LLM evaluation calls until all N succeed (default: disabled)",
    )
    parser.add_argument(
        "--structured-output",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Use JSON-Schema–constrained decoding for Ollama (default: off)",
    )
    parser.add_argument(
        "--generate-all-strategies",
        action="store_true",
        default=False,
        help="Run all strategies sequentially for the selected model and country",
    )
    args = parser.parse_args()

    if args.generate_all_strategies:
        if not args.model_id or not args.country_id:
            parser.error("--generate-all-strategies requires --model-id and --country-id")

        from population_synth.identity.manifest_loader import discover_axis_values

        strategies = discover_axis_values("strategies")
        if not strategies:
            print("WARNING: No strategies found in config/strategies/")
            sys.exit(1)

        script = str(Path(__file__).resolve())
        for strategy in strategies:
            sid = strategy["id"]
            print(f"\n{'=' * 60}")
            print(f"  STRATEGY: {sid}")
            print(f"{'=' * 60}\n")
            sub_cmd = [sys.executable, script, "--model-id", args.model_id, "--strategy-id", sid, "--country-id", args.country_id]
            if args.n is not None:
                sub_cmd += ["--n", str(args.n)]
            if args.workers is not None:
                sub_cmd += ["--workers", str(args.workers)]
            if args.force:
                sub_cmd.append("--force")
            if args.retry_until_success:
                sub_cmd.append("--retry-until-success")
            if args.structured_output:
                sub_cmd.append("--structured-output")
            subprocess.run(sub_cmd, stdout=sys.stdout, stderr=sys.stderr)

        sys.exit(0)

    axis_ids = [args.model_id, args.strategy_id, args.country_id]
    if args.manifest and any(x is not None for x in axis_ids):
        parser.error("--manifest is mutually exclusive with --model-id, --strategy-id, and --country-id")

    m = None
    _composed_manifest = None

    if args.manifest:
        from population_synth.identity.manifest_loader import load_manifest
        m = load_manifest(args.manifest)
        logger.info("Loaded manifest: %s", m.name)
        if args.provider is None:
            args.provider = m.provider
        if args.model is None:
            args.model = m.model
        if args.mode is None:
            args.mode = m.mode
        if args.config is None:
            args.config = str(m.config_path)
        if args.strategy is None and m.strategy_path:
            args.strategy = str(m.strategy_path)
        if args.log_llm is None:
            args.log_llm = m.log_llm
        if args.n is None and m.parallel_n is not None:
            args.n = m.parallel_n
        if args.workers is None and m.parallel_workers is not None:
            args.workers = m.parallel_workers
        if args.output_dir is None and m.parallel_output_dir is not None:
            args.output_dir = str(m.parallel_output_dir)
        if args.base_url is None and m.base_url is not None:
            args.base_url = m.base_url
        if args.api_key_env is None and m.api_key_env_var is not None:
            args.api_key_env = m.api_key_env_var
        if not args.retry_until_success and m.retry_until_success:
            args.retry_until_success = m.retry_until_success
        if args.structured_output is None:
            args.structured_output = m.structured_output
    elif args.model_id is not None:
        if args.strategy_id is None or args.country_id is None:
            parser.error("--model-id, --strategy-id, and --country-id must all be provided together")
        from population_synth.identity.manifest_loader import compose_manifest
        m = compose_manifest(args.model_id, args.strategy_id, args.country_id)
        _composed_manifest = m
        logger.info("Composed manifest: %s", m.name)
        if args.provider is None:
            args.provider = m.provider
        if args.model is None:
            args.model = m.model
        if args.mode is None:
            args.mode = m.mode
        if args.config is None:
            args.config = str(m.config_path)
        if args.strategy is None and m.strategy_path:
            args.strategy = str(m.strategy_path)
        if args.log_llm is None:
            args.log_llm = m.log_llm
        if args.n is None and m.parallel_n is not None:
            args.n = m.parallel_n
        if args.workers is None and m.parallel_workers is not None:
            args.workers = m.parallel_workers
        if args.output_dir is None and m.parallel_output_dir is not None:
            args.output_dir = str(m.parallel_output_dir)
        if args.base_url is None and m.base_url is not None:
            args.base_url = m.base_url
        if args.api_key_env is None and m.api_key_env_var is not None:
            args.api_key_env = m.api_key_env_var
        if not args.retry_until_success and m.retry_until_success:
            args.retry_until_success = m.retry_until_success
        if args.structured_output is None:
            args.structured_output = m.structured_output

    generation_config = m.generation_config if m is not None else {}

    if args.provider is None:
        args.provider = "gemini"
    if args.log_llm is None:
        args.log_llm = True
    if args.workers is None:
        args.workers = 1
    if args.structured_output is None:
        args.structured_output = False

    if not args.mode or not args.config:
        parser.error("Either --manifest or both --mode and --config are required")
    if not args.n:
        parser.error("Either --manifest (with parallel.n) or --n is required")
    if not args.output_dir:
        parser.error("Either --manifest (with parallel.output_dir) or --output-dir is required")

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

    if _composed_manifest is not None:
        from population_synth.identity.manifest_loader import serialize_manifest
        snapshot_path = output_dir / "manifest_snapshot.yaml"
        snapshot_path.write_text(serialize_manifest(_composed_manifest), encoding="utf-8")
        logger.info("Manifest snapshot written to %s", snapshot_path)

    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run_{time.strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(file_handler)
    logger.info("Log file: %s", log_file)

    if args.model:
        model = args.model
    elif args.provider == "gemini":
        model = "gemini-2.5-flash"
    elif args.provider == "ollama":
        model = "llama3.2"
    elif args.provider == "openai_compat":
        model = "mistral-large-latest"
    else:
        model = "sonnet"

    kwargs = {}
    if args.strategy:
        kwargs["strategy_file"] = str(Path(args.strategy))

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    run_metadata = {
        "name": m.name if m is not None else None,
        "manifest": args.manifest,
        "model_config": {
            "provider": args.provider,
            "model": model,
            "base_url": args.base_url,
        },
        "parameters": {
            "mode": args.mode,
            "config": args.config,
            "strategy": args.strategy,
            "log_llm": args.log_llm,
            "n": args.n,
            "workers": args.workers,
            "output_dir": args.output_dir,
            "force": args.force,
            "retry_until_success": args.retry_until_success,
            "structured_output": args.structured_output,
        },
        "started_at": started_at,
    }
    if _composed_manifest is not None:
        run_metadata["axis_ids"] = {
            "model_id": args.model_id,
            "strategy_id": args.strategy_id,
            "country_id": args.country_id,
        }
    metadata_path = output_dir / "run_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(run_metadata, f, indent=2, ensure_ascii=False)
    logger.info("Run metadata written to %s", metadata_path)

    logger.info("Provider: %s | Mode: %s | Config: %s | Strategy: %s", args.provider, args.mode, args.config, args.strategy)
    logger.info("Model: %s | Generating %d identities with %d workers -> %s", model, args.n, args.workers, output_dir)

    t0 = time.perf_counter()

    pending_indices = list(range(args.n))
    all_results: dict[int, tuple[int, bool, str]] = {}
    round_num = 0

    while pending_indices:
        round_num += 1
        is_retry = round_num > 1

        if is_retry:
            logger.info("--- Retry round %d: %d slot(s) remaining ---", round_num, len(pending_indices))

        round_futures = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for i in pending_indices:
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
                    log_llm=args.log_llm,
                    base_url=args.base_url,
                    api_key_env_var=args.api_key_env,
                    generation_config=generation_config,
                    force=True if is_retry else args.force,
                    retry_until_success=args.retry_until_success,
                    structured_output=args.structured_output,
                )
                round_futures.append(fut)

            for fut in as_completed(round_futures):
                idx, ok, msg = fut.result()
                all_results[idx] = (idx, ok, msg)

        if not args.retry_until_success:
            break

        failed_indices = [idx for idx in pending_indices if not all_results[idx][1]]
        if not failed_indices:
            break

        pending_indices = failed_indices

    results = list(all_results.values())

    elapsed = time.perf_counter() - t0
    ok_count = sum(1 for _, ok, _ in results if ok)
    fail_count = sum(1 for _, ok, _ in results if not ok)

    run_metadata["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    run_metadata["retry_stats"] = {
        "retry_until_success": args.retry_until_success,
        "rounds": round_num,
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(run_metadata, f, indent=2, ensure_ascii=False)

    logger.info("Done in %.1fs. Success: %d, Failed: %d, Output: %s", elapsed, ok_count, fail_count, output_dir)


if __name__ == "__main__":
    main()

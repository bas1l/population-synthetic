"""
generate_identity.py -- Standalone CLI entry point for generating a single persona identity.

Usage:
    # Via manifest (recommended):
    python scripts/generate_identity.py \\
        --manifest config/seed_manifests/identity_manifest_014_claude_haiku.yaml

    # Via axis IDs (composable experiment config):
    python scripts/generate_identity.py \\
        --model-id claude_haiku \\
        --strategy-id all_pick \\
        --country-id swedish

    # Via explicit CLI args:
    python scripts/generate_identity.py \\
        --mode batch \\
        --config config/assets/identity/batch/identity_landscape.json \\
        [--output identity.json]

    python scripts/generate_identity.py \\
        --mode configurable \\
        --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json \\
        --strategy config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json \\
        [--output identity.json]

    python scripts/generate_identity.py \\
        --provider claude \\
        --mode configurable \\
        --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json \\
        --strategy config/assets/identity/configurable/strategies/compared_only_generate_evaluate_random_pick.json

Modes:
    batch         Single-prompt narrative-style generation.
    configurable  Configurable strategy with simulation config file (requires --strategy).

Providers:
    gemini  Use Google Gemini via GeminiClient (default model: gemini-2.5-flash).
    claude  Use Claude via ClaudeCodeClient subprocess wrapper (default model: sonnet).
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from population_synth.identity.factory_identity_generator import FactoryIdentityGenerator
from population_synth.identity.llm_interaction_log import LLMInteractionCollector

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a single persona identity using LLM-based generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/generate_identity.py --mode configurable \\\n"
            "      --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json\n"
        ),
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Path to a YAML manifest file (replaces all other arguments)",
    )
    parser.add_argument("--model-id", default=None, help="Axis model ID (e.g., 'claude_haiku') — mutually exclusive with --manifest")
    parser.add_argument("--strategy-id", default=None, help="Axis strategy ID (e.g., 'all_pick') — mutually exclusive with --manifest")
    parser.add_argument("--country-id", default=None, help="Axis country ID (e.g., 'swedish') — mutually exclusive with --manifest")
    parser.add_argument(
        "--mode",
        default=None,
        choices=["batch", "configurable"],
        help="Identity generation strategy: batch or configurable",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the prompt/schema/simulation config file",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path for the generated identity (default: identity.json)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=["gemini", "claude", "ollama", "openai_compat"],
        help="LLM provider to use: gemini, claude, ollama, or openai_compat (default: gemini)",
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
    parser.add_argument(
        "--strategy",
        default=None,
        help="Path to the strategy definition file (required for configurable mode)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override. Defaults: gemini -> gemini-2.5-flash, claude -> sonnet",
    )
    parser.add_argument(
        "--log-llm",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Log all raw LLM interactions (prompt + response) to llm_interactions.json alongside the output (default: on)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite the output file if it already exists",
    )
    parser.add_argument(
        "--retry-until-success",
        action="store_true",
        default=False,
        help="Retry LLM evaluation calls indefinitely until correct (default: cap at 3)",
    )
    parser.add_argument(
        "--structured-output",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Use JSON-Schema–constrained decoding for Ollama (default: off)",
    )
    args = parser.parse_args()

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
        if args.output is None:
            args.output = m.output
        if args.base_url is None and m.base_url is not None:
            args.base_url = m.base_url
        if args.api_key_env is None and m.api_key_env_var is not None:
            args.api_key_env = m.api_key_env_var
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
        if args.output is None:
            args.output = m.output
        if args.base_url is None and m.base_url is not None:
            args.base_url = m.base_url
        if args.api_key_env is None and m.api_key_env_var is not None:
            args.api_key_env = m.api_key_env_var
        if args.structured_output is None:
            args.structured_output = m.structured_output

    if args.provider is None:
        args.provider = "gemini"
    if args.log_llm is None:
        args.log_llm = True
    if args.output is None:
        args.output = "identity.json"
    if args.structured_output is None:
        args.structured_output = False

    if not args.mode or not args.config:
        parser.error("Either --manifest or both --mode and --config are required")

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    if args.mode == "configurable" and not args.strategy:
        logger.error("--strategy is required for configurable mode")
        sys.exit(1)

    if args.strategy:
        strategy_path = Path(args.strategy)
        if not strategy_path.exists():
            logger.error("Strategy file not found: %s", strategy_path)
            sys.exit(1)

    output_path = Path(args.output)
    log_dir = output_path.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run_{time.strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(file_handler)
    logger.info("Log file: %s", log_file)

    logger.info("Provider: %s | Mode: %s", args.provider, args.mode)
    logger.info("Config: %s", config_path)

    if _composed_manifest is not None:
        from population_synth.identity.manifest_loader import serialize_manifest
        snapshot_path = output_path.parent / "manifest_snapshot.yaml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(serialize_manifest(_composed_manifest), encoding="utf-8")
        logger.info("Manifest snapshot written to %s", snapshot_path)

    generation_config = m.generation_config if m is not None else {}

    if args.provider == "gemini":
        from population_synth.clients.gemini_client import GeminiClient
        client = GeminiClient(model_name=args.model or "gemini-2.5-flash", default_config=generation_config)
    elif args.provider == "claude":
        from population_synth.clients.claude_code_client import ClaudeCodeClient
        client = ClaudeCodeClient(model_name=args.model or "sonnet", default_config=generation_config)
    elif args.provider == "ollama":
        from population_synth.clients.ollama_client import OllamaClient
        client = OllamaClient(model_name=args.model or "llama3.2", base_url=args.base_url, default_config=generation_config)
    elif args.provider == "openai_compat":
        from population_synth.clients.openai_compat_client import OpenAICompatClient
        if not args.base_url:
            raise ValueError("--base-url is required for provider 'openai_compat'")
        client = OpenAICompatClient(
            model_name=args.model or "mistral-large-latest",
            base_url=args.base_url,
            api_key_env_var=args.api_key_env or "OPENAI_API_KEY",
            default_config=generation_config,
        )
    else:
        raise ValueError(f"Unknown provider: {args.provider!r}. Expected 'gemini', 'claude', 'ollama', or 'openai_compat'.")

    logger.info("Model: %s", client.get_current_configuration()["model"])
    generator = FactoryIdentityGenerator.create_generator(args.mode, client)
    generator.retry_until_success = args.retry_until_success
    generator.use_structured_output = args.structured_output

    if args.log_llm:
        llm_log_path = output_path.parent / "llm_interactions.jsonl"
        generator.interaction_collector = LLMInteractionCollector(llm_log_path)

    kwargs = {}
    if args.strategy:
        kwargs["strategy_file"] = str(Path(args.strategy))

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        identity_data, level_strings = generator.generate_identity(str(config_path), **kwargs)
    finally:
        if generator.interaction_collector:
            generator.interaction_collector.close()
    completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(identity_data, f, indent=2, ensure_ascii=False)

    logger.info("Identity written to %s", output_path)

    run_metadata = {
        "name": m.name if m is not None else None,
        "manifest": args.manifest,
        "model_config": {
            "provider": args.provider,
            "model": client.get_current_configuration()["model"],
            "base_url": getattr(client, "base_url", None),
        },
        "parameters": {
            "mode": args.mode,
            "config": args.config,
            "strategy": args.strategy,
            "log_llm": args.log_llm,
            "output": args.output,
            "force": args.force,
        },
        "started_at": started_at,
        "completed_at": completed_at,
    }
    if _composed_manifest is not None:
        run_metadata["axis_ids"] = {
            "model_id": args.model_id,
            "strategy_id": args.strategy_id,
            "country_id": args.country_id,
        }
    metadata_path = output_path.parent / "run_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(run_metadata, f, indent=2, ensure_ascii=False)
    logger.info("Run metadata written to %s", metadata_path)

    if level_strings:
        logger.info("Level summaries:")
        for level_id, summary in level_strings.items():
            # Truncate long summaries for console display
            display = summary[:200] + "..." if len(summary) > 200 else summary
            logger.info("  %s: %s", level_id, display)


if __name__ == "__main__":
    main()

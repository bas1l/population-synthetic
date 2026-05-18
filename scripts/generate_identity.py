"""
generate_identity.py -- Standalone CLI entry point for generating a single persona identity.

Usage:
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
from pathlib import Path

from population_synth.identity.factory_identity_generator import FactoryIdentityGenerator

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
        "--mode",
        required=True,
        choices=["batch", "configurable"],
        help="Identity generation strategy: batch or configurable",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the prompt/schema/simulation config file",
    )
    parser.add_argument(
        "--output",
        default="identity.json",
        help="Output file path for the generated identity (default: identity.json)",
    )
    parser.add_argument(
        "--provider",
        default="gemini",
        choices=["gemini", "claude"],
        help="LLM provider to use: gemini or claude (default: gemini)",
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
    args = parser.parse_args()

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

    logger.info("Provider: %s | Mode: %s", args.provider, args.mode)
    logger.info("Config: %s", config_path)

    if args.provider == "gemini":
        from population_synth.clients.gemini_client import GeminiClient
        client = GeminiClient(model_name=args.model or "gemini-2.5-flash")
    elif args.provider == "claude":
        from population_synth.clients.claude_code_client import ClaudeCodeClient
        client = ClaudeCodeClient(model_name=args.model or "sonnet")
    else:
        raise ValueError(f"Unknown provider: {args.provider!r}. Expected 'gemini' or 'claude'.")

    logger.info("Model: %s", client.model_name)
    generator = FactoryIdentityGenerator.create_generator(args.mode, client)

    kwargs = {}
    if args.strategy:
        kwargs["strategy_file"] = str(Path(args.strategy))

    identity_data, level_strings = generator.generate_identity(str(config_path), **kwargs)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(identity_data, f, indent=2, ensure_ascii=False)

    logger.info("Identity written to %s", output_path)

    if level_strings:
        logger.info("Level summaries:")
        for level_id, summary in level_strings.items():
            # Truncate long summaries for console display
            display = summary[:200] + "..." if len(summary) > 200 else summary
            logger.info("  %s: %s", level_id, display)


if __name__ == "__main__":
    main()

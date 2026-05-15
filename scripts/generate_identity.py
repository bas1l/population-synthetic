"""
generate_identity.py -- Standalone CLI entry point for generating a single persona identity.

Usage:
    python scripts/generate_identity.py \\
        --mode sequential \\
        --config config/assets/identity/sequential/identity_landscape.json \\
        [--output identity.json] \\
        [--model gemini-2.5-flash]

    python scripts/generate_identity.py \\
        --mode batch \\
        --config config/assets/identity/batch/identity_landscape.json \\
        [--output identity.json]

    python scripts/generate_identity.py \\
        --mode configurable \\
        --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json \\
        [--output identity.json]

Modes:
    sequential    Hierarchical level-by-level LLM-refined generation.
    batch         Single-prompt narrative-style generation.
    configurable  Configurable strategy with simulation config file.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from population_synth.clients.gemini_client import GeminiClient
from population_synth.identity.factory_identity_generator import FactoryIdentityGenerator

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a single persona identity using LLM-based generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/generate_identity.py --mode sequential \\\n"
            "      --config config/assets/identity/sequential/identity_landscape.json\n"
            "\n"
            "  python scripts/generate_identity.py --mode configurable \\\n"
            "      --config config/assets/identity/configurable/simulation_config_004_swedish_generative.json\n"
        ),
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["sequential", "batch", "configurable"],
        help="Identity generation strategy: sequential, batch, or configurable",
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
        "--model",
        default="gemini-2.5-flash",
        help="Gemini model name (default: gemini-2.5-flash)",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    logger.info("Mode: %s", args.mode)
    logger.info("Config: %s", config_path)
    logger.info("Model: %s", args.model)

    client = GeminiClient(model_name=args.model)
    generator = FactoryIdentityGenerator.create_generator(args.mode, client)

    identity_data, level_strings = generator.generate_identity(str(config_path))

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

"""
extract_population_from_pipeline.py -- Extract demographic profiles from existing pipeline
identity.json files and output them in the same format as scb_population.json.

Usage:
    python scripts/generate/extract_population_from_pipeline.py --seed-root <path> [--output data/pipeline_population.json]

This is a thin CLI wrapper that delegates extraction logic to
population_synth.comparison.extractor.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from population_synth.comparison.extractor import extract_individual

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract pipeline persona demographics into scb_population.json format"
    )
    parser.add_argument("--seed-root", required=True, help="Path to the seed output directory")
    parser.add_argument(
        "--output", default="data/pipeline_population.json", help="Output file path (default: data/pipeline_population.json)"
    )
    args = parser.parse_args()

    seed_root = Path(args.seed_root)
    if not seed_root.exists():
        logger.error("Seed root does not exist: %s", seed_root)
        sys.exit(1)

    identity_files = sorted(seed_root.glob("persona_*/identity.json"))
    if not identity_files:
        logger.error("No persona_*/identity.json files found under %s", seed_root)
        sys.exit(1)

    logger.info("Found %d identity files under %s", len(identity_files), seed_root)

    individuals: list[dict[str, Any]] = []
    skipped = 0
    for path in identity_files:
        result = extract_individual(path)
        if result is None:
            skipped += 1
        else:
            individuals.append(result)

    if skipped:
        logger.warning("Skipped %d persona(s) due to errors or missing data", skipped)

    output = {
        "metadata": {
            "source": "pipeline",
            "seed_root": str(seed_root.resolve()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n": len(individuals),
            "skipped": skipped,
        },
        "individuals": individuals,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote %d individuals to %s", len(individuals), output_path)


if __name__ == "__main__":
    main()

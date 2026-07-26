"""validate_mapped_personas.py -- per-combo CLI entrypoint for the validate_mapped task.

Runs between mapping and population_cap. For one combo it reads the mapped population
file (``03_Analysis/mapping/{slug}.json``) and records, per mapped persona, whether any
canonical field is left as the ``__UNMAPPED__`` sentinel, writing one CSV per combo
(``03_Analysis/validate_mapped/{slug}.csv``). Non-destructive. ``population_cap`` later
intersects this verdict with ``validate_raw``'s to select N clean personas.

Usage:
    python scripts/analyze/validate_mapped_personas.py \
        --model-id claude_haiku --strategy-id all_pick --country-id swedish
    python scripts/analyze/validate_mapped_personas.py ... --output-base /path/to/02_Data --force

--model-id/--strategy-id/--country-id  Axis IDs identifying the combo. Required.
--output-base   Base output directory. Default: output_base from experiment_defaults.yaml.
--force         Overwrite an existing CSV for this combo (default: skip if present).
"""

from __future__ import annotations

import argparse
import logging
import sys

from population_synthetic.analysis.utils.registry import (
    analysis_output_dir,
    resolve_output_base,
)
from population_synthetic.analysis.utils.validity_csv import upsert_summary_row
from population_synthetic.analysis.validate_mapped import (
    SUMMARY_HEADER,
    summary_row,
    validate_mapped_combo,
)
from population_synthetic.generators.synthetic.manifest_loader import axis_slug

logger = logging.getLogger("validate_mapped")

_PROCESS_ID = "validate_mapped"
_MAPPING_PROCESS_ID = "mapping"

# Folder-level roll-up CSV (one row per combo) at the base of the task's output folder.
_SUMMARY_FILENAME = "_summary.csv"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check one combination's mapped personas for unmapped (__UNMAPPED__) values, "
            "writing one CSV per combo."
        )
    )
    parser.add_argument("--model-id", required=True, help="Axis model ID (e.g., 'claude_haiku').")
    parser.add_argument("--strategy-id", required=True, help="Axis strategy ID (e.g., 'all_pick').")
    parser.add_argument("--country-id", required=True, help="Axis country ID (e.g., 'swedish').")
    parser.add_argument(
        "--output-base",
        default=None,
        help="Base output directory (the run base). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing CSV for this combo (default: skip if present).",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()

    slug = axis_slug(args.model_id, args.strategy_id, args.country_id)
    output_base = resolve_output_base(args.output_base)

    mapped_file = analysis_output_dir(_MAPPING_PROCESS_ID, output_base, for_read=True) / f"{slug}.json"
    out_csv = analysis_output_dir(_PROCESS_ID, output_base) / f"{slug}.csv"

    logger.info("validate_mapped: combo %r", slug)
    logger.info("  mapped source: %s", mapped_file)
    logger.info("  csv dest     : %s", out_csv)

    if out_csv.exists() and not args.force:
        logger.info("  SKIP (exists): %s -- pass --force to overwrite.", out_csv)
        return

    if not mapped_file.is_file():
        logger.warning(
            "  no mapped file for combo %r (%s); writing an empty CSV. "
            "Mapping produced no synthetic population for this combo.",
            slug,
            mapped_file,
        )

    summary = validate_mapped_combo(slug, mapped_file, out_csv)

    summary_path = analysis_output_dir(_PROCESS_ID, output_base) / _SUMMARY_FILENAME
    upsert_summary_row(summary_path, SUMMARY_HEADER, summary_row(summary))

    logger.info(
        "  %d persona(s): %d passed, %d failed (unmapped values)",
        summary["n"],
        summary["passed"],
        summary["failed"],
    )
    logger.info("  summary upserted: %s", summary_path)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

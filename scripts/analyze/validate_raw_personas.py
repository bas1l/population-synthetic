"""validate_raw_personas.py -- per-combo CLI entrypoint for the validate_raw task.

The analysis-DAG root. Before mapping, it checks each raw ``persona_*`` directory of one
combo for completeness -- ``identity.json`` present, and every expected category
(config-driven, from the country's mapping ``_index``) carrying a non-empty value -- and
writes one CSV per combo (``03_Analysis/validate_raw/{slug}.csv``). Non-destructive: reads
``01_Raw``, never mutates it. ``population_cap`` later intersects this verdict with
``validate_mapped``'s to select N clean personas.

Usage:
    python scripts/analyze/validate_raw_personas.py \
        --model-id claude_haiku --strategy-id all_pick --country-id swedish
    python scripts/analyze/validate_raw_personas.py ... --output-base /path/to/02_Data --force

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
from population_synthetic.analysis.validate_raw import (
    SUMMARY_HEADER,
    expected_raw_keys,
    summary_row,
    validate_raw_combo,
)
from population_synthetic.generators.synthetic.manifest_loader import axis_slug

logger = logging.getLogger("validate_raw")

# The raw generation stage folder under output_base (an input stage, not a registry
# process), globbed for this combo's persona_* directories.
_RAW_STAGE_DIR = "01_Raw"

_PROCESS_ID = "validate_raw"

# Folder-level roll-up CSV (one row per combo) at the base of the task's output folder.
_SUMMARY_FILENAME = "_summary.csv"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check one combination's raw personas for completeness (identity.json present "
            "and every expected category populated), writing one CSV per combo."
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

    raw_slug_dir = output_base / _RAW_STAGE_DIR / slug
    if not raw_slug_dir.is_dir():
        raise FileNotFoundError(
            f"Raw combo directory not found for slug {slug!r}: {raw_slug_dir}. "
            f"Generate the population for this combo before validating."
        )

    out_csv = analysis_output_dir(_PROCESS_ID, output_base) / f"{slug}.csv"
    logger.info("validate_raw: combo %r", slug)
    logger.info("  raw source: %s", raw_slug_dir)
    logger.info("  csv dest  : %s", out_csv)

    if out_csv.exists() and not args.force:
        logger.info("  SKIP (exists): %s -- pass --force to overwrite.", out_csv)
        return

    expected_keys = expected_raw_keys(args.country_id)
    summary = validate_raw_combo(slug, raw_slug_dir, expected_keys, out_csv)

    summary_path = analysis_output_dir(_PROCESS_ID, output_base) / _SUMMARY_FILENAME
    upsert_summary_row(summary_path, SUMMARY_HEADER, summary_row(summary))

    logger.info(
        "  %d persona(s): %d passed, %d failed (%d missing identity.json)",
        summary["n"],
        summary["passed"],
        summary["failed"],
        summary["missing_identity"],
    )
    logger.info("  summary upserted: %s", summary_path)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

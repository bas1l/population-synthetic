"""cap_populations.py -- per-combo CLI entrypoint for the population_cap task.

The population-cap task runs LAST of the validation gate (validate_raw -> mapping ->
validate_mapped -> population_cap). For a combination it intersects the two per-combo
validity CSVs to the clean persona ids, seeded-selects ``--n`` of them, copies the
selected raw persona directories into the capped mirror under
``{output_base}/03_Analysis/population_cap/{slug}/`` (telemetry for generation-metadata),
and writes the capped mapped file + copied real reference under
``.../population_cap/_mapped/`` (consumed by every mapped-file analysis). No downstream
task analyzes more than N personas, or an incomplete/unmapped one.

This script is a thin per-combo wrapper: it resolves the combo slug from the axis IDs and
the source/destination directories, delegates the seeded selection + copy + mapped-filter
to :func:`population_synthetic.analysis.population_cap.cap_combo`, and records the per-combo
summary in the stage-level ``_index.json`` (raw mirror) and ``_mapped/_index.json``. It
knows nothing about how personas are selected or copied, nor about any statistics.

Usage:
    python scripts/analyze/cap_populations.py \
        --model-id claude_haiku --strategy-id all_pick --country-id swedish --n 100
    python scripts/analyze/cap_populations.py \
        --model-id claude_haiku --strategy-id all_pick --country-id swedish \
        --n 100 --sample-seed 7 --force
    python scripts/analyze/cap_populations.py ... --n 100 --output-base /path/to/02_Data

--model-id      Axis model ID (e.g., 'claude_haiku'). Required.
--strategy-id   Axis strategy ID (e.g., 'all_pick'). Required.
--country-id    Axis country ID (e.g., 'swedish'). Required.
--n             Target number of persona dirs to retain per combo (the cap). Required;
                the task raises if missing or blank (fail-fast; N is never defaulted).
--sample-seed   Seed for the reproducible without-replacement draw (default: 0; 0 is a
                valid seed, not "unset").
--output-base   Base output directory (the run base). Default: output_base from
                config/synthetic/experiment_defaults.yaml.
--force         Overwrite an existing capped mirror for this combo (default: skip if
                the mirror already exists).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from population_synthetic.analysis.population_cap import CapSummary, cap_combo
from population_synthetic.analysis.utils.capped_source import MAPPED_SUBDIR
from population_synthetic.analysis.utils.registry import (
    analysis_output_dir,
    resolve_output_base,
)
from population_synthetic.generators.synthetic.manifest_loader import axis_slug

logger = logging.getLogger("population_cap")

# The raw generation stage folder under output_base (manifest_loader writes runs to
# ``{output_base}/01_Raw/{slug}``). This is the source population the cap subsamples --
# an input stage, not an analysis-output folder, so it is not a registry process.
_RAW_STAGE_DIR = "01_Raw"

_CAP_PROCESS_ID = "population_cap"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seeded-cap one combination's VALIDATED personas to N: select from personas "
            "passing both validity gates, copy the selected raw persona directories into the "
            "capped mirror, and write the capped mapped file consumed by the downstream "
            "mapped-file analyses."
        )
    )
    parser.add_argument("--model-id", required=True, help="Axis model ID (e.g., 'claude_haiku').")
    parser.add_argument("--strategy-id", required=True, help="Axis strategy ID (e.g., 'all_pick').")
    parser.add_argument("--country-id", required=True, help="Axis country ID (e.g., 'swedish').")
    parser.add_argument(
        "--n",
        required=True,
        type=int,
        help="Target number of persona dirs to retain per combo (the cap). "
        "Required -- the task raises if missing or blank (N is never defaulted).",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=0,
        help="Seed for the reproducible without-replacement draw (default: 0).",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Base output directory (the run base). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing capped mirror for this combo (default: skip if present).",
    )
    return parser.parse_args()


def _upsert_index_entry(index_path: Path, entry: dict[str, Any]) -> None:
    """Insert or replace the ``_index.json`` record for ``entry['slug']``, leaving the rest.

    Per-combo runs (one per GUI combo) must accumulate a correct combined index rather
    than clobbering sibling slugs, so we read-modify-write, replacing only the record for
    this slug.
    """
    entries: list[dict[str, Any]] = []
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    for i, existing in enumerate(entries):
        if existing.get("slug") == entry["slug"]:
            entries[i] = entry
            break
    else:
        entries.append(entry)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def _mapped_index_entry(summary: CapSummary) -> dict[str, Any]:
    """Build the ``_mapped/_index.json`` entry from a cap summary.

    Mirrors the mapping stage's ``_index.json`` schema
    (``{slug, country, synthetic_file, real_file, n, skipped}``) so the downstream
    mapped-file consumers iterate the capped index exactly as they did the mapping index.
    """
    return {
        "slug": summary["slug"],
        "country": summary["country"],
        "synthetic_file": summary["synthetic_file"],
        "real_file": summary["real_file"],
        "n": summary["mapped_n"],
        "skipped": summary["synthetic_file"] is None,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()

    slug = axis_slug(args.model_id, args.strategy_id, args.country_id)
    output_base = resolve_output_base(args.output_base)

    raw_slug_dir = output_base / _RAW_STAGE_DIR / slug
    if not raw_slug_dir.is_dir():
        raise FileNotFoundError(
            f"Raw combo directory not found for slug {slug!r}: {raw_slug_dir}. "
            f"Generate the population for this combo before capping."
        )

    mapping_dir = analysis_output_dir("mapping", output_base, for_read=True)
    validate_raw_csv = analysis_output_dir("validate_raw", output_base, for_read=True) / f"{slug}.csv"
    validate_mapped_csv = (
        analysis_output_dir("validate_mapped", output_base, for_read=True) / f"{slug}.csv"
    )

    cap_stage_dir = analysis_output_dir(_CAP_PROCESS_ID, output_base)
    dest_dir = cap_stage_dir / slug
    mapped_dest_dir = cap_stage_dir / MAPPED_SUBDIR
    index_path = cap_stage_dir / "_index.json"
    mapped_index_path = mapped_dest_dir / "_index.json"

    logger.info("population_cap: combo %r (n=%d, seed=%d)", slug, args.n, args.sample_seed)
    logger.info("  raw source  : %s", raw_slug_dir)
    logger.info("  capped dest : %s", dest_dir)
    logger.info("  mapped dest : %s", mapped_dest_dir)

    if dest_dir.exists() and not args.force:
        logger.info(
            "  SKIP (exists): %s -- pass --force to overwrite the existing capped mirror.",
            dest_dir,
        )
        return

    summary: CapSummary = cap_combo(
        slug=slug,
        country=args.country_id,
        raw_slug_dir=raw_slug_dir,
        mapping_dir=mapping_dir,
        validate_raw_csv=validate_raw_csv,
        validate_mapped_csv=validate_mapped_csv,
        n=args.n,
        seed=args.sample_seed,
        dest_dir=dest_dir,
        mapped_dest_dir=mapped_dest_dir,
        force=args.force,
    )

    _upsert_index_entry(index_path, dict(summary))
    _upsert_index_entry(mapped_index_path, _mapped_index_entry(summary))

    logger.info(
        "  capped %d/%d clean persona dir(s) (requested n=%d, truncated=%s); mapped n=%d",
        summary["selected"],
        summary["clean_available"],
        summary["requested_n"],
        summary["truncated"],
        summary["mapped_n"],
    )
    logger.info("  indexes upserted: %s , %s", index_path, mapped_index_path)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, FileExistsError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

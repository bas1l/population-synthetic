"""cap_populations.py -- per-combo CLI entrypoint for the population_cap task.

The population-cap task is the pipeline root: before any mapping or generation-metadata
analysis, it seeded-selects exactly ``--n`` of a combination's generated personas and
copies them into a canonical capped mirror under
``{output_base}/03_Analysis/population_cap/{slug}/``. Every downstream raw-persona
consumer reads that mirror instead of the full ``01_Raw/{slug}/`` directory, so no task
analyzes more than N personas.

This script is a thin per-combo wrapper: it resolves the combo slug from the axis IDs,
resolves the raw source and capped-mirror destination directories, delegates the actual
seeded selection + copy to
:func:`population_synthetic.analysis.population_cap.cap_combo`, and records the per-combo
summary in the stage-level ``_index.json``. It knows nothing about how personas are
selected or copied, nor about any statistics.

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
            "Seeded-cap one combination's generated personas to N, copying the selected "
            "persona directories into the canonical capped mirror consumed by mapping and "
            "generation-metadata."
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

    cap_stage_dir = analysis_output_dir(_CAP_PROCESS_ID, output_base)
    dest_dir = cap_stage_dir / slug
    index_path = cap_stage_dir / "_index.json"

    logger.info("population_cap: combo %r (n=%d, seed=%d)", slug, args.n, args.sample_seed)
    logger.info("  raw source : %s", raw_slug_dir)
    logger.info("  capped dest: %s", dest_dir)

    if dest_dir.exists() and not args.force:
        logger.info(
            "  SKIP (exists): %s -- pass --force to overwrite the existing capped mirror.",
            dest_dir,
        )
        return

    summary: CapSummary = cap_combo(
        raw_slug_dir,
        args.n,
        args.sample_seed,
        dest_dir,
        force=args.force,
    )

    _upsert_index_entry(index_path, dict(summary))

    logger.info(
        "  capped %d/%d persona dir(s) (requested n=%d, truncated=%s)",
        summary["selected"],
        summary["available"],
        summary["requested_n"],
        summary["truncated"],
    )
    logger.info("  index upserted at %s (slug=%s)", index_path, slug)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, FileExistsError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

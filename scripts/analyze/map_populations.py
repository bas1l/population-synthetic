"""
map_populations.py -- Standalone mapping stage of the comparison pipeline.

Reads an explicit targets list (config/analysis/comparison_targets.yaml) naming the
per-run manifests we consider complete, and writes mapped population files under
{output_base}/03_Analysis/mapped/:

    mapped/
      real_{country}.json       mapped real population, one per country (deduped)
      {slug}.json               mapped synthetic population, one per target
      _index.json               [{slug, country, synthetic_file, real_file, n, skipped}]

Mapping logic itself is reused verbatim from the existing mappers -- the synthetic
side via load_synthetic_population -> map_population and the real side via
load_real_population -> map_population. The comparison stage (Phase 3)
becomes a pure consumer of these mapped files.

Both the synthetic and real mapped files are shaped as
``{"metadata": {...}, "individuals": [...]}`` -- exactly what StatisticalEvaluator
consumes -- so the mapped files are directly ``json.load``-able by the comparison
consumers.

Usage:
    python scripts/analyze/map_populations.py
    python scripts/analyze/map_populations.py --targets config/analysis/comparison_targets.yaml
    python scripts/analyze/map_populations.py --output-base /path/to/02_Data
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.mapping.real_mapper import load_real_population
from population_synthetic.analysis.mapping.real_mapper import map_population as map_real
from population_synthetic.analysis.mapping.synthetic_mapper import (
    load_synthetic_population,
)
from population_synthetic.analysis.mapping.synthetic_mapper import (
    map_population as map_synthetic,
)
from population_synthetic.analysis.utils.country_config import (
    infer_country,
    known_country_ids,
    mappings_for_country,
    real_for_country,
)
from population_synthetic.generators.synthetic.manifest_loader import compose_manifest, load_manifest

_DEFAULT_TARGETS = PROJECT_ROOT / "config" / "analysis" / "comparison_targets.yaml"
_DEFAULTS_PATH = PROJECT_ROOT / "config" / "synthetic" / "experiment_defaults.yaml"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Map the targeted synthetic populations and their real populations to "
        "the canonical comparison schema, writing mapped files under 03_Analysis/mapped/."
    )
    parser.add_argument(
        "--targets",
        default=None,
        help="Targets YAML listing the manifests to map (batch mode). "
        f"Defaults to {_DEFAULT_TARGETS.name} when no axis IDs are given; "
        "mutually exclusive with --model-id/--strategy-id/--country-id.",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Axis model ID (e.g., 'claude_haiku') — axis single-target mode; "
        "mutually exclusive with --targets.",
    )
    parser.add_argument(
        "--strategy-id",
        default=None,
        help="Axis strategy ID (e.g., 'all_pick') — axis single-target mode.",
    )
    parser.add_argument(
        "--country-id",
        default=None,
        help="Axis country ID (e.g., 'swedish') — axis single-target mode.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-map even if the mapped files already exist (default: skip if present).",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Base output directory (the 03_Analysis parent). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    return parser.parse_args()


def _resolve_output_base(cli_value: str | None) -> Path:
    """Resolve output_base from the CLI flag or experiment_defaults.yaml."""
    if cli_value:
        return Path(cli_value)
    with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
        defaults = yaml.safe_load(f) or {}
    output_base = (defaults.get("parameters") or {}).get("output_base")
    if not output_base:
        print(
            f"ERROR: no output_base in {_DEFAULTS_PATH} and --output-base not given",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(output_base)


def _load_targets(targets_path: Path) -> list[dict[str, Any]]:
    """Parse the targets YAML into a list of {manifest_path, country} dicts.

    Accepts both the plain-string form (country inferred later) and the mapping
    form ``{manifest: <path>, country: <id>}`` (explicit country override).
    """
    if not targets_path.exists():
        print(f"ERROR: targets file not found: {targets_path}", file=sys.stderr)
        sys.exit(1)

    with open(targets_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    raw_targets = raw.get("targets")
    if not raw_targets:
        print(f"ERROR: no 'targets' list in {targets_path}", file=sys.stderr)
        sys.exit(1)

    parsed: list[dict[str, Any]] = []
    for entry in raw_targets:
        if isinstance(entry, str):
            parsed.append({"manifest": entry, "country": None})
        elif isinstance(entry, dict):
            manifest = entry.get("manifest")
            if not manifest:
                raise ValueError(f"Target mapping entry missing 'manifest': {entry!r}")
            parsed.append({"manifest": manifest, "country": entry.get("country")})
        else:
            raise ValueError(
                f"Target entry must be a string or a mapping, got {type(entry).__name__}: {entry!r}"
            )
    return parsed


def _resolve_country(manifest, override: str | None, manifest_path: Path) -> str:
    """Resolve the country for a target: explicit override or inferred from config."""
    if override is not None:
        if override not in known_country_ids():
            raise ValueError(
                f"Unknown country {override!r} for target {manifest_path}: "
                f"valid ids are {sorted(known_country_ids())}."
            )
        return override
    return infer_country(manifest.config_path)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _skipped_entry(slug: str, country: str) -> dict[str, Any]:
    """The _index.json entry for a target whose synthetic run is not (yet) mappable."""
    return {
        "slug": slug,
        "country": country,
        "synthetic_file": None,
        "real_file": None,
        "n": 0,
        "skipped": True,
    }


def _map_one_target(
    manifest,
    country: str,
    slug: str,
    mapped_dir: Path,
    real_files: dict[str, str],
    force: bool,
) -> dict[str, Any]:
    """Map one synthetic run and its real population; return the _index.json entry.

    ``real_files`` is a mutable ``{country: filename}`` cache shared across calls so the
    real population for a country is mapped at most once per invocation. Unless ``force``
    is set, an already-mapped ``{slug}.json`` / ``real_{country}.json`` is reused rather
    than re-mapped (idempotent, cheap repeated runs).
    """
    print(f"[{slug}] country={country}")
    synthetic_file = mapped_dir / f"{slug}.json"

    # --- Synthetic side: reuse if present, else load raw identities and map.
    if not force and synthetic_file.exists():
        with open(synthetic_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
        n_mapped = existing["metadata"]["n"]
        n_skipped = existing["metadata"].get("skipped", 0)
        print(f"  SKIP (exists): {synthetic_file} (n={n_mapped}, skipped={n_skipped})")
    else:
        seed_root = manifest.parallel_output_dir

        # Seed-root guards (mirroring score_fidelity_all.py): warn & skip, never crash.
        if seed_root is None or not seed_root.exists():
            print(f"  SKIP: parallel_output_dir does not exist: {seed_root}")
            return _skipped_entry(slug, country)

        persona_files = list(seed_root.glob("persona_*/identity.json"))
        if not persona_files:
            print(f"  SKIP: no persona_*/identity.json files found under {seed_root}")
            return _skipped_entry(slug, country)

        try:
            raw_synthetic = load_synthetic_population(seed_root)
        except ValueError as exc:
            print(f"  SKIP: {exc}")
            return _skipped_entry(slug, country)

        synthetic_pop = map_synthetic(raw_synthetic, country=country)
        _write_json(synthetic_file, synthetic_pop)
        n_mapped = synthetic_pop["metadata"]["n"]
        n_skipped = synthetic_pop["metadata"].get("skipped", 0)
        print(f"  Mapped synthetic -> {synthetic_file} (n={n_mapped}, skipped={n_skipped})")

    # --- Real side: map once per country, reuse thereafter.
    real_file = mapped_dir / f"real_{country}.json"
    if country not in real_files:
        if force or not real_file.exists():
            real_path = real_for_country(country)
            if not real_path.exists():
                print(f"  ERROR: real file not found for {country}: {real_path}", file=sys.stderr)
                sys.exit(1)
            mappings_path = mappings_for_country(country)
            raw_real = load_real_population(real_path)
            real_pop = map_real(raw_real, country=country, mappings_path=mappings_path)
            _write_json(real_file, real_pop)
            print(f"  Mapped real -> {real_file} (n={len(real_pop['individuals'])})")
        else:
            print(f"  SKIP (exists): {real_file}")
        real_files[country] = real_file.name

    return {
        "slug": slug,
        "country": country,
        "synthetic_file": synthetic_file.name,
        "real_file": real_files[country],
        "n": n_mapped,
        "skipped": n_skipped,
    }


def _upsert_index_entry(index_path: Path, entry: dict[str, Any]) -> None:
    """Insert or replace the ``_index.json`` entry for ``entry['slug']``, leaving the rest.

    Axis single-target runs (one per GUI combo) must never clobber the sibling slugs that
    score_fidelity_all.py iterates, so we merge into the existing index rather than
    rewriting it wholesale.
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
    _write_json(index_path, entries)


def main() -> None:
    args = _parse_args()

    axis_ids = [args.model_id, args.strategy_id, args.country_id]
    axis_mode = any(x is not None for x in axis_ids)

    if axis_mode and args.targets is not None:
        print(
            "ERROR: --targets is mutually exclusive with --model-id/--strategy-id/--country-id",
            file=sys.stderr,
        )
        sys.exit(1)
    if axis_mode and any(x is None for x in axis_ids):
        print(
            "ERROR: --model-id, --strategy-id, and --country-id must all be provided together",
            file=sys.stderr,
        )
        sys.exit(1)

    output_base = _resolve_output_base(args.output_base)
    mapped_dir = output_base / "03_Analysis" / "mapped"
    mapped_dir.mkdir(parents=True, exist_ok=True)
    index_path = mapped_dir / "_index.json"

    # --- Axis single-target mode: map one composed (model, strategy, country) run.
    if axis_mode:
        country = args.country_id
        if country not in known_country_ids():
            print(
                f"ERROR: unknown country {country!r}: valid ids are {sorted(known_country_ids())}.",
                file=sys.stderr,
            )
            sys.exit(1)
        manifest = compose_manifest(args.model_id, args.strategy_id, args.country_id)
        seed_root = manifest.parallel_output_dir
        slug = (
            seed_root.name
            if seed_root is not None
            else f"{args.country_id}_{args.strategy_id}_{args.model_id}"
        )
        print(f"Axis target: {slug} (country={country})")
        print(f"Mapped output dir: {mapped_dir}")
        print()
        entry = _map_one_target(manifest, country, slug, mapped_dir, real_files={}, force=args.force)
        _upsert_index_entry(index_path, entry)
        print(f"\nIndex upserted at {index_path} (slug={slug})")
        return

    # --- Batch mode: map every target in the targets YAML, then rewrite the full index.
    targets_path = Path(args.targets) if args.targets else _DEFAULT_TARGETS
    targets = _load_targets(targets_path)
    print(f"Loaded {len(targets)} target(s) from {targets_path}")
    print(f"Mapped output dir: {mapped_dir}")
    print()

    # Cache the mapped real population per country -- map it once, reuse across targets.
    real_files: dict[str, str] = {}
    index_entries: list[dict[str, Any]] = []

    for target in targets:
        manifest_rel = target["manifest"]
        manifest_path = (PROJECT_ROOT / manifest_rel).resolve()

        manifest = load_manifest(manifest_path)
        country = _resolve_country(manifest, target["country"], manifest_path)

        seed_root = manifest.parallel_output_dir
        slug = seed_root.name if seed_root is not None else manifest_path.stem

        entry = _map_one_target(manifest, country, slug, mapped_dir, real_files, force=args.force)
        index_entries.append(entry)
        print()

    _write_json(index_path, index_entries)
    print(f"Index written to {index_path} ({len(index_entries)} entries)")


if __name__ == "__main__":
    main()

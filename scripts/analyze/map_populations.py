"""
map_populations.py -- Standalone mapping stage of the comparison pipeline.

Reads an explicit targets list (config/analysis/comparison_targets.yaml) naming the
per-run manifests we consider complete, and writes mapped population files under
{output_base}/03_Analysis/mapped/:

    mapped/
      database_{country}.json   mapped reference population, one per country (deduped)
      {slug}.json               mapped synthetic population, one per target
      _index.json               [{slug, country, synthetic_file, database_file, n, skipped}]

Mapping logic itself is reused verbatim from the existing mappers -- the synthetic
side via load_raw_population -> map_population and the reference side via
load_reference_population -> normalize_population. The comparison stage (Phase 3)
becomes a pure consumer of these mapped files.

Both the synthetic and database mapped files are shaped as
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
from population_synthetic.analysis.utils.country_config import (
    infer_country,
    known_country_ids,
    mappings_for_country,
    reference_for_country,
)
from population_synthetic.analysis.mapping.reference_mapper import load_reference_population, normalize_population
from population_synthetic.analysis.mapping.synthetic_mapper import load_raw_population, map_population
from population_synthetic.generators.synthetic.manifest_loader import load_manifest

_DEFAULT_TARGETS = PROJECT_ROOT / "config" / "analysis" / "comparison_targets.yaml"
_DEFAULTS_PATH = PROJECT_ROOT / "config" / "synthetic" / "experiment_defaults.yaml"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Map the targeted synthetic populations and their reference populations to "
        "the canonical comparison schema, writing mapped files under 03_Analysis/mapped/."
    )
    parser.add_argument(
        "--targets",
        default=str(_DEFAULT_TARGETS),
        help=f"Targets YAML listing the manifests to map (default: {_DEFAULT_TARGETS.name}).",
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


def main() -> None:
    args = _parse_args()

    output_base = _resolve_output_base(args.output_base)
    mapped_dir = output_base / "03_Analysis" / "mapped"
    mapped_dir.mkdir(parents=True, exist_ok=True)

    targets = _load_targets(Path(args.targets))
    print(f"Loaded {len(targets)} target(s) from {args.targets}")
    print(f"Mapped output dir: {mapped_dir}")
    print()

    # Cache the mapped database per country -- map it once, reuse across targets.
    database_files: dict[str, str] = {}
    index_entries: list[dict[str, Any]] = []

    for target in targets:
        manifest_rel = target["manifest"]
        manifest_path = (PROJECT_ROOT / manifest_rel).resolve()

        manifest = load_manifest(manifest_path)
        country = _resolve_country(manifest, target["country"], manifest_path)

        seed_root = manifest.parallel_output_dir
        slug = seed_root.name if seed_root is not None else manifest_path.stem
        print(f"[{slug}] country={country}")

        # Seed-root guards (mirroring compare_all_pipelines.py): warn & skip, never crash.
        if seed_root is None or not seed_root.exists():
            print(f"  SKIP: parallel_output_dir does not exist: {seed_root}")
            index_entries.append({
                "slug": slug,
                "country": country,
                "synthetic_file": None,
                "database_file": None,
                "n": 0,
                "skipped": True,
            })
            continue

        persona_files = list(seed_root.glob("persona_*/identity.json"))
        if not persona_files:
            print(f"  SKIP: no persona_*/identity.json files found under {seed_root}")
            index_entries.append({
                "slug": slug,
                "country": country,
                "synthetic_file": None,
                "database_file": None,
                "n": 0,
                "skipped": True,
            })
            continue

        # --- Synthetic side: load raw identities, then map to the canonical schema.
        try:
            raw_synthetic = load_raw_population(seed_root)
        except ValueError as exc:
            print(f"  SKIP: {exc}")
            index_entries.append({
                "slug": slug,
                "country": country,
                "synthetic_file": None,
                "database_file": None,
                "n": 0,
                "skipped": True,
            })
            continue

        synthetic_pop = map_population(raw_synthetic, country=country)
        synthetic_file = mapped_dir / f"{slug}.json"
        _write_json(synthetic_file, synthetic_pop)
        n_mapped = synthetic_pop["metadata"]["n"]
        n_skipped = synthetic_pop["metadata"].get("skipped", 0)
        print(f"  Mapped synthetic -> {synthetic_file} (n={n_mapped}, skipped={n_skipped})")

        # --- Database side: map once per country, reuse thereafter.
        if country not in database_files:
            reference_path = reference_for_country(country)
            if not reference_path.exists():
                print(f"  ERROR: reference file not found for {country}: {reference_path}", file=sys.stderr)
                sys.exit(1)
            mappings_path = mappings_for_country(country)
            raw_database = load_reference_population(reference_path)
            database_pop = normalize_population(raw_database, country=country, mappings_path=mappings_path)
            database_file = mapped_dir / f"database_{country}.json"
            _write_json(database_file, database_pop)
            database_files[country] = database_file.name
            print(f"  Mapped database -> {database_file} (n={len(database_pop['individuals'])})")

        index_entries.append({
            "slug": slug,
            "country": country,
            "synthetic_file": synthetic_file.name,
            "database_file": database_files[country],
            "n": n_mapped,
            "skipped": n_skipped,
        })
        print()

    index_path = mapped_dir / "_index.json"
    _write_json(index_path, index_entries)
    print(f"Index written to {index_path} ({len(index_entries)} entries)")


if __name__ == "__main__":
    main()

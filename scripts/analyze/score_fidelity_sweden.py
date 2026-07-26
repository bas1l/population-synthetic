"""
score_fidelity_sweden.py -- Compare a pre-mapped synthetic population against a pre-mapped
SCB real population (Sweden).

This script performs NO mapping. It consumes the mapped files produced by the map stage
(scripts/analyze/map_populations.py): the mapped synthetic population {mapped-dir}/{slug}.json
and the shared mapped real population {mapped-dir}/real_swedish.json. Run map_populations.py first.

Usage:
    python scripts/analyze/score_fidelity_sweden.py \\
        --manifest config/synthetic/manifests/identity_manifest_022_claude_sonnet.yaml \\
        [--mapped-dir <dir>] \\
        [--output comparison_report.json] \\
        [--charts-dir <dir>] [--no-charts] [--radar-tv-only]

    python scripts/analyze/score_fidelity_sweden.py \\
        --seed-root <path> \\
        [--mapped-dir <dir>] [--output comparison_report.json] ...

    python scripts/analyze/score_fidelity_sweden.py \\
        --mapped-synthetic <dir>/seed_022_all_pick_sonnet.json \\
        --mapped-real <dir>/real_swedish.json

--manifest         Seed manifest YAML; derives the slug from parallel.output_dir basename.
--seed-root        Pipeline seed output directory; the slug is its basename.
--mapped-dir       Directory holding the mapped files (default: the analysis-stage mapping folder).
--mapped-synthetic Explicit path to the mapped synthetic population JSON (overrides --mapped-dir/{slug}).
--mapped-real      Explicit path to the mapped real population JSON (overrides real_swedish.json).
--output           Path for the JSON comparison report (default: analysis-stage fidelity folder, {slug}/{slug}.json).
"""

import argparse
import json
import sys
from pathlib import Path

from population_synthetic.analysis.fidelity.artifacts import write_comparison_artifacts
from population_synthetic.analysis.fidelity.evaluator import StatisticalEvaluator
from population_synthetic.analysis.fidelity.scheme import load_scheme
from population_synthetic.analysis.utils.capped_source import resolve_mapped_dir
from population_synthetic.analysis.utils.registry import (
    analysis_output_dir,
    resolve_output_base,
)

_COUNTRY = "swedish"


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Compare a pre-mapped synthetic population against a pre-mapped SCB real population"
    )
    parser.add_argument(
        "--manifest", default=None,
        help="Seed manifest YAML; derives the slug from parallel.output_dir basename",
    )
    parser.add_argument(
        "--model-id", default=None,
        help="Axis model ID (e.g., 'claude_haiku') — mutually exclusive with --manifest",
    )
    parser.add_argument(
        "--strategy-id", default=None,
        help="Axis strategy ID (e.g., 'all_pick') — mutually exclusive with --manifest",
    )
    parser.add_argument(
        "--country-id", default=None,
        help="Axis country ID (e.g., 'swedish') — mutually exclusive with --manifest",
    )
    parser.add_argument(
        "--seed-root", default=None,
        help="Pipeline seed output directory; the slug is its basename",
    )
    parser.add_argument(
        "--output-base",
        default=None,
        help="Base output directory (the analysis-stage parent). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--mapped-dir",
        default=None,
        help="Directory holding the mapped files (default: the analysis-stage mapping folder).",
    )
    parser.add_argument(
        "--mapped-synthetic",
        default=None,
        help="Explicit path to the mapped synthetic population JSON (overrides --mapped-dir/{slug}.json).",
    )
    parser.add_argument(
        "--mapped-real",
        default=None,
        help="Explicit path to the mapped real population JSON (overrides real_swedish.json).",
    )
    parser.add_argument(
        "--real-label",
        default=None,
        help="Display label for the real population (default: mapped real file stem).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output JSON report path (default: analysis-stage fidelity folder, {slug}/{slug}.json)",
    )
    parser.add_argument(
        "--charts-dir",
        default=None,
        help="Directory to write comparison chart PNGs. Defaults to <output_parent>/<output_stem>/.",
    )
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Skip chart generation.",
    )
    parser.add_argument(
        "--radar-tv-only",
        action="store_true",
        help="On the radar chart, show only the TV-similarity polygon (omit chi-squared p-value overlay).",
    )
    return parser


def resolve_slug(args: argparse.Namespace, parser: argparse.ArgumentParser):
    """Resolve the run slug (and optional manifest) from the parsed args.

    The slug names the mapped synthetic file ({mapped-dir}/{slug}.json). It comes from
    --seed-root's basename, the manifest's parallel.output_dir basename, or -- when an
    explicit --mapped-synthetic path is given -- that file's stem.

    Returns:
        (slug, manifest) where manifest is None unless --manifest or the axis IDs were supplied.
    """
    axis_ids = [args.model_id, args.strategy_id, args.country_id]
    if args.manifest and any(x is not None for x in axis_ids):
        parser.error("--manifest is mutually exclusive with --model-id, --strategy-id, and --country-id")

    manifest = None
    seed_name: str | None = None
    if args.manifest:
        from population_synthetic.generators.synthetic.manifest_loader import load_manifest
        manifest = load_manifest(args.manifest)
        if manifest.parallel_output_dir is not None:
            seed_name = manifest.parallel_output_dir.name
    elif args.model_id is not None:
        if args.strategy_id is None or args.country_id is None:
            parser.error("--model-id, --strategy-id, and --country-id must all be provided together")
        from population_synthetic.generators.synthetic.manifest_loader import compose_manifest
        manifest = compose_manifest(args.model_id, args.strategy_id, args.country_id)
        if manifest.parallel_output_dir is not None:
            seed_name = manifest.parallel_output_dir.name

    if args.seed_root:
        seed_name = Path(args.seed_root).name

    if seed_name is None:
        if args.mapped_synthetic:
            seed_name = Path(args.mapped_synthetic).stem
        else:
            parser.error(
                "Cannot determine the run slug: provide --manifest, the axis IDs, --seed-root, "
                "or an explicit --mapped-synthetic path."
            )

    return seed_name, manifest


def resolve_country(args: argparse.Namespace, manifest) -> str:
    """Resolve the comparison country: which real population and scheme to score against.

    Priority: the explicit ``--country-id`` axis value, then the country inferred from a
    composed/loaded manifest's simulation config, else the default (``swedish``) for the
    manifest-less ``--seed-root`` / ``--mapped-*`` paths that carry no country.
    """
    if args.country_id:
        return args.country_id
    if manifest is not None and getattr(manifest, "config_path", None) is not None:
        from population_synthetic.analysis.utils.country_config import infer_country
        return infer_country(manifest.config_path)
    return _COUNTRY


def _load_mapped(path: Path, label: str) -> dict:
    """json.load a pre-mapped population file, with a clear error if it is absent."""
    if not path.exists():
        print(
            f"ERROR: Mapped {label} file not found: {path}. "
            "Run scripts/analyze/map_populations.py first.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_output_path(args: argparse.Namespace, manifest, slug: str, output_base: Path) -> Path:
    """Determine the JSON report output path from args, manifest, or the comparison default."""
    if args.output:
        return Path(args.output)
    if manifest is not None and manifest.comparison_output_dir is not None:
        return manifest.comparison_output_dir / f"{slug}.json"
    return analysis_output_dir("fidelity", output_base) / slug / f"{slug}.json"


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def score_fidelity(
    real_pop: dict,
    synthetic_pop: dict,
    output_path: Path,
    args: argparse.Namespace,
    slug: str,
    real_label: str,
    country: str,
) -> None:
    """Score the synthetic population against the real population and emit artifacts.

    Writes the JSON report, the CSV marginals summary, and (unless --no-charts)
    the per-attribute bar charts plus the radar chart.
    """
    if synthetic_pop["metadata"]["n"] < 5:
        n = synthetic_pop["metadata"]["n"]
        print(f"WARNING: Synthetic population has only {n} individuals"
              " -- statistical tests will be unreliable.\n")

    scheme = load_scheme(country)
    evaluator = StatisticalEvaluator(real_pop, synthetic_pop, scheme=scheme)
    evaluator.print_summary(real_label, slug)

    report = evaluator.generate_report()
    write_comparison_artifacts(
        report, real_pop, synthetic_pop, output_path, scheme,
        slug=slug, real_label=real_label,
        charts_dir=Path(args.charts_dir) if args.charts_dir else None,
        no_charts=args.no_charts, radar_tv_only=args.radar_tv_only,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    slug, manifest = resolve_slug(args, parser)
    country = resolve_country(args, manifest)
    output_base = resolve_output_base(args.output_base)
    mapped_dir = (
        Path(args.mapped_dir) if args.mapped_dir else resolve_mapped_dir(output_base)
    )

    synthetic_path = Path(args.mapped_synthetic) if args.mapped_synthetic else mapped_dir / f"{slug}.json"
    real_path = Path(args.mapped_real) if args.mapped_real else mapped_dir / f"real_{country}.json"

    synthetic_pop = _load_mapped(synthetic_path, "synthetic")
    real_pop = _load_mapped(real_path, "real")

    real_label = Path(args.real_label).stem if args.real_label else real_path.stem
    output_path = resolve_output_path(args, manifest, slug, output_base)

    score_fidelity(real_pop, synthetic_pop, output_path, args, slug, real_label, country)


if __name__ == "__main__":
    main()

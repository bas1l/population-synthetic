"""analyze_persona_realism.py -- Individual persona realism judge (LLM-as-judge).

Sits AFTER the mapping stage: for each selected generation combination it reads the
already-mapped synthetic population (``03_Analysis/mapping/{slug}.json``, shape
``{"metadata", "individuals"}``) and judges every persona N times with an LLM
(default ``claude-fable-5``), scoring per-persona ``can_exist`` (binary possibility)
and ``typicality`` (0-10 ordinal) plus severity-tagged attribute clashes. It then
reduces round -> persona -> combination into a per-combination impossibility rate
(bootstrap CI), a typicality dispersion vs the SCB real reference (Levene variance
test), and a judge self-reliability metric (ICC / Krippendorff's alpha across
rounds). Each selected country's real API-sourced population (``real_{country}.json``)
is judged as an additional competitor labelled ``real_{country}`` and serves as the
dispersion reference for that country's synthetic combos plus a plotted point on the
headline map.

This script owns argparse, registry/output-dir resolution, and input loading only;
all judging, reduction, statistics, and rendering live in the ``persona_realism``
subpackage (it never reaches into the judge/stats internals). The combo set is
enumerated from the mapping stage ``_index.json`` (decomposed via the shared axis
registry), so it needs ``map_populations.py`` (and the population_cap it depends on)
to have run first. Judge model, rounds, temperature, sampling size, and bootstrap
params are config-driven (``config/analysis/persona_realism/``); cost per combo
reuses ``config/analysis/model_pricing.yaml`` (fail-fast on a missing pricing row).

Outputs are nested one level per country (``persona_realism/{country}/...``), matching
the repo's other per-country analysis outputs:
    {country}/{combo}/persona_XXXXX.json    per-persona verdict cache (combo root; resumable)
    {country}/{combo}/persona_XXXXX.jsonl   per-persona token/timing telemetry (1:1 with the cache)
    {country}/{combo}/{combo}.csv / .json   per-combination stats + cost + validation
    {country}/{combo}/typicality.png/.svg   per-combo typicality distribution
    {country}/{combo}/clash_taxonomy.png/.svg  per-combo attribute-clash taxonomy
    {country}/real_{country}/...            the judged real reference (same layout)
    {country}/headline_map.png/.svg         impossibility rate x typicality-dispersion-vs-real
    {country}/realism_summary.csv           one row per competitor (this country)
    {country}/run_report.json               provenance + per-combo summaries + plotted points
The run-level headline artifacts are per-country: a multi-country CLI batch emits one
headline map / summary / run report under each selected country's folder.

Usage:
    python scripts/analyze/analyze_persona_realism.py
    python scripts/analyze/analyze_persona_realism.py --country swedish
    python scripts/analyze/analyze_persona_realism.py --slug swedish_all_pick_claude_haiku
    python scripts/analyze/analyze_persona_realism.py --model-id claude_haiku \
        --strategy-id all_pick --country-id swedish            # GUI per_combo shape
    python scripts/analyze/analyze_persona_realism.py --sample 50 --workers 8 --force
    python scripts/analyze/analyze_persona_realism.py --judge-model claude-sonnet-5

--country / --country-id   Country axis ID filter. Repeatable. Default: all countries.
--model / --model-id       Model axis ID filter. Repeatable. Default: all models.
--strategy / --strategy-id Strategy axis ID filter. Repeatable. Default: all strategies.
--slug                     Exact slug filter ({country}_{strategy}_{model}). Repeatable.
--output-base              Base output directory. Default: experiment_defaults.yaml.
--force                    Re-judge personas and re-write artifacts (default: resume/skip).
--workers                  Override the config judge-call fan-out width.
--sample                   Override the config per-combo persona sample size (synthetic combos).
--real-sample              Cap personas judged for the real reference population (real_{country}).
--rounds                   Override the config judge rounds per persona (n_rounds; must be >= 1).
--judge-model              Override the config judge model (must be in model_options).
--dpi                      PNG render resolution. Default: 200.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from pathlib import Path
from typing import Any

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.generation_metadata.pricing import load_pricing_table
from population_synthetic.analysis.model_ranking.loader import scheme_attributes
from population_synthetic.analysis.persona_realism.artifacts import (
    ComboArtifacts,
    load_realism_hard_rules,
    write_combo_artifacts,
    write_headline_map,
)
from population_synthetic.analysis.persona_realism.reduce import ComboRealism
from population_synthetic.analysis.persona_realism.runner import JudgeConfig, run_combo_judgements
from population_synthetic.analysis.utils.axes import decompose_slug, diagnose_slug
from population_synthetic.analysis.utils.capped_source import resolve_mapped_dir
from population_synthetic.analysis.utils.registry import analysis_output_dir, resolve_output_base
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_CONFIG_DIR = PROJECT_ROOT / "config" / "analysis" / "persona_realism"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Individual persona realism judge: score each mapped persona's internal "
            "coherence with an LLM and rank every combination (plus the real reference) "
            "on impossibility rate x typicality dispersion."
        )
    )
    # Canonical repeatable filters (CLI batch use).
    parser.add_argument(
        "--country", dest="countries", action="append", default=None, metavar="COUNTRY_ID",
        help="Country axis ID filter. May be repeated. Default: all countries.",
    )
    parser.add_argument(
        "--model", dest="models", action="append", default=None, metavar="MODEL_ID",
        help="Model axis ID filter. May be repeated. Default: all models.",
    )
    parser.add_argument(
        "--strategy", dest="strategies", action="append", default=None, metavar="STRATEGY_ID",
        help="Strategy axis ID filter. May be repeated. Default: all strategies.",
    )
    parser.add_argument(
        "--slug", dest="slugs", action="append", default=None, metavar="SLUG",
        help="Exact slug filter ({country}_{strategy}_{model}). May be repeated.",
    )
    # Singular ``-id`` aliases: the GUI per_combo dispatch emits exactly these three
    # (one combo per subprocess); they fold into the repeatable filters above.
    parser.add_argument("--country-id", dest="country_id", default=None, metavar="COUNTRY_ID",
                        help="Single country axis ID (GUI per_combo dispatch); folds into --country.")
    parser.add_argument("--model-id", dest="model_id", default=None, metavar="MODEL_ID",
                        help="Single model axis ID (GUI per_combo dispatch); folds into --model.")
    parser.add_argument("--strategy-id", dest="strategy_id", default=None, metavar="STRATEGY_ID",
                        help="Single strategy axis ID (GUI per_combo dispatch); folds into --strategy.")
    parser.add_argument(
        "--output-base", default=None,
        help="Base output directory (the analysis-stage parent). "
        "Default: output_base from config/synthetic/experiment_defaults.yaml.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-judge personas from scratch and re-write artifacts (default: resume -- the runner "
        "tops up personas below the --rounds target and skips those already cached; artifacts are "
        "re-written only when the cache changed or the report is missing).",
    )
    parser.add_argument("--workers", type=int, default=None,
                        help="Override the config judge-call fan-out width (ThreadPool workers).")
    parser.add_argument("--sample", type=int, default=None,
                        help="Override the config per-combo persona sample size (synthetic combos).")
    parser.add_argument("--real-sample", type=int, default=None, dest="real_sample",
                        help="Cap personas judged for the real reference population "
                             "(blank = config default, currently 100).")
    parser.add_argument("--rounds", type=int, default=None, dest="rounds",
                        help="Judge rounds per persona (blank = config default, currently 3). Must be >= 1.")
    parser.add_argument("--judge-model", dest="judge_model", default=None,
                        help="Override the config judge model (must be in the config model_options).")
    parser.add_argument("--dpi", type=int, default=200, help="PNG render resolution. Default: 200.")
    return parser.parse_args()


def _split_csv(values: list[str] | None) -> list[str] | None:
    """Split repeated/comma-joined CLI values into a flat list (or ``None``)."""
    if values is None:
        return None
    return [v.strip() for item in values for v in item.split(",") if v.strip()] or None


def _merge_singular(filters: list[str] | None, singular: str | None) -> list[str] | None:
    """Fold a singular ``-id`` value into a repeatable filter list."""
    if singular is None:
        return filters
    merged = list(filters) if filters else []
    if singular not in merged:
        merged.append(singular)
    return merged


def _validate_filter_ids(filter_ids: list[str], axis_ids: set[str], axis_name: str) -> None:
    unknown = [fid for fid in filter_ids if fid not in axis_ids]
    if unknown:
        raise ValueError(
            f"Unknown {axis_name} ID(s): {unknown}. Valid IDs are: {sorted(axis_ids)}"
        )


def _apply_overrides(cfg: JudgeConfig, args: argparse.Namespace) -> JudgeConfig:
    """Return a copy of *cfg* with the CLI overrides applied (fail-fast on bad values)."""
    updates: dict[str, Any] = {}
    if args.judge_model is not None:
        if args.judge_model not in cfg.model_options:
            raise ValueError(
                f"--judge-model {args.judge_model!r} is not in the config model_options "
                f"{list(cfg.model_options)}. Add it to config/analysis/persona_realism/judge.yaml "
                "(and a matching pricing row) before selecting it."
            )
        updates["judge_model"] = args.judge_model
    if args.workers is not None:
        if args.workers < 1:
            raise ValueError(f"--workers must be >= 1, got {args.workers}")
        updates["workers"] = args.workers
    if args.sample is not None:
        if args.sample < 1:
            raise ValueError(f"--sample must be >= 1, got {args.sample}")
        updates["sample_size"] = args.sample
    if args.real_sample is not None:
        if args.real_sample < 1:
            raise ValueError(f"--real-sample must be >= 1, got {args.real_sample}")
        updates["real_sample_size"] = args.real_sample
    if args.rounds is not None:
        if args.rounds < 1:
            raise ValueError(f"--rounds must be >= 1, got {args.rounds}")
        updates["n_rounds"] = args.rounds
    return dataclasses.replace(cfg, **updates) if updates else cfg


def _enumerate_combos(
    mapping_dir: Path,
    *,
    countries: list[str] | None,
    models: list[str] | None,
    strategies: list[str] | None,
    slugs: list[str] | None,
    axis_ids: tuple[list[str], list[str], list[str]],
) -> tuple[list[tuple[str, str, str, str]], list[tuple[str, str]]]:
    """Enumerate selected mapped synthetic combos from the mapping ``_index.json``.

    Returns ``(combos, skipped)`` where *combos* is a list of
    ``(slug, country, strategy, model)`` and *skipped* lists ``(slug, reason)`` for
    index entries that were selected but not usable (no mapped file / undecomposable
    slug). Mirrors ``model_ranking.loader.load_combo_performances``' discovery walk
    but stops at the mapping stage (no fidelity report is required for this task).
    """
    index_path = mapping_dir / "_index.json"
    if not index_path.is_file():
        raise FileNotFoundError(
            f"Mapped index not found: {index_path}. Run scripts/analyze/map_populations.py "
            "(and the population_cap it depends on) first."
        )
    country_ids, strategy_ids, model_ids = axis_ids
    with open(index_path, "r", encoding="utf-8") as fh:
        entries = json.load(fh)

    combos: list[tuple[str, str, str, str]] = []
    skipped: list[tuple[str, str]] = []
    for entry in entries:
        slug = entry["slug"]
        if slugs and slug not in slugs:
            continue
        if entry.get("skipped") is True or entry.get("synthetic_file") is None:
            if not slugs:
                continue  # unselected + unmapped -> silently out of scope
            skipped.append((slug, "skipped during mapping (no mapped synthetic file)"))
            continue
        decomposed = decompose_slug(slug, country_ids, strategy_ids, model_ids)
        if decomposed is None:
            skipped.append((slug, diagnose_slug(slug, country_ids, strategy_ids, model_ids)))
            continue
        country, strategy, model = decomposed
        if countries and country not in countries:
            continue
        if models and model not in models:
            continue
        if strategies and strategy not in strategies:
            continue
        combos.append((slug, country, strategy, model))
    return combos, skipped


def _load_individuals(path: Path, *, what: str) -> list[dict[str, Any]]:
    """Load a mapped population file's ``individuals`` list (fail-fast)."""
    if not path.is_file():
        raise FileNotFoundError(
            f"No mapped {what} population: {path} not found. Run the 'mapping' analysis "
            "task first (scripts/analyze/map_populations.py)."
        )
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    individuals = data.get("individuals")
    if not isinstance(individuals, list):
        raise ValueError(f"Mapped {what} population {path} has no 'individuals' list")
    return individuals


def _run_one_combo(
    *,
    label: str,
    individuals: list[dict[str, Any]],
    analyzed_attrs: list[str],
    out_dir: Path,
    scb_ref: ComboRealism | None,
    cfg: JudgeConfig,
    dpi: int,
    force: bool,
    hard_rules: Any,
    pricing: Any,
    sample_size_override: int | None = None,
) -> ComboArtifacts:
    """Judge (top-up if needed) then compute + render one combination's artifacts.

    The runner is **always** invoked -- its per-persona, round-count-aware resume
    gate is the authority on what needs judging and is cheap when everything is
    already cached (file-existence + round-count reads, no LLM call). This is what
    lets a ``--rounds 1`` run be topped up to ``--rounds 2`` on a later invocation
    even though the combo's ``{label}.json`` report already exists: a combo-level
    report-exists gate would skip the runner wholesale and defeat the top-up.

    Artifacts are re-written only when the runner actually did work (wrote or topped
    up a persona), the report is missing, or *force* is set -- otherwise nothing
    changed on disk, so the idempotent "don't rewrite unchanged outputs" behavior is
    preserved. Under ``--force`` the runner re-judges every persona from scratch
    (truncating) and the artifacts are always rewritten.
    """
    report_path = out_dir / f"{label}.json"
    report_exists = report_path.exists()

    summary = run_combo_judgements(
        individuals, label, analyzed_attrs, out_dir, cfg, force=force,
        sample_size_override=sample_size_override, logger=logger,
    )
    if summary.failed:
        logger.warning(
            "combo %s: %d persona(s) had all rounds fail this run (uncached, retryable)",
            label, summary.failed,
        )

    # Regenerate the combo artifacts when the runner actually changed the cache
    # (wrote a fresh persona or topped one up), when the report is missing, or under
    # --force; otherwise nothing on disk changed and the existing artifacts stand.
    # ``write_combo_artifacts`` is *always* called (its return value seeds the
    # cross-combo headline map + this country's scb_ref), but its file writes key on
    # output-file existence, so a top-up onto an existing combo (data changed, files
    # already present) must force the rewrite to avoid stale artifacts.
    did_work = summary.written > 0 or summary.topped_up > 0
    rewrite_artifacts = did_work or not report_exists or force
    if not rewrite_artifacts:
        logger.info(
            "combo %s: nothing changed (report exists, no personas written/topped-up); "
            "skipping artifact re-write", label,
        )

    return write_combo_artifacts(
        out_dir, label,
        scb_ref=scb_ref, cfg=cfg, dpi=dpi, force=rewrite_artifacts,
        hard_rules=hard_rules, pricing=pricing, logger=logger,
    )


def main() -> None:
    args = _parse_args()

    countries = _merge_singular(_split_csv(args.countries), args.country_id)
    models = _merge_singular(_split_csv(args.models), args.model_id)
    strategies = _merge_singular(_split_csv(args.strategies), args.strategy_id)
    slugs = _split_csv(args.slugs)

    country_ids = sorted(d["id"] for d in discover_axis_values("countries"))
    strategy_ids = sorted(d["id"] for d in discover_axis_values("strategies"))
    model_ids = sorted(d["id"] for d in discover_axis_values("models"))

    try:
        if countries:
            _validate_filter_ids(countries, set(country_ids), "country")
        if models:
            _validate_filter_ids(models, set(model_ids), "model")
        if strategies:
            _validate_filter_ids(strategies, set(strategy_ids), "strategy")
        cfg = _apply_overrides(JudgeConfig.load(_CONFIG_DIR), args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    output_base = resolve_output_base(args.output_base)
    out_root = analysis_output_dir("persona_realism", output_base)
    mapping_dir = resolve_mapped_dir(output_base)

    try:
        combos, skipped = _enumerate_combos(
            mapping_dir,
            countries=countries, models=models, strategies=strategies, slugs=slugs,
            axis_ids=(country_ids, strategy_ids, model_ids),
        )
    except (FileNotFoundError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if skipped:
        print(f"Skipped {len(skipped)} combo(s):")
        for slug, reason in skipped:
            print(f"  {slug}: {reason}")
        print()

    if not combos:
        print(
            "ERROR: no mapped synthetic combos matched the selection. "
            "Run scripts/analyze/map_populations.py first (and check your filters).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load once, share across every combo (fail-fast here surfaces a missing pricing
    # file or malformed hard-rules config before any judging cost is incurred).
    pricing = load_pricing_table()
    hard_rules = load_realism_hard_rules(cfg)

    # Distinct countries drive the real-reference set; group synthetic combos under them.
    combos_by_country: dict[str, list[tuple[str, str, str, str]]] = {}
    for combo in combos:
        combos_by_country.setdefault(combo[1], []).append(combo)

    logger.info(
        "persona_realism: %d combo(s) across %d country/countries; judge_model=%s "
        "n_rounds=%d workers=%d sample=%s real_sample=%s",
        len(combos), len(combos_by_country), cfg.judge_model, cfg.n_rounds, cfg.workers,
        cfg.sample_size, cfg.real_sample_size,
    )

    # One country per iteration: judge that country's real reference, then its synthetic
    # combos against it, then write that country's own headline map / summary / run report
    # under persona_realism/{country}/ (each country has its own real reference marker, so
    # a multi-country batch produces one anchored map per country -- no shared/unmarked map).
    total_ranked = 0
    for country in sorted(combos_by_country):
        analyzed_attrs = scheme_attributes(country)
        real_label = f"real_{country}"
        country_root = out_root / country
        print(f"=== {country.upper()} :: {real_label} (real reference) ===")

        real_individuals = _load_individuals(
            mapping_dir / f"{real_label}.json", what=f"real {country}",
        )
        # The real reference is its own dispersion baseline (no scb_ref) and is capped
        # independently by real_sample_size (deterministic first-N prefix, not the seeded
        # sample_size draw used for synthetic combos); it is the headline reference below.
        real_ca = _run_one_combo(
            label=real_label, individuals=real_individuals, analyzed_attrs=analyzed_attrs,
            out_dir=country_root / real_label, scb_ref=None,
            cfg=cfg, dpi=args.dpi, force=args.force, hard_rules=hard_rules, pricing=pricing,
            sample_size_override=cfg.real_sample_size,
        )
        country_artifacts: list[ComboArtifacts] = [real_ca]
        scb_ref = real_ca.combo  # this country's real ComboRealism (== load_combo_realism)

        for slug, _c, strategy, model in combos_by_country[country]:
            print(f"=== {slug} (strategy={strategy}, model={model}) ===")
            individuals = _load_individuals(mapping_dir / f"{slug}.json", what=f"synthetic {slug}")
            ca = _run_one_combo(
                label=slug, individuals=individuals, analyzed_attrs=analyzed_attrs,
                out_dir=country_root / slug, scb_ref=scb_ref,
                cfg=cfg, dpi=args.dpi, force=args.force, hard_rules=hard_rules, pricing=pricing,
            )
            country_artifacts.append(ca)

        # Per-country headline map + combined CSV + run report. This country's real
        # reference is always the marked y==0 point (one reference per country).
        written = write_headline_map(
            country_artifacts, country_root,
            cfg=cfg, dpi=args.dpi, force=args.force, scb_label=real_label,
            pricing=pricing, logger=logger,
        )
        total_ranked += len(country_artifacts)
        print(f"[{country}] headline map + summary written under {country_root} "
              f"({len(written)} file(s)).")

    print()
    print(f"Competitors ranked: {total_ranked} "
          f"({len(combos_by_country)} real reference(s) + {len(combos)} synthetic combo(s)) "
          f"across {len(combos_by_country)} country/countries.")


if __name__ == "__main__":
    main()

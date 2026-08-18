"""analyze_persona_realism.py -- Individual persona realism judge (LLM-as-judge).

Sits AFTER the mapping stage: for each selected combination it reads the already-mapped
population (``03_Analysis/mapping/{label}.json``, shape ``{"metadata", "individuals"}``)
and judges every persona N times with an LLM, scoring per-persona ``can_exist`` (binary
possibility) and ``typicality`` (0-10 ordinal) plus severity-tagged attribute clashes.
It then reduces round -> persona -> combination into that combination's own
impossibility rate (bootstrap CI), typicality dispersion, and judge self-reliability
metric (ICC / Krippendorff's alpha across rounds).

**This task is strictly per-combination.** Judging one combination requires no other
combination: nothing is compared, ranked, or accumulated across units here, and each
combination's artifacts are byte-reproducible in isolation and independent of the order
in which units were processed. The real API-sourced population is enumerated as an
**ordinary competitor** labelled ``real_{country}`` with no reference role -- it is
judged exactly like a synthetic combination, differing only in its ``real_sample_size``
cap and deterministic prefix draw. Every cross-combination claim (the ranking, the
contrast against the real population, the headline map, factor significance) belongs to
the downstream ``realism_ranking`` task, which consumes the per-persona tidy CSVs this
script writes -- see ``scripts/analyze/rank_persona_realism.py``.

This script owns argparse, registry/output-dir resolution, and input loading only;
all judging, reduction, statistics, and rendering live in the ``persona_realism``
subpackage (it never reaches into the judge/stats internals). The combo set is
enumerated from the mapping stage ``_index.json`` (decomposed via the shared axis
registry), so it needs ``map_populations.py`` (and the population_cap it depends on)
to have run first. Judge model, rounds, temperature, sampling size, and bootstrap
params are config-driven (``config/analysis/persona_realism/``); cost per combo
reuses ``config/analysis/model_pricing.yaml`` (fail-fast on a missing pricing row).

Outputs are nested one level per country (``persona_realism/{country}/...``) and consist
of combination directories ONLY -- no country-level aggregate file is produced here:
    {country}/{combo}/persona_XXXXX.json    per-persona verdict cache (combo root; resumable)
    {country}/{combo}/persona_XXXXX.jsonl   per-persona token/timing telemetry (1:1 with the cache)
    {country}/{combo}/{combo}.csv / .json   this combination's stats + cost + validation
    {country}/{combo}/{combo}_personas.csv  per-persona tidy rows (the realism_ranking contract)
    {country}/{combo}/typicality.png/.svg   this combination's typicality distribution
    {country}/{combo}/clash_taxonomy.png/.svg  this combination's attribute-clash taxonomy
    {country}/real_{country}/...            the real competitor (identical layout)

Usage:
    python scripts/analyze/analyze_persona_realism.py
    python scripts/analyze/analyze_persona_realism.py --country swedish
    python scripts/analyze/analyze_persona_realism.py --slug swedish_all_pick_claude_haiku
    python scripts/analyze/analyze_persona_realism.py --slug real_swedish
    python scripts/analyze/analyze_persona_realism.py --model-id claude_haiku \
        --strategy-id all_pick --country-id swedish            # GUI per_combo shape
    python scripts/analyze/analyze_persona_realism.py --sample 50 --workers 8 --force
    python scripts/analyze/analyze_persona_realism.py --rewrite-artifacts   # no LLM calls

--country / --country-id   Country axis ID filter. Repeatable. Default: all countries.
--model / --model-id       Model axis ID filter. Repeatable. Default: all models.
--strategy / --strategy-id Strategy axis ID filter. Repeatable. Default: all strategies.
--slug                     Exact combination filter ({country}_{strategy}_{model} or
                           real_{country}). Repeatable. Selects ONLY what it names.
--no-real                  Do not enumerate the real_{country} competitor.
--output-base              Base output directory. Default: experiment_defaults.yaml.
--force                    Re-judge personas from scratch AND re-write artifacts. Costs LLM calls.
--rewrite-artifacts        Re-write the derived artifacts from the existing verdict cache
                           WITHOUT re-judging (zero LLM calls). Use after a schema change.
--workers                  Override the config judge-call fan-out width.
--sample                   Override the config per-combo persona sample size (synthetic combos).
--real-sample              Cap personas judged for the real competitor (real_{country}).
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
)
from population_synthetic.analysis.persona_realism.config import JudgeConfig
from population_synthetic.analysis.persona_realism.runner import run_combo_judgements
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
        help="Exact combination filter ({country}_{strategy}_{model}, or real_{country} for "
        "the real competitor). May be repeated. Selects ONLY the combinations it names -- "
        "the real competitor is not pulled in implicitly.",
    )
    parser.add_argument(
        "--no-real", dest="no_real", action="store_true",
        help="Do not enumerate the real_{country} competitor for the selected countries "
        "(it is enumerated by default whenever --slug is not used).",
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
        "re-written only when the cache changed or the report is missing). COSTS LLM CALLS: it "
        "truncates every verdict cache. To rewrite artifacts only, use --rewrite-artifacts.",
    )
    parser.add_argument(
        "--rewrite-artifacts", dest="rewrite_artifacts", action="store_true",
        help="Re-write the derived artifacts ({combo}.json/.csv, {combo}_personas.csv, the "
        "figures) from the EXISTING verdict cache, without re-judging anything -- zero LLM "
        "calls on a fully-cached combination. This is the supported way to regenerate "
        "artifacts after an output-schema change; --force is not (it discards the cache).",
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


@dataclasses.dataclass(frozen=True)
class _Combo:
    """One enumerated unit of work -- a synthetic combination or the real competitor.

    ``is_real_reference`` is a *label*, not a role: the real competitor is judged,
    reduced, scored and rendered exactly like any synthetic combination. The only two
    things it changes are the persona draw (``sample_size_override`` -> a deterministic
    first-N prefix instead of the seeded ``sample_size`` sample, because the mapped real
    population is ~10 000 individuals) and the empty ``model``/``strategy`` recorded in
    the tidy CSV, since it is not a model x method cell.
    """

    label: str
    country: str
    strategy: str
    model: str
    is_real_reference: bool
    sample_size_override: int | None


def _enumerate_combos(
    mapping_dir: Path,
    *,
    countries: list[str] | None,
    models: list[str] | None,
    strategies: list[str] | None,
    slugs: list[str] | None,
    axis_ids: tuple[list[str], list[str], list[str]],
    real_sample_size: int | None,
    include_real: bool,
) -> tuple[list[_Combo], list[tuple[str, str]]]:
    """Enumerate the selected combinations from the mapping ``_index.json``.

    Returns ``(combos, skipped)`` where *combos* is a sorted list of :class:`_Combo`
    and *skipped* lists ``(label, reason)`` for units that were selected but not usable
    (no mapped file / undecomposable slug). Mirrors
    ``model_ranking.loader.load_combo_performances``' discovery walk but stops at the
    mapping stage (no fidelity report is required for this task).

    The ``real_{country}`` competitor is enumerated alongside the synthetic units of
    every selected country, so a broad run judges the full competitor set. An explicit
    ``--slug`` selection is taken literally: it judges exactly the labels it names and
    never pulls the real competitor in behind the caller's back -- which is what lets a
    single slug be judged in complete isolation.
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

    combos: list[_Combo] = []
    skipped: list[tuple[str, str]] = []
    seen_countries: list[str] = []
    for entry in entries:
        slug = entry["slug"]
        if slugs and slug not in slugs:
            continue
        if entry.get("skipped") is True or entry.get("synthetic_file") is None:
            if not slugs:
                continue  # unselected + unmapped -> silently out of scope
            skipped.append((slug, entry.get("skip_reason") or "skipped during mapping (no mapped synthetic file)"))
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
        combos.append(
            _Combo(label=slug, country=country, strategy=strategy, model=model,
                   is_real_reference=False, sample_size_override=None)
        )
        if country not in seen_countries:
            seen_countries.append(country)

    # The real competitor: one per country in scope. Under an explicit --slug selection
    # only the labels literally named are eligible; otherwise every selected country's
    # real population joins the competitor set.
    real_countries: list[str] = []
    if include_real:
        if slugs:
            for label in slugs:
                if not label.startswith("real_"):
                    continue
                country = label[len("real_"):]
                if country not in country_ids:
                    skipped.append((label, f"unknown country {country!r} in real competitor label"))
                    continue
                if countries and country not in countries:
                    continue
                real_countries.append(country)
        else:
            real_countries = list(seen_countries)

    for country in real_countries:
        label = f"real_{country}"
        if not (mapping_dir / f"{label}.json").is_file():
            skipped.append((label, "no mapped real population (run map_populations.py)"))
            continue
        combos.append(
            _Combo(label=label, country=country, strategy="", model="",
                   is_real_reference=True, sample_size_override=real_sample_size)
        )

    combos.sort(key=lambda c: c.label)
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
    combo: _Combo,
    individuals: list[dict[str, Any]],
    analyzed_attrs: list[str],
    out_dir: Path,
    cfg: JudgeConfig,
    dpi: int,
    force: bool,
    rewrite_artifacts: bool = False,
    hard_rules: Any,
    pricing: Any,
) -> ComboArtifacts:
    """Judge (top-up if needed) then compute + render one combination's artifacts.

    Everything this function reads and writes belongs to *combo* alone; it is called
    once per unit and the units are independent, so the caller may process them in any
    order (or not at all) without changing any result.

    The runner is **always** invoked -- its per-persona, round-count-aware resume
    gate is the authority on what needs judging and is cheap when everything is
    already cached (file-existence + round-count reads, no LLM call). This is what
    lets a ``--rounds 1`` run be topped up to ``--rounds 2`` on a later invocation
    even though the combo's ``{label}.json`` report already exists: a combo-level
    report-exists gate would skip the runner wholesale and defeat the top-up.

    Artifacts are re-written when the runner actually did work (wrote or topped up a
    persona), when the report is missing, under *force*, or under *rewrite_artifacts*
    -- otherwise nothing on disk changed and the existing artifacts stand.

    The two rewrite triggers are deliberately distinct. *force* re-judges from scratch
    (truncating every verdict cache) and therefore costs the full LLM bill;
    *rewrite_artifacts* recomputes the derived files from the cache already on disk and
    costs nothing. An output-schema change needs the second, never the first.

    Under *rewrite_artifacts* the runner is put in **plan-only** mode: it still resolves
    the persona roster (so ``n_failed`` counts the personas that left no cache file) but
    makes no judge call. That makes the flag zero-cost *by construction* rather than by
    the operator remembering to match ``--rounds`` to whatever round count is cached --
    a config sitting above the cached count would otherwise silently top every persona
    up, turning a file rewrite into a full re-judge.
    """
    report_path = out_dir / f"{combo.label}.json"
    report_exists = report_path.exists()

    summary = run_combo_judgements(
        individuals, combo.label, analyzed_attrs, out_dir, cfg, force=force,
        plan_only=rewrite_artifacts and not force,
        sample_size_override=combo.sample_size_override, logger=logger,
    )
    if summary.failed:
        logger.warning(
            "combo %s: %d persona(s) had all rounds fail this run (uncached, retryable)",
            combo.label, summary.failed,
        )

    did_work = summary.written > 0 or summary.topped_up > 0
    rewrite = did_work or not report_exists or force or rewrite_artifacts
    if not rewrite:
        logger.info(
            "combo %s: nothing changed (report exists, no personas written/topped-up); "
            "skipping artifact re-write", combo.label,
        )

    return write_combo_artifacts(
        out_dir, combo.label,
        cfg=cfg, dpi=dpi, force=rewrite,
        country=combo.country, model=combo.model, strategy=combo.strategy,
        is_real_reference=combo.is_real_reference,
        expected_ids=list(summary.selected_ids) or None,
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
            real_sample_size=cfg.real_sample_size,
            include_real=not args.no_real,
        )
    except (FileNotFoundError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if skipped:
        print(f"Skipped {len(skipped)} combination(s):")
        for label, reason in skipped:
            print(f"  {label}: {reason}")
        print()

    if not combos:
        print(
            "ERROR: no mapped combination matched the selection. "
            "Run scripts/analyze/map_populations.py first (and check your filters).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load once, share across every combo (fail-fast here surfaces a missing pricing
    # file or malformed hard-rules config before any judging cost is incurred).
    pricing = load_pricing_table()
    hard_rules = load_realism_hard_rules(cfg)

    logger.info(
        "persona_realism: %d combination(s); judge_model=%s n_rounds=%d workers=%d "
        "sample=%s real_sample=%s",
        len(combos), cfg.judge_model, cfg.n_rounds, cfg.workers,
        cfg.sample_size, cfg.real_sample_size,
    )

    # An unordered set of independent units. They are iterated in sorted label order for
    # readable logs only -- no unit reads another's output, so the order cannot change
    # any result, and a run that judges a subset produces exactly the artifacts it would
    # have produced inside a full batch.
    attrs_by_country: dict[str, list[str]] = {}
    judged = 0
    for combo in combos:
        if combo.country not in attrs_by_country:
            attrs_by_country[combo.country] = scheme_attributes(combo.country)
        role = (
            "real competitor" if combo.is_real_reference
            else f"strategy={combo.strategy}, model={combo.model}"
        )
        print(f"=== {combo.label} ({role}) ===")

        individuals = _load_individuals(
            mapping_dir / f"{combo.label}.json", what=combo.label,
        )
        ca = _run_one_combo(
            combo=combo, individuals=individuals,
            analyzed_attrs=attrs_by_country[combo.country],
            out_dir=out_root / combo.country / combo.label,
            cfg=cfg, dpi=args.dpi, force=args.force,
            rewrite_artifacts=args.rewrite_artifacts,
            hard_rules=hard_rules, pricing=pricing,
        )
        rate = ca.stats.impossibility.get("rate")
        rate_str = "n/a" if rate is None else f"{rate:.4f}"
        print(f"    n={ca.stats.n_personas} (failed {ca.stats.n_failed})  "
              f"impossibility={rate_str}  -> {out_root / combo.country / combo.label}")
        judged += 1

    print()
    print(f"Combinations judged: {judged}. Cross-combination ranking is a separate task -- "
          f"run scripts/analyze/rank_persona_realism.py.")


if __name__ == "__main__":
    main()

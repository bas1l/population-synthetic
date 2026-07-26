"""artifacts.py -- orchestrate one combo's (and the run's) realism artifacts.

The **only** path-aware module of the persona-realism subpackage and its
aggregation+reporting orchestrator. It consumes an *already-judged* verdict cache
(``<out_dir>/persona_XXXXX.json`` at the combo root, written by Phase 2's
``runner``) -- it does NOT call the judge. Its per-combo entry point runs the pure
pipeline

    load_combo_verdicts -> reduce_combo -> compute_realism_stats -> cost -> sinks

and materialises the publication artifacts idempotently (skip a unit whose output
already exists unless ``force``; dual PNG+SVG via ``utils/figures.save_figure``;
skip a chart only when its field is genuinely empty). A cross-combo entry renders
the headline map from a set of already-computed :class:`RealismStats` plus the
combined CSV and the run-level report.

Boundary (02-architecture guide sect. 2/9): this module owns output paths, the
per-unit skip decision, and the cost aggregation; it must NOT know how the
population/scheme were loaded, how the combos were selected, or anything about the
CLI / GUI dispatch -- those live in the Phase-5 script. Statistics come entirely
from the pure ``reduce``/``stats`` layers; the cost chain reuses the
``generation_metadata`` primitives (fail-fast on a missing pricing row).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from population_synthetic.analysis.generation_metadata.cost import persona_cost
from population_synthetic.analysis.generation_metadata.interaction_parser import parse_interactions
from population_synthetic.analysis.generation_metadata.persona_metrics import (
    reduce_persona as reduce_persona_metrics,
)
from population_synthetic.analysis.generation_metadata.pricing import PricingTable, load_pricing_table
from population_synthetic.analysis.persona_realism.charts import (
    HeadlinePoint,
    plot_clash_taxonomy,
    plot_headline_map,
    plot_typicality_distribution,
)
from population_synthetic.analysis.persona_realism.csv_writer import RealismRow, write_realism_csv
from population_synthetic.analysis.persona_realism.reduce import (
    ClashKey,
    ComboRealism,
    LoadedPersona,
    load_combo_verdicts,
    reduce_combo,
    reduce_persona,
)
from population_synthetic.analysis.persona_realism.report import write_combo_report, write_run_report
from population_synthetic.analysis.persona_realism.runner import JudgeConfig
from population_synthetic.analysis.persona_realism.stats import RealismStats, compute_realism_stats
from population_synthetic.analysis.persona_realism.validation import (
    HardRule,
    load_hard_rules,
    validate_against_hard_rules,
)
from population_synthetic.analysis.utils.figures import save_figure

__all__ = [
    "ComboArtifacts",
    "load_combo_realism",
    "load_realism_hard_rules",
    "write_combo_artifacts",
    "write_headline_map",
]

_LOGGER = logging.getLogger(__name__)

# Default dispersion measure the headline-map y-axis (distance-to-SCB) uses.
_DEFAULT_HEADLINE_MEASURE = "variance"


@dataclass(frozen=True)
class ComboArtifacts:
    """One combination's computed stats + written artifacts.

    ``stats``/``combo`` are the pure reductions (carried so the cross-combo
    :func:`write_headline_map` needs no reload); ``row`` is the flat CSV record;
    ``cost_coverage`` is the resume-honesty marker; ``paths`` lists every artifact
    written OR left in place (existing-and-skipped paths are included so the caller
    can report the full set either way).
    """

    stats: RealismStats
    combo: ComboRealism
    row: RealismRow
    cost_coverage: dict[str, Any]
    paths: list[Path] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# provenance / pricing meta                                                    #
# --------------------------------------------------------------------------- #


def _prompt_template_hash(path: Path) -> str:
    """SHA-256 of the prompt template file (provenance stamp)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _provenance_meta(cfg: JudgeConfig) -> dict[str, Any]:
    """Build the run/combo provenance meta from the judge config (verbatim snapshot)."""
    return {
        "judge_model": cfg.judge_model,
        "n_rounds": cfg.n_rounds,
        "temperature": cfg.temperature,
        "bootstrap": dict(cfg.bootstrap),
        "typicality_level": cfg.reliability.get("typicality_level", "ordinal"),
        "sample_size": cfg.sample_size,
        "severity_weights": dict(cfg.severity_weights),
        "impossibility_severities": list(cfg.impossibility_severities),
        "prompt_template": str(cfg.prompt_template),
        "prompt_template_sha256": _prompt_template_hash(cfg.prompt_template),
        "config_dir": str(cfg.config_dir),
    }


def _pricing_meta(pricing: PricingTable) -> dict[str, Any]:
    """The pricing-provenance stamps carried into every report."""
    meta: dict[str, Any] = {
        "observed_date": pricing.observed_date,
        "source": pricing.source,
        "currency": pricing.currency,
    }
    if pricing.cache_multipliers is not None:
        meta["cache_multipliers"] = dict(pricing.cache_multipliers)
        meta["cache_note"] = (
            "Cached input is priced at the config cache_multipliers relative to the "
            "base input rate (read x, write x); uncached input/output at the base rates."
        )
    return meta


# --------------------------------------------------------------------------- #
# cost aggregation (reuses generation_metadata primitives; fail-fast pricing)  #
# --------------------------------------------------------------------------- #


def _sum_optional(values: list[int | None]) -> int | None:
    """Sum, keeping ``None`` (no telemetry) distinct from a genuine ``0``."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _combo_cost(
    out_dir: Path,
    judge_model: str,
    pricing: PricingTable,
    n_cached_personas: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Aggregate a combo's judge-call cost from the per-persona ``persona_*.jsonl`` logs.

    Each ``<out_dir>/persona_XXXXX.jsonl`` is exactly one persona's telemetry
    (append-accumulated across resumed/top-up passes), so the combo cost is the sum
    over those files. Each is reduced to a
    :class:`~population_synthetic.analysis.generation_metadata.persona_metrics.PersonaMetrics`
    and priced via :func:`persona_cost` (which **raises** if the persona has token
    telemetry but *judge_model* is absent from the pricing table -- fail-fast).
    Returns ``(cost, cost_coverage)``.

    ``cost_coverage`` records the resume-honesty marker. Because the telemetry is now
    per-persona and 1:1 with the verdict cache, a resumed run's logs cover every
    cached persona: ``judged_this_run`` (number of ``persona_*.jsonl`` files) equals
    ``total_personas`` and ``status`` is ``complete``. ``partial`` fires only on a
    genuine per-file gap (fewer telemetry files than cached personas); ``none`` when
    no telemetry files are present (**no legacy single-file fallback**).
    """
    coverage: dict[str, Any] = {
        "judged_this_run": 0,
        "total_personas": n_cached_personas,
        "status": "none",
    }
    jsonl_files = sorted(out_dir.glob("persona_*.jsonl"))
    if not jsonl_files:
        cost = {
            "input_tokens": None, "output_tokens": None, "total_tokens": None,
            "usd": None, "n_calls": 0, "n_personas_costed": 0,
            "note": "no per-persona telemetry logs present under this combo",
        }
        return cost, coverage

    input_tokens: list[int | None] = []
    output_tokens: list[int | None] = []
    total_tokens: list[int | None] = []
    cache_read_tokens: list[int | None] = []
    cache_creation_tokens: list[int | None] = []
    costs: list[float] = []
    n_calls = 0
    n_costed = 0
    for jsonl_file in jsonl_files:
        pm = reduce_persona_metrics(parse_interactions(jsonl_file))
        n_calls += pm.n_calls
        input_tokens.append(pm.input_tokens)
        output_tokens.append(pm.output_tokens)
        total_tokens.append(pm.total_tokens)
        cache_read_tokens.append(pm.cache_read_tokens)
        cache_creation_tokens.append(pm.cache_creation_tokens)
        # Cache tokens are priced via the config `cache_multipliers` block; passing
        # them makes the input-cost line reflect the (prompt-cached) judge prompt.
        usd = persona_cost(
            judge_model, pm.input_tokens, pm.output_tokens, pricing,
            cache_read_tokens=pm.cache_read_tokens,
            cache_creation_tokens=pm.cache_creation_tokens,
        )  # raises if unpriceable
        if usd is not None:
            costs.append(usd)
            n_costed += 1

    judged_this_run = len(jsonl_files)
    if judged_this_run == 0:
        status = "none"
    elif judged_this_run >= n_cached_personas:
        status = "complete"
    else:
        status = "partial"
    coverage.update(judged_this_run=judged_this_run, status=status)

    cost = {
        "input_tokens": _sum_optional(input_tokens),
        "output_tokens": _sum_optional(output_tokens),
        "total_tokens": _sum_optional(total_tokens),
        "cache_read_tokens": _sum_optional(cache_read_tokens),
        "cache_creation_tokens": _sum_optional(cache_creation_tokens),
        "usd": sum(costs) if costs else None,
        "n_calls": n_calls,
        "n_personas_costed": n_costed,
    }
    return cost, coverage


# --------------------------------------------------------------------------- #
# serialisation helpers                                                        #
# --------------------------------------------------------------------------- #


def _serialise_clash_taxonomy(clash_taxonomy: dict[ClashKey, int]) -> list[dict[str, Any]]:
    """Convert the ``{ClashKey: count}`` taxonomy to a serialisable, ranked list."""
    severity_rank = {"S3": 0, "S2": 1, "S1": 2}
    items = sorted(
        clash_taxonomy.items(),
        key=lambda kv: (-kv[1], severity_rank.get(kv[0].severity, 9), kv[0].pair),
    )
    return [
        {"pair": list(key.pair), "severity": key.severity, "n_personas": count}
        for key, count in items
    ]


def _build_row(stats: RealismStats, cost: dict[str, Any], validation: dict[str, Any] | None) -> RealismRow:
    """Flatten a :class:`RealismStats` (+ cost + validation) into a CSV row."""
    imp = stats.impossibility
    disp = stats.dispersion
    dist = disp.get("distance_to_scb") or {}
    veq = disp.get("variance_equality") or {}
    rel = stats.reliability
    return RealismRow(
        combo_label=stats.combo_label,
        n_personas=stats.n_personas,
        n_failed=stats.n_failed,
        impossibility_rate=imp.get("rate"),
        imp_ci_lo=imp.get("lo"),
        imp_ci_hi=imp.get("hi"),
        impossible_count=imp.get("impossible_count", 0),
        disp_variance=disp.get("variance"),
        disp_entropy=disp.get("entropy"),
        disp_tail_coverage=disp.get("tail_coverage"),
        dist_variance=dist.get("variance"),
        dist_entropy=dist.get("entropy"),
        dist_tail_coverage=dist.get("tail_coverage"),
        variance_equality_stat=veq.get("statistic"),
        variance_equality_p=veq.get("p"),
        can_exist_alpha=rel["can_exist_alpha"].get("alpha"),
        typicality_alpha=rel["typicality_alpha"].get("alpha"),
        typicality_icc=rel["typicality_icc"].get("icc"),
        hard_rules_agreement=validation.get("agreement") if validation else None,
        hard_rules_recall=validation.get("recall_on_rule_impossibilities") if validation else None,
        total_tokens=cost.get("total_tokens"),
        cost_usd=cost.get("usd"),
    )


def _headline_point(stats: RealismStats, *, is_reference: bool, measure: str) -> HeadlinePoint | None:
    """Build a map point from a combo's stats (``None`` when its coords are undefined)."""
    x = stats.impossibility.get("rate")
    if x is None:
        return None
    if is_reference:
        y: float | None = 0.0
    else:
        y = (stats.dispersion.get("distance_to_scb") or {}).get(measure)
    if y is None:
        return None
    return HeadlinePoint(
        label=stats.combo_label,
        impossibility_rate=float(x),
        dispersion_distance=float(y),
        is_reference=is_reference,
        n_personas=stats.n_personas,
    )


# --------------------------------------------------------------------------- #
# loaders + per-combo orchestration                                            #
# --------------------------------------------------------------------------- #


def load_realism_hard_rules(cfg: JudgeConfig) -> tuple[HardRule, ...]:
    """Load the config-driven hard-rules validation subset (fail-fast)."""
    return load_hard_rules(cfg.config_dir / "hard_rules.yaml")


def load_combo_realism(
    combo_dir: Path,
    combo_label: str,
    *,
    expected_ids: list[str] | None = None,
) -> tuple[ComboRealism, list[LoadedPersona]]:
    """Load the combo-root cache -> reduce to a :class:`ComboRealism` + present personas.

    Reads ``<combo_dir>/persona_XXXXX.json`` (combo root, no ``raw/`` subdir).
    ``expected_ids`` (the selected persona roster) maps every selected id without a
    cache file to a failed/absent persona (counted in ``n_failed``); without it only
    the on-disk personas are seen (``n_failed == 0``). Returns the reduced combo and
    the list of successfully-loaded personas (for the hard-rules validation subset).
    """
    loaded = load_combo_verdicts(combo_dir, expected_ids=expected_ids)
    personas = [
        reduce_persona(lp.rounds, persona_id=pid) if lp is not None else None
        for pid, lp in loaded.items()
    ]
    combo = reduce_combo(personas, combo_label)
    present = [lp for lp in loaded.values() if lp is not None]
    return combo, present


def write_combo_artifacts(
    out_dir: Path,
    combo_label: str,
    *,
    scb_ref: ComboRealism | None,
    cfg: JudgeConfig,
    dpi: int,
    force: bool,
    expected_ids: list[str] | None = None,
    hard_rules: tuple[HardRule, ...] | None = None,
    pricing: PricingTable | None = None,
    provenance: dict[str, Any] | None = None,
    logger: logging.Logger | None = None,
) -> ComboArtifacts:
    """Compute + render + write one combination's realism artifacts under *out_dir*.

    Runs the pure pipeline on the already-judged ``<out_dir>/persona_XXXXX.json``
    combo-root cache, computes the combo's cost by summing the per-persona
    ``<out_dir>/persona_XXXXX.jsonl`` telemetry logs (fail-fast if the judge model's
    pricing row is absent), and writes ``{combo}.csv``, ``{combo}.json``,
    ``typicality.png/.svg`` and ``clash_taxonomy.png/.svg``. The idempotent skip keys
    on those specific output filenames, so the sibling ``persona_*.json/.jsonl``
    files never confuse it.

    The stats are **always** computed (cheap, pure) so the returned
    :class:`ComboArtifacts` can seed the cross-combo headline map even when every
    file is skipped; only the file *writes* honour the idempotent skip (a unit whose
    output already exists is left untouched unless *force*). A chart is skipped only
    when its field is genuinely empty (no can_exist typicality means / no clashes).

    Args:
        out_dir: the combo's resolved output dir (holds the per-persona cache +
            telemetry directly at its root).
        combo_label: the combination label (a ``{slug}`` or ``real_{country}``).
        scb_ref: the SCB real-population :class:`ComboRealism` dispersion reference
            (``None`` when *combo* itself is the reference).
        cfg: the loaded :class:`JudgeConfig`.
        dpi, force: forwarded to ``save_figure`` / the skip gate.
        expected_ids: the selected persona roster (marks absent personas failed).
        hard_rules: pre-loaded hard rules; loaded from config when ``None``.
        pricing: pre-loaded pricing table; the default table is loaded when ``None``.
        provenance: pre-built provenance meta; built from *cfg* when ``None``.
    """
    logger = logger or _LOGGER
    out_dir = Path(out_dir)

    if pricing is None:
        pricing = load_pricing_table()
    if hard_rules is None:
        hard_rules = load_realism_hard_rules(cfg)
    if provenance is None:
        provenance = _provenance_meta(cfg)

    typ_level = cfg.reliability.get("typicality_level", "ordinal")
    tail_threshold = float(cfg.reliability.get("tail_threshold", 3.0))
    variance_center = str(cfg.reliability.get("variance_center", "median"))

    combo, present = load_combo_realism(out_dir, combo_label, expected_ids=expected_ids)
    stats = compute_realism_stats(
        combo, scb_ref,
        bootstrap=cfg.bootstrap,
        typicality_level=typ_level,
        tail_threshold=tail_threshold,
        variance_center=variance_center,
    )

    cost, cost_coverage = _combo_cost(out_dir, cfg.judge_model, pricing, combo.n_personas)

    validation: dict[str, Any] | None = None
    if hard_rules and present:
        hrv = validate_against_hard_rules(present, hard_rules, sample_size=None, seed=cfg.bootstrap.get("seed"))
        validation = asdict(hrv)

    row = _build_row(stats, cost, validation)
    paths: list[Path] = []

    # --- CSV (single-combo row) ------------------------------------------------ #
    csv_path = out_dir / f"{combo_label}.csv"
    if force or not csv_path.exists():
        paths.append(write_realism_csv([row], csv_path))
    else:
        logger.info("combo %s: %s exists; skipping (force=False)", combo_label, csv_path.name)
        paths.append(csv_path)

    # --- JSON report ----------------------------------------------------------- #
    json_path = out_dir / f"{combo_label}.json"
    if force or not json_path.exists():
        paths.append(
            write_combo_report(
                json_path,
                stats=stats,
                clash_taxonomy=_serialise_clash_taxonomy(combo.clash_taxonomy),
                cost=cost,
                cost_coverage=cost_coverage,
                validation=validation,
                provenance=provenance,
                pricing=_pricing_meta(pricing),
            )
        )
    else:
        logger.info("combo %s: %s exists; skipping (force=False)", combo_label, json_path.name)
        paths.append(json_path)

    # --- typicality distribution figure (skip only when genuinely empty) ------- #
    paths.extend(
        _emit_figure(
            out_dir / "typicality.png",
            present=bool(combo.typicality_means),
            build=lambda: plot_typicality_distribution(
                combo.typicality_means, combo_label, tail_threshold=tail_threshold
            ),
            empty_msg=f"combo {combo_label}: no can_exist typicality means; skipping typicality chart",
            dpi=dpi, force=force, logger=logger,
        )
    )

    # --- clash-taxonomy figure (skip only when genuinely empty) ---------------- #
    paths.extend(
        _emit_figure(
            out_dir / "clash_taxonomy.png",
            present=bool(combo.clash_taxonomy),
            build=lambda: plot_clash_taxonomy(combo.clash_taxonomy, combo_label),
            empty_msg=f"combo {combo_label}: no attribute clashes; skipping clash-taxonomy chart",
            dpi=dpi, force=force, logger=logger,
        )
    )

    return ComboArtifacts(stats=stats, combo=combo, row=row, cost_coverage=cost_coverage, paths=paths)


def _emit_figure(png_path, *, present, build, empty_msg, dpi, force, logger) -> list[Path]:
    """Render/save (or skip) one figure, returning the PNG+SVG paths it owns.

    Returns ``[]`` when the field is genuinely empty (logged). Honours the
    idempotent skip: an existing PNG+SVG pair is left in place unless *force*.
    """
    png_path = Path(png_path)
    svg_path = png_path.with_suffix(".svg")
    if not present:
        logger.info(empty_msg)
        return []
    if not force and png_path.exists() and svg_path.exists():
        logger.info("%s exists; skipping (force=False)", png_path.name)
        return [png_path, svg_path]
    saved = save_figure(build(), png_path, dpi=dpi)
    return [saved, saved.with_suffix(".svg")]


# --------------------------------------------------------------------------- #
# cross-combo orchestration (headline map + combined CSV + run report)         #
# --------------------------------------------------------------------------- #


def write_headline_map(
    combos: list[ComboArtifacts],
    out_root: Path,
    *,
    cfg: JudgeConfig,
    dpi: int,
    force: bool,
    scb_label: str | None = None,
    measure: str = _DEFAULT_HEADLINE_MEASURE,
    pricing: PricingTable | None = None,
    provenance: dict[str, Any] | None = None,
    logger: logging.Logger | None = None,
) -> list[Path]:
    """Render the cross-combo headline map + combined CSV + run report under *out_root*.

    ``combos`` are the per-combo results from :func:`write_combo_artifacts` (incl.
    the SCB reference, whose label is *scb_label*). Builds one :class:`HeadlinePoint`
    per combo (x = impossibility rate, y = typicality-dispersion distance to SCB;
    the reference sits at ``y == 0``), skipping any whose coordinates are undefined.
    Writes ``headline_map.png/.svg``, ``realism_summary.csv`` (all rows) and
    ``run_report.json`` (provenance + per-combo summaries + the plotted points),
    each honouring the idempotent skip unless *force*.
    """
    logger = logger or _LOGGER
    out_root = Path(out_root)
    if pricing is None:
        pricing = load_pricing_table()
    if provenance is None:
        provenance = _provenance_meta(cfg)

    points: list[HeadlinePoint] = []
    for ca in combos:
        pt = _headline_point(ca.stats, is_reference=ca.stats.combo_label == scb_label, measure=measure)
        if pt is None:
            logger.info("combo %s: headline coords undefined (skipped from map)", ca.stats.combo_label)
        else:
            points.append(pt)

    paths: list[Path] = []

    # --- headline map figure --------------------------------------------------- #
    png_path = out_root / "headline_map.png"
    svg_path = png_path.with_suffix(".svg")
    if not points:
        logger.warning("write_headline_map: no plottable competitor points; skipping the map figure")
    elif not force and png_path.exists() and svg_path.exists():
        logger.info("headline_map exists under %s; skipping (force=False)", out_root)
        paths.extend([png_path, svg_path])
    else:
        saved = save_figure(plot_headline_map(points, measure_label=measure), png_path, dpi=dpi)
        paths.extend([saved, saved.with_suffix(".svg")])

    # --- combined CSV (one row per combo) -------------------------------------- #
    csv_path = out_root / "realism_summary.csv"
    if force or not csv_path.exists():
        paths.append(write_realism_csv([ca.row for ca in combos], csv_path))
    else:
        logger.info("realism_summary.csv exists under %s; skipping (force=False)", out_root)
        paths.append(csv_path)

    # --- run-level report ------------------------------------------------------ #
    json_path = out_root / "run_report.json"
    if force or not json_path.exists():
        combos_summary = [
            {
                "combo_label": ca.stats.combo_label,
                "n_personas": ca.stats.n_personas,
                "n_failed": ca.stats.n_failed,
                "impossibility_rate": ca.stats.impossibility.get("rate"),
                "impossibility_ci": [ca.stats.impossibility.get("lo"), ca.stats.impossibility.get("hi")],
                "dispersion_distance_to_scb": ca.stats.dispersion.get("distance_to_scb"),
                "cost_coverage": ca.cost_coverage,
            }
            for ca in combos
        ]
        headline = {
            "measure": measure,
            "reference": scb_label,
            "points": [
                {
                    "label": pt.label,
                    "impossibility_rate": pt.impossibility_rate,
                    "dispersion_distance": pt.dispersion_distance,
                    "is_reference": pt.is_reference,
                }
                for pt in points
            ],
        }
        paths.append(
            write_run_report(
                json_path,
                combos=combos_summary,
                headline=headline,
                provenance=provenance,
                pricing=_pricing_meta(pricing),
            )
        )
    else:
        logger.info("run_report.json exists under %s; skipping (force=False)", out_root)
        paths.append(json_path)

    return paths

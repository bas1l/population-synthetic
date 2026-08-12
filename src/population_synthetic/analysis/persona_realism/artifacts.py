"""artifacts.py -- orchestrate ONE combination's realism artifacts.

The **only** path-aware module of the persona-realism subpackage. It consumes an
*already-judged* verdict cache (``<out_dir>/persona_XXXXX.json`` at the combo root,
written by ``runner``) -- it does NOT call the judge. Its single entry point runs the
pure pipeline

    load_combo_verdicts -> reduce_combo -> compute_realism_stats -> cost -> sinks

and materialises the publication artifacts idempotently (skip a unit whose output
already exists unless ``force``; dual PNG+SVG via ``utils/figures.save_figure``;
skip a chart only when its field is genuinely empty).

**Strictly per-combination.** Every artifact written here is a deterministic function
of *this* combination's verdict cache plus config -- it does not read, accumulate, or
depend on the existence, content, or processing order of any other combination. That
is what makes ``{combo}.json`` and ``{combo}.csv`` byte-reproducible in isolation and
identical no matter which slug was judged first. The cross-combination sinks (the
headline map, the combined summary CSV, the run report) moved to the ``realism_ranking``
process, which consumes the two tidy contracts this module writes:
``{combo}_personas.csv`` (one row per persona) and ``{combo}_clashes.csv`` (one row per
clash). The third file, ``{combo}_clash_explanations.csv``, is a side file carrying the
judge's free text at the same key; nothing downstream reads it.

The two row builders :func:`persona_rows` and :func:`combo_clash_rows` are public
because they *define* the row grain of those two contracts. A consumer that has to
rebuild the rows from the same verdict cache -- the ranking's round cap re-reduces a
combination over its first N rounds -- calls them instead of growing a second copy of
the row shape that would silently drift from the published files.

Boundary (02-architecture guide sect. 2/9): this module owns output paths, the
per-unit skip decision, and the cost aggregation; it must NOT know how the
population/scheme were loaded, how the combos were selected, or anything about the
CLI / GUI dispatch -- those live in the driver script. Statistics come entirely from
the pure ``reduce``/``stats`` layers; the cost chain reuses the
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
    plot_clash_taxonomy,
    plot_typicality_distribution,
)
from population_synthetic.analysis.persona_realism.clash_explanations_csv import (
    ClashExplanationRow,
    write_clash_explanations_csv,
)
from population_synthetic.analysis.persona_realism.config import JudgeConfig
from population_synthetic.analysis.persona_realism.csv_writer import RealismRow, write_realism_csv
from population_synthetic.analysis.persona_realism.reduce import (
    ClashKey,
    ComboRealism,
    LoadedPersona,
    PersonaVerdict,
    clash_explanation_rows,
    clash_rows,
    load_combo_verdicts,
    reduce_combo,
    reduce_persona,
)
from population_synthetic.analysis.persona_realism.report import write_combo_report
from population_synthetic.analysis.persona_realism.stats import RealismStats, compute_realism_stats
from population_synthetic.analysis.persona_realism.validation import (
    HardRule,
    load_hard_rules,
    validate_against_hard_rules,
)
from population_synthetic.analysis.utils.figures import save_figure
from population_synthetic.analysis.utils.realism_clash_csv import (
    SCHEMA_VERSION as CLASH_CSV_SCHEMA_VERSION,
)
from population_synthetic.analysis.utils.realism_clash_csv import (
    RealismClashRow,
    write_realism_clashes_csv,
)
from population_synthetic.analysis.utils.realism_csv import (
    SCHEMA_VERSION as PERSONA_CSV_SCHEMA_VERSION,
)
from population_synthetic.analysis.utils.realism_csv import (
    SEVERITY_LEVELS,
    SEVERITY_RANK,
    RealismPersonaRow,
    write_realism_personas_csv,
)

__all__ = [
    "ComboArtifacts",
    "combo_clash_rows",
    "load_combo_realism",
    "load_realism_hard_rules",
    "persona_rows",
    "write_combo_artifacts",
]

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComboArtifacts:
    """One combination's computed stats + written artifacts.

    ``stats``/``combo`` are the pure reductions (returned so the caller can report
    without re-reading the files it just wrote); ``row`` is the flat CSV record;
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


#: Stamped beside the severity config so a reader can never mistake a declared-but-
#: unwired knob for an active one (the honest alternative to deleting the keys).
_SEVERITY_CONFIG_STATUS = (
    "declared but not wired: a persona's impossibility is decided solely by the "
    "majority of the boolean can_exist across rounds (reduce.possible_majority). "
    "severity_weights and impossibility_severities gate nothing in this pipeline."
)


def _provenance_meta(cfg: JudgeConfig) -> dict[str, Any]:
    """Build the combo provenance meta from the judge config (verbatim snapshot).

    Every tunable that can move a published number is stamped here, because this is
    the block the downstream ``realism_ranking`` homogeneity guard compares across
    combinations: ranking units judged by different judge models, prompt versions, or
    round counts measures the judges, not the units.
    """
    return {
        "judge_model": cfg.judge_model,
        "n_rounds": cfg.n_rounds,
        "temperature": cfg.temperature,
        "bootstrap": dict(cfg.bootstrap),
        "typicality_level": cfg.reliability_value("typicality_level"),
        "tail_threshold": float(cfg.reliability_value("tail_threshold")),
        "sample_size": cfg.sample_size,
        "severity_weights": dict(cfg.severity_weights),
        "impossibility_severities": list(cfg.impossibility_severities),
        "severity_config_status": _SEVERITY_CONFIG_STATUS,
        "prompt_template": str(cfg.prompt_template),
        "prompt_template_sha256": _prompt_template_hash(cfg.prompt_template),
        "persona_csv_schema_version": PERSONA_CSV_SCHEMA_VERSION,
        # A separate key, not a bump of the one above: the two tidy CSVs are
        # independently versioned contracts, and folding them into one number would
        # make a reader unable to tell which file its mismatch is about.
        "clash_csv_schema_version": CLASH_CSV_SCHEMA_VERSION,
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
    items = sorted(
        clash_taxonomy.items(),
        key=lambda kv: (-kv[1], SEVERITY_RANK.get(kv[0].severity, len(SEVERITY_LEVELS)), kv[0].pair),
    )
    return [
        {"pair": list(key.pair), "severity": key.severity, "n_personas": count}
        for key, count in items
    ]


def _build_row(stats: RealismStats, cost: dict[str, Any], validation: dict[str, Any] | None) -> RealismRow:
    """Flatten a :class:`RealismStats` (+ cost + validation) into a CSV row."""
    imp = stats.impossibility
    disp = stats.dispersion
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
        can_exist_alpha=rel["can_exist_alpha"].get("alpha"),
        typicality_alpha=rel["typicality_alpha"].get("alpha"),
        typicality_icc=rel["typicality_icc"].get("icc"),
        hard_rules_agreement=validation.get("agreement") if validation else None,
        hard_rules_recall=validation.get("recall_on_rule_impossibilities") if validation else None,
        total_tokens=cost.get("total_tokens"),
        cost_usd=cost.get("usd"),
    )


def _max_severity(persona: PersonaVerdict) -> str:
    """Worst clash severity the judge raised for *persona* (``""`` when none)."""
    severities = {key.severity for key in persona.clash_frequency}
    for level in SEVERITY_LEVELS:
        if level in severities:
            return level
    return ""


def _severity_counts(persona: PersonaVerdict) -> dict[str, int]:
    """Distinct clashes per severity level for *persona*.

    Counts ``ClashKey``s, not rounds -- the same unit ``clash_count`` uses, so the three
    levels sum to it. This is what makes the severities independently countable: a
    persona carrying both an S3 and an S2 is counted under both, where ``max_severity``
    would file it under S3 alone and understate the S2 prevalence.
    """
    counts = {level: 0 for level in SEVERITY_LEVELS}
    for key in persona.clash_frequency:
        if key.severity in counts:
            counts[key.severity] += 1
    return counts


def persona_rows(
    personas: dict[str, PersonaVerdict],
    loaded: dict[str, LoadedPersona],
    *,
    combo_label: str,
    country: str,
    model: str,
    strategy: str,
    is_real_reference: bool,
) -> list[RealismPersonaRow]:
    """Build the tidy per-persona rows -- the inter-task contract for ``realism_ranking``.

    One row per persona with **>= 1 successful round** (a persona whose every round
    failed is uncached by construction and is carried instead as the combination's
    ``n_failed``), sorted by persona id so two runs over the same cache write byte-
    identical files. ``n_rounds_attempted`` adds back the round-level failures the
    runner recorded, so the successful count is never read as if it were the attempt
    count.
    """
    rows: list[RealismPersonaRow] = []
    for persona_id in sorted(personas):
        pv = personas[persona_id]
        failed_rounds = loaded[persona_id].failed_rounds
        severity_counts = _severity_counts(pv)
        rows.append(
            RealismPersonaRow(
                persona_id=persona_id,
                slug=combo_label,
                country=country,
                model=model,
                strategy=strategy,
                is_real_reference=is_real_reference,
                n_rounds_attempted=pv.n_rounds + failed_rounds,
                n_rounds_successful=pv.n_rounds,
                can_exist_true_votes=pv.n_possible,
                can_exist_majority=pv.possible_majority,
                typicality_mean=pv.typicality_mean,
                typicality_sd=pv.typicality_sd,
                typicality_rounds=pv.typicality_rounds,
                max_severity=_max_severity(pv),
                clash_count=len(pv.clash_frequency),
                clash_count_s1=severity_counts["S1"],
                clash_count_s2=severity_counts["S2"],
                clash_count_s3=severity_counts["S3"],
            )
        )
    return rows


def combo_clash_rows(
    present: list[LoadedPersona],
    *,
    combo_label: str,
    country: str,
    model: str,
    strategy: str,
    is_real_reference: bool,
) -> list[RealismClashRow]:
    """Build the combination's per-clash rows -- the finer-grained contract file.

    Concatenates each loaded persona's expansion (see
    :func:`~population_synthetic.analysis.persona_realism.reduce.clash_rows`) in
    persona-id order. A persona with no clash contributes nothing, and a combination
    with no clash at all yields ``[]`` -- written as a header-only file, which is a
    different fact from an absent one.
    """
    rows: list[RealismClashRow] = []
    for lp in sorted(present, key=lambda p: p.persona_id):
        rows.extend(
            clash_rows(
                lp, slug=combo_label, country=country, model=model,
                strategy=strategy, is_real_reference=is_real_reference,
            )
        )
    return rows


def _combo_explanation_rows(present: list[LoadedPersona]) -> list[ClashExplanationRow]:
    """Build the combination's clash-explanation side-file rows (same key, same order)."""
    rows: list[ClashExplanationRow] = []
    for lp in sorted(present, key=lambda p: p.persona_id):
        rows.extend(clash_explanation_rows(lp))
    return rows


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
    cfg: JudgeConfig,
    dpi: int,
    force: bool,
    country: str = "",
    model: str = "",
    strategy: str = "",
    is_real_reference: bool = False,
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
    ``{combo}_personas.csv``, ``{combo}_clashes.csv``,
    ``{combo}_clash_explanations.csv``, ``typicality.png/.svg`` and
    ``clash_taxonomy.png/.svg``. The idempotent skip keys on those specific output
    filenames, so the sibling ``persona_*.json/.jsonl`` files never confuse it.

    Nothing written here depends on any other combination: judging this slug on an
    empty output base produces the complete artifact set, and judging it before or
    after any other slug produces identical bytes (modulo nothing -- the reports carry
    no timestamp).

    The stats are **always** computed (cheap, pure) so the returned
    :class:`ComboArtifacts` is complete even when every file write is skipped; only
    the file *writes* honour the idempotent skip (a unit whose output already exists
    is left untouched unless *force*). A chart is skipped only when its field is
    genuinely empty (no can_exist typicality means / no clashes).

    Args:
        out_dir: the combo's resolved output dir (holds the per-persona cache +
            telemetry directly at its root).
        combo_label: the combination label (a ``{slug}`` or ``real_{country}``).
        cfg: the loaded :class:`JudgeConfig`.
        dpi, force: forwarded to ``save_figure`` / the skip gate.
        country, model, strategy: the decomposed axis ids, recorded verbatim in the
            per-persona tidy CSV so the aggregator's factor tests need not re-parse
            the slug. Empty for the real competitor, which is not a model x method
            cell -- that is what *is_real_reference* marks.
        is_real_reference: whether this combination is the ``real_{country}``
            competitor. It is a *label only*: the real competitor's artifacts are
            computed exactly like any other combination's.
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

    # Fail-fast config reads: no in-code default, so an emitted number can never
    # silently disagree with the judge.yaml that is supposed to describe it.
    typ_level = str(cfg.reliability_value("typicality_level"))
    tail_threshold = float(cfg.reliability_value("tail_threshold"))

    combo, present = load_combo_realism(out_dir, combo_label, expected_ids=expected_ids)
    stats = compute_realism_stats(
        combo,
        bootstrap=cfg.bootstrap,
        typicality_level=typ_level,
        tail_threshold=tail_threshold,
    )

    cost, cost_coverage = _combo_cost(out_dir, cfg.judge_model, pricing, combo.n_personas)

    validation: dict[str, Any] | None = None
    if hard_rules and present:
        hrv = validate_against_hard_rules(present, hard_rules, sample_size=None, seed=cfg.bootstrap.get("seed"))
        validation = asdict(hrv)

    row = _build_row(stats, cost, validation)
    paths: list[Path] = []

    # --- CSV (single-combo row) ------------------------------------------------ #
    paths.append(
        _emit_csv(
            out_dir / f"{combo_label}.csv",
            build_rows=lambda: [row],
            write=write_realism_csv,
            force=force, logger=logger,
        )
    )

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

    # --- per-persona tidy CSV (the realism_ranking inter-task contract) -------- #
    # Written whole (never appended), so N runs are equivalent to one and its row
    # count keeps matching the report's n_personas -- the completeness marker the
    # aggregator gates on.
    def _build_persona_rows() -> list[RealismPersonaRow]:
        loaded_by_id = {lp.persona_id: lp for lp in present}
        reduced_by_id = {
            pid: reduce_persona(lp.rounds, persona_id=pid) for pid, lp in loaded_by_id.items()
        }
        return persona_rows(
            reduced_by_id, loaded_by_id,
            combo_label=combo_label, country=country, model=model,
            strategy=strategy, is_real_reference=is_real_reference,
        )

    paths.append(
        _emit_csv(
            out_dir / f"{combo_label}_personas.csv",
            build_rows=_build_persona_rows,
            write=write_realism_personas_csv,
            force=force, logger=logger,
        )
    )

    # --- per-clash tidy CSV + its explanation side file ------------------------ #
    # Both derive from the same verdict cache in the same pass and sit under the same
    # force gate as everything above, so --rewrite-artifacts regenerates the whole
    # SET: a tree can never hold a clashes file from one generation beside a personas
    # file from another, which is exactly what the reconciliation check would then
    # report as corruption.
    paths.append(
        _emit_csv(
            out_dir / f"{combo_label}_clashes.csv",
            build_rows=lambda: combo_clash_rows(
                present, combo_label=combo_label, country=country, model=model,
                strategy=strategy, is_real_reference=is_real_reference,
            ),
            write=write_realism_clashes_csv,
            force=force, logger=logger,
        )
    )
    paths.append(
        _emit_csv(
            out_dir / f"{combo_label}_clash_explanations.csv",
            build_rows=lambda: _combo_explanation_rows(present),
            write=write_clash_explanations_csv,
            force=force, logger=logger,
        )
    )

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


def _emit_csv(csv_path, *, build_rows, write, force, logger) -> Path:
    """Write (or skip) one tidy CSV, returning the path it owns.

    The file-sink counterpart of :func:`_emit_figure`, and the reason
    :func:`write_combo_artifacts` does not carry four near-identical
    exists-else-write blocks. Every writer routed through here shares the
    ``(rows, path) -> Path`` shape, so the schema stays with the module that owns it
    and this helper never learns a column name.

    *build_rows* is called **only** when the file is actually written, so a skipped
    unit costs no derivation -- which is what keeps the per-persona re-reduction and
    the per-clash expansion off the idempotent no-op path.

    Unlike a figure there is no emptiness gate: an empty result is written as a
    header-only file, so "this combination has nothing to report" stays
    distinguishable from "this combination was never processed".
    """
    csv_path = Path(csv_path)
    if not force and csv_path.exists():
        logger.info("%s exists; skipping (force=False)", csv_path.name)
        return csv_path
    return write(build_rows(), csv_path)


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

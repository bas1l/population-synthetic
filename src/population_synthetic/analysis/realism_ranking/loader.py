"""loader.py -- discover, gate and type the consumption set for the realism ranking.

Owns the data contract of the cross-combination process: the per-competitor
:class:`CompetitorRecord` DTO and the discovery walk that welds the capped mapped
index to the per-combination artifacts ``persona_realism`` wrote. By default it reads
only the published on-disk contract -- ``{combo}.json`` plus ``{combo}_personas.csv``
plus ``{combo}_clashes.csv`` -- and never reaches into the judge's reduction
internals, so the judging half can change freely as long as those three files keep
their shape.

The one exception is the **round cap** (``rounds_cap``), which re-derives each
competitor over its first N judge rounds instead of consuming the published
artifacts -- see :func:`load_competitors`. That path reads the verdict caches through
``persona_realism``'s own pure reducers and re-runs its own statistics function, so it
adds no second implementation of any published number; what it does not do is read the
two tidy CSVs, whose row grain (a persona's votes already summed over *all* its cached
rounds) cannot express a cap.

Two gates run before any statistic is computed, because both failure modes produce
numbers that look perfectly reasonable and are wrong:

**Completeness.** A *consumable* combination has a report, has a per-persona CSV, has
a per-clash CSV, and the two CSVs agree with the report (row count == ``n_personas``;
distinct clashes per level == the summed ``clash_count_s{L}``). Anything else is a
partial directory -- a run that was interrupted after caching verdicts but before
writing artifacts, of which several exist on any real output base. Such a directory is
skipped with a machine-readable reason (or raises under ``strict``); it is never
silently ranked, because a combination missing half its personas would simply appear
to have an unusually clean impossibility rate.

**Homogeneity.** Every consumed combination must share the same ``judge_model``,
``prompt_template_sha256`` and ``n_rounds``. Ranking units judged by different judges,
prompts, or round counts measures the judges, not the units. The identity is read from
each report's stamped ``provenance`` block -- what was actually used -- and never from
the config as it currently stands, which may have moved on since. Under a round cap
the third key is not dropped but *changed in kind*: the set is held to one consumed
round count by construction, so ``n_rounds`` becomes a **capacity** requirement (every
persona of every competitor must hold at least N cached rounds) instead of an equality.
The first two keys are never relaxed -- no cap can repair a different judge or prompt.

Failure policy mirrors ``model_ranking/loader.py``:

* a missing mapped index or a **malformed** artifact (unreadable JSON, absent
  ``provenance``/``n_personas``, a CSV whose schema does not parse) always raises,
  naming the upstream script to re-run;
* a **missing** per-combination artifact is a pipeline-progress state: skip with a
  reason, or raise under ``strict``;
* degenerate values are carried through as ``None`` and omitted downstream -- never
  imputed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from population_synthetic.analysis.persona_realism.artifacts import combo_clash_rows, persona_rows
from population_synthetic.analysis.persona_realism.config import JudgeConfig
from population_synthetic.analysis.persona_realism.reduce import (
    LoadedPersona,
    load_combo_verdicts,
    reduce_combo,
    reduce_persona,
)
from population_synthetic.analysis.persona_realism.stats import compute_realism_stats
from population_synthetic.analysis.utils.axes import decompose_slug, diagnose_slug
from population_synthetic.analysis.utils.capped_source import resolve_mapped_dir
from population_synthetic.analysis.utils.realism_clash_csv import (
    RealismClashRow,
    read_realism_clashes_csv,
)
from population_synthetic.analysis.utils.realism_csv import (
    SEVERITY_COUNT_FIELDS,
    SEVERITY_LEVELS,
    RealismPersonaRow,
    read_realism_personas_csv,
)
from population_synthetic.analysis.utils.registry import analysis_output_dir
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

__all__ = [
    "CompetitorRecord",
    "JUDGE_IDENTITY_KEYS",
    "N_ROUNDS_SOURCE_AUTO",
    "N_ROUNDS_SOURCE_CAP",
    "N_ROUNDS_SOURCE_REPORT",
    "load_competitors",
]

_LOGGER = logging.getLogger(__name__)

#: The provenance key holding the consumed round count. Named once because it is the
#: single key the round cap treats differently from the rest of the judge identity.
ROUND_COUNT_KEY = "n_rounds"

#: The provenance fields that must agree across the whole consumption set. Each one
#: changes what the judge measured, so a mismatch makes the units incomparable.
JUDGE_IDENTITY_KEYS: tuple[str, ...] = ("judge_model", "prompt_template_sha256", ROUND_COUNT_KEY)

#: The subset compared when a round cap is active -- derived from the full tuple rather
#: than restated, so the two can never list different judge fields. The cap already
#: forces one consumed round count, which is why that key leaves the equality check;
#: it is replaced by the per-persona capacity check in :func:`_trim_to_cap`.
CAPPED_IDENTITY_KEYS: tuple[str, ...] = tuple(k for k in JUDGE_IDENTITY_KEYS if k != ROUND_COUNT_KEY)

#: How a record's ``provenance["n_rounds"]`` came to be, stamped on every loaded
#: record: read from the combination's published report, pinned by an explicit cap, or
#: derived from the shallowest cached competitor. A capped ranking must never be
#: mistakable for a full one, and the three cases are answered differently by an
#: operator (nothing to do / re-run uncapped when the sweep finishes / top up the
#: named combinations).
N_ROUNDS_SOURCE_REPORT = "report"
N_ROUNDS_SOURCE_CAP = "cap"
N_ROUNDS_SOURCE_AUTO = "auto"


@dataclass(frozen=True)
class CompetitorRecord:
    """One ranked competitor: a synthetic combination or the real population.

    ``personas`` is the tidy per-persona series -- the granularity the rank-based tests
    and the mixed model need; ``impossibility`` / ``dispersion`` / ``reliability`` are
    the single-combination blocks lifted verbatim from the report, so the aggregator
    never recomputes what the per-combination task already published.

    ``clashes`` is the finer per-clash series (one row per persona x round x sorted
    attribute pair x severity) read from the sibling ``{combo}_clashes.csv``. It is
    what makes a severity cell explainable -- *which* attributes clashed, and with
    which category values -- and it is reconciled against ``personas`` at read time, so
    the two are always two views of one verdict cache rather than two states of it. It
    defaults to empty for hand-built records in tests; the loader always sets it, and a
    genuinely clash-free combination is legitimately empty (a header-only file, which
    is a different fact from an absent one and is why the file's absence is a skip).

    ``is_real_reference`` marks the real population. It carries **no** privilege on
    Axis A (it is ranked like anything else) and is the target on Axis B; it is held
    out of the model x method factor tests because it is not a model x method cell and
    would unbalance the design.
    """

    slug: str
    country: str
    model: str
    strategy: str
    is_real_reference: bool
    n_personas: int
    n_failed: int
    personas: tuple[RealismPersonaRow, ...]
    impossibility: dict[str, Any]
    dispersion: dict[str, Any]
    reliability: dict[str, Any]
    provenance: dict[str, Any]
    report_path: Path
    personas_csv_path: Path
    clashes: tuple[RealismClashRow, ...] = ()

    @property
    def impossible_indicators(self) -> tuple[int, ...]:
        """Per-persona 0/1 impossibility series -- the bootstrap's sampling unit.

        Rebuilt from the tidy rows rather than read from the report so the resampled
        base is provably the same set of personas every downstream statistic uses.
        """
        return tuple(0 if row.can_exist_majority else 1 for row in self.personas)

    @property
    def typicality_means(self) -> tuple[float, ...]:
        """Per-persona mean typicality over the majority-possible personas.

        Personas with no typicality at all (every successful round judged impossible)
        are absent, not zero -- a 0 would be the lowest rating on the scale, a
        different and much stronger claim than "undefined".
        """
        return tuple(
            row.typicality_mean
            for row in self.personas
            if row.can_exist_majority and row.typicality_mean is not None
        )


def _judge_identity(provenance: dict[str, Any], keys: tuple[str, ...] = JUDGE_IDENTITY_KEYS) -> tuple[Any, ...]:
    return tuple(provenance.get(key) for key in keys)


def _identity_mismatches(records: list[CompetitorRecord]) -> set[str]:
    """The judge-identity keys that are **not** constant across *records*.

    The non-raising half of the homogeneity gate: the caller needs to know *which*
    key disagrees to decide whether the disagreement is recoverable (a round-count
    spread, which a cap can equalise) or terminal (a different judge or prompt, which
    it cannot). Empty for a homogeneous -- or single-record -- set.
    """
    if len(records) < 2:
        return set()
    baseline = records[0].provenance
    return {
        key
        for key in JUDGE_IDENTITY_KEYS
        for record in records[1:]
        if record.provenance.get(key) != baseline.get(key)
    }


def _read_report(path: Path) -> dict[str, Any]:
    """Read one combination report, raising on anything malformed."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Malformed persona-realism report {path}: {exc}. Re-run "
            "scripts/analyze/analyze_persona_realism.py --rewrite-artifacts for this "
            "combination."
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Persona-realism report {path} did not parse to a mapping.")
    for key in ("n_personas", "impossibility", "dispersion", "provenance"):
        if key not in payload:
            raise ValueError(
                f"Persona-realism report {path} is missing required key {key!r}. It "
                "predates the per-combination split -- re-run "
                "scripts/analyze/analyze_persona_realism.py --rewrite-artifacts."
            )
    return payload


def _distinct_clash_counts(rows: list[RealismPersonaRow]) -> dict[str, int]:
    """Per severity level, the distinct clashes the per-persona rows declare.

    The reconciliation baseline for the per-clash file: each row's ``clash_count_s{L}``
    is that persona's number of distinct ``(attribute-pair, severity)`` clashes at
    level *L*, so the sum over the combination is the same quantity the per-clash file
    counts one row per round of. Derived from the rows already read rather than from
    the report, which carries no per-level breakdown.
    """
    return {
        level: sum(getattr(row, SEVERITY_COUNT_FIELDS[level]) for row in rows)
        for level in SEVERITY_LEVELS
    }


def _load_one(
    combo_dir: Path,
    label: str,
    *,
    country: str,
    model: str,
    strategy: str,
    is_real_reference: bool,
) -> CompetitorRecord | str:
    """Load one combination, or return a machine-readable skip reason.

    A *missing* artifact is a skip (the judge has not run here yet); a *present but
    malformed* one raises -- corruption must never be downgraded to a silent exclusion.
    """
    report_path = combo_dir / f"{label}.json"
    personas_csv_path = combo_dir / f"{label}_personas.csv"
    clashes_csv_path = combo_dir / f"{label}_clashes.csv"
    if not report_path.is_file():
        return "no combination report (judge has not completed this combination)"
    if not personas_csv_path.is_file():
        return (
            "no per-persona CSV (judged before the tidy-CSV contract existed) -- re-run "
            "analyze_persona_realism.py --rewrite-artifacts for this combination"
        )
    if not clashes_csv_path.is_file():
        return (
            "no per-clash CSV (judged before the per-clash contract existed) -- re-run "
            "analyze_persona_realism.py --rewrite-artifacts for this combination"
        )

    report = _read_report(report_path)
    n_personas = int(report["n_personas"])
    # Raises on a row-count disagreement: the CSV and the report would then describe
    # different persona sets, and every rate below would be over the wrong base.
    rows = read_realism_personas_csv(personas_csv_path, expected_rows=n_personas)
    # Same guard one grain finer, and computed from the rows just read rather than from
    # the report: the per-clash file must describe the *same* personas, or a driver
    # prevalence would be a numerator from one state of the cache over a denominator
    # from another.
    clashes = read_realism_clashes_csv(
        clashes_csv_path,
        expected_counts=_distinct_clash_counts(rows),
        expected_counts_source=personas_csv_path,
    )

    return CompetitorRecord(
        slug=label,
        country=country,
        model=model,
        strategy=strategy,
        is_real_reference=is_real_reference,
        n_personas=n_personas,
        n_failed=int(report.get("n_failed", 0)),
        personas=tuple(rows),
        impossibility=dict(report["impossibility"]),
        dispersion=dict(report["dispersion"]),
        reliability=dict(report.get("reliability") or {}),
        # The published round count, marked as read (not capped): the two are the same
        # number here, and only the source distinguishes this record from a capped one.
        provenance={**dict(report["provenance"]), "n_rounds_source": N_ROUNDS_SOURCE_REPORT},
        report_path=report_path,
        personas_csv_path=personas_csv_path,
        clashes=tuple(clashes),
    )


# --------------------------------------------------------------------------- #
# the round-cap path: re-derive one competitor over its first N judge rounds    #
# --------------------------------------------------------------------------- #


def _present_personas(combo_dir: Path, label: str) -> list[LoadedPersona]:
    """The combination's cached personas in persona-id order (fail-fast when empty).

    The verdict cache is read exclusively through ``persona_realism``'s own loader, so
    this package never learns the cache's file layout beyond the directory holding it.
    An empty cache raises rather than yielding an empty competitor: the report the
    caller just read says this combination was judged, so an empty cache means the two
    disagree -- and a rate over a base of zero would still rank.
    """
    loaded = load_combo_verdicts(combo_dir)
    present = [lp for lp in loaded.values() if lp is not None]
    if not present:
        raise ValueError(
            f"Combination {label!r} has a published report but no per-persona verdict "
            f"cache under {combo_dir}. A round cap re-reduces every competitor from that "
            "cache; re-judge the combination with scripts/analyze/analyze_persona_realism.py, "
            "or drop the cap to consume the published artifacts as they stand."
        )
    return present


def _trim_to_cap(persona: LoadedPersona, rounds_cap: int, *, label: str) -> LoadedPersona:
    """Keep *persona*'s first *rounds_cap* cached rounds, or raise on a shortfall.

    The capacity check that replaces the ``n_rounds`` equality when a cap is active.
    A shortfall is a hard failure and never a short-ranked competitor: consuming the
    3 rounds a persona happens to hold against a cap of 5 is precisely the mixed-depth
    comparison the gate exists to refuse, and it would be invisible in the output.

    The retained rounds are positions ``0 .. N-1`` of the cache, which is judgment
    order (the runner appends successes). Rounds are cold and independent, so the
    leading N is an unbiased subsample -- no re-ordering or sampling is introduced.
    """
    cached = len(persona.rounds)
    if cached < rounds_cap:
        raise ValueError(
            f"Combination {label!r} cannot be ranked at {rounds_cap} round(s): persona "
            f"{persona.persona_id!r} holds only {cached} cached judge round(s). The round "
            "cap must not exceed the shortest cached persona of the consumption set -- "
            f"judge that combination up to {rounds_cap} rounds "
            "(scripts/analyze/analyze_persona_realism.py), or lower the cap to at most "
            f"{cached}."
        )
    return replace(persona, rounds=persona.rounds[:rounds_cap])


def _load_one_capped(
    combo_dir: Path,
    label: str,
    *,
    country: str,
    model: str,
    strategy: str,
    is_real_reference: bool,
    rounds_cap: int,
    judge_cfg: JudgeConfig,
    n_rounds_source: str,
) -> CompetitorRecord | str:
    """Rebuild one competitor from its verdict cache over the first *rounds_cap* rounds.

    The cap-active counterpart of :func:`_load_one`. It reads the combination's report
    for its ``provenance`` and ``n_failed`` only -- every published statistic is
    recomputed -- and reads **neither** tidy CSV, because a capped record's rows are by
    definition not the rows those files hold.

    Nothing is reimplemented here: the reduction is ``persona_realism``'s own
    ``reduce_persona``/``reduce_combo``, the statistics its own
    ``compute_realism_stats`` under the same config-sourced arguments the artifact
    writer passes, and the two tidy row sets its own ``persona_rows``/
    ``combo_clash_rows``. At ``rounds_cap == the cached depth`` this therefore
    reproduces the published record rather than approximating it.

    A missing report is still a skip (the judge has not completed this combination);
    every other disagreement raises.
    """
    report_path = combo_dir / f"{label}.json"
    if not report_path.is_file():
        return "no combination report (judge has not completed this combination)"

    report = _read_report(report_path)
    trimmed = [_trim_to_cap(lp, rounds_cap, label=label) for lp in _present_personas(combo_dir, label)]

    n_personas = int(report["n_personas"])
    if len(trimmed) != n_personas:
        raise ValueError(
            f"Combination {label!r} caches {len(trimmed)} persona(s) but its report "
            f"{report_path} declares n_personas={n_personas}. The published artifacts "
            "describe a different state of the cache than the round cap would re-reduce; "
            "re-run scripts/analyze/analyze_persona_realism.py --rewrite-artifacts for "
            "this combination."
        )

    reduced = {lp.persona_id: reduce_persona(lp.rounds, persona_id=lp.persona_id) for lp in trimmed}
    # The failed personas the cache cannot hold (every judge call failed, so no file was
    # written) are carried back as the ``None`` slots ``reduce_combo`` counts, keeping
    # the base of every rate identical to the published one.
    n_failed = int(report.get("n_failed", 0))
    combo = reduce_combo([*reduced.values(), *([None] * n_failed)], label)
    stats = compute_realism_stats(
        combo,
        bootstrap=judge_cfg.bootstrap,
        typicality_level=str(judge_cfg.reliability_value("typicality_level")),
        tail_threshold=float(judge_cfg.reliability_value("tail_threshold")),
    )

    rows = persona_rows(
        reduced, {lp.persona_id: lp for lp in trimmed},
        combo_label=label, country=country, model=model,
        strategy=strategy, is_real_reference=is_real_reference,
    )
    clashes = combo_clash_rows(
        trimmed, combo_label=label, country=country, model=model,
        strategy=strategy, is_real_reference=is_real_reference,
    )

    return CompetitorRecord(
        slug=label,
        country=country,
        model=model,
        strategy=strategy,
        is_real_reference=is_real_reference,
        n_personas=combo.n_personas,
        n_failed=combo.n_failed,
        personas=tuple(rows),
        impossibility=dict(stats.impossibility),
        dispersion=dict(stats.dispersion),
        reliability=dict(stats.reliability),
        # The consumed count, not the judged one: everything above was computed over
        # exactly `rounds_cap` rounds, so the published provenance would be a lie.
        provenance={
            **dict(report["provenance"]),
            ROUND_COUNT_KEY: rounds_cap,
            "n_rounds_source": n_rounds_source,
        },
        report_path=report_path,
        # Declared for the same combination, but deliberately not read on this path:
        # downstream messages point at the file a reader would inspect.
        personas_csv_path=combo_dir / f"{label}_personas.csv",
        clashes=tuple(clashes),
    )


def _assert_homogeneous(records: list[CompetitorRecord], *, cap_active: bool) -> None:
    """Raise unless every consumed combination was judged the same way.

    *cap_active* narrows the comparison to :data:`CAPPED_IDENTITY_KEYS`: with a cap
    the consumed round count is one by construction, so ``n_rounds`` is enforced as a
    per-persona capacity in :func:`_trim_to_cap` instead of as an equality here. The
    judge model and prompt hash are compared either way.
    """
    if not records:
        return
    keys = CAPPED_IDENTITY_KEYS if cap_active else JUDGE_IDENTITY_KEYS
    baseline = records[0]
    reference = _judge_identity(baseline.provenance, keys)
    for record in records[1:]:
        identity = _judge_identity(record.provenance, keys)
        if identity != reference:
            differing = [
                f"{key}: {record.provenance.get(key)!r} != {baseline.provenance.get(key)!r}"
                for key in keys
                if record.provenance.get(key) != baseline.provenance.get(key)
            ]
            raise ValueError(
                f"Heterogeneous judge across the consumption set: {record.slug!r} differs "
                f"from {baseline.slug!r} ({'; '.join(differing)}). Ranking combinations "
                "judged by different judges, prompts, or round counts measures the judges, "
                "not the combinations. Re-judge the odd combination(s) under one "
                "configuration, or narrow the selection with --slug / --model / --strategy."
            )


def _probe_cached_depths(records: list[CompetitorRecord]) -> dict[str, int]:
    """Each competitor's shallowest cached persona, keyed by slug.

    Reads the **verdict caches**, never ``provenance.n_rounds``: that field is the
    round count the judge was *configured* for, which sits above what a part-way
    topped-up cache actually holds. A depth derived from the target would then fail
    the very capacity check it was derived to satisfy.
    """
    return {
        record.slug: min(
            len(persona.rounds)
            for persona in _present_personas(record.report_path.parent, record.slug)
        )
        for record in records
    }


def _load_competitor(
    combo_dir: Path,
    label: str,
    *,
    country: str,
    model: str,
    strategy: str,
    is_real_reference: bool,
    rounds_cap: int | None,
    judge_cfg: JudgeConfig | None,
    n_rounds_source: str,
) -> CompetitorRecord | str:
    """Route one competitor to the published-artifact path or the round-cap path."""
    if rounds_cap is None:
        return _load_one(
            combo_dir, label, country=country, model=model,
            strategy=strategy, is_real_reference=is_real_reference,
        )
    if judge_cfg is None:
        raise ValueError(
            f"Cannot re-derive {label!r} at {rounds_cap} round(s) without a judge config "
            "(bootstrap + reliability parameters); load_competitors validates this at its "
            "entry, so reaching here means the walk was driven directly."
        )
    return _load_one_capped(
        combo_dir, label, country=country, model=model,
        strategy=strategy, is_real_reference=is_real_reference,
        rounds_cap=rounds_cap, judge_cfg=judge_cfg, n_rounds_source=n_rounds_source,
    )


def _load_all(
    output_base: str | Path,
    *,
    countries: list[str] | None,
    models: list[str] | None,
    strategies: list[str] | None,
    slugs: list[str] | None,
    strict: bool,
    axis_ids: tuple[list[str], list[str], list[str]] | None,
    rounds_cap: int | None,
    judge_cfg: JudgeConfig | None,
    n_rounds_source: str,
) -> tuple[list[CompetitorRecord], list[tuple[str, str]]]:
    """The discovery walk, in construction order and without the homogeneity gate.

    Split out of :func:`load_competitors` because the auto-derived cap has to walk the
    same selection twice -- once to discover what is there and how deep it was judged,
    once to re-derive it at the common depth -- and re-walking is what guarantees the
    two passes consume exactly the same set rather than a remembered approximation of it.
    """
    output_base = Path(output_base)
    mapped_dir = resolve_mapped_dir(output_base)
    judge_root = analysis_output_dir("persona_realism", output_base, for_read=True)

    index_path = mapped_dir / "_index.json"
    if not index_path.is_file():
        raise FileNotFoundError(
            f"Mapped index not found: {index_path}. Run scripts/analyze/map_populations.py "
            "(and the population_cap it depends on), then "
            "scripts/analyze/analyze_persona_realism.py, before ranking."
        )

    if axis_ids is None:
        country_ids = sorted(d["id"] for d in discover_axis_values("countries"))
        strategy_ids = sorted(d["id"] for d in discover_axis_values("strategies"))
        model_ids = sorted(d["id"] for d in discover_axis_values("models"))
    else:
        country_ids, strategy_ids, model_ids = axis_ids

    with open(index_path, "r", encoding="utf-8") as fh:
        index_entries = json.load(fh)

    records: list[CompetitorRecord] = []
    skipped: list[tuple[str, str]] = []
    selected_countries: list[str] = []

    for entry in index_entries:
        slug = entry["slug"]
        if slugs and slug not in slugs:
            continue
        if entry.get("skipped") is True or entry.get("synthetic_file") is None:
            if slugs:
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
        if country not in selected_countries:
            selected_countries.append(country)

        loaded = _load_competitor(
            judge_root / country / slug, slug,
            country=country, model=model, strategy=strategy, is_real_reference=False,
            rounds_cap=rounds_cap, judge_cfg=judge_cfg, n_rounds_source=n_rounds_source,
        )
        if isinstance(loaded, str):
            if strict:
                raise RuntimeError(f"Combination {slug!r} is not consumable: {loaded}")
            skipped.append((slug, loaded))
            continue
        records.append(loaded)

    # The real competitor of every country that contributed a record. Unlike the judge --
    # where an explicit --slug must stay literal so one combination can be judged in
    # isolation -- the ranking always wants it: it is a ranked row on Axis A and the
    # target of Axis B, so a --slug-narrowed ranking that silently dropped it would
    # quietly lose half the analysis. Its absence is never fatal: the Axis A ranking of
    # the synthetic competitors still stands, and the builder records the skipped Axis B
    # and contrast tests with a reason.
    for country in selected_countries:
        label = f"real_{country}"
        loaded = _load_competitor(
            judge_root / country / label, label,
            country=country, model="", strategy="", is_real_reference=True,
            rounds_cap=rounds_cap, judge_cfg=judge_cfg, n_rounds_source=n_rounds_source,
        )
        if isinstance(loaded, str):
            if strict:
                raise RuntimeError(f"Real competitor {label!r} is not consumable: {loaded}")
            skipped.append((label, loaded))
            continue
        records.append(loaded)

    return records, skipped


def load_competitors(
    output_base: str | Path,
    *,
    countries: list[str] | None = None,
    models: list[str] | None = None,
    strategies: list[str] | None = None,
    slugs: list[str] | None = None,
    strict: bool = False,
    axis_ids: tuple[list[str], list[str], list[str]] | None = None,
    rounds_cap: int | None = None,
    judge_cfg: JudgeConfig | None = None,
) -> tuple[list[CompetitorRecord], list[tuple[str, str]]]:
    """Load every consumable competitor under *output_base*.

    Returns ``(records, skipped)`` where *skipped* lists ``(slug, reason)`` for units
    that were selected but not consumable. Filters narrow the selection silently
    (a filtered-out combination is neither a record nor a skip).

    The upstream folder is resolved through the analysis registry
    (``analysis_output_dir("persona_realism", ...)``) rather than a path literal, and
    the combination set from the capped mapped ``_index.json`` -- the same discovery
    route every other downstream reader takes.

    Round count
    -----------
    Three states, in increasing order of intervention:

    * *rounds_cap is None and the set agrees on* ``n_rounds`` -- the default. Every
      record is read from the published artifacts and nothing here executes
      differently from before the cap existed. ``provenance["n_rounds_source"]`` is
      ``"report"``.
    * *rounds_cap is None and the set differs on* ``n_rounds`` *alone* -- the gate has
      already failed, so instead of stopping, the shallowest **cached** depth is
      derived and every competitor is re-derived at it, with a warning naming the
      depth and the trimmed combinations (``"auto"``). A set differing on the judge
      model or the prompt hash still raises: no round cap repairs a different judge.
      Auto-derivation needs *judge_cfg* to recompute the statistics; without it the
      heterogeneity is reported unchanged.
    * *rounds_cap is set* -- every competitor is re-derived over its first N cached
      rounds and a persona holding fewer than N is a hard failure (``"cap"``). This is
      the form to pin for anything published: the auto-derived depth moves as a sweep
      tops up, so two auto runs can rank at different depths.

    Both re-deriving forms read the verdict caches (through ``persona_realism``'s own
    reducers) and **not** the two tidy CSVs, whose row grain has already summed each
    persona's votes over all of its cached rounds and so cannot express a cap.

    Args:
        rounds_cap: the number of leading cached rounds to consume per persona, or
            ``None`` for the published/auto behaviour above.
        judge_cfg: the loaded judge config supplying the bootstrap and reliability
            parameters. **Required** whenever *rounds_cap* is set -- the re-derived
            statistics must be computed under exactly the arguments the per-combination
            artifacts were, and there is no in-code default for them.
    """
    if rounds_cap is not None:
        if judge_cfg is None:
            raise ValueError(
                "load_competitors(rounds_cap=...) requires judge_cfg: a capped record is "
                "recomputed from the verdict cache, and the bootstrap seed / reliability "
                "parameters that make it comparable to an uncapped one come only from "
                "judge.yaml (there is no in-code default)."
            )
        if rounds_cap < 1:
            raise ValueError(f"rounds_cap must be >= 1, got {rounds_cap}")

    discovery: dict[str, Any] = {
        "countries": countries, "models": models, "strategies": strategies,
        "slugs": slugs, "strict": strict, "axis_ids": axis_ids,
    }
    records, skipped = _load_all(
        output_base, **discovery,
        rounds_cap=rounds_cap, judge_cfg=judge_cfg,
        n_rounds_source=N_ROUNDS_SOURCE_REPORT if rounds_cap is None else N_ROUNDS_SOURCE_CAP,
    )

    if rounds_cap is not None:
        _assert_homogeneous(records, cap_active=True)
    elif judge_cfg is not None and _identity_mismatches(records) == {ROUND_COUNT_KEY}:
        depths = _probe_cached_depths(records)
        derived = min(depths.values())
        trimmed = sorted(slug for slug, depth in depths.items() if depth > derived)
        _LOGGER.warning(
            "Consumption set disagrees on %s only; ranking every competitor at the "
            "shallowest cached depth of %d round(s). Trimmed: %s. Pin --rounds for "
            "anything published -- a derived depth moves as the sweep tops up, so two "
            "runs can rank at different depths without the command changing.",
            ROUND_COUNT_KEY, derived, ", ".join(trimmed) or "(none)",
        )
        records, skipped = _load_all(
            output_base, **discovery,
            rounds_cap=derived, judge_cfg=judge_cfg,
            n_rounds_source=N_ROUNDS_SOURCE_AUTO,
        )
        _assert_homogeneous(records, cap_active=True)
    else:
        _assert_homogeneous(records, cap_active=False)

    records.sort(key=lambda r: r.slug)
    return records, skipped

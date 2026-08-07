"""loader.py -- discover, gate and type the consumption set for the realism ranking.

Owns the data contract of the cross-combination process: the per-competitor
:class:`CompetitorRecord` DTO and the discovery walk that welds the capped mapped
index to the per-combination artifacts ``persona_realism`` wrote. It reads only the
published on-disk contract -- ``{combo}.json`` plus ``{combo}_personas.csv`` -- and
never reaches into the judge's reduction internals, so the judging half can change
freely as long as those two files keep their shape.

Two gates run before any statistic is computed, because both failure modes produce
numbers that look perfectly reasonable and are wrong:

**Completeness.** A *consumable* combination has a report, has a per-persona CSV, and
the CSV's row count equals the report's ``n_personas``. Anything else is a partial
directory -- a run that was interrupted after caching verdicts but before writing
artifacts, of which several exist on any real output base. Such a directory is skipped
with a machine-readable reason (or raises under ``strict``); it is never silently
ranked, because a combination missing half its personas would simply appear to have an
unusually clean impossibility rate.

**Homogeneity.** Every consumed combination must share the same ``judge_model``,
``prompt_template_sha256`` and ``n_rounds``. Ranking units judged by different judges,
prompts, or round counts measures the judges, not the units. The identity is read from
each report's stamped ``provenance`` block -- what was actually used -- and never from
the config as it currently stands, which may have moved on since.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from population_synthetic.analysis.utils.axes import decompose_slug, diagnose_slug
from population_synthetic.analysis.utils.capped_source import resolve_mapped_dir
from population_synthetic.analysis.utils.realism_csv import (
    RealismPersonaRow,
    read_realism_personas_csv,
)
from population_synthetic.analysis.utils.registry import analysis_output_dir
from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values

__all__ = [
    "CompetitorRecord",
    "JUDGE_IDENTITY_KEYS",
    "load_competitors",
]

#: The provenance fields that must agree across the whole consumption set. Each one
#: changes what the judge measured, so a mismatch makes the units incomparable.
JUDGE_IDENTITY_KEYS: tuple[str, ...] = ("judge_model", "prompt_template_sha256", "n_rounds")


@dataclass(frozen=True)
class CompetitorRecord:
    """One ranked competitor: a synthetic combination or the real population.

    ``personas`` is the tidy per-persona series -- the granularity the rank-based tests
    and the mixed model need; ``impossibility`` / ``dispersion`` / ``reliability`` are
    the single-combination blocks lifted verbatim from the report, so the aggregator
    never recomputes what the per-combination task already published.

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


def _judge_identity(provenance: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(provenance.get(key) for key in JUDGE_IDENTITY_KEYS)


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
    if not report_path.is_file():
        return "no combination report (judge has not completed this combination)"
    if not personas_csv_path.is_file():
        return (
            "no per-persona CSV (judged before the tidy-CSV contract existed) -- re-run "
            "analyze_persona_realism.py --rewrite-artifacts for this combination"
        )

    report = _read_report(report_path)
    n_personas = int(report["n_personas"])
    # Raises on a row-count disagreement: the CSV and the report would then describe
    # different persona sets, and every rate below would be over the wrong base.
    rows = read_realism_personas_csv(personas_csv_path, expected_rows=n_personas)

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
        provenance=dict(report["provenance"]),
        report_path=report_path,
        personas_csv_path=personas_csv_path,
    )


def _assert_homogeneous(records: list[CompetitorRecord]) -> None:
    """Raise unless every consumed combination was judged the same way."""
    if not records:
        return
    baseline = records[0]
    reference = _judge_identity(baseline.provenance)
    for record in records[1:]:
        identity = _judge_identity(record.provenance)
        if identity != reference:
            differing = [
                f"{key}: {record.provenance.get(key)!r} != {baseline.provenance.get(key)!r}"
                for key in JUDGE_IDENTITY_KEYS
                if record.provenance.get(key) != baseline.provenance.get(key)
            ]
            raise ValueError(
                f"Heterogeneous judge across the consumption set: {record.slug!r} differs "
                f"from {baseline.slug!r} ({'; '.join(differing)}). Ranking combinations "
                "judged by different judges, prompts, or round counts measures the judges, "
                "not the combinations. Re-judge the odd combination(s) under one "
                "configuration, or narrow the selection with --slug / --model / --strategy."
            )


def load_competitors(
    output_base: str | Path,
    *,
    countries: list[str] | None = None,
    models: list[str] | None = None,
    strategies: list[str] | None = None,
    slugs: list[str] | None = None,
    strict: bool = False,
    axis_ids: tuple[list[str], list[str], list[str]] | None = None,
) -> tuple[list[CompetitorRecord], list[tuple[str, str]]]:
    """Load every consumable competitor under *output_base*.

    Returns ``(records, skipped)`` where *skipped* lists ``(slug, reason)`` for units
    that were selected but not consumable. Filters narrow the selection silently
    (a filtered-out combination is neither a record nor a skip).

    The upstream folder is resolved through the analysis registry
    (``analysis_output_dir("persona_realism", ...)``) rather than a path literal, and
    the combination set from the capped mapped ``_index.json`` -- the same discovery
    route every other downstream reader takes.
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

        loaded = _load_one(
            judge_root / country / slug, slug,
            country=country, model=model, strategy=strategy, is_real_reference=False,
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
        loaded = _load_one(
            judge_root / country / label, label,
            country=country, model="", strategy="", is_real_reference=True,
        )
        if isinstance(loaded, str):
            if strict:
                raise RuntimeError(f"Real competitor {label!r} is not consumable: {loaded}")
            skipped.append((label, loaded))
            continue
        records.append(loaded)

    _assert_homogeneous(records)
    records.sort(key=lambda r: r.slug)
    return records, skipped

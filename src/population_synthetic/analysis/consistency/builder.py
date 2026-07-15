"""builder.py -- Scan a mapped population against consistency rules and persist results.

:func:`scan_population` is a pure function: individuals in, a
:class:`ConsistencyReport` out (never mutates its input, per the pipeline's
purity/idempotency conventions). The three writers are thin, side-effecting sinks
that serialise a report (or a set of reports) to JSON/CSV; none of them compute
anything -- they only shape and persist what :func:`scan_population` already
decided.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from population_synthetic.analysis.consistency.rules import Rule, is_violation

#: Capped sample size of offending records kept per rule per population.
_DEFAULT_MAX_EXAMPLES = 20

_SUMMARY_FIELDNAMES: tuple[str, ...] = ("population", "rule_id", "severity", "violations", "rate")


@dataclass(frozen=True)
class RuleResult:
    """One rule's outcome against one population: count, rate, capped examples."""

    rule_id: str
    description: str
    severity: str
    n_violations: int
    violation_rate: float
    examples: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ConsistencyReport:
    """One population's consistency scan: every rule's :class:`RuleResult`."""

    population: str
    country: str
    n_individuals: int
    generated_at: str
    results: tuple[RuleResult, ...]


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def scan_population(
    individuals: list[dict],
    rules: tuple[Rule, ...],
    *,
    population: str = "population",
    country: str = "",
    max_examples: int = _DEFAULT_MAX_EXAMPLES,
) -> ConsistencyReport:
    """Scan every individual against every rule and assemble a :class:`ConsistencyReport`.

    For each rule: the violation count (individuals matching ``when`` but failing
    ``require``), the violation rate (``violations / n``, ``NaN`` when the
    population is empty rather than a divide-by-zero), and a sample of up to
    *max_examples* offending records (shallow copies -- *individuals* is never
    mutated).
    """
    n = len(individuals)
    results: list[RuleResult] = []
    for rule in rules:
        offenders = [ind for ind in individuals if is_violation(ind, rule)]
        n_violations = len(offenders)
        rate = (n_violations / n) if n > 0 else float("nan")
        examples = tuple(dict(ind) for ind in offenders[:max_examples])
        results.append(
            RuleResult(
                rule_id=rule.id,
                description=rule.description,
                severity=rule.severity,
                n_violations=n_violations,
                violation_rate=rate,
                examples=examples,
            )
        )
    return ConsistencyReport(
        population=population,
        country=country,
        n_individuals=n,
        generated_at=datetime.now(timezone.utc).isoformat(),
        results=tuple(results),
    )


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _rule_result_to_dict(result: RuleResult, *, include_examples: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rule_id": result.rule_id,
        "description": result.description,
        "severity": result.severity,
        "n_violations": result.n_violations,
        "violation_rate": result.violation_rate,
    }
    if include_examples:
        payload["examples"] = list(result.examples)
    return payload


def _report_to_dict(report: ConsistencyReport, *, include_examples: bool) -> dict[str, Any]:
    return {
        "population": report.population,
        "country": report.country,
        "n_individuals": report.n_individuals,
        "generated_at": report.generated_at,
        "results": [_rule_result_to_dict(r, include_examples=include_examples) for r in report.results],
    }


def build_summary_rows(reports: list[ConsistencyReport]) -> list[dict[str, Any]]:
    """Flatten a set of per-population reports into one row per (population, rule).

    Mirrors ``multivariate_fidelity.builder.aggregate_multivariate_fidelity``: a
    pure roll-up, no I/O. Feeds both :func:`write_summary_csv` and the violation-rate
    chart.
    """
    rows: list[dict[str, Any]] = []
    for report in reports:
        for result in report.results:
            rows.append({
                "population": report.population,
                "rule_id": result.rule_id,
                "severity": result.severity,
                "n_individuals": report.n_individuals,
                "violations": result.n_violations,
                "rate": result.violation_rate,
            })
    return rows


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_report_json(reports: list[ConsistencyReport], out_path: str | Path) -> Path:
    """Write the per-country consistency report to *out_path*.

    One entry per scanned population (the real reference population and each
    requested slug), each carrying its per-rule counts and rates. Offending-record
    examples are *not* included here (they go to :func:`write_violations_csv`,
    one file per population) so this file stays a compact summary.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [_report_to_dict(r, include_examples=False) for r in reports]
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return out_path


def write_summary_csv(rows: list[dict[str, Any]], out_path: str | Path) -> Path:
    """Write the flat per-country summary table: one row per (population, rule).

    Columns: ``population, rule_id, severity, violations, rate``. *rows* is the
    output of :func:`build_summary_rows`.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(_SUMMARY_FIELDNAMES), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return out_path


def write_violations_csv(report: ConsistencyReport, out_path: str | Path) -> Path:
    """Write one population's capped sample of offending records to *out_path*.

    One row per (rule, offending individual), with ``rule_id``/``severity`` first
    followed by every field the offending records carry. Field names are derived
    from the examples themselves (never a hardcoded attribute list, per the
    config-is-truth convention) -- a population with zero examples across every
    rule writes a header-only ``rule_id, severity`` file rather than raising.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    attr_keys: list[str] = []
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for result in report.results:
        for example in result.examples:
            for key in example:
                if key not in seen:
                    seen.add(key)
                    attr_keys.append(key)
            rows.append({"rule_id": result.rule_id, "severity": result.severity, **example})

    fieldnames = ["rule_id", "severity", *attr_keys]
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return out_path

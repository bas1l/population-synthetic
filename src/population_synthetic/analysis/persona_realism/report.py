"""report.py -- write per-combination and run-level realism JSON reports.

Pure sink: assembles already-computed structures into a JSON document and writes
it via ``json.dump(indent=2, ensure_ascii=False)`` with a parent ``mkdir``. It
computes no statistics -- the caller (:mod:`artifacts`) hands over the
:class:`~population_synthetic.analysis.persona_realism.stats.RealismStats`, the
serialised clash taxonomy, the cost + cost-coverage blocks, the hard-rules
validation block, and the pricing/provenance meta; this module only nests and
serialises them.

Two measurement-honesty invariants are baked into the emitted structure (they are
labels, not computations):

* **Reliability != validity.** The ``reliability`` block is emitted under a
  ``reliability_note`` that names it self-consistency, and the ``hard_rules_validation``
  block is always present as the validity anchor.
* **Cost-coverage honesty.** Telemetry is now per-persona (``persona_XXXXX.jsonl``,
  append-accumulated across resumed/top-up passes) and 1:1 with the verdict cache,
  so a resumed run's cost reliably covers every cached persona (``status`` is
  ``complete``). The ``cost_coverage`` block (``{judged_this_run, total_personas,
  status}``) is still carried verbatim; a genuine per-file gap surfaces as
  ``partial`` so it is never misread as the full-population cost.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from population_synthetic.analysis.persona_realism.stats import RealismStats

__all__ = ["write_combo_report", "write_run_report"]

_PROCESS = "persona_realism"
_RELIABILITY_NOTE = (
    "The 'reliability' block is the judge's self-consistency across rounds "
    "(precision), NOT its correctness. The 'hard_rules_validation' block is the "
    "only validity anchor."
)


def _dump(payload: dict[str, Any], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def write_combo_report(
    path: Path,
    *,
    stats: RealismStats,
    clash_taxonomy: list[dict[str, Any]],
    cost: dict[str, Any],
    cost_coverage: dict[str, Any],
    validation: dict[str, Any] | None,
    provenance: dict[str, Any],
    pricing: dict[str, Any],
) -> Path:
    """Write one combination's realism JSON report to *path*.

    ``stats`` is serialised via :func:`dataclasses.asdict` (its ``impossibility``/
    ``dispersion``/``reliability`` fields are already plain dicts). ``clash_taxonomy``
    is the caller's serialisable clash list (``[{pair, severity, n_personas}]``).
    ``validation`` is the hard-rules validation block (``None`` when no rules were
    evaluated). All meta blocks are written verbatim.
    """
    stats_dict = asdict(stats)
    payload = {
        "process": _PROCESS,
        "combo_label": stats.combo_label,
        "n_personas": stats.n_personas,
        "n_failed": stats.n_failed,
        "impossibility": stats_dict["impossibility"],
        "dispersion": stats_dict["dispersion"],
        "reliability": stats_dict["reliability"],
        "reliability_note": _RELIABILITY_NOTE,
        "clash_taxonomy": clash_taxonomy,
        "hard_rules_validation": validation,
        "cost": cost,
        "cost_coverage": cost_coverage,
        "pricing": pricing,
        "provenance": provenance,
    }
    return _dump(payload, path)


def write_run_report(
    path: Path,
    *,
    combos: list[dict[str, Any]],
    headline: dict[str, Any],
    provenance: dict[str, Any],
    pricing: dict[str, Any],
) -> Path:
    """Write the run-level realism JSON report to *path*.

    ``combos`` is one compact summary dict per combination (label + headline
    metrics + cost-coverage), ``headline`` is the map metadata (measure + the
    plotted point coordinates), and the pricing/provenance meta are carried
    verbatim. This is the run's provenance record (judge model, prompt hash, N,
    temperature, bootstrap seed, config snapshot).
    """
    payload = {
        "process": _PROCESS,
        "reliability_note": _RELIABILITY_NOTE,
        "provenance": provenance,
        "pricing": pricing,
        "headline_map": headline,
        "combos": combos,
    }
    return _dump(payload, path)

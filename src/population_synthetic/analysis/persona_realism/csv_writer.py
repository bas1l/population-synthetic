"""csv_writer.py -- write one combination's flat realism summary row to CSV.

Pure sink: takes an already-assembled :class:`RealismRow` record and a target path,
and writes it via the stdlib ``csv`` module with a **fixed** column set. Knows
nothing about matplotlib, the country id, the stats formulas, or how the row was
computed -- the caller (:mod:`artifacts`) assembles it from a
:class:`~population_synthetic.analysis.persona_realism.stats.RealismStats` plus the
cost/validation blocks and resolves the path.

Every column describes the combination **on its own**. The five columns that
described it relative to the SCB reference (``dist_variance``, ``dist_entropy``,
``dist_tail_coverage``, ``variance_equality_stat``, ``variance_equality_p``) are
gone: they made a single combination's row unreproducible without first judging a
different combination. The contrast now lives in ``realism_ranking``'s
``scb_contrast.csv``, computed from the per-persona tidy CSVs.

:data:`FIELDNAMES` is the single source of truth for the column set and order,
consumed by both the header and each row; :class:`RealismRow`'s fields are kept
in lock-step with it so the two can never drift.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path

__all__ = ["FIELDNAMES", "RealismRow", "write_realism_csv"]


@dataclass(frozen=True)
class RealismRow:
    """One combination's flat CSV record.

    Every metric field is ``float | None`` (``None`` == the metric was skipped on
    degenerate input -- e.g. no can_exist personas, a single round -- kept distinct
    from a genuine ``0``). ``n_personas`` (successful base) and ``n_failed``
    (all-rounds-failed / absent) are carried on every row so a rate is never read
    without its denominator. ``cost_usd``/``total_tokens`` are ``None`` when the
    combo has no token telemetry.
    """

    combo_label: str
    n_personas: int
    n_failed: int
    impossibility_rate: float | None
    imp_ci_lo: float | None
    imp_ci_hi: float | None
    impossible_count: int
    disp_variance: float | None
    disp_entropy: float | None
    disp_tail_coverage: float | None
    can_exist_alpha: float | None
    typicality_alpha: float | None
    typicality_icc: float | None
    hard_rules_agreement: float | None
    hard_rules_recall: float | None
    total_tokens: int | None
    cost_usd: float | None


#: Column order == :class:`RealismRow` field order (single source of truth).
FIELDNAMES: tuple[str, ...] = tuple(f.name for f in fields(RealismRow))


def write_realism_csv(rows: list[RealismRow], path: Path) -> Path:
    """Write *rows* to *path* as CSV with the :data:`FIELDNAMES` columns.

    One row per combination, in the given order. Creates the parent directory if
    needed. Returns *path*.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    return path

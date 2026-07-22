"""csv_writer.py -- write the per-category proportion table to CSV.

Pure sink: takes already-computed :class:`CategoryStat` rows and a target path, and
writes them via the stdlib ``csv`` module. Knows nothing about matplotlib, the
country id, or the comparison scheme -- the caller resolves both the rows and the
path.
"""

from __future__ import annotations

import csv
from pathlib import Path

from population_synthetic.analysis.real_population_stats.stats import CategoryStat

_FIELDNAMES = ("value", "count", "total", "proportion", "percent")


def write_proportions_csv(rows: list[CategoryStat], path: Path) -> Path:
    """Write *rows* to *path* as CSV with columns ``value,count,total,proportion,percent``.

    One row per config category value, in the given order. Creates the parent
    directory if needed. Returns *path*.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "value": row.value,
                    "count": row.count,
                    "total": row.total,
                    "proportion": row.proportion,
                    "percent": row.percent,
                }
            )

    return path

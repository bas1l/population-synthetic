"""Golden inputs of the typicality closeness prototype (swedish_02, first judge round).

``tests/data/closeness/`` holds two extracts of the prototype kept under
``docs/development/plans/active/typicality-distribution-grid/``:

* ``combination_outcomes.csv`` -- one row per present (model, strategy) combination (58;
  two withdrawn cells absent) with the prototype's per-combination closeness outcomes
  (Cliff's delta, the share-<=4 gap, the mean CDF gap from ``closeness/``, and TV
  distance and Cramer distance from ``closeness_shape/``).
* ``first_round_histograms.csv`` -- the integer first-round score histogram (levels
  0..10) of each combination and of the reference (``real_swedish_02``).

The expected numbers the tests pin are copied from the prototype's own output files
(``decomposition.csv``, ``permutation_tests.csv``, ``complete_block_tests.json``,
``posthoc_pairs.csv``, ``shape_meta.json``) and cited at each use.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data" / "closeness"

#: The prototype's model_ranking column order (``meta.json``), which fixes the row order
#: of both fixtures (models outer, strategies inner).
STRATEGIES = [
    "all_pick_v2",
    "all_pick_dag_v2",
    "all_generate_pick_v2",
    "all_generate_evaluate_pick_v2",
    "all_generate_evaluate_random_pick_v2",
]
LETTERS = ["A", "B", "C", "D", "E"]
REFERENCE = "real_swedish_02"


def combination_outcomes() -> list[dict]:
    """The 58 combination rows, numeric columns as float."""
    rows = []
    with open(DATA_DIR / "combination_outcomes.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows.append({**r, **{k: float(r[k]) for k in ("n", "delta", "le4", "cdf", "tv", "cramer")}})
    return rows


def first_round_histograms() -> tuple[list[tuple[str, str]], np.ndarray, np.ndarray]:
    """``(keys, combination_counts (58, 11), reference_counts (11,))``."""
    keys, counts, reference = [], [], None
    with open(DATA_DIR / "first_round_histograms.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            row = np.array([int(r[f"c{k}"]) for k in range(11)], dtype=float)
            assert row.sum() == int(r["n"])
            if r["model"] == REFERENCE:
                reference = row
            else:
                keys.append((r["model"], r["strategy"]))
                counts.append(row)
    assert reference is not None
    return keys, np.stack(counts), reference


def one_hot_units(counts: np.ndarray) -> np.ndarray:
    """``(n, K)`` one-hot unit rows reproducing an integer histogram."""
    levels = np.repeat(np.arange(counts.size), counts.astype(int))
    return np.eye(counts.size)[levels]

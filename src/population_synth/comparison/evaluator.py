"""
evaluator.py -- Statistical comparison of two demographic population files.

Provides ``StatisticalEvaluator`` for chi-square, KL divergence, total-variation
distance, joint distribution, and individual coherence tests.  Also includes
``write_csv_summary`` for exporting marginal metrics to CSV.
"""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import chi2_contingency, chisquare

from population_synth.comparison.scheme import ComparisonScheme
from population_synth.population.helpers import age_to_group

# ------------------------------------------------------------------
# Shared constants used across the comparison package
# ------------------------------------------------------------------

DEMOGRAPHIC_ATTRIBUTES = [
    "age_group",
    "biological_sex",
    "education_level",
    "employment_status",
    "birth_location",
    "socioeconomic_class",
    "parental_structure",
    "region",
    "civil_status",
    "industry_sector",
    "employment_type",
    "housing_tenure",
    "household_size",
    "income_source",
    "birth_country_detail",
]

JOINT_PAIRS = [
    ("age_group", "education_level"),
    ("age_group", "employment_status"),
    ("education_level", "employment_status"),
]

COHERENCE_ATTRIBUTES = ("age_group", "education_level", "employment_status")

COHERENCE_THRESHOLD = 0.001


# ------------------------------------------------------------------
# Derived-attribute access (age binning lives in the stats layer)
# ------------------------------------------------------------------

def _bin_age(age: Any) -> str | None:
    """Bin a raw age into the canonical age group, or ``None`` if missing/non-int/out-of-range."""
    try:
        return age_to_group(int(age))
    except (TypeError, ValueError):
        return None


def attr_value(ind: dict, attr: str) -> Any:
    """Return an individual's value for *attr*, deriving ``age_group`` from raw ``age``.

    Canonical individuals store only the integer ``age`` (not a pre-binned
    ``age_group``); the bin is computed on demand here so the comparison can keep
    age as a dimension without baking it into the schema. Falls back to a stored
    ``age_group`` for legacy populations (e.g. the ``flatten_raw`` path) that still
    carry it.
    """
    if attr == "age_group":
        if ind.get("age") is not None:
            return _bin_age(ind["age"])
        return ind.get("age_group")
    return ind.get(attr)


# ------------------------------------------------------------------
# StatisticalEvaluator
# ------------------------------------------------------------------

class StatisticalEvaluator:
    def __init__(self, pop_a: dict, pop_b: dict, scheme: ComparisonScheme | None = None):
        self.pop_a = pop_a
        self.pop_b = pop_b
        self.scheme = scheme
        self.individuals_a: list[dict] = pop_a["individuals"]
        self.individuals_b: list[dict] = pop_b["individuals"]
        self.n_a = len(self.individuals_a)
        self.n_b = len(self.individuals_b)

    # --- Marginal comparison -----------------------------------------------

    def _freq_table(self, individuals: list[dict], attr: str) -> Counter:
        return Counter(attr_value(ind, attr) for ind in individuals)

    def _smoothed_probs(self, counts: Counter, categories: list) -> np.ndarray:
        """Laplace-smoothed probability vector over the given categories."""
        arr = np.array([counts.get(c, 0) + 1 for c in categories], dtype=float)
        return arr / arr.sum()

    def _marginal_metrics(self, attr: str) -> dict[str, Any]:
        counts_a = self._freq_table(self.individuals_a, attr)
        counts_b = self._freq_table(self.individuals_b, attr)

        if self.scheme is not None and attr in self.scheme.categories:
            # Scheme-driven: the comparison axis is exactly the DB-grounded category
            # set, so values the reference never emits cannot appear, and synthetic-only
            # values fall outside the axis (reported as unmapped, not silently scored).
            all_categories = list(self.scheme.categories[attr])
            unmapped = [c for c in counts_b if c is not None and c not in all_categories]
        else:
            all_categories = sorted((set(counts_a) | set(counts_b)) - {None})
            unmapped = [c for c in counts_b if c not in counts_a and c is not None]
        unknown_count_b = int(counts_b.get("Non-standard label", 0))
        unknown_count_a = int(counts_a.get("Non-standard label", 0))

        if not all_categories:
            return {
                "chi_sq_p": float("nan"),
                "kl_divergence": float("nan"),
                "tv_distance": float("nan"),
                "max_diff": float("nan"),
                "categories": [],
                "unmapped": unmapped,
                "unknown_count_a": unknown_count_a,
                "unknown_count_b": unknown_count_b,
            }

        # Expected counts for chi-squared: pop_a proportions scaled to n_b
        total_a = sum(counts_a.get(c, 0) for c in all_categories) or 1
        f_exp = np.array([counts_a.get(c, 0) / total_a * self.n_b for c in all_categories], dtype=float)
        f_obs = np.array([counts_b.get(c, 0) for c in all_categories], dtype=float)

        # Chi-squared goodness-of-fit -- guard against zero expected cells.
        valid_mask = f_exp > 0
        if valid_mask.sum() >= 2:
            f_obs_m = f_obs[valid_mask]
            f_exp_m = f_exp[valid_mask]
            obs_sum = f_obs_m.sum()
            exp_sum = f_exp_m.sum()
            if obs_sum > 0 and exp_sum > 0:
                f_exp_m = f_exp_m / exp_sum * obs_sum
                _, chi_p = chisquare(f_obs_m, f_exp=f_exp_m)
            else:
                chi_p = float("nan")
        else:
            chi_p = float("nan")

        # KL divergence (Laplace-smoothed) -- D_KL(B || A)
        p_b = self._smoothed_probs(counts_b, all_categories)
        p_a = self._smoothed_probs(counts_a, all_categories)
        kl_div = float(np.sum(p_b * np.log2(p_b / p_a)))

        # Total Variation distance (raw proportions, zero-filled)
        total_b = sum(counts_b.get(c, 0) for c in all_categories) or 1
        q_a = np.array([counts_a.get(c, 0) / total_a for c in all_categories])
        q_b = np.array([counts_b.get(c, 0) / total_b for c in all_categories])
        tv_dist = float(0.5 * np.sum(np.abs(q_a - q_b)))

        max_diff = float(np.max(np.abs(q_a - q_b)))

        return {
            "chi_sq_p": float(chi_p),
            "kl_divergence": kl_div,
            "tv_distance": tv_dist,
            "max_diff": max_diff,
            "categories": all_categories,
            "unmapped": unmapped,
            "unknown_count_a": unknown_count_a,
            "unknown_count_b": unknown_count_b,
        }

    def compute_marginals(self) -> dict[str, dict[str, Any]]:
        attrs = self.scheme.attributes if self.scheme is not None else DEMOGRAPHIC_ATTRIBUTES
        return {attr: self._marginal_metrics(attr) for attr in attrs}

    # --- Joint chi-squared -------------------------------------------------

    def _joint_chi_sq(self, attr_x: str, attr_y: str) -> float:
        all_x = sorted({attr_value(ind, attr_x) for ind in self.individuals_a + self.individuals_b} - {None})
        all_y = sorted({attr_value(ind, attr_y) for ind in self.individuals_a + self.individuals_b} - {None})

        def _crosstab(individuals: list[dict]) -> np.ndarray:
            table = np.zeros((len(all_x), len(all_y)), dtype=float)
            x_idx = {v: i for i, v in enumerate(all_x)}
            y_idx = {v: i for i, v in enumerate(all_y)}
            for ind in individuals:
                xi = x_idx.get(attr_value(ind, attr_x))
                yi = y_idx.get(attr_value(ind, attr_y))
                if xi is not None and yi is not None:
                    table[xi, yi] += 1
            return table

        table_a = _crosstab(self.individuals_a)
        table_b = _crosstab(self.individuals_b)

        combined = table_a + table_b
        if combined.sum() < 2:
            return float("nan")

        _, p, _, _ = chi2_contingency(combined + 1e-10)
        return float(p)

    def compute_joint_chi_sq(self) -> dict[str, float]:
        pairs = self.scheme.joint_pairs if self.scheme is not None else JOINT_PAIRS
        result = {}
        for attr_x, attr_y in pairs:
            key = f"{attr_x}_x_{attr_y}"
            result[key] = self._joint_chi_sq(attr_x, attr_y)
        return result

    # --- Individual coherence ----------------------------------------------

    def compute_coherence(self) -> dict[str, Any]:
        # Build joint probability table from pop_a for
        # (age_group, education_level, employment_status)
        coherence_attrs = self.scheme.coherence_attributes if self.scheme is not None else COHERENCE_ATTRIBUTES
        threshold = self.scheme.coherence_threshold if self.scheme is not None else COHERENCE_THRESHOLD
        tuple_counts: Counter = Counter()
        for ind in self.individuals_a:
            key = tuple(attr_value(ind, a) for a in coherence_attrs)
            if None not in key:
                tuple_counts[key] += 1

        total = sum(tuple_counts.values()) or 1
        joint_probs = {k: v / total for k, v in tuple_counts.items()}

        flagged = []
        n_plausible = 0
        for ind in self.individuals_b:
            key = tuple(attr_value(ind, a) for a in coherence_attrs)
            if None in key:
                prob = 0.0
            else:
                prob = joint_probs.get(key, 0.0)

            if prob >= threshold:
                n_plausible += 1
            else:
                flagged.append({
                    "id": ind.get("id"),
                    "age_group": attr_value(ind, "age_group"),
                    "education_level": ind.get("education_level"),
                    "employment_status": ind.get("employment_status"),
                    "probability": round(prob, 6),
                })

        score = n_plausible / self.n_b if self.n_b > 0 else 0.0
        return {
            "score": round(score, 4),
            "n_plausible": n_plausible,
            "n_total": self.n_b,
            "flagged": flagged,
        }

    # --- Report generation -------------------------------------------------

    def generate_report(self) -> dict[str, Any]:
        meta_a = self.pop_a.get("metadata", {})
        meta_b = self.pop_b.get("metadata", {})

        marginals = self.compute_marginals()
        joint_chi_sq = self.compute_joint_chi_sq()
        coherence = self.compute_coherence()

        marginals_clean = {
            attr: {
                "chi_sq_p": m["chi_sq_p"],
                "kl_divergence": m["kl_divergence"],
                "tv_distance": m["tv_distance"],
                "max_diff": m["max_diff"],
                **({"unmapped": m["unmapped"]} if m["unmapped"] else {}),
                **({"unknown_count_a": m["unknown_count_a"]} if m.get("unknown_count_a") else {}),
                **({"unknown_count_b": m["unknown_count_b"]} if m.get("unknown_count_b") else {}),
            }
            for attr, m in marginals.items()
        }

        return {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "population_a": {
                    "source": meta_a.get("source", "unknown"),
                    "n": self.n_a,
                },
                "population_b": {
                    "source": meta_b.get("source", "unknown"),
                    "n": self.n_b,
                },
            },
            "marginals": marginals_clean,
            "joint_chi_sq": joint_chi_sq,
            "coherence": coherence,
        }

    def print_summary(self, file_a: str, file_b: str) -> None:
        if self.n_b < 5:
            print(
                f"WARNING: Population B has only {self.n_b} individuals"
                " -- chi-squared results are unreliable (n < 5).\n"
            )

        marginals = self.compute_marginals()
        joint_chi_sq = self.compute_joint_chi_sq()
        coherence = self.compute_coherence()

        print("==== Population Comparison Report ====")
        print(f"Population A: {file_a} (n={self.n_a})")
        print(f"Population B: {file_b} (n={self.n_b})")
        print()
        print("--- Marginal Distributions ---")
        header = f"{'Attribute':<26} {'Chi-sq p':<12} {'KL div':<10} {'TV dist':<10} {'Max diff'}"
        print(header)
        print("-" * 70)
        for attr, m in marginals.items():
            p = m["chi_sq_p"]
            sig = " *" if not np.isnan(p) and p < 0.05 else "  "
            p_str = f"{p:.3f}{sig}" if not np.isnan(p) else "  nan  "
            row = (
                f"{attr:<26} {p_str:<12} {m['kl_divergence']:<10.3f} "
                f"{m['tv_distance']:<10.3f} {m['max_diff']:.3f}"
            )
            print(row)
            if m["unmapped"]:
                print(f"  {'':24} (unmapped categories in B: {', '.join(str(u) for u in m['unmapped'])})")
            if m.get("unknown_count_b", 0) > 0:
                pct = m["unknown_count_b"] / self.n_b * 100
                print(f"  {'':24} (Non-standard label in B: {m['unknown_count_b']} / {self.n_b} = {pct:.1f}%)")
        print()
        print("(* = significant divergence at p < 0.05)")
        print()
        print("--- Joint Distribution Coherence ---")
        label_map = {
            "age_group_x_education_level": "age x education",
            "age_group_x_employment_status": "age x employment",
            "education_level_x_employment_status": "education x employment",
        }
        for key, p in joint_chi_sq.items():
            label = label_map.get(key, key)
            p_str = f"{p:.3f}" if not np.isnan(p) else "nan"
            print(f"  {label:<28} chi-sq p = {p_str}")
        print()
        print("--- Individual Coherence ---")
        pct = coherence["score"] * 100
        print(f"Coherence score: {pct:.1f}% ({coherence['n_plausible']}/{coherence['n_total']} individuals plausible)")
        if coherence["flagged"]:
            print("Flagged individuals:")
            for ind in coherence["flagged"]:
                print(
                    f"  - ID {ind['id']}: (age_group={ind['age_group']}, "
                    f"employment_status={ind['employment_status']}) -- p = {ind['probability']:.4f}"
                )
        else:
            print("  No individuals flagged.")


# ------------------------------------------------------------------
# CSV summary export
# ------------------------------------------------------------------

def write_csv_summary(report: dict, output_path: Path | str) -> None:
    """Write one row per marginal attribute to a CSV file."""
    marginals = report.get("marginals", {})
    output_path = Path(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "attribute", "chi_sq_p", "kl_divergence", "tv_distance",
                "max_diff", "unmapped_categories", "unknown_count_a",
                "unknown_count_b",
            ],
        )
        writer.writeheader()
        for attr, m in marginals.items():
            unmapped = m.get("unmapped", [])
            writer.writerow({
                "attribute": attr,
                "chi_sq_p": m["chi_sq_p"],
                "kl_divergence": m["kl_divergence"],
                "tv_distance": m["tv_distance"],
                "max_diff": m["max_diff"],
                "unmapped_categories": len(unmapped),
                "unknown_count_a": m.get("unknown_count_a", 0),
                "unknown_count_b": m.get("unknown_count_b", 0),
            })

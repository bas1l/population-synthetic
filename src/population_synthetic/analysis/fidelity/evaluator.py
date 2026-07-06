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

from population_synthetic.analysis.fidelity.scheme import ComparisonScheme
from population_synthetic.generators.real.helpers import age_to_group

# The comparison axis (attributes, categories, joint pairs, coherence attributes,
# coherence threshold) is not defined here: it is the single source of truth in the
# per-country config, loaded into a ``ComparisonScheme`` (see ``scheme.load_scheme``).
# There is deliberately no in-code default to fall back to -- ``StatisticalEvaluator``
# requires a scheme and fails loudly without one (config is authoritative).


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
    def __init__(self, pop_a: dict, pop_b: dict, scheme: ComparisonScheme):
        if scheme is None:
            raise ValueError(
                "StatisticalEvaluator requires a ComparisonScheme (the comparison axis "
                "lives in config, loaded via scheme.load_scheme); there is no in-code default."
            )
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

        if attr in self.scheme.categories:
            # Scheme-driven: the comparison axis is exactly the DB-grounded category
            # set, so values the real population never emits cannot appear, and synthetic-only
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
        attrs = self.scheme.attributes
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
        pairs = self.scheme.joint_pairs
        result = {}
        for attr_x, attr_y in pairs:
            key = f"{attr_x}_x_{attr_y}"
            result[key] = self._joint_chi_sq(attr_x, attr_y)
        return result

    # --- Individual coherence ----------------------------------------------

    def compute_coherence(self) -> dict[str, Any]:
        # Build joint probability table from pop_a for
        # (age_group, education_level, employment_status)
        coherence_attrs = self.scheme.coherence_attributes
        threshold = self.scheme.coherence_threshold
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

    # --- Multivariate / joint fidelity -------------------------------------

    def compute_multivariate(self) -> dict[str, Any]:
        """Assemble the ``multivariate`` block: C2ST, association fidelity, joint
        fidelity, and k-way combination plausibility.

        Consumes the Phase-2 scheme fields (``grounded_joint_pairs``,
        ``combination_checks``, ``c2st_config``) and the Phase-1 pure primitives in
        ``comparison.multivariate`` (imported *lazily* here: that module imports
        ``attr_value`` from this one at load time, so a top-level import would be a
        cycle).

        Degrades gracefully for a tiny/failed synthetic population B (``n_b`` small
        or zero): C2ST returns NaN AUC/p-value (balanced size below 2), joint TV
        returns NaN where a side has no in-grid mass, and combination fractions
        return NaN when ``n_b == 0`` -- no crash, mirroring the ``n_b < 5`` caveat
        the marginal path already documents.
        """
        # Lazy import to avoid the circular import (multivariate imports attr_value
        # from this module at load time).
        from population_synthetic.analysis.fidelity import multivariate

        return {
            "c2st": self._compute_c2st(multivariate),
            "association": self._compute_association(multivariate),
            "joint_fidelity": self._compute_joint_fidelity(multivariate),
            "combination_plausibility": self._compute_combination_plausibility(),
        }

    def _compute_c2st(self, multivariate: Any) -> dict[str, Any]:
        """Run the classifier two-sample test on the one-hot-encoded populations.

        Uses ``scheme.c2st_config`` when present; falls back to documented defaults
        (folds=5, method="auto", seed=0) when the config omits the ``c2st`` block --
        no baked-in distribution, just backend tuning. The primitive balances the
        classes by subsampling and returns NaN for a balanced size below 2.
        """
        cfg = self.scheme.c2st_config
        folds = cfg.folds if cfg is not None else 5
        method = cfg.method if cfg is not None else "auto"
        seed = cfg.seed if cfg is not None else 0

        x_real = multivariate.one_hot_encode(self.individuals_a, self.scheme)
        x_syn = multivariate.one_hot_encode(self.individuals_b, self.scheme)
        result = multivariate.c2st(x_real, x_syn, method=method, folds=folds, seed=seed)
        return {
            "auc": result["auc"],
            "p_value": result["p_value"],
            "method": result["method"],
            "balanced_n": result["balanced_n"],
        }

    def _compute_association(self, multivariate: Any) -> dict[str, Any]:
        """Pairwise Cramer's V fidelity between the two populations.

        Reports per shared attribute pair ``v_real``/``v_syn``/``abs_delta_v`` plus
        the summary ``mean_abs_delta_v`` and ``frobenius_norm`` of the |Delta V|
        vector. Cramer's V is defined (0.0) for degenerate tables, so a tiny B never
        raises here.
        """
        attrs = self.scheme.attributes
        v_real = multivariate.association_matrix(self.individuals_a, attrs, self.scheme)
        v_syn = multivariate.association_matrix(self.individuals_b, attrs, self.scheme)

        pairs: list[dict[str, Any]] = []
        deltas: list[float] = []
        for key in v_real:  # both maps share the same ordered pair keys
            attr_x, attr_y = key
            vr = v_real[key]
            vs = v_syn[key]
            delta = abs(vr - vs)
            deltas.append(delta)
            pairs.append({
                "attr_x": attr_x,
                "attr_y": attr_y,
                "v_real": round(vr, 6),
                "v_syn": round(vs, 6),
                "abs_delta_v": round(delta, 6),
            })

        if deltas:
            mean_abs = float(np.mean(deltas))
            frobenius = float(np.sqrt(np.sum(np.square(deltas))))
        else:
            mean_abs = float("nan")
            frobenius = float("nan")

        return {
            "pairs": pairs,
            "mean_abs_delta_v": round(mean_abs, 6),
            "frobenius_norm": round(frobenius, 6),
        }

    def _compute_joint_fidelity(self, multivariate: Any) -> dict[str, Any]:
        """Per-pair joint total-variation distance with the config grounding flag.

        Iterates ``scheme.grounded_joint_pairs`` (which carries both the grounded and
        the non-grounded pairs, so the paper does not over-claim); each entry reports
        the joint TV, the ``grounded`` verdict, and the ``basis`` audit note. Joint TV
        is NaN when either side has no in-grid observations.
        """
        pairs: list[dict[str, Any]] = []
        for gp in self.scheme.grounded_joint_pairs:
            attr_x, attr_y = gp.pair
            tv = multivariate.joint_tv(self.individuals_a, self.individuals_b, attr_x, attr_y, self.scheme)
            pairs.append({
                "attr_x": attr_x,
                "attr_y": attr_y,
                "joint_tv": tv if np.isnan(tv) else round(tv, 6),
                "grounded": gp.grounded,
                "basis": gp.basis,
            })
        return {"pairs": pairs}

    def _compute_combination_plausibility(self) -> dict[str, Any]:
        """Generalise the coherence check to each configured k-way combination set.

        Reuses the ``compute_coherence`` joint-probability-table logic: build the real
        (population A) joint over the check's attribute tuple, then classify each B
        individual as impossible (zero real support, incl. a tuple with a missing
        value) or rare (support below the check's threshold). Fractions are over
        ``n_b`` and NaN when B is empty.
        """
        checks: list[dict[str, Any]] = []
        for check in self.scheme.combination_checks:
            attrs = check.attributes
            threshold = check.threshold

            tuple_counts: Counter = Counter()
            for ind in self.individuals_a:
                key = tuple(attr_value(ind, a) for a in attrs)
                if None not in key:
                    tuple_counts[key] += 1
            total = sum(tuple_counts.values()) or 1
            joint_probs = {k: v / total for k, v in tuple_counts.items()}

            n_impossible = 0
            n_rare = 0
            n_plausible = 0
            for ind in self.individuals_b:
                key = tuple(attr_value(ind, a) for a in attrs)
                prob = 0.0 if None in key else joint_probs.get(key, 0.0)
                if prob <= 0.0:
                    n_impossible += 1
                elif prob < threshold:
                    n_rare += 1
                else:
                    n_plausible += 1

            if self.n_b > 0:
                frac_impossible = round(n_impossible / self.n_b, 6)
                frac_rare = round(n_rare / self.n_b, 6)
            else:
                frac_impossible = float("nan")
                frac_rare = float("nan")

            checks.append({
                "attributes": list(attrs),
                "k": check.k,
                "threshold": threshold,
                "n_total": self.n_b,
                "n_impossible": n_impossible,
                "n_rare": n_rare,
                "n_plausible": n_plausible,
                "fraction_impossible": frac_impossible,
                "fraction_rare": frac_rare,
            })
        return {"checks": checks}

    # --- Report generation -------------------------------------------------

    def generate_report(self) -> dict[str, Any]:
        meta_a = self.pop_a.get("metadata", {})
        meta_b = self.pop_b.get("metadata", {})

        marginals = self.compute_marginals()
        joint_chi_sq = self.compute_joint_chi_sq()
        coherence = self.compute_coherence()
        multivariate = self.compute_multivariate()

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
            "multivariate": multivariate,
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
        multivariate = self.compute_multivariate()

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
        print()
        self._print_multivariate_summary(multivariate)

    def _print_multivariate_summary(self, multivariate: dict[str, Any]) -> None:
        """Print the short multivariate section (C2ST, association, joint, k-way)."""
        print("--- Multivariate / Joint Fidelity ---")

        c2st = multivariate["c2st"]
        auc = c2st["auc"]
        auc_str = f"{auc:.3f}" if not np.isnan(auc) else "nan"
        p = c2st["p_value"]
        p_str = f"{p:.3f}" if not np.isnan(p) else "nan"
        print(
            f"C2ST ({c2st['method']}): AUC = {auc_str}, p = {p_str}, "
            f"balanced n = {c2st['balanced_n']} (0.5 = indistinguishable joint)"
        )

        assoc = multivariate["association"]
        mean_dv = assoc["mean_abs_delta_v"]
        frob = assoc["frobenius_norm"]
        mean_str = f"{mean_dv:.4f}" if not np.isnan(mean_dv) else "nan"
        frob_str = f"{frob:.4f}" if not np.isnan(frob) else "nan"
        print(
            f"Association (Cramer's V): mean |dV| = {mean_str}, "
            f"Frobenius = {frob_str} over {len(assoc['pairs'])} pairs"
        )

        joint_pairs = multivariate["joint_fidelity"]["pairs"]
        if joint_pairs:
            print("Joint TV per pair:")
            for jp in joint_pairs:
                tv = jp["joint_tv"]
                tv_str = f"{tv:.3f}" if not np.isnan(tv) else "nan"
                tag = "grounded" if jp["grounded"] else "reference"
                print(f"  {jp['attr_x']} x {jp['attr_y']:<20} TV = {tv_str}  [{tag}]")

        checks = multivariate["combination_plausibility"]["checks"]
        for chk in checks:
            fi = chk["fraction_impossible"]
            fr = chk["fraction_rare"]
            fi_str = f"{fi:.3f}" if not np.isnan(fi) else "nan"
            fr_str = f"{fr:.3f}" if not np.isnan(fr) else "nan"
            label = " x ".join(chk["attributes"])
            print(f"Combination ({label}, k={chk['k']}): impossible = {fi_str}, rare = {fr_str}")


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


def write_association_csv(report: dict, output_path: Path | str) -> None:
    """Write one row per attribute pair from the multivariate association block.

    Mirrors :func:`write_csv_summary` but emits the pairwise Cramer's V fidelity
    (``v_real``/``v_syn``/``abs_delta_v``). A report without a ``multivariate`` block
    (an old pre-Phase-3 report) writes a header-only file rather than raising, so the
    caller stays additive.
    """
    pairs = report.get("multivariate", {}).get("association", {}).get("pairs", [])
    output_path = Path(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["attr_x", "attr_y", "v_real", "v_syn", "abs_delta_v"],
        )
        writer.writeheader()
        for pair in pairs:
            writer.writerow({
                "attr_x": pair["attr_x"],
                "attr_y": pair["attr_y"],
                "v_real": pair["v_real"],
                "v_syn": pair["v_syn"],
                "abs_delta_v": pair["abs_delta_v"],
            })


# ------------------------------------------------------------------
# Multivariate metric CSV exports (C2ST, grounded joint TV, k-way)
# ------------------------------------------------------------------
#
# Each mirrors :func:`write_association_csv`: a pure dict -> file writer that
# reads a single report block, writes one row per entity, and degrades to a
# header-only file (no raise) when the block is absent -- so a pre-multivariate
# report, or a tiny/failed synthetic population whose block is missing, never
# breaks the caller.


def write_c2st_csv(report: dict, output_path: Path | str) -> None:
    """Write the single C2ST readout row (auc / p_value / method / balanced_n).

    Reads ``report["multivariate"]["c2st"]``. A report without a C2ST block
    writes a header-only file.
    """
    c2st = report.get("multivariate", {}).get("c2st")
    output_path = Path(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["auc", "p_value", "method", "balanced_n"],
        )
        writer.writeheader()
        if c2st:
            writer.writerow({
                "auc": c2st.get("auc"),
                "p_value": c2st.get("p_value"),
                "method": c2st.get("method"),
                "balanced_n": c2st.get("balanced_n"),
            })


def write_joint_fidelity_csv(report: dict, output_path: Path | str) -> None:
    """Write one row per grounded-joint-TV pair (attr_x/attr_y/joint_tv/grounded/basis).

    Reads ``report["multivariate"]["joint_fidelity"]["pairs"]``. A report without
    the block writes a header-only file.
    """
    pairs = report.get("multivariate", {}).get("joint_fidelity", {}).get("pairs", [])
    output_path = Path(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["attr_x", "attr_y", "joint_tv", "grounded", "basis"],
        )
        writer.writeheader()
        for pair in pairs:
            writer.writerow({
                "attr_x": pair["attr_x"],
                "attr_y": pair["attr_y"],
                "joint_tv": pair["joint_tv"],
                "grounded": pair["grounded"],
                "basis": pair["basis"],
            })


def write_combination_plausibility_csv(report: dict, output_path: Path | str) -> None:
    """Write one row per k-way combination-plausibility check.

    Reads ``report["multivariate"]["combination_plausibility"]["checks"]``. The
    ``attributes`` tuple is serialised as a ``" | "``-joined string. A report
    without the block writes a header-only file.
    """
    checks = report.get("multivariate", {}).get("combination_plausibility", {}).get("checks", [])
    output_path = Path(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "attributes", "k", "threshold", "n_total", "n_impossible",
                "n_rare", "n_plausible", "fraction_impossible", "fraction_rare",
            ],
        )
        writer.writeheader()
        for check in checks:
            writer.writerow({
                "attributes": " | ".join(check["attributes"]),
                "k": check["k"],
                "threshold": check["threshold"],
                "n_total": check["n_total"],
                "n_impossible": check["n_impossible"],
                "n_rare": check["n_rare"],
                "n_plausible": check["n_plausible"],
                "fraction_impossible": check["fraction_impossible"],
                "fraction_rare": check["fraction_rare"],
            })


# ------------------------------------------------------------------
# Legacy metric CSV exports (joint chi-squared, coherence)
# ------------------------------------------------------------------
#
# The report labels families 2-3 "legacy"; these writers are kept in their own
# section so the pair can be dropped in one edit if the legacy tier is retired.


def write_joint_chi_sq_csv(report: dict, output_path: Path | str) -> None:
    """Write one row per configured joint-chi-squared pair (pair/attr_x/attr_y/chi_sq_p).

    Reads the ``report["joint_chi_sq"]`` map of ``"{attr_x}_x_{attr_y}" -> p``.
    The key is split on ``"_x_"`` only when that yields exactly two parts;
    otherwise the two attribute columns are left blank and ``pair`` keeps the raw
    key. An absent block writes a header-only file.
    """
    joint = report.get("joint_chi_sq", {})
    output_path = Path(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["pair", "attr_x", "attr_y", "chi_sq_p"],
        )
        writer.writeheader()
        for key, p in joint.items():
            parts = key.split("_x_")
            attr_x, attr_y = (parts[0], parts[1]) if len(parts) == 2 else ("", "")
            writer.writerow({
                "pair": key,
                "attr_x": attr_x,
                "attr_y": attr_y,
                "chi_sq_p": p,
            })


def write_coherence_csv(report: dict, output_path: Path | str) -> None:
    """Write one row per flagged individual from the coherence block.

    Reads ``report["coherence"]["flagged"]`` (the JSON-only detail; the aggregate
    ``score`` already surfaces in the batch ``comparison_summary.json`` and the
    performance CSV). An absent block or an empty flagged list writes a
    header-only file.
    """
    flagged = report.get("coherence", {}).get("flagged", [])
    output_path = Path(output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id", "age_group", "education_level",
                "employment_status", "probability",
            ],
        )
        writer.writeheader()
        for ind in flagged:
            writer.writerow({
                "id": ind.get("id"),
                "age_group": ind.get("age_group"),
                "education_level": ind.get("education_level"),
                "employment_status": ind.get("employment_status"),
                "probability": ind.get("probability"),
            })

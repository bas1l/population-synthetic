"""Sample-size / statistical-power analysis for a categorical population attribute.

For a chosen country and one (or all) of its comparison attributes, this script answers:
**how many generated samples (N) are needed to estimate each category's probability
precisely enough to compare the sampled distribution against the "true" probabilities?**

A K-category multinomial's requirement is dominated by the *rarest* category, so the
report surfaces that explicitly and reports three families of thresholds:

1. Per-category estimation precision (Wald N = z^2 p(1-p) / E^2), single and
   Bonferroni-simultaneous across the K categories.
2. Expected-count floors for the rarest cell (N = k / p_min) that govern when the
   normal approximation and the chi-square goodness-of-fit test become valid.
3. Chi-square goodness-of-fit power over df = K-1 (N = lambda / w^2) for a range of
   Cohen's w effect sizes and target powers.

The "true" probabilities are estimated empirically by tallying the attribute over a
reference population. Both the reference file and the mapping directory are resolved
from the country's axis YAML (`config/synthetic/axes/countries/<country>.yaml`) -- no
hardcoded paths. Attributes listed under the mapping index's `deprecated_attributes`
are skipped by default (they are excluded from analysis), matching the comparison
pipeline.

Examples
--------
    # Every (non-deprecated) attribute for Sweden, consolidated report:
    python scripts/analyze/attribute_power_analysis.py --country swedish

    # A single attribute:
    python scripts/analyze/attribute_power_analysis.py --country swedish --attribute region

Requires scipy; uses statsmodels for a GOF-power cross-check when available.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path

import yaml
from scipy.stats import ncx2, norm

REPO_ROOT = Path(__file__).resolve().parents[2]
COUNTRY_AXIS_DIR = REPO_ROOT / "config" / "synthetic" / "axes" / "countries"

# A config value set that looks like numeric ranges ("18-24", "75-85", "75+") marks a
# derived numeric-bin attribute (e.g. age_group), tallied by binning a raw integer field.
_RANGE_RE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)|(\+))\s*$")


def resolve_country(country: str, population_override: str | None, mappings_override: str | None):
    """Resolve (reference-population path, mapping dir) from the country axis YAML."""
    axis_path = COUNTRY_AXIS_DIR / f"{country}.yaml"
    if not axis_path.is_file():
        raise FileNotFoundError(f"No country axis YAML for {country!r}: {axis_path}")
    with open(axis_path, encoding="utf-8") as fh:
        axis = yaml.safe_load(fh)
    params = axis.get("parameters", {})

    pop_rel = population_override or params.get("reference")
    if not pop_rel:
        raise KeyError(f"{axis_path} has no `parameters.reference` and no --population override given")
    map_rel = mappings_override or params.get("mappings")
    if not map_rel:
        raise KeyError(f"{axis_path} has no `parameters.mappings` and no --mappings override given")

    pop_path = (REPO_ROOT / pop_rel).resolve()
    map_dir = (REPO_ROOT / map_rel).resolve()
    if not pop_path.is_file():
        raise FileNotFoundError(f"Reference population not found: {pop_path}")
    if not (map_dir / "_index.json").is_file():
        raise FileNotFoundError(f"Mapping index not found: {map_dir / '_index.json'}")
    return pop_path, map_dir


def load_index(map_dir: Path):
    with open(map_dir / "_index.json", encoding="utf-8") as fh:
        index = json.load(fh)
    attributes = index["attributes"]  # ordered dict: name -> filename
    deprecated = list(index.get("deprecated_attributes", []))
    return attributes, deprecated


def load_individuals(pop_path: Path) -> list[dict]:
    with open(pop_path, encoding="utf-8") as fh:
        pop = json.load(fh)
    if isinstance(pop, list):
        return pop
    if isinstance(pop, dict):
        for key in ("population", "individuals", "people", "records", "data"):
            if isinstance(pop.get(key), list):
                return pop[key]
        # fall back to the first list-valued entry
        for value in pop.values():
            if isinstance(value, list):
                return value
    raise ValueError(f"Could not locate a list of individuals in {pop_path}")


def _label(value):
    """Extract a category label from an attribute value.

    Handles three shapes: a scalar; a `{'label': ...}` dict; and a *composite* dict whose
    sub-fields each carry their own label (e.g. employment_type's `attachment` x `hours`),
    which is joined into one combined category, matching its canonical grid resolution.
    """
    if not isinstance(value, dict):
        return value
    if "label" in value:
        return value["label"]
    parts = []
    for sub in value.values():
        if isinstance(sub, dict) and "label" in sub:
            parts.append(str(sub["label"]))
        elif sub is not None and not isinstance(sub, dict):
            parts.append(str(sub))
    return " | ".join(parts) if parts else None


def _parse_ranges(values: list[str]):
    """Return [(lo, hi_inclusive_or_None, label), ...] if every value is a numeric range, else None."""
    parsed = []
    for label in values:
        m = _RANGE_RE.match(str(label))
        if not m:
            return None
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else None  # None => open-ended ("75+")
        parsed.append((lo, hi, label))
    return parsed


def tally_attribute(attr: str, individuals: list[dict], config_values: list[str]):
    """Tally realized category labels for *attr*, returning (Counter, mode) where mode is
    'direct' (attribute field present) or 'derived:<field>' (numeric-bin derivation)."""
    present = any(attr in ind for ind in individuals)
    if present:
        counts = collections.Counter(_label(ind.get(attr)) for ind in individuals if ind.get(attr) is not None)
        return counts, "direct"

    # Attribute field absent: attempt numeric-bin derivation (e.g. age_group from `age`).
    ranges = _parse_ranges(config_values)
    if ranges is not None:
        raw_field = next((f for f in ("age",) if any(f in ind for ind in individuals)), None)
        if raw_field is not None:
            counts = collections.Counter()
            for ind in individuals:
                raw = ind.get(raw_field)
                if raw is None:
                    continue
                try:
                    x = int(raw)
                except (TypeError, ValueError):
                    continue
                for lo, hi, label in ranges:
                    if x >= lo and (hi is None or x <= hi):
                        counts[label] += 1
                        break
            return counts, f"derived:{raw_field}"
    return collections.Counter(), "absent"


# --------------------------- power / sample-size math ---------------------------


def n_wald(p: float, error: float, z: float) -> float:
    return z * z * p * (1.0 - p) / (error * error)


def lambda_for_power(crit: float, df: int, power: float) -> float:
    """Noncentrality lambda s.t. a noncentral chi-square(df, lambda) exceeds *crit* with prob *power*."""
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if ncx2.sf(crit, df, mid) < power:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def analyze_attribute(attr, counts, mode, config_values, args, sm_power):
    """Compute all sample-size thresholds for one attribute and return a result dict."""
    n_total = sum(counts.values())
    k = len(counts)
    if k < 2 or n_total == 0:
        return {"attr": attr, "skipped": f"only {k} realized categor(y/ies), n={n_total}", "mode": mode}

    p = {name: c / n_total for name, c in counts.items()}
    pmin_name = min(p, key=p.get)
    pmax_name = max(p, key=p.get)
    p_min, p_max = p[pmin_name], p[pmax_name]

    z95 = norm.ppf(0.975)
    z_bonf = norm.ppf(1.0 - args.alpha / (2.0 * k))

    precision = {
        "abs": {E: (math.ceil(n_wald(0.5, E, z95)), math.ceil(n_wald(p_min, E, z95))) for E in args.abs_errors},
        "rel_single": {r: math.ceil(n_wald(p_min, r * p_min, z95)) for r in args.rel_precisions},
        "rel_bonf": {r: math.ceil(n_wald(p_min, r * p_min, z_bonf)) for r in args.rel_precisions},
    }
    expected_counts = {c: math.ceil(c / p_min) for c in (5, 10, 15)}

    df = k - 1
    crit = ncx2.ppf(1.0 - args.alpha, df, 0)
    gof = {}
    for power in args.powers:
        lam = lambda_for_power(crit, df, power)
        row = {}
        for w in args.effect_sizes:
            manual = math.ceil(lam / (w * w))
            cross = None
            if sm_power is not None:
                try:
                    cross = math.ceil(sm_power.solve_power(effect_size=w, nobs=None, alpha=args.alpha, power=power, n_bins=k))
                except Exception:
                    cross = None
            row[w] = (manual, cross)
        gof[power] = (lam, row)

    # Binding criteria -> recommendations.
    chi2_floor = expected_counts[5]                         # all expected >= 5
    wald_ok = expected_counts[15]                           # rarest cell normal CI trustworthy
    small_w = min(args.effect_sizes)
    max_power = max(args.powers)
    gof_small = math.ceil(gof[max_power][0] / (small_w * small_w))
    recommended = max(wald_ok, gof_small)
    high_precision = precision["rel_single"].get(0.20) or max(precision["rel_single"].values())

    return {
        "attr": attr, "mode": mode, "n_total": n_total, "k": k,
        "config_k": len(config_values),
        "not_in_config": sorted(set(map(str, counts)) - set(map(str, config_values))),
        "config_not_seen": sorted(set(map(str, config_values)) - set(map(str, counts))),
        "p_min": p_min, "pmin_name": pmin_name, "pmin_count": counts[pmin_name],
        "p_max": p_max, "pmax_name": pmax_name,
        "z95": z95, "z_bonf": z_bonf,
        "precision": precision, "expected_counts": expected_counts,
        "df": df, "crit": crit, "gof": gof,
        "chi2_floor": chi2_floor, "wald_ok": wald_ok, "gof_small": gof_small,
        "recommended": recommended, "high_precision": high_precision, "small_w": small_w, "max_power": max_power,
        "dist": sorted(p.items(), key=lambda kv: -kv[1]),
    }


# --------------------------------- reporting ---------------------------------


def print_attribute_report(r):
    print(f"\n{'=' * 78}\n## {r['attr']}", end="")
    if r.get("skipped"):
        print(f"  -- SKIPPED ({r['skipped']}; mode={r['mode']})")
        return
    print(f"   (K={r['k']} realized / {r['config_k']} in config, n={r['n_total']}, tally mode: {r['mode']})")
    if r["k"] != r["config_k"]:
        print(f"   WARNING: {r['k']} realized categories != {r['config_k']} config values "
              f"-- raw labels may collapse/expand under mapping; power computed on realized categories.")
    elif r["not_in_config"]:
        print("   note: reference stores raw pre-mapping labels (K matches config; canonical relabel is 1:1).")

    print(f"\n   Rarest category (binds everything): {r['pmin_name']}  "
          f"p_min={r['p_min']:.5f}  (count={r['pmin_count']})")
    print(f"   Most common:                        {r['pmax_name']}  p_max={r['p_max']:.5f}")

    print("\n   -- Per-category precision  (Wald N = z^2 p(1-p)/E^2) --")
    for E, (worst, at_min) in r["precision"]["abs"].items():
        print(f"      abs E={E:<6}: worst-case p=0.5 -> N={worst:>9,}   rarest p_min -> N={at_min:>9,}")
    for rel, n in r["precision"]["rel_single"].items():
        print(f"      rarest +/-{int(rel * 100)}% relative (single 95% CI):        N={n:>9,}")
    for rel, n in r["precision"]["rel_bonf"].items():
        print(f"      rarest +/-{int(rel * 100)}% relative (Bonferroni, all {r['k']} joint): N={n:>9,}")

    print("\n   -- Expected-count floors for rarest cell  (N = k/p_min) --")
    for c, n in r["expected_counts"].items():
        tag = {5: "chi-square GOF validity", 10: "normal CI marginal", 15: "normal CI trustworthy"}[c]
        print(f"      rarest expected = {c:>2} counts: N={n:>8,}   ({tag})")

    print(f"\n   -- Goodness-of-fit power  (chi-square, df={r['df']}, alpha=0.05; crit={r['crit']:.3f}) --")
    for power, (lam, row) in r["gof"].items():
        print(f"      power={power}  (lambda={lam:.3f}):")
        for w, (manual, cross) in row.items():
            extra = f"  [statsmodels: {cross:,}]" if cross is not None else ""
            print(f"         w={w} -> N={manual:>8,}{extra}")

    print("\n   -- Bottom line --")
    print(f"      min defensible (all expected >= 5):           N ~= {r['chi2_floor']:>7,}")
    print(f"      recommended working target:                   N ~= {r['recommended']:>7,}  "
          f"(max of rarest-cell valid {r['wald_ok']:,} and small-effect GOF power {r['gof_small']:,})")
    print(f"      high per-estimate precision (rarest +/-20%):  N ~= {r['high_precision']:>7,}")


def print_summary(results):
    print(f"\n{'=' * 78}\n## SUMMARY  (binding = rarest category)\n")
    header = f"{'Attribute':<22}{'K':>4}{'rarest p_min':>14}{'rarest cat':>22}{'min N':>9}{'rec. N':>9}{'±20% N':>10}"
    print(header)
    print("-" * len(header))
    for r in results:
        if r.get("skipped"):
            print(f"{r['attr']:<22}{'--':>4}{'--':>14}{'(skipped)':>22}{'--':>9}{'--':>9}{'--':>10}")
            continue
        cat = (r["pmin_name"] or "")[:20]
        print(f"{r['attr']:<22}{r['k']:>4}{r['p_min']:>14.5f}{cat:>22}"
              f"{r['chi2_floor']:>9,}{r['recommended']:>9,}{r['high_precision']:>10,}")
    print("\nmin N     = all rarest-cell expected counts >= 5 (chi-square GOF validity floor)")
    print("rec. N    = max(rarest cell expected>=15, small-effect GOF power at highest target power)")
    print("+/-20% N  = single-CI N to pin the rarest category's own probability to +/-20% relative")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", default="swedish", help="country axis id (default: swedish)")
    ap.add_argument("--attribute", default=None, help="single attribute; omit to analyze all non-deprecated")
    ap.add_argument("--population", default=None, help="override reference population path (repo-relative or absolute)")
    ap.add_argument("--mappings", default=None, help="override mapping dir (repo-relative or absolute)")
    ap.add_argument("--include-deprecated", action="store_true", help="also analyze deprecated attributes")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--powers", type=float, nargs="+", default=[0.80, 0.90])
    ap.add_argument("--effect-sizes", type=float, nargs="+", default=[0.1, 0.3, 0.5], help="Cohen's w for GOF power")
    ap.add_argument("--abs-errors", type=float, nargs="+", default=[0.01, 0.005], help="absolute CI half-widths")
    ap.add_argument("--rel-precisions", type=float, nargs="+", default=[0.10, 0.20], help="relative CI half-widths on p_min")
    args = ap.parse_args()

    # Report contains Swedish labels (å, ö) and math glyphs; force UTF-8 so a cp1252
    # console does not crash the run.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    pop_path, map_dir = resolve_country(args.country, args.population, args.mappings)
    attributes, deprecated = load_index(map_dir)
    individuals = load_individuals(pop_path)

    if args.attribute:
        if args.attribute not in attributes:
            raise SystemExit(f"Attribute {args.attribute!r} not in index; available: {list(attributes)}")
        selected = [args.attribute]
    else:
        selected = [a for a in attributes if args.include_deprecated or a not in deprecated]

    try:
        from statsmodels.stats.power import GofChisquarePower
        sm_power = GofChisquarePower()
    except Exception:
        sm_power = None

    print(f"Country            : {args.country}")
    print(f"Reference pop      : {pop_path}  (n={len(individuals):,})")
    print(f"Mapping dir        : {map_dir}")
    print(f"Deprecated (skipped): {deprecated if not args.include_deprecated else '(included)'}")
    print(f"Attributes analyzed: {len(selected)}")
    if sm_power is None:
        print("statsmodels not available -- GOF power via scipy noncentral-chi-square only.")

    results = []
    for attr in selected:
        with open(map_dir / attributes[attr], encoding="utf-8") as fh:
            config_values = json.load(fh).get("values", [])
        counts, mode = tally_attribute(attr, individuals, config_values)
        r = analyze_attribute(attr, counts, mode, config_values, args, sm_power)
        results.append(r)
        print_attribute_report(r)

    if len(results) > 1:
        print_summary(results)


if __name__ == "__main__":
    main()

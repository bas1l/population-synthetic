"""audit_persona_realism.py -- LLM-judgment realism audit of SCB synthetic personas.

This script does the deterministic, non-LLM halves of the audit; the realism
judgement itself is performed by per-persona subagents that Claude Code spawns
(one persona each). See the plan / rubric for the methodology.

Two modes:

  prep       Slice the first N personas out of the population JSON into per-id
             input files (inputs/persona_<id>.json) and write the realism rubric
             (rubric.md). Each subagent reads exactly one input file plus the
             rubric. Cheap, deterministic, re-runnable -- keeps persona data out
             of the orchestrator's context.

  aggregate  Read every subagent verdict (results/persona_<id>.json) and join it
             with the flattened persona attributes to emit:
               - realism_results.csv   (id + 15 attribute labels + score/flag/summary)
               - realism_report.md     (metadata, flag-rate, score distribution,
                                        flagged personas grouped by issue + full table)

No LLM calls happen in this file. The CSV/JSON handling mirrors the writer style
of population_synthetic.analysis.consistency.builder.

Usage:
    python scripts/dev/audit_persona_realism.py prep --n 300
    python scripts/dev/audit_persona_realism.py aggregate
    # optional overrides:
    python scripts/dev/audit_persona_realism.py prep --n 10000 --source <path> --out-dir <path>
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Repo-relative defaults -------------------------------------------------

_THIS = Path(__file__).resolve()
PROJECT_ROOT = _THIS.parents[2]
DEFAULT_SOURCE = (
    PROJECT_ROOT
    / "data"
    / "scb_api"
    / "scb_population_n10000_seed42_merge-status-edu_2026-07-16.json"
)
DEFAULT_OUT_DIR = (
    PROJECT_ROOT / "data" / "scb_api" / "realism_audit_n10000_seed42_2026-07-16"
)

#: The 15 persona categories, in canonical order (age is the only non-label int).
#: This audits the raw persona *data*, which retains every field, so ``birth_location``
#: stays here even though it is deprecated from the fidelity/comparison *analysis* axis
#: (via ``deprecated_attributes`` in the mapping ``_index.json``; Sweden analyzes 14 axes).
DEMOGRAPHIC_ATTRIBUTES: tuple[str, ...] = (
    "age",
    "biological_sex",
    "education_level",
    "employment_status",
    "socioeconomic_class",
    "birth_location",
    "region",
    "civil_status",
    "industry_sector",
    "employment_type",
    "housing_tenure",
    "household_size",
    "income_source",
    "birth_country_detail",
    "parental_structure",
)

#: Verdict fields each subagent must write to results/persona_<id>.json.
_VERDICT_FIELDS: tuple[str, ...] = ("id", "realism_score", "flag", "summary", "top_issues")


# --- Shared helpers ---------------------------------------------------------

def _load_population(source: Path) -> list[dict[str, Any]]:
    """Load the population file and return its ``individuals`` list, fail-fast."""
    if not source.is_file():
        raise FileNotFoundError(f"Population file not found: {source}")
    with source.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "individuals" not in data:
        raise ValueError(f"Unexpected population schema in {source}: missing 'individuals'")
    individuals = data["individuals"]
    if not isinstance(individuals, list) or not individuals:
        raise ValueError(f"Population file {source} has no individuals")
    return individuals


def _flatten(individual: dict[str, Any]) -> dict[str, Any]:
    """Flatten a persona's ``{label: ...}`` attribute objects to plain values.

    ``age`` passes through as an int; a null attribute becomes an empty string;
    every other attribute becomes its ``label``.
    """
    row: dict[str, Any] = {"id": individual["id"]}
    for attr in DEMOGRAPHIC_ATTRIBUTES:
        val = individual.get(attr)
        if attr == "age":
            row[attr] = val
        elif val is None:
            row[attr] = ""
        elif isinstance(val, dict):
            row[attr] = val.get("label", "")
        else:
            row[attr] = val
    return row


def _rubric_text() -> str:
    """The realism rubric handed to every subagent (written once as rubric.md)."""
    return _RUBRIC


# --- prep -------------------------------------------------------------------

def cmd_prep(source: Path, out_dir: Path, n: int) -> None:
    individuals = _load_population(source)
    if n > len(individuals):
        raise ValueError(f"--n {n} exceeds population size {len(individuals)}")

    inputs_dir = out_dir / "inputs"
    results_dir = out_dir / "results"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    # Personas are keyed by their own `id` field (0-based, contiguous in this file).
    by_id = {ind["id"]: ind for ind in individuals}
    written = 0
    for pid in range(n):
        if pid not in by_id:
            raise KeyError(f"Persona id {pid} missing from {source}")
        path = inputs_dir / f"persona_{pid:05d}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(by_id[pid], fh, ensure_ascii=False, indent=2)
        written += 1

    rubric_path = out_dir / "rubric.md"
    rubric_path.write_text(_rubric_text(), encoding="utf-8")

    print(f"prep: wrote {written} input files -> {inputs_dir}")
    print(f"prep: wrote rubric -> {rubric_path}")
    print(f"prep: results will be collected in -> {results_dir}")


# --- aggregate --------------------------------------------------------------

def _read_verdicts(results_dir: Path) -> dict[int, dict[str, Any]]:
    """Load every results/persona_<id>.json, keyed by int id, fail-fast on shape."""
    if not results_dir.is_dir():
        raise FileNotFoundError(f"No results directory: {results_dir}")
    verdicts: dict[int, dict[str, Any]] = {}
    for path in sorted(results_dir.glob("persona_*.json")):
        with path.open(encoding="utf-8") as fh:
            v = json.load(fh)
        missing = [k for k in ("id", "realism_score", "flag") if k not in v]
        if missing:
            raise ValueError(f"Verdict {path.name} missing fields: {missing}")
        verdicts[int(v["id"])] = v
    if not verdicts:
        raise ValueError(f"No verdicts found in {results_dir} -- run the subagents first")
    return verdicts


def _write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    fieldnames = ["id", *DEMOGRAPHIC_ATTRIBUTES, "realism_score", "flag", "summary"]
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_report(rows: list[dict[str, Any]], source: Path, out_path: Path) -> None:
    n = len(rows)
    flagged = [r for r in rows if r["flag"]]
    scores = [r["realism_score"] for r in rows if isinstance(r["realism_score"], (int, float))]
    generated_at = datetime.now(timezone.utc).isoformat()

    # Score distribution buckets.
    buckets = Counter()
    for s in scores:
        buckets[min(int(s) // 10 * 10, 90)] += 1

    # Group flagged personas by their dominant (first) issue tag.
    issue_counts: Counter[str] = Counter()
    for r in flagged:
        issues = r.get("top_issues") or []
        issue_counts[issues[0] if issues else "(unspecified)"] += 1

    lines: list[str] = []
    lines.append("# Persona realism audit report")
    lines.append("")
    lines.append(f"- **Source population:** `{source.name}`")
    lines.append(f"- **Personas analyzed:** {n}")
    lines.append(f"- **Flagged (potentially unrealistic):** {len(flagged)} "
                 f"({len(flagged) / n:.1%})" if n else "- **Flagged:** 0")
    if scores:
        lines.append(f"- **Realism score:** min {min(scores)}, "
                     f"mean {sum(scores) / len(scores):.1f}, max {max(scores)}")
    lines.append(f"- **Generated at:** {generated_at}")
    lines.append("")

    lines.append("## Score distribution")
    lines.append("")
    lines.append("| Score band | Count |")
    lines.append("|---|---|")
    for lo in range(0, 100, 10):
        lines.append(f"| {lo}-{lo + 9} | {buckets.get(lo, 0)} |")
    lines.append("")

    lines.append("## Flagged personas by dominant issue")
    lines.append("")
    if issue_counts:
        lines.append("| Issue | Count |")
        lines.append("|---|---|")
        for issue, cnt in issue_counts.most_common():
            lines.append(f"| {issue} | {cnt} |")
    else:
        lines.append("_No personas flagged._")
    lines.append("")

    lines.append("## Flagged personas")
    lines.append("")
    if flagged:
        lines.append("| id | score | age | sex | employment | civil | income | summary |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in sorted(flagged, key=lambda x: (x["realism_score"], x["id"])):
            summary = str(r.get("summary", "")).replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {r['id']} | {r['realism_score']} | {r['age']} | {r['biological_sex']} | "
                f"{r['employment_status']} | {r['civil_status']} | {r['income_source']} | {summary} |"
            )
    else:
        lines.append("_No personas flagged._")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def cmd_aggregate(source: Path, out_dir: Path) -> None:
    individuals = _load_population(source)
    by_id = {ind["id"]: ind for ind in individuals}
    verdicts = _read_verdicts(out_dir / "results")

    rows: list[dict[str, Any]] = []
    for pid in sorted(verdicts):
        if pid not in by_id:
            raise KeyError(f"Verdict id {pid} has no matching persona in {source}")
        row = _flatten(by_id[pid])
        v = verdicts[pid]
        row["realism_score"] = v["realism_score"]
        row["flag"] = bool(v["flag"])
        row["summary"] = v.get("summary", "")
        row["top_issues"] = v.get("top_issues") or []
        rows.append(row)

    csv_path = out_dir / "realism_results.csv"
    report_path = out_dir / "realism_report.md"
    _write_csv(rows, csv_path)
    _write_report(rows, source, report_path)

    n_flagged = sum(1 for r in rows if r["flag"])
    print(f"aggregate: {len(rows)} verdicts -> {csv_path}")
    print(f"aggregate: report ({n_flagged} flagged) -> {report_path}")


# --- rubric text ------------------------------------------------------------

_RUBRIC = """# Persona realism rubric

You are auditing ONE synthetic Swedish persona produced by **independent-marginal /
conditional chained sampling** from Statistics Sweden (SCB) distributions. Each
attribute reproduces its own real marginal, but many attribute PAIRS are sampled
independently. As a result, **locally-unusual-but-possible combinations occur by
design and are NOT defects.** Your job is to catch only genuine SAME-PERSON logical
impossibilities (or strong, near-impossible incoherence) -- not statistical rarity.

Default to NOT flagging. Flag only when two attributes cannot both be true of the
same real person at the same time.

## The 15 attributes

age, biological_sex, education_level, employment_status, socioeconomic_class,
birth_location, region, civil_status, industry_sector, employment_type,
housing_tenure, household_size, income_source, birth_country_detail,
parental_structure.

## What to FLAG (closed set of hard same-person impossibilities)

- **Employment <-> income_source** (the main real defect class): `Retired` +
  `wage and business income`; `Employed` + `pensions`; a non-employed status
  (`Unemployed`/`Student`/`Other`) + `wage and business income`. The declared income
  source must be consistent with the employment status.
- **Age <-> life-stage:** `employment_status=Retired` with age < 55; `civil_status`
  married/divorced/widowed with age < 18.
- **Education <-> age:** post-graduate or post-secondary-3-years-or-more attainment at
  an age too young to have realistically completed it (roughly < 24 for post-grad).
- **birth_location <-> birth_country_detail disagreement:** the two must agree
  (born in Sweden <-> Sweden; born outside the EU <-> a non-EU country; born in another
  EU state <-> an EU country).

Anything outside this closed set: do not flag. If you are unsure, do not flag.

## Explicit NON-issues -- NEVER flag these

- `employment_type` is **always null** in this dataset (the field was dropped for lack
  of a clean API source). Its absence is expected.
- `industry_sector` is null for non-employed personas (retired, student, unemployed,
  etc.). That is expected, not a defect.
- `parental_structure` is a **family-of-origin classification** (the family type the
  person grew up in), sampled **independently** of the persona's current household,
  sex, and own parenthood. It is NOT a current-household roster. Therefore:
  * "single father" for a woman / "single mother" for a man is fine.
  * "married or cohabiting natural parents" for a person who lives alone
    (`household_size=1 person`), for an elderly widow(er), or for anyone at all is fine.
  * NEVER cross-check parental_structure against household_size, civil_status, sex,
    or age.
- `household_size` vs `civil_status` (e.g. `married` living in a `1 person` household)
  is NOT a contradiction -- married-but-living-apart is real and these are independent
  marginals. Do not flag it.
- socioeconomic_class is a derived income-bracket band; do not flag it against
  income_source or employment unless it is a stark impossibility.

## Scoring guidance

- No hard impossibility -> `flag=false`, `realism_score` typically 85-100.
- One clear hard impossibility -> `flag=true`, `realism_score` typically 30-60
  depending on severity.

## Output

Write your verdict to the results file you are told to write, as JSON with exactly
these keys:
- `id` (int): the persona's id.
- `realism_score` (int 0-100): 100 = fully realistic and coherent; lower = more/worse
  coherence problems.
- `flag` (bool): true if the persona has a clear logical impossibility or a strong
  demographic implausibility; false otherwise.
- `summary` (string, 1-3 sentences): cite the specific coherence issue(s), or confirm
  the persona is coherent.
- `top_issues` (list of short strings): kebab-case issue tags in priority order, e.g.
  `["retired-with-wage-income"]`. Empty list if none.
"""


# --- CLI --------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_prep = sub.add_parser("prep", help="Slice first N personas into input files + write rubric.")
    p_prep.add_argument("--n", type=int, default=300, help="Number of personas (ids 0..N-1). Default 300.")
    p_prep.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Population JSON.")
    p_prep.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Audit output folder.")

    p_agg = sub.add_parser("aggregate", help="Join verdicts with attributes -> CSV + report.")
    p_agg.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Population JSON.")
    p_agg.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Audit output folder.")

    args = parser.parse_args()
    if args.mode == "prep":
        cmd_prep(args.source, args.out_dir, args.n)
    elif args.mode == "aggregate":
        cmd_aggregate(args.source, args.out_dir)


if __name__ == "__main__":
    main()

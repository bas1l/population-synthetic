#!/usr/bin/env python3
"""Embed a minified SCB population snapshot into the Sweden generation explorer HTML.

The explorer page ``docs/architecture/sweden-generation-explorer.html`` overlays a
single generated individual onto its conditional-sampling DAG. Browsers refuse to
``fetch()`` a sibling file when the page is opened from ``file://``, so the default
population has to travel *inside* the HTML. This dev tool reads a generated SCB
population JSON, projects each individual onto a compact array-of-arrays (16 columns),
and injects the minified payload into the HTML between two marker comments as a
``<script id="embedded-pop" type="application/json">`` island the page parses on load.

Run after regenerating the population (this snapshot is otherwise stale)::

    python scripts/dev/embed_population_in_explorer.py
    python scripts/dev/embed_population_in_explorer.py --source data/scb_api/other.json

Staleness note: the embedded snapshot is a *copy*. If the source population is
regenerated (new seed / new SCB vintage / schema change), re-run this script so the
page's default individual and summary line reflect the current data. Re-running is
idempotent -- it replaces the existing island in place rather than appending.

The injection is a pure string/regex rewrite of the HTML file; the multi-megabyte
payload is never read back for analysis. Prints the resulting HTML size and count.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "scb_api" / "scb_population_pop-10000_02.json"
DEFAULT_HTML = PROJECT_ROOT / "docs" / "architecture" / "sweden-generation-explorer.html"

# The compact column order. The row index IS the individual id (0-based).
COLUMNS = [
    "age",
    "sex_label",
    "education_level",
    "employment_status",
    "industry_sector",
    "attachment",
    "hours",
    "income_source",
    "socioeconomic_class",
    "civil_status",
    "birth_location",
    "birth_country_detail",
    "region",
    "parental_structure",
    "housing_tenure",
    "household_size",
]

START_MARKER = "<!-- EMBEDDED-POP:START -->"
END_MARKER = "<!-- EMBEDDED-POP:END -->"

DIST_START_MARKER = "<!-- EMBEDDED-DIST:START -->"
DIST_END_MARKER = "<!-- EMBEDDED-DIST:END -->"

# SPEC node id -> how the page slices the embedded source distributions.
#   field   : key into payload["conditional"] or payload["marginal"]
#   kind    : "hub" (the aggregated age_sex_group display dist),
#             "conditional" (sliced by parent key), or "marginal" (same for all)
#   parents : ordered parent *roles*; the page derives each role's value from a
#             context and joins them with "|" to key the conditional dict.
#             roles: age_group, sex, aku_edu (edu->AKU bucket via bridge),
#                    inc_emp (employment_status->income bucket), inc_age (age_group->band)
#   gate    : None, "employed" (N/A when not employed), or "foreign_born"
#             (N/A when born in Sweden)
DIST_SCHEMA: dict[str, dict] = {
    "agesex": {"field": "age_sex_group", "kind": "hub", "parents": [], "gate": None},
    "education": {"field": "education_by_age", "kind": "conditional",
                  "parents": ["age_group", "sex"], "gate": None},
    "employment": {"field": "employment_by_sex_education", "kind": "conditional",
                   "parents": ["sex", "aku_edu"], "gate": None},
    "industry": {"field": "industry_sector", "kind": "marginal", "parents": [], "gate": "employed"},
    "emptype": {"field": "employment_type_by_age", "kind": "conditional",
                "parents": ["age_group", "sex"], "gate": "employed"},
    "income_source": {"field": "income_source_by_employment_age", "kind": "conditional",
                      "parents": ["inc_emp", "inc_age"], "gate": None},
    "socio": {"field": "socioeconomic", "kind": "conditional",
              "parents": ["age_group", "sex"], "gate": None},
    "civil": {"field": "civil_status_by_age_sex", "kind": "conditional",
              "parents": ["age_group", "sex"], "gate": None},
    "birthloc": {"field": "birth_location", "kind": "marginal", "parents": [], "gate": None},
    "birthdetail": {"field": "birth_country_detail", "kind": "conditional",
                    "parents": ["age_group", "sex"], "gate": "foreign_born"},
    "region": {"field": "region", "kind": "marginal", "parents": [], "gate": None},
    "parental": {"field": "parental_structure", "kind": "marginal", "parents": [], "gate": None},
    "housing": {"field": "housing_tenure", "kind": "marginal", "parents": [], "gate": None},
    "household": {"field": "household_size", "kind": "marginal", "parents": [], "gate": None},
}


def _label(obj: dict | None, field: str) -> str | None:
    """Return ``obj[field]['label']`` or ``None`` when the source field is null."""
    node = obj.get(field)
    if node is None:
        return None
    label = node.get("label")
    if label is None:
        raise ValueError(f"individual field {field!r} present but has no label: {node!r}")
    return label


def build_rows(individuals: list[dict]) -> list[list]:
    """Project each individual onto the 16-column compact row, id-ordered."""
    rows: list[list] = []
    for i, ind in enumerate(individuals):
        src_id = ind.get("id")
        if src_id != i:
            raise ValueError(f"individual at index {i} has non-matching id {src_id!r}; rows are id-indexed")

        et = ind.get("employment_type")
        if et is None:
            attachment = hours = None
        else:
            attachment = _label(et, "attachment")
            hours = _label(et, "hours")
            if attachment is None or hours is None:
                raise ValueError(f"individual {i}: employment_type present but attachment/hours incomplete: {et!r}")

        rows.append(
            [
                ind["age"],
                _label(ind, "biological_sex"),
                _label(ind, "education_level"),
                _label(ind, "employment_status"),
                _label(ind, "industry_sector"),
                attachment,
                hours,
                _label(ind, "income_source"),
                _label(ind, "socioeconomic_class"),
                _label(ind, "civil_status"),
                _label(ind, "birth_location"),
                _label(ind, "birth_country_detail"),
                _label(ind, "region"),
                _label(ind, "parental_structure"),
                _label(ind, "housing_tenure"),
                _label(ind, "household_size"),
            ]
        )
    return rows


def build_payload(source: Path) -> tuple[str, int]:
    """Read the population and return (minified JSON payload, individual count)."""
    data = json.loads(source.read_text(encoding="utf-8"))
    individuals = data.get("individuals")
    if not isinstance(individuals, list) or not individuals:
        raise ValueError(f"{source} has no non-empty 'individuals' array")
    src_meta = data.get("metadata", {})

    rows = build_rows(individuals)
    payload = {
        "columns": COLUMNS,
        "metadata": {
            "source": src_meta.get("source"),
            "n": src_meta.get("n"),
            "seed": src_meta.get("seed"),
            "data_vintage": src_meta.get("data_vintage"),
            "generated_at": src_meta.get("generated_at"),
        },
        "rows": rows,
    }
    minified = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return minified, len(rows)


def _join_key(key) -> str:
    """Join a tuple dict key with ``|``; pass scalar keys through unchanged."""
    if isinstance(key, tuple):
        return "|".join(str(part) for part in key)
    return str(key)


def _conv_conditional(dd: dict) -> dict:
    """``{tuple|str -> {label: P}}`` -> ``{'a|b' -> {label: P}}`` (tuple keys joined)."""
    return {_join_key(k): dict(sub) for k, sub in dd.items()}


def build_dist_payload() -> tuple[str, dict]:
    """Compute the source conditional distributions offline from the SCB cache.

    Runs the real fetch/parse pipeline against the on-disk PxWeb cache (no
    network), then serializes every ``PopulationDistributions`` field into a
    JSON-friendly island the page slices by context. Tuple keys are joined with
    ``|``. Returns ``(minified_json, sanity_counts)``.
    """
    # Imports are local so the (network-free) population embed path never needs
    # the generator package importable.
    from population_synthetic.clients.scb_client import SCBPxWebClient
    from population_synthetic.generators.real.helpers import AGE_GROUP_BOUNDS, age_to_group
    from population_synthetic.generators.real.sweden import sample_service as ss
    from population_synthetic.generators.real.sweden.fetch_service import FetchService

    d = FetchService.load_all(SCBPxWebClient())  # reads config/database/caches/scb, no network

    # age_sex is {(age_int, sex) -> P}; aggregate single years into the 7 pipeline
    # groups for a compact hub display ({"<group>|<sex>" -> P}, 14 rows).
    age_sex_group: dict[str, float] = defaultdict(float)
    for (age, sex), p in d.age_sex.items():
        age_sex_group[f"{age_to_group(int(age))}|{sex}"] += p

    # employment_by_sex_education is {sex -> {aku_edu -> {status -> P}}}; flatten the
    # two parent levels into a single "sex|aku_edu" key so the page slices uniformly.
    employment_flat: dict[str, dict] = {}
    for sex, buckets in d.employment_by_sex_education.items():
        for bucket, status_dist in buckets.items():
            employment_flat[f"{sex}|{bucket}"] = dict(status_dist)

    # Resolve each age_group to the actual income age-band string present in the
    # data, so the page needn't guess among the candidate spellings.
    present_bands = {band for (_emp, band) in d.income_source_by_employment_age}
    age_group_to_inc_age: dict[str, str] = {}
    for age_group, candidates in ss._AGE_GROUP_TO_INC_AGE.items():
        for candidate in candidates:
            if candidate in present_bands:
                age_group_to_inc_age[age_group] = candidate
                break

    conditional = {
        "education_by_age": _conv_conditional(d.education_by_age),
        "employment_by_sex_education": employment_flat,
        "employment_type_by_age": _conv_conditional(d.employment_type_by_age),
        "income_source_by_employment_age": _conv_conditional(d.income_source_by_employment_age),
        "socioeconomic": _conv_conditional(d.socioeconomic),
        "civil_status_by_age_sex": _conv_conditional(d.civil_status_by_age_sex),
        "birth_country_detail": _conv_conditional(d.birth_country_detail),
    }
    marginal = {
        "age_sex_group": dict(age_sex_group),
        "birth_location": dict(d.birth_location),
        "region": dict(d.region),
        "parental_structure": dict(d.parental_structure),
        "industry_sector": dict(d.industry_sector),
        "housing_tenure": dict(d.housing_tenure),
        "household_size": dict(d.household_size),
    }
    # Constants copied VERBATIM from the sampler (imported, not re-typed, to avoid
    # drift) so the page can derive parent keys from a context the same way.
    constants = {
        "AGE_GROUP_BOUNDS": [[lo, hi, group] for lo, hi, group in AGE_GROUP_BOUNDS],
        "AGE_GROUPS": [group for _lo, _hi, group in AGE_GROUP_BOUNDS],
        "SUN2020_TO_AKU_EDU": dict(ss._SUN2020_TO_AKU_EDU),  # bridge keys are lowercased
        "AKU_TO_INC_EMP": dict(ss._AKU_TO_INC_EMP),
        "AGE_GROUP_TO_INC_AGE": age_group_to_inc_age,
        "SEX_CODES": dict(ss._SEX_CODES),
        "IS_EMPLOYED": sorted(ss._IS_EMPLOYED_AKU),
        "SWEDEN_LABELS": sorted(ss._SWEDEN_LABELS),
    }
    payload = {
        "conditional": conditional,
        "marginal": marginal,
        "schema": DIST_SCHEMA,
        "constants": constants,
    }
    minified = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    counts = {
        "conditional_fields": len(conditional),
        "marginal_fields": len(marginal),
        "age_sex_group_rows": len(age_sex_group),
        "cells_per_conditional": {name: len(cells) for name, cells in conditional.items()},
    }
    return minified, counts


def _island(minified: str, start: str, end: str, script_id: str) -> str:
    return f'{start}\n<script id="{script_id}" type="application/json">{minified}</script>\n{end}'


def _replace_or_insert(html: str, island: str, start: str, end: str) -> str:
    """Idempotently replace a marker block, else insert it before the app <script>."""
    block_re = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if block_re.search(html):
        return block_re.sub(lambda _m: island, html, count=1)
    # Insert right before the page's main app <script> (the first inline
    # <script> with no src that opens the "use strict" app block).
    anchor = re.search(r'\n<script>\n"use strict";', html)
    if not anchor:
        raise ValueError("could not locate the main app <script> to anchor an embedded island")
    insert_at = anchor.start()
    return html[:insert_at] + "\n" + island + html[insert_at:]


def inject(html_path: Path, pop_minified: str, dist_minified: str) -> int:
    """Idempotently replace (or insert) BOTH embedded islands. Returns byte size."""
    html = html_path.read_text(encoding="utf-8")
    html = _replace_or_insert(
        html, _island(pop_minified, START_MARKER, END_MARKER, "embedded-pop"),
        START_MARKER, END_MARKER,
    )
    html = _replace_or_insert(
        html, _island(dist_minified, DIST_START_MARKER, DIST_END_MARKER, "embedded-dist"),
        DIST_START_MARKER, DIST_END_MARKER,
    )
    html_path.write_text(html, encoding="utf-8")
    return len(html.encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="population JSON to embed")
    ap.add_argument("--html", type=Path, default=DEFAULT_HTML, help="explorer HTML to inject into")
    args = ap.parse_args()

    pop_minified, count = build_payload(args.source)
    dist_minified, dist_counts = build_dist_payload()
    size = inject(args.html, pop_minified, dist_minified)

    print(f"Embedded {count:,} individuals from {args.source.name}")
    print(f"  pop island:  {len(pop_minified.encode('utf-8')):,} bytes (minified JSON)")
    print(f"  dist island: {len(dist_minified.encode('utf-8')):,} bytes (minified JSON)")
    print(f"    conditional fields: {dist_counts['conditional_fields']}, "
          f"marginal fields: {dist_counts['marginal_fields']}, "
          f"age_sex_group rows: {dist_counts['age_sex_group_rows']}")
    print(f"    cells/conditional: {dist_counts['cells_per_conditional']}")
    print(f"  {args.html.name}: {size:,} bytes ({size / 1_048_576:.2f} MiB)")


if __name__ == "__main__":
    main()

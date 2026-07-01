# ISTAT (Italy) comparison mapping config

This directory is the **single source of truth** for how the population comparison
maps both the ISTAT/Eurostat reference database and the LLM pipeline output into one
shared canonical schema, and for which categories each attribute is scored on. One
JSON file per comparison attribute, plus an `_index.json` master. Loaded by
`comparison/reference_mapper/mappings.py` and driven by the shared resolver
`comparison/mapping_engine.py`.

The file shape, matcher vocabulary, directives, and `_index.json` role are **identical
to the SCB directory** — see [`../scb/README.md`](../scb/README.md) for the full
reference. In brief:

## File shape

Each per-attribute file is symmetric across the two mapper sides:

```json
{
  "values":    ["Italy", "Europe (Other)", "Outside Europe"],
  "database":  { "Italy": {"equals": ["Italy"]}, ... },
  "synthetic": { "Italy": {"contains": ["italia", "roma", ...]}, ...,
                 "refine_from": "birth_country_detail", "fuzzy": false }
}
```

- `values` — the unified category set **and** the scored axis / chart order (both
  sides emit only these labels or `None`; there is no separate scheme/filter).
- `database` — resolves a raw ISTAT value; `synthetic` — resolves a raw
  `identity.json` free-text value. Keyed by unified value → matcher; **key order =
  match priority**.
- `age.json` is values-only: `age_group` is derived from raw `age` at scoring time.

## Matcher vocabulary & directives (summary)

- Matchers: `equals`, `contains`, `all_of`, `none_of`, `int`, `int_gte`, plus the
  composite sub-field matcher (`employment_type`).
- Precedence within a value: `none_of` → `equals` → `all_of` → `contains` → numeric.
- Directives: `absent`, `refine_from`, `on_miss`, `fuzzy` (default `true`).

## `_index.json` master

Lists the in-scope attributes (`attribute → filename`, key order = axis order) plus
`joint_pairs` and `coherence_attributes`. Only files listed here are read.

## Source-key convention

Record/output key = attribute name; the age exception uses raw `age`, from which
`age_group` is derived at scoring time.

## Italy specifics

- **No `income_source`.** ISTAT provides no income-source field, so it is simply
  omitted from `_index.json` and never enters Italy's comparison axis. Country scope
  is thus data-driven — there is no code branch.
- Italy legitimately keeps categories Sweden drops, where ISTAT grounds them:
  `Other` (housing_tenure), `Extended Family` and `Couple without Children`
  (parental_structure).
- `birth_location` is `["Italy", "Europe (Other)", "Outside Europe"]` — no separate
  "Nordic Country" bucket; Nordic origins fold into `Europe (Other)`.
- `household_size` `values` are human-readable labels (`"1 person"` …
  `"6 persons or more"`) — the Phase-3 reconciliation replaced the old raw-code axis
  (`1` … `GE6`) with these labels. The `database` matchers key those labels; the
  `synthetic` side buckets an integer count via `int` / `int_gte`.

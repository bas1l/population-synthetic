# SCB (Sweden) comparison mapping config

This directory is the **single source of truth** for how the population comparison
maps both the SCB reference database and the LLM pipeline output into one shared
canonical schema, and for which categories each attribute is scored on. One JSON
file per comparison attribute, plus an `_index.json` master. Loaded by
`comparison/reference_mapper/mappings.py` (`load_mappings` / `load_index`) and driven
by the shared resolver `comparison/mapping_engine.py`.

## File shape

Every per-attribute file (e.g. `biological_sex.json`) is **symmetric** across the two
mapper sides:

```json
{
  "values": ["Male", "Female"],
  "database":  { "Male": {"equals": ["men", "male", "1"]},
                 "Female": {"equals": ["women", "female", "2"]} },
  "synthetic": { "Male": {"contains": ["male", "pojke"], "equals": ["man", "m"]},
                 "Female": {"contains": ["female", "kvinna"], "equals": ["f"]},
                 "fuzzy": false }
}
```

- **`values`** — the unified category set **and** the chart/axis order. Both mapper
  sides emit only these labels (or `None`), so `values` *is* the scored comparison
  axis; there is no separate scheme/filter.
- **`database`** — resolves a raw national-statistics value (already coded).
- **`synthetic`** — resolves a raw `identity.json` free-text value.
- Both blocks are keyed by unified value → matcher. **Key order within a block is
  match priority**: the resolver walks `values` in declared order and returns the
  first value whose matcher hits.

`age.json` is a special case: it declares only `values` (the seven age-bin labels).
`age_group` is *derived* from the raw integer `age` by `evaluator.attr_value` at
scoring time, so there is no `database`/`synthetic` block to resolve.

## Matcher vocabulary

Inside a value's matcher block:

| Key | Meaning |
|---|---|
| `equals` | exact match: normalized+stripped raw equals a normalized token |
| `contains` | substring: raw contains any token |
| `all_of` | AND-of-ORs: raw contains ≥1 token from *every* group (list of lists) |
| `none_of` | veto: if any token is present, this value is rejected outright |
| `int` | numeric: `int(raw)` is in the list |
| `int_gte` | numeric: `int(raw)` ≥ the bound |

**Composite matcher** — for `employment_type`, whose raw DB record has sub-fields
(`attachment` + `hours`). A value block that keys sub-field names (instead of the
matcher keys above) is composite; every named sub-field's own matcher must hit:

```json
"Permanent Full-time": {
  "attachment": {"contains": ["permanent employees"]},
  "hours":      {"contains": ["35+ hours"]}
}
```

**Matcher precedence within one value** (first hit wins, `none_of` vetoes):
`none_of` → `equals` → `all_of` → `contains` → `int`/`int_gte`.

## Attribute-level directives

Reserved keys on a `database`/`synthetic` block (never confused with values, since
the walk is driven by `values`):

| Directive | Effect |
|---|---|
| `absent` | literal emitted when the raw input is missing/empty (e.g. `"Not Applicable"`) |
| `refine_from` | on a primary miss, re-walk against a sibling attribute's already-resolved value (e.g. `birth_location` refined from `birth_country_detail`) |
| `on_miss` | literal default when everything misses (default `None`) |
| `fuzzy` | after explicit matchers miss, substring-match raw against the `values` labels (default `true`; set `false` where free-text fuzzing is unsafe) |

## `_index.json` master

```json
{
  "attributes": { "age_group": "age.json", "biological_sex": "biological_sex.json", ... },
  "joint_pairs": [["age_group","education_level"], ...],
  "coherence_attributes": ["age_group","education_level","employment_status"]
}
```

- `attributes` — the in-scope comparison attributes; **key order = axis order**. Only
  files listed here are read by the mappers and the scheme.
- `joint_pairs` / `coherence_attributes` — the cross-attribute tests.

## Source-key convention

The record key / output key for an attribute is the attribute name itself
(`biological_sex`, `education_level`, …). The one exception is age: the mappers read
and emit the raw integer under `age`, and the `age_group` comparison attribute is
derived from it at scoring time.

## Sweden specifics

- `employment_status` is **binary** — `["Employed", "Unemployed"]`. The SCB
  labour-force extract does not distinguish students/retirees/not-in-labour-force, so
  those are *not* Swedish comparison categories (a synthetic value that looks like
  "student" resolves to `None` for this attribute, not a new bucket).
- `birth_location` is `["Sweden", "Europe (Other)", "Outside Europe"]` — there is no
  separate "Nordic Country" bucket; Nordic origins fold into `Europe (Other)`.
- Sweden includes `income_source` (SCB provides the field); Italy's config omits it.

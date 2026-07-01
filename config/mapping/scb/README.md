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
                 "Female": {"contains": ["female", "kvinna"], "equals": ["f"]} }
}
```

- **`values`** — the unified category set **and** the chart/axis order. Both mapper
  sides emit only these labels (or `None`), so `values` *is* the scored comparison
  axis; there is no separate scheme/filter.
- **`database`** — resolves a raw national-statistics value (already coded).
- **`synthetic`** — resolves a raw `identity.json` free-text value.
- Both blocks are keyed by unified value → matcher. The resolver matches with a
  **global tiered sweep** (see precedence below): each matcher tier is tried across
  *all* values before the next tier, and **`values` declared order breaks ties within
  a tier**.

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

**Matcher precedence** — a **global tiered sweep**: each tier is swept across *all*
values before the next tier, so a later value's `equals` beats an earlier value's
`contains`. Within a tier, `values` declared order breaks ties. Tier order:
`equals` → `all_of` → `contains` → `int`/`int_gte`, with composite matchers in a
final pass. `none_of` is a veto (not a tier): it rejects its value in every tier.

## Attribute-level directives

Reserved keys on a `database`/`synthetic` block (never confused with values, since
the walk is driven by `values`):

| Directive | Effect |
|---|---|
| `absent` | literal emitted when the raw input is missing/empty (e.g. `"Not Applicable"`) |
| `refine_from` | on a primary miss, re-walk against a sibling attribute's already-resolved value (e.g. `birth_location` refined from `birth_country_detail`) |
| `on_miss` | literal default when everything misses (default `None`) |

## `_index.json` master

```json
{
  "attributes": { "age_group": "age.json", "biological_sex": "biological_sex.json", ... }
}
```

- `attributes` — the in-scope comparison attributes; **key order = axis order**. Only
  files listed here are read by the mappers and the scheme. This is the master's only
  required key: it declares pure *mapping scope* (which per-attribute files exist).

The cross-attribute statistics (`joint_pairs`, `coherence_attributes`,
`coherence_threshold`) are **not** in this file — they are evaluator tuning, not mapping,
and live in the comparison-analysis config `config/analysis/comparison/{scb,istat}.json`.

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

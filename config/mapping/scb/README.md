# SCB (Sweden) comparison mapping config

> **Tier note (2026-07-14).** This coarse schema is now the **(deferred) global /
> cross-country tier**. The primary *within-country* Sweden comparison no longer uses
> this directory — it uses the native high-fidelity tier
> [`config/mapping/scb_native/`](../scb_native/README.md), which scores Sweden at the
> real SCB data's own category resolution. This coarse schema is retained because its
> value sets are chosen so that Sweden, Italy and Norway can eventually share **one**
> cross-country comparison axis; the collapse that would feed it (native → global) is
> **not implemented yet** (see the [Global tier (deferred)](#global-tier-deferred--design-only)
> note below and the plan
> `docs/development/plans/active/native-highfidelity-mapping-sweden.md`). 12 of the 15
> attributes are identical between the two tiers; only `industry_sector`,
> `employment_type` and `parental_structure` are coarser here.

This directory is the **single source of truth** for how the population comparison
maps both the SCB real population data and the LLM pipeline output into one shared
canonical schema, and for which categories each attribute is scored on. One JSON
file per comparison attribute, plus an `_index.json` master. Loaded by
`analysis/mapping/real_mapper/mappings.py` (`load_mappings` / `load_index`) and driven
by the shared resolver `analysis/mapping/mapping_engine.py`.

## File shape

Every per-attribute file (e.g. `biological_sex.json`) is **symmetric** across the two
mapper sides:

```json
{
  "values": ["Male", "Female"],
  "real":      { "Male": {"equals": ["men", "male", "1"]},
                 "Female": {"equals": ["women", "female", "2"]} },
  "synthetic": { "Male": {"contains": ["male", "pojke"], "equals": ["man", "m"]},
                 "Female": {"contains": ["female", "kvinna"], "equals": ["f"]} }
}
```

- **`values`** — the unified category set **and** the chart/axis order. Both mapper
  sides emit only these labels (or `None`), so `values` *is* the scored comparison
  axis; there is no separate scheme/filter.
- **`real`** — resolves a raw national-statistics value (already coded).
- **`synthetic`** — resolves a raw `identity.json` free-text value.
- Both blocks are keyed by unified value → matcher. The resolver matches with a
  **global tiered sweep** (see precedence below): each matcher tier is tried across
  *all* values before the next tier, and **`values` declared order breaks ties within
  a tier**.

`age.json` is a special case: it declares only `values` (the seven age-bin labels).
`age_group` is *derived* from the raw integer `age` by `evaluator.attr_value` at
scoring time, so there is no `real`/`synthetic` block to resolve.

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

Reserved keys on a `real`/`synthetic` block (never confused with values, since
the walk is driven by `values`):

| Directive | Effect |
|---|---|
| `absent` | literal emitted when the raw input is missing/empty (e.g. `"Not Applicable"`) |
| `refine_from` | on a primary miss, re-walk against a sibling attribute's already-resolved value (e.g. `birth_location` refined from `birth_country_detail`) |
| `on_miss` | literal default when everything misses (default `None`) |

## `_index.json` master

```json
{
  "deprecated_attributes": ["birth_location"],
  "attributes": { "age_group": "age.json", "biological_sex": "biological_sex.json", ... }
}
```

- `attributes` — the in-scope comparison attributes; **key order = axis order**. Only
  files listed here are read by the mappers and the scheme. This is the master's only
  **required** key: it declares pure *mapping scope* (which per-attribute files exist).
- `deprecated_attributes` *(optional)* — attribute names that are still **mapped and
  emitted into the population data** (they remain in `attributes`, so the mapper keeps
  producing them) but are **excluded from the comparison axis and every analysis stage**
  (marginals, bar charts, TV radar, multivariate/C2ST, model-ranking, method-significance,
  consistency). The filter is applied once, at the scheme chokepoint
  `analysis/fidelity/scheme.py:_scheme_from_index`, so every downstream stage that reads
  `ComparisonScheme.attributes` honours it automatically. Fail-loud: a name that is not in
  `attributes`, or a list that would leave the axis empty, raises. To deprecate another
  axis, add its name here — no code change. To reactivate one, remove it here (leaving its
  `attributes` entry untouched).

### Why `birth_location` is deprecated

`birth_location` (coarse `Sweden` / `Europe (Other)` / `Outside Europe`, from SCB
`FolkmFodlandHVD`) and `birth_country_detail` (top-20 specific countries, from
`FodelselandArK`) are sampled as **independent** age×sex marginals joined only by a binary
Sweden/non-Sweden gate — nothing forces the sampled country into the matching coarse
EU/non-EU bucket, so contradictory pairs occur (e.g. "Outside Europe" + "Germany"). That
makes the coarse `birth_location` axis a contradictory, lower-value signal in fidelity
scoring. `birth_country_detail` already carries the birthplace signal we want (it resolves
to `Sweden` for natives via the gate, and to the specific country otherwise), so
`birth_location` is deprecated from analysis while retained in the data. Note this
**sidesteps** the underlying sampling-independence issue rather than fixing it — the
contradictory pair still exists in the raw/mapped data; it is simply no longer scored. See
`docs/development/plans/active/deprecate-birth-location-analysis-axis.md`.

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

## Global tier (deferred) — design only

> **Not yet implemented.** This section sketches the intended future mechanism. No
> global-collapse code exists today; the within-country tiers (`scb_native`, and later a
> native `istat`) are the only mappers that run.

The two-tier model separates two jobs the coarse schema used to do at once:

1. **Native (within-country) tier** — `config/mapping/scb_native/` — maps raw SCB / raw
   LLM text onto the **real data's own resolution**. This is what scores Sweden today.
2. **Global (cross-country) tier** — this directory — a *coarser* shared axis onto which
   several countries' native categories collapse so they can be compared to each other.

When cross-country analysis is actually built, the global tier will **not** be a second
raw→canonical mapping (that would re-author the synthetic free-text cascades a second time
and create a second source of truth). Instead it becomes a thin downstream **native →
global overlay**: a per-attribute **finite value → bucket lookup** keyed on the *native*
canonical values (which are a small, closed set), **not** a free-text matcher.

```
raw SCB / LLM ──► NATIVE tier (scb_native) ──► within-country fidelity      (NOW)
                        │
                        └──► native→global value lookup ──► cross-country compare  (DEFERRED)
```

Design constraints for that overlay:

- **Defined only for the attributes that actually collapse.** For Sweden that is
  `industry_sector` (12 → 8/9), `employment_type` (9 → 6), `parental_structure` (6 → 3),
  plus any attribute that needs cross-country harmonisation (e.g. aligning SCB regions,
  Swedish `birth_location` buckets, and ISTAT equivalents onto one shared set).
- **Identical attributes pass through native unchanged** — the 12 attributes whose native
  and coarse value sets already match need no lookup; they are already on the shared axis.
- **Finite value map, fail-loud.** Every native value maps to exactly one global bucket in
  config; an unmapped native value raises rather than silently dropping (the closed native
  vocabulary makes this a total, checkable map — no `on_miss` sink needed at this layer).
- **Authored when cross-country analysis is built**, not before. Until then this coarse
  schema stands in as the eventual global target so its buckets and history are preserved.

**Italy** (`config/mapping/istat/`) follows the same pattern: it gets its **own native
tier** (`istat_native`, by analogy to `scb_native`) authored to ISTAT's own resolution,
and the same native → global overlay collapses both countries' native categories onto the
shared global buckets. Norway would join identically.

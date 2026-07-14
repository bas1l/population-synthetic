# `scb_native` — Sweden native high-fidelity mapping tier

This directory is the **native, within-country** mapping tier for Sweden. It maps both the
real SCB population and the LLM-synthetic population onto the **real data's own category
resolution**, so within-country fidelity is scored at the full resolution the national
statistics actually carry.

It is the high-fidelity counterpart to `config/mapping/scb/`, which is retained as the
**(deferred) global / cross-country tier** — a coarser schema whose value sets are chosen so
that Sweden, Italy, and Norway can eventually share one comparison axis. The global collapse
(native → global value lookup) is not implemented yet; see the plan
`docs/development/plans/active/native-highfidelity-mapping-sweden.md`.

## File schema

Same symmetric per-attribute schema as `config/mapping/scb/` (see
`src/population_synthetic/analysis/mapping/mapping_engine.py`):

- `values` — the ordered unified value set (also the comparison axis order).
- `real` — raw national-statistics label → unified value matchers, plus attribute
  directives (`absent`, `on_miss`, `refine_from`).
- `synthetic` — raw LLM `identity.json` value → unified value matchers, plus directives.

`_index.json` maps each comparison attribute to its per-attribute file (identical order to
the coarse tier).

## Resolution vs the coarse (global) tier

12 of the 15 attributes are **identical** to `config/mapping/scb/` — their coarse value sets
already equal native resolution, so those files are copied verbatim and must be kept in sync
until the global tier is formalised as a native → global overlay:

`age_group`, `biological_sex`, `education_level`, `employment_status`, `birth_location`,
`socioeconomic_class`, `region`, `civil_status`, `housing_tenure`, `household_size`,
`income_source`, `birth_country_detail`.

3 attributes are **expanded to native resolution** here (the coarse tier merges them):

| attribute | coarse | native | what native restores |
|---|---|---|---|
| `industry_sector` | 9 | 14 (12 SNI2007 groups + `Other` + `Not Applicable`) | the 12 SNI2007 groups, 1:1 — manufacturing/construction, trade/transport/accommodation, info-comm/financial-business are no longer folded |
| `employment_type` | 6 | 10 (3 attachment × 3 hours + `Not Applicable`) | the full attachment × hours grid — hours are no longer collapsed for the self-employed, and 1-19 h is split from 20-34 h |
| `parental_structure` | 3 | 6 | the 6 LE0102T17 family types — stepparent/blended variants are no longer folded into the natural-parent bucket |

For these 3 attributes the `real` block is a **clean 1:1 relabel** (Option A): every distinct
raw SCB label becomes its own native value under a readable English canonical name — no
merging, no collapse. Category boundaries are preserved exactly; only the display string is
canonicalised. The `synthetic` blocks carry finer keyword cascades so the LLM free-text can be
routed to the finer native categories (`industry_sector` retains its `on_miss → Other` sink;
`employment_type` and `parental_structure` route unmatched text to `None`, matching the coarse
tier). `age_group` is left at the coarse 7-bin scheme this pass (single-year bins are deferred —
see the plan's Out of Scope).

## Note on value counts

The success-criteria shorthand "12 / 9 / 6 native values" counts the real-producible
categories: 12 SNI industry groups, the 9-cell attachment × hours grid, and the 6 family
types. The `industry_sector` and `employment_type` files additionally declare the
sentinel values (`Not Applicable` for the `absent` directive, and `Other` for the
`industry_sector` synthetic `on_miss`), exactly as the coarse tier does.

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

## Deprecated attributes

`_index.json` also carries an optional `deprecated_attributes` list (schema documented in
[`../scb/README.md`](../scb/README.md#_indexjson-master)). Names in it stay in `attributes`
— so the mapper keeps emitting them into the population data — but are excluded from the
comparison axis and every analysis stage, via the single filter at
`analysis/fidelity/scheme.py:_scheme_from_index` (fail-loud on an unknown name or an emptied
axis).

This tier deprecates **`birth_location`**, so Sweden analyses **14** axes (not 15) while the
field is still present in generated/mapped populations. Reason: `birth_location` (coarse
Sweden/EU/non-Europe) and `birth_country_detail` (top-20 specific countries) are sampled as
independent marginals joined only by a binary Sweden/non-Sweden gate, so contradictory pairs
occur (e.g. "Outside Europe" + "Germany"); `birth_country_detail` already carries the
birthplace signal, so the coarse axis is dropped from scoring while retained in data. This
sidesteps — does not fix — the sampling independence; see
`docs/development/plans/active/deprecate-birth-location-analysis-axis.md`.

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

## Classification note: same-sex-couple families → `Natural Parents`

`parental_structure.json` (synthetic) routes same-sex-couple values (`same-sex couple`,
`two mothers`, `gay couple`, …) to **`Natural Parents`**, and vetoes only `non-traditional`.
This is **not an ad-hoc choice** — it mirrors how the official statistics that define these
categories actually classify such children. Rationale (researched 2026-07-26):

- **No official framework has a distinct "same-sex family" category.** SCB, Eurostat, and the
  UN/UNECE census recommendations all place same-sex couples with children **by legal
  parenthood, not by the parents' sex.**
- **SCB's own `familjetyp` variable** (LE0102, the source of these 6 categories) is keyed on
  **"ursprunglig förälder" = biological _or_ adoptive parent** and **"styvförälder" = a
  co-resident adult who is _not_ a registered legal parent.** It is register-derived from legal
  parent–child links; there is no biology test and no same-sex flag. So "Natural Parents" here
  is really SCB's *two original (legal) parents* — which **includes adoptive parents**, and
  therefore includes a same-sex couple who are both legal parents.
- **UNECE** defines a *family nucleus* to explicitly include *"a marital (registered) same-sex
  couple"*, counted as a two-parent couple family; **Eurostat**: *"couples include adults in
  same-sex as well as opposite-sex relationships."*
- **Swedish law makes dual legal parenthood the modal case** for these children — same-sex
  adoption (2003), assisted reproduction for female couples (2005), gender-neutral marriage
  (2009), and the **parenthood presumption for married female couples (2022)**.

SCB's deterministic rule (which we approximate): **both partners legal parents → Natural
Parents**; **only one legal parent + non-legal co-resident → Mother/Father and Stepparent**;
**neither → Other Than Parents**. Our generator emits only "same-sex couple, child present"
with no legal-parenthood flag, so the **register-consistent default is `Natural Parents`** (the
modal Swedish outcome). The rare blended case ("same-sex couple with children from previous
relationships") is formally a stepfamily, but is not reliably detectable from the free text and
is left to the default.

Sources: SCB barn- och familjestatistik (LE0102 `familjetyp`); UNECE CES Recommendations for
the 2020/2030 censuses, ch. Household & family; Eurostat "Household composition statistics";
MFoF / Government.se on the 2022 parenthood presumption.

## Note on value counts

The success-criteria shorthand "12 / 9 / 6 native values" counts the real-producible
categories: 12 SNI industry groups, the 9-cell attachment × hours grid, and the 6 family
types. The `industry_sector` and `employment_type` files additionally declare the
sentinel values (`Not Applicable` for the `absent` directive, and `Other` for the
`industry_sector` synthetic `on_miss`), exactly as the coarse tier does.

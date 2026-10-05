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
- `priority` — the same values in **rule-priority** order (a permutation of `values`, required),
  consulted when several values hit in the same tier. Kept separate from `values` so the chart
  order never decides a tie.
- `real` — raw national-statistics label → unified value matchers, plus attribute
  directives (`absent`, `on_miss`, `refine_from`, `subfields`).
- `synthetic` — raw LLM `identity.json` value → unified value matchers, plus directives.

`_index.json` maps each comparison attribute to its per-attribute file (identical order to
the coarse tier) and declares the required `matching` block (below).

## Matching rules (`_index.json` → `matching`)

The engine has no in-code matching defaults; a missing or malformed block raises when a mapper is
built. This tier's `real` side keeps the historic rules (`substring`, no negation,
`tie_break: ["priority"]`); the `synthetic` side, which reads free LLM text, uses:

- **`token_mode: "prefix"`** — a `contains` / `all_of` / `none_of` token must start at a word
  start (the preceding character is not a letter or digit). This stops the left-embedding hits
  the SCB-checked audit found (`gymnasial` in *efter*gymnasial, `male` in *fe*male, `rent` in
  pa*rent*s, `skild` in *en*skild, `hög inkomst` in *medel*hög inkomst, `0 timmar` in
  4*0 timmar*) while keeping compound *modifiers* (`högskole` in högskoleexamen). Compound
  *heads*, which Swedish puts last and which must match mid-word (`lön` in månadslön, `anställd`
  in heltidsanställd, `vård` in hemvård, `pension` in garantipension), are written as
  `{"token": "lön", "mode": "substring"}`. The override list was generated over the full
  `01_Raw` Swedish pool (tokens whose only hit in a persona value was mid-word) and reviewed by
  hand; the tokens whose mid-word hits are the defect itself stay prefix. A token missing an
  override fails loudly (`__UNMAPPED__`, visible to `validate_mapped`) rather than silently
  matching the wrong category.
- **`negation`** — a cue word (`inte`, `ej`, `ingen`, `not`, `no`, `never`, `utan`, …) among the
  two words before a token, in the same clause, discards that hit; applies to `contains`, `all_of`
  members and `none_of` (a negated veto does not veto), never to `equals`. A token that itself
  starts with a cue still hits ("never married"). Past tense is not negation. `biological_sex`
  and `birth_location` opt out (`"negation": null` in their `synthetic` block: "non-binary",
  "non-EU").
- **`tie_break: ["longest", "priority"]`** — within the winning tier, the value whose matched
  token is longest wins (for `all_of`, the summed length of the group hits), then `priority`.
  Tier precedence is unchanged. `employment_status` (SCB BAS hierarchy Employed > Unemployed >
  Student > Retired > Sick > Other) and `income_source` (wage first) override it with
  `"tie_break": ["priority"]`. Every multi-hit is written to `{slug}.ties.csv`.

`employment_type`'s `synthetic` block also declares a **`numeric_facet`**: after the walk, weekly
hours (or a percentage of a 40 h week) stated in the text re-band the walked attachment into the
AKU agreed-hours bands 1–19 / 20–34 / 35+. A range spanning two bands or a number behind a
comparator ("över 30") keeps the walked value and is logged as `facet_ambiguous` in the ties
sidecar; `0 timmar` is in no band and never overrides. The attachment rules therefore carry no
hour tokens; `heltid` / `deltid` remain the fallback when no hours are stated. Zero stated hours
are handled in config instead: every employed value vetoes `0 timmar` / `0 h/v` / `0 hours` (prefix
mode keeps them off "40 timmar") and `Not Applicable` lists them.

`education_level` routes post-secondary text by stated length in its `all_of` tier: 4+5B needs a
higher-education word and a short-length marker (`kortare än 3`, `2-årig`, `120 hp`, …, vetoed by
`master` / `magister` / `kandidat` / `bachelor`), 5A a higher-education word and a ≥ 3-year or
degree marker (`3 år eller`, `kandidat`, `master`, …). Without it, "Eftergymnasial utbildning,
3 år eller längre" — which reached 3A only through the `gymnasial` substring bug — would fall
to `__UNMAPPED__` under `prefix`.

## Per-attribute rules from the SCB-checked audit

Each rule follows SCB's own definition of the category; the regression cases live in
`tests/test_scb_native_audit_rules_core.py`.

- **`civil_status`** is the legal register status. A sambo / cohabiting / partner text is
  `Single/Never Married` (a sambo is not married); a separated spouse stays `Married` (Sweden has
  no legal separation); registered partnership is `Married`. Negated forms ("ej gift",
  "utan sambo") carry positive Single tokens, because the engine discards the negated `gift` hit
  rather than inverting it. A stated prior status beats "ensamstående" (Single vetoes divorce and
  widowhood words), and "previously married" with the current status unstated is `Divorced`.
- **`education_level`** codes the highest *completed* SUN level. A bare `högskoleexamen` is
  `Post-Secondary < 3 yrs (4+5B)` (SCB codes an 80 p examen as under 3 years); a 3-year or degree
  marker routes it to 5A. Upper secondary with no stated length is 3A, and 3C needs an explicit
  ≤ 2-year length. Folkhögskola has no general SUN level and is unmapped; folkskola is ISCED 1;
  incomplete or ongoing gymnasium is ISCED 2. Post-secondary text vetoes both upper-secondary
  values, so "post-secondary education" with no length is unmapped.
- **`employment_status`** follows the BAS hierarchy (`tie_break: ["priority"]`): a working student
  or pensioner is `Employed`; job-seeking and past-tense text leave `Employed`; förtidspension /
  sjukersättning is `Sick Leave`, not `Retired`; homemakers and carers are `Other`.
- **`employment_type`**: fixed-term, project, probation and doctoral posts are Temporary; an own
  company, sole trader or näringsidkare is Self-Employed; negated employment and zero stated hours
  are `Not Applicable`.
- **`housing_tenure`** is a property of the building: `Owner-occupied` is SMAG only, so any
  apartment, BRF or rental word vetoes it and an owned flat is a bostadsrätt. Ägarlägenhet (OB)
  is not fetched and is unmapped; bostadsbolag is a landlord (`Rental`). A house-or-flat
  disjunction ("Eget hus eller lägenhet") names no tenure and is unmapped.
- **`income_source`** is wage first (`tie_break: ["priority"]`, Wage first in `values`): any stated
  paid work, including an occupation or employer named as the source, is `Wage / Business`.
  CSN / studielån / barnbidrag are `General Allowances` (component 325) and bostadsbidrag /
  bostadstillägg `Housing Allowance` (330); since `priority` is shared with the real side and
  stays the `values` order, the generic `Insurance / Allowance` (which precedes them) vetoes their
  tokens. Parental or family support is not an SCB income component and is unmapped.

The rules below have their regression cases in `tests/test_scb_native_audit_rules_social.py`.

- **`industry_sector`** is SNI 2007, which classifies by *activity*, not by owner or wording:
  professional / scientific / technical activities, R&D (SNI 72), marketing and PR, engineering
  services and administrative services are `Financial & Business Services` (sections M–N);
  municipal elderly care is `Healthcare & Social Work`, not `Public Administration`; vehicle sale and
  repair is `Trade` (G 45); warehouse work without a trade context is `Transport` (H 52); labour-
  market services — Arbetsförmedlingen, staffing, recruitment — are SNI 78 (`Financial & Business
  Services`). A bare "Engineering" (C 25–30 or M 71), "Administration", general advice and
  media-plus-culture texts (J or R) name no single section and are unmapped; a pensioner's former
  job is not a current sector. Phrase priority is native: the longer phrase wins the contains tier.
- **`parental_structure`** follows LE0102's legal ("ursprunglig") parents and folkbokföring
  residence: a cohabiting or married couple's child has `Natural Parents` (a sambo couple counts);
  adoptive parents are `Natural Parents`; after a divorce the parent the child lived with decides
  (`Single Mother` / `Single Father`); a parent's new partner makes a stepparent family. A
  two-phase text keeps the **earlier** phase ("both parents until the divorce …" → `Natural
  Parents`), so `mother remarried` is not a token. Joint custody / alternating residence is
  unmapped (the registered parent is unknown); a bare same-sex couple keeps `Natural Parents`
  (above). Known residue: five two-phase texts whose *later* phase carries a divorce or custody veto
  word ("…, then shared custody", "later separated") resolve to `__UNMAPPED__`, because a `none_of`
  veto applies in every tier; honouring the earlier phase there needs clause splitting in the
  engine.
- **`socioeconomic_class`** is an income band relative to the (age, sex) median, so only income or
  class wording places a persona: explicit poverty cues → `Poverty`; low income / låginkomst /
  lägre inkomst / underklass → `Poverty`; modest / moderate, lower class / lägre klass, lower or
  low socioeconomic status, lower-middle class, limited / pressed economy → `Working Class`;
  median / average income → `Middle Class`; high-income / affluent → `Wealthy`. Explicit cues are
  a single-group `all_of` (they must beat any `contains` token, which `longest` alone would not
  give). Occupation, employment-status and SEI group words (student, pensionär, tjänsteman,
  akademiker, professional, kunskapsarbetare, företagare, …) carry no income band and are
  unmapped: no SCB table places an occupation in these bands without inventing the mapping.
- **Small attributes.** `biological_sex`: text naming both sexes is unmapped. `region`: unaccented
  and province names that lie in one län; "Uppland" and "Region Väst" are unmapped.
  `birth_country_detail`: "Sverige (född i utlandet)" is not Sweden-born. `household_size`: "With
  parents (2)" is three persons.

## Deprecated attributes

`_index.json` also carries an optional `deprecated_attributes` list (schema documented in
[`../scb/README.md`](../scb/README.md#_indexjson-master)). Names in it stay in `attributes`
— so the mapper keeps emitting them into the population data — but are excluded from the
comparison axis and every analysis stage, via the single filter at
`analysis/fidelity/scheme.py:_scheme_from_index` (fail-loud on an unknown name or an emptied
axis).

This tier deprecates **`birth_location`**, so Sweden analyses **14** axes (not 15) while the
field is still present in generated/mapped populations. Reason: `birth_location` (coarse
Sweden / other EU / outside the EU) and `birth_country_detail` (top-20 specific countries) are
sampled as independent marginals joined only by a binary Sweden/non-Sweden gate, so
contradictory pairs occur (e.g. "Born outside the EU" + "Germany"); `birth_country_detail`
already carries the birthplace signal, so the coarse axis is dropped from scoring while retained
in data. This sidesteps — does not fix — the sampling independence; see
`docs/development/plans/active/deprecate-birth-location-analysis-axis.md`.

**Birth-region labels.** FolkmFodlandHVD returns `FSV` / `FEU` / `FUEU` — born in Sweden, in
another EU member state, outside the EU — so the two foreign values are named **`Born in another
EU country`** and **`Born outside the EU`** (they were "Europe (Other)" / "Outside Europe", which
misdescribed the table). The synthetic country lists follow EU membership: Norway, Iceland, the
UK, Switzerland, Serbia, Bosnia, Ukraine, (former) Yugoslavia, Kosovo, Albania, Belarus, Moldova,
Montenegro and North Macedonia are outside the EU; `nordic`, `scandinav`, `europe`, `european`
and `immigrant` fit neither side and are not tokens. The `real` block lists only the three
FolkmFodlandHVD labels (the legacy labels of other tables were dead). Still open: `refine_from`
re-walks only the *resolved* `birth_country_detail` value, so a country outside its 21
categories leaves `birth_location` unmapped even when the country is in these lists. The global
tier `config/mapping/scb/` and Italy's `istat` keep the old labels (Italy's "Europe (Other)" is
the same EU27 mislabel, out of scope).

## Resolution vs the coarse (global) tier

12 of the 15 attributes are **identical** to `config/mapping/scb/` — their coarse value sets
already equal native resolution, so those files are copied verbatim and must be kept in sync
until the global tier is formalised as a native → global overlay:

`age_group`, `biological_sex`, `education_level`, `employment_status`, `birth_location`,
`socioeconomic_class`, `region`, `civil_status`, `housing_tenure`, `household_size`,
`income_source`, `birth_country_detail`.

Since the SCB-checked audit (`docs/development/plans/pending/mapping-fixes-scb-audit.md`) these
files are **no longer verbatim copies**: the native synthetic blocks are written for this tier's
`prefix` / negation / `longest` matching and carry the audit's rule changes and the birth-region
rename, while `config/mapping/scb/` keeps the historic behaviour-preserving matching and rules.
The global tier was deliberately not mirrored (it is read by no Swedish axis file, and the native
rules would not mean the same under `substring` matching); re-deriving it is part of formalising
the native → global overlay.

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
routed to the finer native categories; **no attribute in this tier declares `on_miss`**, so text
that matches nothing resolves to the explicit `__UNMAPPED__` sentinel and the persona fails
`validate_mapped` — see [No `on_miss` sinks](#no-on_miss-sinks) below. `age_group` is left at the
coarse 7-bin scheme this pass (single-year bins are deferred — see the plan's Out of Scope).

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
`Not Applicable` sentinel for the `absent` directive.

`industry_sector` previously carried a 14th value, `Other`, reachable *only* through its
synthetic `on_miss`. When that sink was removed the value became unreachable in both blocks —
SCB's register aggregates the fine SNI2007 codes into exactly the 12 sectors, with no residual
group — so it was dropped rather than left as a zero-mass phantom category on the comparison
axis.

## No `on_miss` sinks

No attribute in this tier declares `on_miss`. The directive names a literal to return when the
whole value-walk misses, and both former uses here (`industry_sector → Other`,
`income_source → Wage / Business`) were **silent failures**: the mapped record carried a
real-looking category, so `validate_mapped` — which only ever sees the `__UNMAPPED__` sentinel
— could not tell the miss from a genuine hit, and the miss mass was folded into that category's
marginal, the very quantity the fidelity score measures.

Consequences of the removal, all intended:

- A raw value matching nothing now resolves to `__UNMAPPED__` and the persona **fails**
  `validate_mapped`, so it is excluded from the capped population instead of quietly inflating
  a real category.
- The mass those sinks absorbed does not disappear; it becomes visible attrition. The honest
  remedy is a matcher token for a variant the config already commits to — never a new sink.
- Every miss, masked or not, is recorded to `03_Analysis/mapping/{slug}.misses.csv` with the
  raw string that caused it (`mapping_engine.resolve_detailed` reports the miss flag
  separately from the value, because a sink makes it unrecoverable from the value alone).

Re-introducing `on_miss` on any attribute in this tier is a regression and is asserted against
in `tests/test_mapping_config_no_on_miss.py`. Italy (`config/mapping/istat/`) still declares it
on two attributes; that is a separate change, since removing it there invalidates every Italian
mapped artefact.

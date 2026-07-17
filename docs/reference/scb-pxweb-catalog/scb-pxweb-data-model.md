# How SCB's data works — the PxWeb table model

A conceptual reference for anyone sourcing Swedish statistics from the **SCB PxWeb API**
(`https://api.scb.se/OV0104/v1/doris/en/ssd`). It explains *why the data is shaped the way it
is* — not how to call it (for the mechanics and the sweep tooling, see [`HOW-TO.md`](./HOW-TO.md);
for the full table inventory, open [`scb-am-uf-catalog.html`](./scb-am-uf-catalog.html)).

Written from what we established while investigating "employment status by age" for the Swedish
population generator (2026-07-15). Grounded in a live sweep of **968 tables** across the AM and UF
subject areas.

---

## TL;DR

SCB's public API does **not** serve raw microdata you can slice arbitrarily. It serves a large
set of **pre-computed cross-tabulations** — each a fixed table that crosses one measured concept
against a *specific, chosen* set of breakdown dimensions, from a *specific source*, at a *specific*
geography and periodicity. One concept ("employment status") therefore appears across **many**
tables, each keeping a different subset of dimensions and dropping the rest. A combination SCB
never chose to publish (e.g. status × education × age) **does not exist on the API at all**, even
when the underlying register could produce it. "A variable appears in a table's metadata" is **not**
the same as "you can cross-tabulate by it" — a dimension can collapse to a single aggregate the
moment another is added.

---

## 1. The mental model: published tables, not a queryable cube

Think of PxWeb as a **library of pre-baked pivot tables**, not a database you send arbitrary
`GROUP BY` queries to.

- SCB's statisticians decide which cross-tabs are worth publishing, compute them, and expose each
  as a table (a "matrix").
- You can select *which rows/columns/values* of an existing table to return, but you **cannot**
  ask for a cross-tab that was never published.
- The raw person-level microdata that underlies these tables lives inside SCB and is **not** on the
  public API (see §7).

This single fact explains almost everything below.

## 2. How tables are addressed — the subject-area tree

The API is a tree. `GET .../ssd/{path}` returns either a **list of child nodes** (each typed
`"l"` = folder or `"t"` = table) or, for a full table path, that **table's metadata**.

Paths read `AREA / SURVEY / SUB / MATRIX`, e.g. `AM/AM0401/AM0401A/AKURLBefAr`:

| Segment | Example | Meaning |
|---------|---------|---------|
| Area | `AM` | Subject area (labour market) |
| Survey/product | `AM0401` | Statistical product (AKU — Labour Force Survey) |
| Sub-node | `AM0401A` | A grouping within the product |
| Matrix | `AKURLBefAr` | The actual table |

### The 19 top-level subject areas

| Code | Area | | Code | Area |
|------|------|-|------|------|
| AA | General statistics | | LE | Living conditions |
| AM | **Labour market** | | ME | Democracy |
| BE | **Population** | | MI | Environment |
| BO | **Housing & construction** | | NR | National accounts |
| EN | Energy | | NV | Business activities |
| FM | Financial markets | | OE | Public finances |
| HA | Trade in goods & services | | OV | Other |
| HE | **Household finances** | | PR | Prices & consumption |
| JO | Agriculture, forestry, fishery | | TK | Transport & communications |
| | | | UF | **Education & research** |

**Bold** = areas this project's population generator draws on. Person-level demographic attributes
live in AM, BE, BO, HE, LE, MI, UF; the others (EN, FM, HA, JO, ME, NR, NV, OE, PR, TK) are
macro/sectoral and describe *the economy or the country*, not *individuals crossed by age/sex*.

## 3. Anatomy of one table

A table's metadata is a list of **variables** (dimensions). Every query picks values for each.

- **`ContentsCode`** — the *measure(s)*: what the numbers count (e.g. `number of employed`,
  `unemployment rate`). A table can offer several.
- **Classification variables** — the breakdowns: `Alder` (age), `Kon` (sex), `Region`,
  `UtbildningsNiva` (education level), `Fodelseregion` (region of birth), `Arbetskraftstillh`
  (labour-force status), etc.
- **`Tid`** — the time dimension (`time: true`), e.g. years or months.
- **`elimination: true`** — this dimension can be *omitted* from a query and SCB returns its
  aggregate. `elimination: false` means you **must** pick a value.
- Each variable carries `values` (codes, e.g. `SYS`) and `valueTexts` (labels, e.g. `employed`).

Queries are POSTed as JSON selecting `{code, selection:{filter:"item", values:[...]}}` per
dimension, with `response.format: "json-stat2"` (see `src/.../sweden/fetch_service.py` for
worked examples).

## 4. Why one concept spans many tables (the core insight)

In the sweep, **134 of 968** tables carry a labour-force-status variable — not one. Four
compounding reasons:

1. **Pre-computed tabs, not microdata (§1).** Each published combination of
   `status × {chosen breakdowns}` is its own table. Status × age × sex is one table; status ×
   education × sex is another; status × industry × region is another. Same variable, different
   companions → different tables.

2. **Multiple sources measure the same concept.** Employment status is produced by *different
   statistical products*, each its own folder:
   - **AKU** (Arbetskraftsundersökningarna / Labour Force Survey) — **sample-based**,
     monthly/quarterly/annual, ILO definitions, ages 15–74. Folders `AM0401`, `AM0403`.
   - **Register-based** labour market status (BAS / RAMS) — **full-count administrative**,
     annual. Folders `AM0210`, `AM0207`.
   - Short-term / other employment products.
   The survey and the register genuinely yield *slightly different numbers*, so SCB keeps them as
   distinct tables rather than a single figure. **Pick the source deliberately.**

3. **Combinatorial explosion + confidentiality.** A single mega-cube
   (status × single-year-age × sex × region × education × birth-country × year) would be enormous
   and mostly **suppressed** — small cells are hidden to protect privacy. So SCB instead publishes
   many small 2–4-dimension slices, each dropping most dimensions. One concept → dozens of tables.

4. **Vintages & themes.** Preliminary vs final, annual vs monthly, old vs new classifications
   (SSYK96 vs SSYK2012, SUN2000 vs SUN2020), and thematic packagings (NEET youth, by working
   hours, by attachment) each spawn their own table.

### Consequence: the combination you want may simply not exist

Because SCB publishes *specific* slices, a cross-tab they never released is **absent from the API
entirely**. Concretely, for Sweden there is **no** table giving labour-force status × education ×
a genuine age band:
- status × education × sex (no age): `AM/AM0401/AM0401P/NAKUBefUtbNivAr`
- status × age (5-yr bands) × sex (no education): `AM/AM0210/AM0210D/ArRegArbStatus` (register) or
  `AM/AM0401/AM0401A/AKURLBefAr` (AKU)

The register microdata *could* produce the three-way — SCB just never published that pivot.

## 5. The critical trap: "present in metadata" ≠ "cross-tabulable"

A variable can be listed in a table's metadata yet **collapse to a single aggregate** the moment
you cross it with another. Real example from the sweep:

- `AM/AM0210/AM0210A/ArbStatusUtbM` lists **all** of `Alder`, `UtbildningsNiva`, and a status
  `ContentsCode`. It *looks* like the three-way table.
- But its `Alder` values are only `20–64`, `20–65`, `20–66 years` — **working-age totals**, not an
  age breakdown. Cross status × education and age is forced to a single lump.

**Always confirm a real cross-tab by issuing an actual query** for the specific cell combination,
not by trusting that two variables coexist in metadata. When classifying age programmatically,
distinguish a genuine breakdown (single years or narrow bands) from an aggregate range like
`20–64` — and normalise the en-dash `–` (U+2013) vs hyphen `-` first, or totals get misread as
bands (see `build_report.py::classify_age`).

## 6. Practical rules of thumb for this repo

- **Locate a source by dimension, not by name.** To answer "can I get X by Y?", find a table whose
  metadata carries both — then verify §5. The [catalog HTML](./scb-am-uf-catalog.html) and
  [JSONL](./scb-am-uf-metadata.jsonl) make this a search, not a manual hunt.
- **Choose the source on purpose.** Register (full-count, annual) vs AKU (survey, timelier, ILO
  definitions) is a real modelling choice, not interchangeable.
- **Honour the no-synthetic-distributions rule.** If SCB doesn't publish a needed cross-tab, the
  project's principle is to **drop the field**, not invent it — never fabricate a distribution to
  fill a gap the API can't serve. (See `docs/architecture/design-principles.md`.)
- **Watch coverage edges.** Labour-status tables cap at age 74 (AKU universe); there is no
  status-by-age table for 75+. Know each table's universe before relying on it.

## 7. When the public API can't give a combination — microdata

If a required cross-tab isn't published, the only route to it is SCB **microdata**, accessed via
a formal research application (the **MONA** platform, register data / RTB). That is *outside* the
public PxWeb API, requires approval and typically an ethics/legal basis, and is **out of scope**
for this project, which sources only public API distributions. Treat "not on PxWeb" as "not
available to us" unless a microdata agreement is explicitly established.

---

## See also

- [`HOW-TO.md`](./HOW-TO.md) — replicate the sweep + report (the mechanics)
- [`scb-am-uf-catalog.html`](./scb-am-uf-catalog.html) — searchable inventory of all 968 AM+UF tables
- [`scb-am-uf-metadata.jsonl`](./scb-am-uf-metadata.jsonl) — the complete raw metadata
- `docs/scb_population_and_comparison.md` — how the SCB sampling/comparison pipeline runs
- `docs/istat_population_data_sources.md` — the Italy/ISTAT analog (field-by-field source matrix)
- `docs/architecture/design-principles.md` — the no-synthetic-distributions invariant

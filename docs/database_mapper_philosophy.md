# The Database (Reference) Mapper — Philosophy

This note explains *why* `comparison/reference_mapper/` exists as its own thing,
what it is responsible for, and the principle that governs it: **the reference
database is the source of truth for the comparison's category space.** It is the
companion of `comparison/synthetic_mapper/`, and the contrast between the two is
the clearest way to understand either.

## The setting: a two-population face-off

Population comparison scores one population against another:

- the **reference** population — real national-statistics data (SCB for Sweden,
  ISTAT for Italy), the ground truth we want the synthetic data to resemble;
- the **synthetic** population — the LLM pipeline's `identity.json` output.

`StatisticalEvaluator` can only compare them if both speak the **same canonical
schema** — identical attribute names and identical category labels per attribute.
Each side therefore has a mapper whose single job is to translate its raw input
into that shared schema. They are separate packages because the two inputs are
fundamentally different shapes and require fundamentally different work.

| | reference_mapper (database) | synthetic_mapper (pipeline) |
|---|---|---|
| Input | already-coded `{code,label}` dicts from a stats API | free-text LLM values (Swedish/Italian/English), multiple formats, mojibake |
| Rules block consulted | each attribute file's `database` block | each attribute file's `synthetic` block |
| Typical matchers | `equals`, composite (attachment×hours), decile-as-`equals` | `contains`, `all_of`/`none_of`, numeric (`int`/`int_gte`), `refine_from`, `fuzzy` |
| Extra work | flatten nested `RawCategory` dicts; `id` passthrough | encoding repair, narrative-format skip, persona-skip `age` gate |
| Country divergence | **data** — one class attribute (the mapping directory) | **data** — one class attribute (the mapping directory) |
| Output | the shared canonical schema | the shared canonical schema |

Both sides are now **thin loaders over one shared resolver**,
`comparison/mapping_engine.py` (`resolve`). Each per-country subclass
(`SwedishReferenceMapper`/`ItalianReferenceMapper`,
`SwedishSyntheticMapper`/`ItalianSyntheticMapper`) holds only its mapping directory
(`MAPPINGS_SUBDIR`); all algorithm and label knowledge lives in the JSON config. The
reference side is thin *because the statistics agency already did the hard
categorisation work* (a coded value resolves with plain `equals`); the synthetic side
does the same ordered value-walk but leans on the richer matchers and the `fuzzy`
tier to tame free text. Neither base class contains a single field-name or category
literal: the comparison attributes come from the per-country `_index.json` master
(attribute → filename, in axis order) and every label comes from the matched
attribute file's `values`. Adding or removing a comparison field is a config-only
edit — add the file and list it in `_index.json`. The two packages stay separate so
the messy free-text path (encoding repair, narrative skip) never contaminates the
clean coded-reference path, even though they share the resolver.

## What the mapping actually does — relabel *and* collapse

It is tempting to read the reference mapper as cosmetic ("make labels prettier").
It is not. It does two substantive things, driven entirely by the JSON tables
under `config/mapping/{scb,istat}/`:

1. **Relabel** — near-1:1 for cleanly-coded fields. SCB's
   `"upper secondary education, 2 years or less (ISCED97 3C)"` →
   `"Upper Secondary ≤ 2 yrs (ISCED 3C)"`.
2. **Collapse** — deliberate coarsening where the agency is finer-grained than the
   analysis needs: 10 income deciles → 4 socioeconomic classes; 12 SNI sectors → 8
   industry groups. This is real information reduction, not renaming.

The labels are not chosen to be pretty — they are the **common denominator with
the synthetic side**. Both mappers point at the same right-hand-side vocabulary so
a chi-square test compares like with like.

## The governing principle: the database defines the category space

The comparison must measure the synthetic data against *what the reference
database actually contains* — nothing invented, nothing assumed. Concretely:

- **No empty canonical buckets.** A category only belongs in the comparison if the
  reference database emits it. If SCB's labour-force extract only yields
  `Employed`/`Unemployed`, then `Student` and `Retired` are not comparison
  categories for Sweden — even though the synthetic side can produce them. (A
  synthetic-only value becomes an *unmapped* value, reported as such, rather than
  silently widening the axis.)
- **No properties the database lacks.** ISTAT provides no income-source field, so
  `income_source` is simply not a comparison attribute for Italy. The canonical
  scheme is therefore **per-country** in which properties it contains.
- **No synthesized/derived categories.** A category the mapper *invents* rather
  than reads from the record is not part of the stored schema (see age below).

This is the same discipline as the project-wide *no synthetic distributions* rule,
applied to categories: just as every probability must come from a real API
response, every comparison category must come from real reference data.

> One subtlety: when a raw value matches no matcher, the reference side resolves it
> to `None` (dropped from the comparison) rather than erroring or passing it through.
> So if the database ever emits a label outside the curated `database` matchers, that
> mass silently disappears from the axis. A golden diff of the mapper over the real
> reference file is how this is caught — every value the DB emits must be claimed by
> some matcher.

## The comparison scheme — no longer a separate filter

Earlier, the principle lived in a second file — a per-country `_scheme.json` whose
only job was to *filter out* the looser labels the mappers could emit (the mappers
had a broad `output_categories`; the scheme narrowed it back to the DB-grounded
axis). That dual-list arrangement is gone. The per-attribute file is now the **single
symmetric source of truth**, and because both mappers emit *only* the labels they
declare, the scored axis simply **is** each file's `values` — there is nothing left
to filter.

Each attribute file (e.g. `config/mapping/scb/biological_sex.json`) declares:

- `values` — the unified category set **and** the chart/axis order. This is the
  DB-grounded scored axis for the attribute;
- `database` — unified value → matcher, resolving a raw national-statistics value;
- `synthetic` — unified value → matcher, resolving a raw `identity.json` value.

A per-country `_index.json` master lists the in-scope attributes (`attribute →
filename`, key order = axis order) plus `joint_pairs` and `coherence_attributes`.
Country scope is therefore data-driven with no code branch: Italy's `_index.json`
simply omits `income_source` (ISTAT provides no such field), so it never appears in
Italy's axis.

`comparison/scheme.py` (`ComparisonScheme` / `load_scheme`) is unchanged in
*interface* — `StatisticalEvaluator`, `charts.py`, and the compare scripts still
receive the same four fields — but it now **sources** them from `_index.json` + each
file's `values` rather than from a standalone scheme file. This still enforces "no
empty buckets" and "no DB-absent properties", because the axis is exactly the values
both mappers are constrained to emit.

### Changing the category axis

To add, drop, or rename a category, edit that attribute file's `values` (and the
matcher entries that resolve to it) — one file, both sides. Because the mappers can
only emit declared `values`, there is no separate scheme to keep in sync. When a
reference population file changes and a new coded label appears, add it to the
matching value's `database` matcher; a label the DB emits but no matcher catches
resolves to `None` (dropped from the comparison), so a golden diff over the real
reference file is the check that the config is complete.

## Age: a derived dimension, not a stored field

`age_group` is the one category the mappers used to *synthesize* — by binning the
raw integer `age`, which neither database stores as a category. Under the
DB-grounded principle a synthesized category does not belong in the schema, so the
canonical populations now carry only the raw `age`, and the **binning lives in the
stats layer**: `evaluator.attr_value` derives the age group on the fly (reusing the
canonical `population/helpers.age_to_group`) for the age marginal, the joint pairs,
and the coherence test. The comparison still reports on age groups; it simply does
not pretend the database provided them.

## Why not merge the two mappers

You could fold both sides into one class, but you would gain nothing: they share no
transformation logic (a dictionary lookup vs a fuzzy-NLP toolbox), and the merged
code would just be `if input_is_clean: lookup else: fuzzy_match`. The two packages
are deliberately built as mirror images —
`load_reference_population → normalize_population` vs
`load_raw_population → map_population` — so the symmetry is visible at every call
site while the clean and messy paths stay isolated. The reference mapper is small
on purpose: that smallness is the evidence that the database, not the code, is
doing the categorisation.

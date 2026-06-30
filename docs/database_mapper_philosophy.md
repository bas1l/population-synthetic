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
| Work | a single case-insensitive dictionary lookup per attribute | fuzzy matching, keyword cascades, encoding repair, narrative parsing |
| Country divergence | **data** — one class attribute (the mapping directory) | **behaviour** — ~12 per-attribute methods reimplemented per country |
| Output | the shared canonical schema | the shared canonical schema |

The reference side is thin *because the statistics agency already did the hard
categorisation work*. SCB/ISTAT emit a small, closed set of coded categories;
turning them into canonical labels is a rename, so one mappings-driven loop in
`BaseReferenceMapper` serves every country and each subclass
(`SwedishReferenceMapper`, `ItalianReferenceMapper`) holds only its mapping
directory (`MAPPINGS_SUBDIR`). `BaseReferenceMapper` is both **field-agnostic** and **label-agnostic**. Field-agnosticism
is achieved by *self-declaration*: the field set is not a column in the code but lives in
config — each per-attribute mapping JSON declares its own `reference_handler` (the generic
algorithm to run: `passthrough`/`label`/`composite`/`decile_coded`/`substring_coded`) and an
optional `reference_attr` (its output schema key). At construction the base scans the loaded
mappings for blocks carrying a `reference_handler` and registers one generic handler each, so
the class contains zero field-name literals and adding/removing a comparison field is a
config-only edit (it fails fast on an unknown handler kind or when no block declares one).
Label-agnosticism follows the same discipline: it contains no canonical category string —
every output label, including the domestic-birth collapse, is an ordinary entry in the
country's mapping tables, read through role-based sub-keys like `reference_label_mappings`.
Keeping it apart from the synthetic side stops the messy free-text heuristics from
contaminating the clean coded-reference path.

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

> One subtlety: the reference mapper passes an unrecognised value through unchanged
> rather than erroring. So if the database ever emits a label outside the curated
> tables, it lands in the output verbatim — quietly, not loudly. Curated category
> lists are validated against the real reference file precisely to catch this.

## The comparison scheme — where the principle lives

The principle is made explicit in a per-country **scheme** file:
`config/mapping/{scb,istat}/_scheme.json`, loaded by
`comparison/scheme.py` (`ComparisonScheme` / `load_scheme`). Each scheme declares:

- `attributes` — the in-scope properties for that country (Sweden: 15; Italy: 14,
  no `income_source`);
- `categories` — the DB-exact category set per attribute, **built empirically** by
  enumerating the distinct non-None values the reference mapper produces over that
  country's real reference population — *not* copied from the mapper's broader
  `output_categories` (which is the looser set of labels the mappers may emit).
- `joint_pairs` / `coherence_attributes` — the cross-attribute tests.

`StatisticalEvaluator` takes the scheme and uses `categories[attr]` as the scored
axis. This is what enforces "no empty buckets" and "no DB-absent properties" at the
point of comparison. The scheme is the single source of truth for *what the
comparison scores*; it is deliberately distinct from the per-attribute mapping
files (which govern *what the mappers translate*).

### Regenerating a scheme

When a reference population file changes, rebuild the `categories` lists by running
the reference mapper over the new file and collecting, per attribute,
`sorted({ind[attr] for ind in individuals} - {None})`. Every value the reference
emits must appear in the scheme — a missing value would silently drop that
reference mass from the comparison.

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

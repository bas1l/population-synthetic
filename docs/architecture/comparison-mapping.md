# Comparison & Mapping

> **Architecture wiki:** [Home](README.md) · [Sub-packages](sub-packages.md) ·
> **Comparison & mapping** · [Design principles](design-principles.md) ·
> [Axis composition](axis-composition.md) · [Configuration](configuration.md) · [Commands](commands.md)

How the `comparison/` package maps both a **reference** (database) population and a
**synthetic** (pipeline) population onto one canonical schema so they can be scored against
each other. This is the densest part of the architecture; for the deeper rationale see
[`../database_mapper_philosophy.md`](../database_mapper_philosophy.md) and the per-country
config READMEs (`config/mapping/scb/README.md`, `config/mapping/istat/README.md`).

## Two-stage flow (map -> compare)

Mapping is a standalone pipeline stage, not an inline step of each comparison script.

**Stage 1 (map)** -- `scripts/analyze/map_populations.py` reads the explicit completeness list
`config/analysis/comparison_targets.yaml` (entries are plain manifest-path strings or
`{manifest, country}` mappings), maps each target's synthetic population (`load_raw_population`
-> `map_population`) and its reference once per country (`load_reference_population` ->
`normalize_population`), and writes to `{output_base}/03_Analysis/mapped/`: `{slug}.json` (mapped
synthetic, one per target), `database_{country}.json` (mapped reference, deduped one per country),
and `_index.json` (list of `{slug, country, synthetic_file, database_file, n, skipped}`).
Missing/empty seed roots warn and skip, never crash.

**Stage 2 (compare)** -- the three comparison scripts perform **no** mapping; they `json.load` the
pre-mapped files (a missing mapped file raises a clear "Run scripts/analyze/map_populations.py
first." error) and run the existing evaluator/chart path. `compare_all_pipelines.py` iterates
`mapped/_index.json` (imports zero mappers); `compare_pipeline_to_scb.py` /
`compare_pipeline_to_istat.py` resolve mapped files from `--mapped-dir` (default
`{output_base}/03_Analysis/mapped`) + `{slug}`, or take explicit `--mapped-synthetic` /
`--mapped-database`. All comparison artifacts land under
`{output_base}/03_Analysis/comparison/{slug}/` (per-target JSON report + CSV + 15 bar charts +
radar), with the summary and `{country}_radar_grid.png` at `.../comparison/`.

`comparison/country_config.py` is the shared country resolver -- `reference_for_country`,
`mappings_for_country`, `known_country_ids`, `infer_country(config_path)` -- reading
`parameters.reference` / `parameters.mappings` from the **country axis YAMLs**
(`config/synthetic/axes/countries/{swedish,italian}.yaml`), so references/mappings are
config-driven, not hardcoded, and adding a country needs only a new YAML.

## Unified symmetric mapping config

Both mapper sides are driven by one per-country config tree (`config/mapping/{scb,istat}/`, one
JSON file per comparison attribute + an `_index.json` master) and one shared resolver
`comparison/mapping_engine.py` (`resolve`). Each per-attribute file is *symmetric*: it declares
`values` once (the unified category set **and** the scored axis / chart order) plus a `database`
rules block and a `synthetic` rules block, both keyed by unified value -> matcher. The resolver
matches with a **global tiered sweep**: each matcher tier is tried across *all* values before the
next tier, and `values` declared order breaks ties within a tier (so a later value's `equals`
beats an earlier value's `contains`); a total miss yields `None`. Matcher vocabulary:
`equals`/`contains`/`all_of`/`none_of`/`int`/`int_gte` + a composite sub-field matcher (for
`employment_type`'s attachment x hours). Tier order is `equals` -> `all_of` -> `contains` ->
numeric (composite in a final pass), with `none_of` a veto (not a tier) that rejects its value in
every tier. Attribute-level directives: `absent` (missing-input literal), `refine_from` (re-walk a
sibling's resolved value, e.g. `birth_location` from `birth_country_detail`), `on_miss` (default
when all miss). The `_index.json` master lists the in-scope attributes (`attribute -> filename`,
key order = axis order) -- pure mapping scope; country scope is data-driven (Italy's master omits
`income_source`). The cross-attribute statistics (`joint_pairs`/`coherence_attributes`/
`coherence_threshold`) are evaluator tuning, not mapping, and live in a separate
comparison-analysis config `config/analysis/comparison/{scb,istat}.json` (one file per country)
read by `scheme.py`. There is no `_scheme.json` filter and no
`output_categories`/`reference_*`/`pipeline_*` dual vocabulary -- the scored axis simply *is* each
file's `values` because both mappers emit only declared values. See
`config/mapping/{scb,istat}/README.md` and [`../database_mapper_philosophy.md`](../database_mapper_philosophy.md).

## Reference mapper (`reference_mapper/`)

Maps the **reference** (database) population -- raw national-statistics records (nested
`RawCategory` dicts from SCB/ISTAT) -> canonical schema labels. Class hierarchy
`AbstractReferenceMapper -> BaseReferenceMapper -> {SwedishReferenceMapper, ItalianReferenceMapper}`
with a `get_reference_mapper(country, mappings_path=None)` factory. `BaseReferenceMapper` is a
**thin loader** over `mapping_engine.resolve`: it reads the `_index.json` master + each attribute
file's `database` block/`values`, flattens the raw `RawCategory` dicts (or, for `employment_type`,
the attachment/hours sub-field dict) and delegates. It holds **zero field-name/category literals**
-- the only in-code responsibilities are `id` passthrough and the raw `age` passthrough
(`age_group` is derived at scoring time). Country divergence is one subclass attribute,
`MAPPINGS_SUBDIR`. Two-step API: `load_reference_population(path)` then
`normalize_population(raw_pop, country)` (normalizes only if raw-format; an already-flat population
passes through). Supporting primitives `load_mappings`/`load_index`/`is_raw_format` live in the
package; `normalizer.py` is a thin backward-compat facade delegating to it, kept because
`extract/mappings.py` imports `load_mappings` from there.

## Synthetic mapper (`synthetic_mapper/`)

Maps the **synthetic** (pipeline) population -- raw `identity.json` free-text values -> canonical
schema labels -- via `AbstractSyntheticMapper -> BaseSyntheticMapper -> {SwedishSyntheticMapper,
ItalianSyntheticMapper}`. `BaseSyntheticMapper` is the synthetic-side mirror of the reference
base: a thin loader over `mapping_engine.resolve` reading each attribute's `synthetic`
block/`values`, delegating every attribute. Its remaining in-code responsibilities are the format
gate (unrecognised formats such as a legacy `{"narrative": ...}` blob warn and return `None`),
record-level UTF-8 repair, and the persona-skip `age` gate (missing/non-integer `age` skips the
persona). Country divergence is one subclass attribute, `MAPPINGS_SUBDIR`. Two-step API:
`load_raw_population(seed_root)` then `map_population(raw_pop, country)`, mirroring the reference
side. `get_synthetic_mapper(country)` is the factory; text helpers live in
`synthetic_mapper/_text_helpers.py`.

## Extractor facade

`extractor` is a thin backward-compat facade: `extract_individual()` / `extract_population()`
(both take a `country` param) delegate to the synthetic mapper; kept for tests and
`extract_population_from_pipeline.py`.

## See also

- [`../database_mapper_philosophy.md`](../database_mapper_philosophy.md) — *why* the reference
  mapper exists and the principle that governs it.
- [Design principles](design-principles.md) — the "config is the single source of truth" and
  "full comparison output" hard rules that this package enforces.
- [Configuration](configuration.md) — the `config/mapping/*` and `config/analysis/comparison/*`
  files these mappers read.

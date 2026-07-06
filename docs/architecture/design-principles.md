# Design Principles & Key Patterns

> **Architecture wiki:** [Home](README.md) · [Sub-packages](sub-packages.md) ·
> [Comparison & mapping](comparison-mapping.md) · **Design principles** ·
> [Axis composition](axis-composition.md) · [Configuration](configuration.md) · [Commands](commands.md)

The recurring architectural patterns and the **hard behavioral rules** for this repository.
`CLAUDE.md` keeps one-line statements of the hard rules (marked **Core invariants**); this page
holds the full rationale. When a rule here conflicts with convenience, the rule wins.

## Key design patterns

- **Shared population layer** -- Breaks the SCB<->SSB cross-dependency. Both `sweden/` and `norway/` import from the shared `generators/real/` parent, never from each other
- **Factory + Strategy** -- `FactoryIdentityGenerator` selects generation strategy at runtime based on mode string
- **Conditional chained sampling** -- Population sampling conditions each attribute on prior draws (e.g., education given age/sex, employment given education)
- **Local file caching** -- PxWeb clients cache API responses as JSON files in `config/database/caches/{scb,ssb}/` to avoid redundant API calls

## Hard rules

### No synthetic distributions

Every probability distribution used in population generation must come from a real statistical API
response. Hardcoded probability tables, fallback distributions, parametric approximations (e.g.
lognormal models), and manually estimated rates are prohibited as primary data sources. If no API
provides data for a demographic field, that field must be dropped from the output -- never filled
with invented values. Code-level constants for structural purposes (API dataset IDs, code-to-label
maps, query parameters) are acceptable; constants that define *what probability a person has of
being in a given category* are not.

### No hardcoded fallbacks (config is the single source of truth)

HARD RULE. Domain content that belongs in config -- the comparison attribute list / axis order,
category values, per-attribute matcher rules, joint/coherence attribute pairs, sex-harmonization
maps, and any similar attribute-name or category-value literal -- must be read from the config
files (`config/mapping/{scb,istat}/`, `config/analysis/fidelity/*.json`, etc.), never duplicated
as an in-code default or `attr or DEFAULT` fallback. Config is authoritative; there is no second
copy in Python to "fall back" to. If the config is missing, empty, or malformed, **fail loudly**
(raise) -- a fail-fast crash is the expected, correct behavior, not a silent revert to a baked-in
list. This applies to *values and names*, not to structural numeric primitives (e.g. age binning,
integer parsing) or format sentinels. Reference migrations (the pattern in practice):
`StatisticalEvaluator` dropped its `DEMOGRAPHIC_ATTRIBUTES` / `JOINT_PAIRS` /
`COHERENCE_ATTRIBUTES` fallbacks and now *requires* a `ComparisonScheme` (raises without one); the
chart functions take a required `attributes` axis; `analysis/mapping/flatten_raw.py` derives its field
set from each record's own keys and harmonizes sex through the `biological_sex` mapping config
instead of a hardcoded map.

### Full comparison output

When comparing pipeline output against the real population, every output artifact
must be generated: a bar chart for each of the 15 demographic attributes in
`DEMOGRAPHIC_ATTRIBUTES` (age_group, biological_sex, education_level, employment_status,
birth_location, socioeconomic_class, parental_structure, region, civil_status, industry_sector,
employment_type, housing_tenure, household_size, income_source, birth_country_detail), a radar
chart with TV-similarity across all attributes, the JSON comparison report (marginals + joint
chi-squared + coherence), and the CSV marginals summary. Charts are only skipped when an attribute
has zero data in both populations -- if the real population provides the field, the chart
must appear.

## See also

- [Comparison & mapping](comparison-mapping.md) — where the "config is the single source of truth"
  and "full comparison output" rules are enforced.
- [Sub-packages](sub-packages.md) — the packages these patterns shape
  (`generators/real/`, `generators/synthetic/`, `analysis/`).

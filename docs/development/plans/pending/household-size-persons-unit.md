# Plan: Count Persons, Not Households, in the Swedish `household_size` Reference

**Date:** 2026-10-03
**Author:** Basil
**Status:** In progress — code and docs changed on the branch; re-sampling and re-runs not started
**Base Branch:** `feature/typicality-distribution-grid`
**Branch:** `feature/household-size-persons-unit`

---

## Overview

The Swedish real reference population draws each person's `household_size` from SCB table
`BE/BE0101/BE0101S/HushallT03` with `ContentsCode = BE0101CZ`, which SCB labels **"Number of
households"**. A persona is a person, and its `household_size` answers "how many people live in
my household". The person-weighted series of the same table, `BE0101DK` (**"Number of
persons"**), answers that question. This plan switches the query to `BE0101DK`, records the
series in the population's provenance, updates the living docs, and lays out the re-sampling and
re-run protocol. LLM persona generation is not re-run.

## Problem Statement

SCB 2024, whole of Sweden (fetched 2026-10-03 from the PxWeb API):

| Size | Share of households (`BE0101CZ`, current) | Share of persons (`BE0101DK`, new) |
|---|---|---|
| 1 | 41.8 % | 19.7 % |
| 2 | 30.0 % | 28.2 % |
| 3 | 11.2 % | 15.9 % |
| 4 | 11.3 % | 21.2 % |
| 5 | 3.9 % | 9.3 % |
| 6 | 1.1 % | 3.2 % |
| 7+ | 0.7 % | 2.6 % |

The current reference therefore puts about twice as many people in one-person households as live
in them. Every `household_size` fidelity score, the model ranking on that axis, the realism
ranking's real competitor (`real_{country}`) and the published figures inherit the wrong unit.

Found during the SCB-checked mapping audit (2026-10-03); the reference audit was confirmed by a
challenger against the live table metadata
(<https://api.scb.se/OV0104/v1/doris/en/ssd/BE/BE0101/BE0101S/HushallT03>).

## Decision and its residual bias

Three options were assessed (decision recorded 2026-10-03):

1. **Persons, same table (`BE0101DK`) — chosen.** Same bands 1..7+, so the mapping config is
   unchanged.
2. Adults-only persons by household size — **not available.** SCB publishes no table crossing
   household size with age (checked live across BE0101S and HE0111; also recorded in
   `docs/reference/scb-pxweb-catalog/scb-source-audit.md`). From the registers only the
   one-person band is exact for ages 18–85 (23.5 %); bands 2..7+ can only be bounded.
3. Keep households and disclose — rejected: the axis would measure the wrong unit.

**Residual bias of option 1:** `BE0101DK` counts children (0–17), who are never personas and never
live alone. Against the adult bounds, option 1 understates one-person (19.7 % vs exactly 23.5 %)
and two-person households (28.2 % vs 32.0–37.1 %), and overstates 3+ persons by 7.6–12.7 points
combined; how that excess splits across 3..7+ cannot be determined from SCB tables. This is to be
stated as a limitation in the manuscript.

## Scope

In scope: the query, the provenance note, living docs, the run protocol below.
Out of scope: sampling `household_size` conditional on age (no SCB table supports it), the
hash-seed dependence of the sampler (a separate defect; see Prerequisites), and the global tier
`config/mapping/scb/`.

## Implementation (done on the branch)

| File | Change |
|---|---|
| `src/population_synthetic/generators/real/sweden/fetch_service.py` | `ContentsCode` `BE0101CZ` → `BE0101DK` in `fetch_household_size`, with a comment on the unit |
| `scripts/generate/generate_scb_population.py` | `HushallT03` table note names the series (`BE0101DK`, persons) so the output's `metadata.tables_used` records the unit |
| `docs/scb_population_and_comparison.md` | table row names the persons series |
| `docs/scb_population_distribution_analysis.md` | §12 query names the series and the residual child bias |
| `docs/reference/scb-pxweb-catalog/scb-source-audit.md` | row 7 records the series switch |
| `docs/architecture/sweden-generation-explorer/js/data.js` | `household` node: table name, query and note |

Dated audits (`docs/audit_scb_comparison_api_rooting_2026-05-11.md`,
`docs/scb02_comparison_category_mapping_2026-05-11.md`) are left as historical records.

Unchanged by design: `parsers.py::parse_household_size` (same dimension and labels),
`config/mapping/scb_native/household_size.json` (same seven categories), every synthetic file.

## Prerequisites before re-sampling

1. **Hash seed.** The real sampler iterates a Python `set` in its sex-fallback steps, so its output
   depends on the interpreter's hash seed. With a random seed about 850 `employment_type` values
   differ from the published reference; with `PYTHONHASHSEED=0` the current code reproduces it
   exactly. Re-sample with `PYTHONHASHSEED=0` (and fix the set iteration in a separate change).
2. **SCB cache.** `SCBPxWebClient` caches responses under `config/database/caches/scb/` with a
   90-day TTL on file mtime; nine tables in use are past it and the rest expire around
   2026-10-13. Extend the TTL for this run so only the new `BE0101DK` query is fetched live; any
   other live re-fetch could pick up an SCB revision and change other attributes.
3. **Expected diff.** `sample_from` draws exactly one uniform per persona whatever the
   probabilities (verified by re-sampling seed 42: only `household_size` changed, all other
   attributes byte-identical). After re-sampling, diff against
   `data/scb_api/scb_population_n10000_seed42_merge-status-edu_2026-07-16.json`; any change outside
   `household_size` stops the run.

## Re-run protocol (not started)

All compute except step 4. Every step needs `--force` because each skips existing outputs.

1. Re-sample the real population (`scripts/generate/generate_scb_population.py`, seed 42,
   n 10000, `PYTHONHASHSEED=0`); point `config/synthetic/axes/countries/swedish.yaml:5` and
   `swedish_02.yaml:5` at the new file.
2. `mapping --force`, `validate_mapped`, `population_cap --force` (selection is seeded, so the same
   personas are kept).
3. `fidelity`, `real_population_stats`, `model_ranking`, `method_significance`,
   `generation_metadata` is unaffected, `cost_efficiency` (reads `model_ranking`), each `--force`.
4. **`persona_realism --slug real_{country} --force`** — LLM calls, the real competitor only. Its
   cache is keyed by persona id and round count, so without `--force` it silently reuses the old
   verdicts; `--rewrite-artifacts` replays old attribute values and is not a substitute. Consider
   running it together with the judge context-leak fix
   (`docs/development/plans/pending/fix-claude-cli-conversation-leak.md`).
5. `realism_ranking --force`, `figure_selection --force`.

## Verification

- `ruff check src/` and `pytest` pass (no test hard-codes `BE0101CZ`).
- The new real population's `household_size` shares match the `BE0101DK` row above within sampling
  error (n = 10,000).
- The diff check in Prerequisites 3 passes.
- The re-run fidelity report shows the `household_size` change only on that axis for every model.

## Manuscript follow-up

State the unit (persons) and the residual child bias in Methods; update any `household_size`
numbers, figures and rankings after the re-run.

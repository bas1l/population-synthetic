# Runbook — Mapping-Gap Investigation & Fix

**Purpose.** A self-contained guide to reproduce, end to end, the work done in the Swedish
campaign of 2026-06-29: assess how well each model maps onto the canonical comparison schema,
identify mapping issues, and close the *genuine* gaps without inventing data. Point an agent
at this file and say *"do this for `<country>`"* and it has everything it needs.

**Scope of "the same work":** (1) an analysis of model state + per-attribute mapping gaps,
(2) a plan, (3) the harvest → triage → fix → verify loop, (4) the written deliverables.

**Golden rule (applies throughout).** Map only *semantic descriptors* of a category — a
synonym, an inflected form, a translation, an unambiguous nature-descriptor. **Never** map an
occupation title, a hallucination, or a macro-category into a specific class: that fabricates a
distribution and violates the no-synthetic-distributions rule (see CLAUDE.md). When a value
can't be resolved without *guessing* its class, leave it unmapped — it correctly counts as
`Non-standard label`.

---

## 0. Orientation — where everything lives

- **Run outputs:** `{output_base}/01_Raw/{country}_*/persona_*/identity.json`
  where `output_base` is read from `config/experiment_defaults.yaml`
  (currently `F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data`).
- **Comparison reports:** `{output_base}/03_Analysis/{country}_*/...json` (+ CSV + chart PNGs).
- **Extractor (generated → schema):** `src/population_synth/comparison/extractor.py`
  — `_extract_flat()` and the `_normalize_<attr>()` / `_normalize_<attr>_it()` helpers.
- **Evaluator (marginals + TV + unmapped counts):** `src/population_synth/comparison/evaluator.py`.
- **Aliases:** `config/assets/scb_reference/category_mappings.json` (Sweden),
  `config/assets/istat_reference/category_mappings.json` (Italy) — `pipeline_label_mappings`.
- **Harvester:** `scripts/_throwaway_harvest_unmapped.py` (Step 2 below).
- **Comparison scripts:** `scripts/analyze/compare_pipeline_to_scb.py` (single run, Sweden),
  `scripts/analyze/compare_pipeline_to_istat.py` (Italy), `scripts/analyze/compare_all_pipelines.py` (batch).
- **Worked examples / prior output:** `docs/swedish_model_state_and_mapping_2026-06-29.md`,
  `docs/swedish_mapping_fix_2026-05-29.md`.

### How mapping works (and the two ways it silently fails)

`_extract_flat` resolves each attribute through a cascade:
`_json_lookup` (JSON alias) → keyword heuristics in `_normalize_<attr>()` → `_fuzzy_match` →
fallback `"Non-standard label"` (flagged + appended to the `unmapped` list).

Failure modes to watch for and fix when found:
- **Pass-through leak** — a helper that `return raw` on no-match (instead of `None`/
  `"Non-standard label"`), so the raw value poses as a real category and is *not* counted as
  unmapped. Collapse it at the call site with a canonical-output membership check (see
  `_EMPLOYMENT_TYPE_OUTPUT` / `_CIVIL_STATUS_OUTPUT` in extractor.py).
- **Silent collapse** — a field that buckets to `"Non-standard label"` *without* appending to
  `unmapped` (housing_tenure did this), hiding its raw values from any log-based harvest. Add
  the `unmapped.append(f"{attr}={raw!r}")`.

Note: `normalizer.py::normalize_raw_to_schema` (the *reference* path; now a thin facade over
`reference_mapper/base.py::BaseReferenceMapper`) passes unmapped values through via `_ci_get`;
reported unmapped-% is therefore a **lower bound** where it's involved.

---

## 1. Investigation — analyse model state & mapping gaps

Goal: a report like `docs/swedish_model_state_and_mapping_2026-06-29.md`.

1. **Coverage:** list `{output_base}/01_Raw/{country}_*` runs; note model × strategy coverage and
   persona counts (which models are complete, thin, or un-run).
2. **Quality:** read several `03_Analysis/{country}_*/*.json` reports; record mean and
   per-attribute `tv_distance` (low = good). Separate *sampling-hard* attributes (high TV even
   when fully mapped — e.g. household_size, age_group, region, industry_sector) from *mapping*
   problems.
3. **Mapping status:** from the reports' `unmapped` / `unknown_count_b` fields plus Step 2's
   harvest, build a per-attribute verdict: solved / genuine-gap / partly-unmappable / noise.
4. Write it up: root cause (generative config → free-form labels → mappings must catch all),
   the coverage matrix, the quality snapshot, and the per-attribute mapping table that marks
   **genuine categories currently unmapped** distinctly from the noise floor.

## 2. Harvest the real unmapped values (never guess)

Theoretical "config-category vs mapping-key" diffs are unreliable — drive the fix from data.

```
python scripts/_throwaway_harvest_unmapped.py --country <country>
```

Writes `scratch_unmapped_harvest_<country>.txt`: a per-attribute, frequency-sorted table of
the distinct raw values that failed to map (merging both the extractor's `unmapped` warnings
and the pass-through leaks). Console prints ASCII summary only (Windows cp1252 can't print
non-ASCII labels; read the file for the actual strings).

If adding a **new country**: add a `_CANONICAL_OUTPUT["<country>"]` entry (the pass-through
fields' real output values, read from the `_normalize_<attr>_it`-style helpers) so leak
detection works.

## 3. Triage by frequency

Open the file. Ignore the freq-1 long tail (mostly hallucinations). Inspect `count >= 2–3`
rows — those are the systematic gaps. Classify each cluster:

- **Genuine → canonical target.** e.g. `Båda föräldrarna bor tillsammans` → Nuclear Family;
  `in a relationship` / `cohabitant` → Married; `hyres*` / student / shared → Rental;
  `fulltid` → Permanent Full-time; `Hög` → Wealthy.
- **Noise → leave unmapped.** Occupation titles in a contract-type field (`Software
  Developer`), hallucinations (`samarbeta`), category confusions (`Egen hemförsäkring` = home
  *insurance*), macro-regions (`Svealand`), ambiguous tokens (`Living with parents`).

## 4. Apply the fix (lowest-risk mechanism first)

1. **JSON alias** in the country's `category_mappings.json` → `pipeline_label_mappings`:
   for discrete exact tokens, *especially* ones unsafe as substrings (e.g. bare `Hög`, which
   would false-match `Hög utbildning`). Pure data, no code risk.
2. **Heuristic keyword stem** in `_normalize_<attr>()`: for inflection-heavy clusters where one
   stem replaces a dozen JSON keys (`båda föräldra`, `hyres`). **Guard ordering** so the more
   specific branch wins (e.g. `condominium`/`cooperative` → tenant-owned *before* generic
   `owned` → owner-occupied). The helpers are shared across countries — non-target-language
   stems won't collide, but verify.
3. **Structural code fix** when you hit the failure modes from §0: collapse a pass-through field
   to `"Non-standard label"` with a canonical-output set; add a missing `unmapped.append(...)`;
   normalize separators (`raw.lower().replace("_", " ")`) where snake_case output is dropping.

Compliance check on every entry: is it a label *translation*, or am I *guessing* a class? If
the latter, don't add it.

## 5. Verify (three gates, then regenerate)

1. **Re-harvest** (Step 2): target-field occurrence counts should fall; macro-regions /
   hallucinations should **remain** (proof you didn't force-map noise).
2. **No-regression on a clean run** (catches over-broad stems): regenerate a model that was
   already clean and confirm its target-field TV/unknown are essentially unchanged:
   ```
   python scripts/analyze/compare_pipeline_to_scb.py --model-id claude_haiku --strategy-id all_pick \
       --country-id <country> --no-charts --output <scratch>/check.json
   ```
   (Italy: `scripts/analyze/compare_pipeline_to_istat.py`.)
3. **Honest-accounting awareness:** collapsing pass-through leaks makes `unknown_count_b`
   *rise* on noisy runs while TV holds/improves — that is correction, not regression. Confirm
   no attribute's TV gets worse anywhere.

Then regenerate the full set and lint:
```
python scripts/analyze/compare_all_pipelines.py --country <country>     # all reports + charts
ruff check src/population_synth/comparison/extractor.py
```
Confirm **no new** lint errors by diffing against the baseline:
`git show HEAD:src/population_synth/comparison/extractor.py | ruff check -`.

## 6. Deliverables & cleanup

- Updated `category_mappings.json` + `_normalize_*` helpers (the fix).
- Regenerated reports/charts under `{output_base}/03_Analysis/`.
- A short triage record: what was mapped, and what was deliberately left unmapped and why.
- If a field's residual is dominated by **field-misuse** (e.g. occupation strings in a
  contract-type field), flag it as a **generation-prompt / model-behaviour** issue, not a
  mapping gap — the remedy is a tighter prompt or constrained config, not more aliases.
- Delete `scratch_unmapped_harvest_<country>.txt`. Keep the throwaway harvester.

---

## Country entry points

| Concern | Sweden / SCB | Italy / ISTAT |
|---|---|---|
| Mappings JSON | `config/assets/scb_reference/category_mappings.json` | `config/assets/istat_reference/category_mappings.json` |
| Normalizer helpers | `_normalize_<attr>` | `_normalize_<attr>_it` |
| Canonical label sets | `*_LABELS` | `*_LABELS_IT` |
| Single-run compare | `scripts/analyze/compare_pipeline_to_scb.py` | `scripts/analyze/compare_pipeline_to_istat.py` |
| Batch / harvest | `--country swedish` | `--country italian` |

When defining canonical-output sets (harvester, collapse checks), read the values the
`_normalize_*` helpers actually **return** — not the `*_LABELS` input constants, whose
casing/slash-forms differ from real output.

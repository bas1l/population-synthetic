# Persona Data-Quality Observations

**Date:** 2026-07-24
**Status:** Observation only — no analysis, no decisions, no fixes proposed.

This is a plain record of two things noticed while running the Swedish analysis
pipeline. It exists so the next person starts from the same facts. It intentionally
does **not** recommend any change.

Data root: `F:\liu-onedrive-nospecial-carac\_Teams\Gauss\02_Data`

---

## Observation 1 — `identity.json` is not always present in a `persona_*` folder

Each generated persona lives in its own `persona_XXXXX/` directory. Some of these
directories contain an `identity.json`; some contain only `llm_interactions.jsonl`
(the LLM call log) and **no** `identity.json`.

Because the downstream steps that read personas key off `identity.json`, a folder
without one is effectively invisible to them. The counts that appear later in the
run (the mapped population `n=…`, and the persona-realism `judged: written=…`)
therefore come out **below 100**, even though 100 persona folders were selected.

Counts observed (Swedish, `claude_haiku`):

| Combo | Raw `persona_*` dirs | Raw dirs *with* `identity.json` | Capped dirs | Capped dirs *with* `identity.json` |
|---|---|---|---|---|
| `all_generate_evaluate_pick` | 500 | 245 | 100 | 48 |
| `all_generate_evaluate_random_pick` | 500 | 120 | 100 | 22 |
| `all_generate_pick` | 500 | 351 | 100 | 68 |
| `all_pick` | 100 | 100 | 100 | 100 |

Notes on what was seen:
- The folders missing `identity.json` still exist and still contain
  `llm_interactions.jsonl`.
- The shortfall tracks the strategy: the `all_generate_evaluate_*` /
  `all_generate_pick` strategies show many folders without `identity.json`; the plain
  `all_pick` strategy shows none missing (100/100).
- Example of a folder that has it — `population_cap/swedish_all_generate_evaluate_pick_claude_haiku/persona_00001/`
  contains `identity.json` and `llm_interactions.jsonl`. Other sibling folders in the
  same combo contain only `llm_interactions.jsonl`.

Where this surfaces in the console output:
- Mapping line, e.g. `... swedish_all_generate_evaluate_pick_claude_haiku.json (n=48, skipped=0)`
- Persona-realism line, e.g. `combo ... judged: written=48 ... (new rounds ok=144 ...)`
  (144 = 48 personas × 3 rounds).

Open question left for the reader (not answered here): whether a `persona_*` folder
without `identity.json` represents a *failed/incomplete generation* or an
*intentionally-discarded candidate* of the generate-evaluate strategies.

---

## Observation 2 — some field values are inherently wrong

Separately from the count issue, some persona field values are not valid for the
field they sit in. The concrete example seen before is a **city name appearing where a
country is expected** — e.g. `Stockholm` showing up as a country-level value.

This is recorded here only as an observation that bad/mismatched category values exist
in the persona data. No judgement is made here about how many, which fields, or why.

(Related earlier note: the birth-field realism discrepancy between `birth_location`
and `birth_country_detail`.)

---

## Scope of this document

Purely informative. It lists what was observed, with the numbers and file locations to
reproduce it. Any interpretation, cause analysis, or remediation is out of scope and
left to whoever picks this up.

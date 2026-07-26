# simulation_config_006_swedish_generative_guided

**Created:** 2026-07-24 · **Base:** `simulation_config_004_swedish_generative.json`

A copy of config `004` with **three** field `description` strings refined to better orient the
model. Everything else — the `instruction` block and all other category descriptions — is
byte-identical to `004`. This file **does not override** `004`: no axis or manifest points to it
yet. Config `004` remains the baseline that produced the current benchmark results; `006` exists
for future runs and A/B comparison.

## Why this upgrade exists

An investigation into the validation-gate `__UNMAPPED__` rates (see the manuscript analysis note
`…/Manuscripts/40_llm-population-fidelity-benchmark/analysis-notes/employment-mapping-confound.md`)
found that a few attributes fail to map heavily — up to **68.6%** for `employment_type` on
deepseek-r1-14b — largely because their prompt `description` **under-specifies the question**, not
because the model lacks the knowledge. Diagnosed failure modes:

- **`employment_type`** — the prompt asked for "the type of employment contract" as free text with
  no mention of the two dimensions the target schema needs (contract **duration** and weekly
  **working hours**). Weak models returned occupations ("Software Developer"); mid-tier models
  returned a single dimension ("temporary", no hours) that the 9-cell attachment×hours grid cannot
  place. Empirically, **no model that supplied both dimensions ever failed to map.**
- **`employment_status`** — the flat "current employment status" phrasing was less explicit than it
  could be about asking for the persona's basic work situation.
- **`parental_structure`** — "household structure … as a child" was vague about the fact that the
  attribute is specifically about **which parents were present**, inviting off-schema answers
  (custody arrangements, extended-family descriptions).

## What changed (only these three)

| field | `004` (baseline) | `006` (guided) |
|---|---|---|
| `parental_structure` | "The household structure the persona grew up in as a child." | "The family composition the persona grew up in as a child — specifically, which parents were present." |
| `employment_status` | "The persona's current employment status." | "Whether the persona is currently in work — and if not, their main current activity instead." |
| `employment_type` | "The type of employment contract the persona holds." | "The type of employment contract the persona holds — not the occupation or job title — including its duration and the number of weekly working hours." |

**Revision 2026-07-25:** the `employment_type` description gained the "— not the occupation or job
title —" clause. A first pilot run (deepseek × all_generate_pick × `swedish_02`) showed the
duration/hours hint made the model *decorate* answers with contract terms (e.g. "software developer
(permanent, full-time)", which maps) but it still often *led* with a bare occupation ("Manager",
"Software Developer", which does not). The added clause disambiguates by contrast without naming any
canonical value, so it stays value-agnostic.

## Design intent: value-agnostic

The revisions clarify the **question**, not the **answer**. They name the *dimensions* of a valid
answer (e.g. duration + working hours for `employment_type`) and the *subject* (which parents were
present), but deliberately **do not enumerate the canonical category values** (e.g. never
"Permanent"/"Temporary"/"Full-time", hence "duration" and "number of weekly working hours"). This
keeps the free-generation paradigm intact — the model still invents its own value — while removing
the ambiguity that made a share of the failures a prompt artifact rather than a fidelity signal.

## Not included

The proposed shared **system-instruction** addition (a global "answer with a single canonical
label as used in official statistics" line) was **discarded** — `006` keeps the `instruction`
block identical to `004`.

## Status / next step

Because `006` changes what the prompt asks, runs made with it are a **new condition**, not a
retroactive fix to the `004` results. To use it, point a new manifest/axis at this file and run the
two most diagnostic combos first — `deepseek × all_generate_pick` (tests the `employment_type`
disambiguation) and `haiku × all_generate_evaluate_random_pick` (tests the candidate-pool effect) —
then compare `employment_type` / `employment_status` / `parental_structure` unmapped rates against
the `004` baseline before wider adoption.

# Plan: Continue the manuscript red-line dictation

**Date:** 2026-08-17
**Author:** Basil
**Status:** Pending
**Base Branch:** `dev`
**Branch:** `feature/manuscript-red-line-dictation`

> **Scope note.** This is a *documentation* plan with **no code changes**. The deliverable
> lives outside git, in the OneDrive manuscript folder. The standard Testing Plan and
> Rollback sections are therefore omitted rather than filled with placeholders — there is
> nothing to unit-test and nothing to revert beyond a markdown file that is versioned by
> its own change log. Kept in the repo because manuscript-driven plans have precedent here
> (`plans/completed/manuscript-fidelity-tables.md`, `method-comparison-significance-figures.md`).

---

## Overview

Capture the intended narrative flow ("red line") of the LLM population-fidelity manuscript by
dictation, section by section, into a working note beside the two existing structural notes.
Methods and Results are captured; seven sections remain. The purpose is to fix the *intended*
argument in writing so a restructure can be diffed against the *current* text rather than
reconstructed from memory.

## Problem Statement

The manuscript has a structural snapshot (`manuscript-skeleton_2026-08-14.md`, what the paper
**is**) and an argument map (`results-derivation-ladder_2026-08-14.md`, what it **derives**),
but no record of what it **should say and in what order**. Without that third document a
proposed restructure has nothing to be judged against, and the reasoning behind decisions
already taken in conversation — section ordering, subsection naming, SCB's dual role — exists
only in chat history.

## Goals

### In Scope

1. Dictate and restructure the seven remaining sections: Abstract, Introduction, Related Work,
   Discussion, Limitations, Conclusion, Reproducibility.
2. Review and validate the M4 (analysis techniques) inventory table, which is currently an
   inference rather than a dictation.
3. Once the red line is complete, produce a delta table against
   `manuscript-skeleton_2026-08-14.md`: intended flow vs. current `.tex`, per section, with a
   verdict column.

### Out of Scope

- **Any edit to the `.tex` sources or the PDF.** The red line is a planning artefact; it does
  not touch `automated/`.
- **Resolving the two empirical gaps** (see Risks). Those need analysis runs, not dictation,
  and belong in their own plans.
- Restructuring the manuscript itself. This plan produces the map, not the move.

## Success Criteria

- [ ] All ten paper sections present in `## The red line` with a stated job, claim, and handoff.
- [ ] `## Key points (TL;DR)` reads end-to-end as a single chain with no broken links.
- [ ] Every dictation turn preserved verbatim under `## Raw dictation`, with transcription
      readings flagged where speech-to-text was ambiguous.
- [ ] M4's inventory table reviewed by Basil; each row either confirmed, corrected, or cut.
- [ ] Open items list contains only items that are genuinely blocked on data, not on dictation.
- [ ] Delta table against the 2026-08-14 skeleton written as its own file.

## Definitions

- **Red line:** the intended narrative through-line — for each section, the job it does, the
  single claim it must land, what it inherits from the previous section, and what it hands to
  the next. Explicitly *not* prose, and *not* a description of the current text.
- **Captured (a section is "captured"):** it appears in `## The red line` with all four of
  job / claim / inherits / hands-forward stated, **and** its source dictation appears verbatim
  in `## Raw dictation`. A section summarised from conversation without a verbatim source is
  not captured.
- **Inferred (a passage is "inferred"):** written by reasoning backwards from what other
  sections require, not from dictation. Inferred passages carry an explicit marker and stay in
  Open items until reviewed.

---

## Technical Design

### Approach

Append-only dictation capture in a three-layer markdown note. Each new turn is restructured
into the red line, its verbatim text appended to `## Raw dictation`, and any decision recorded
in the Decisions table. Re-dictation of already-captured material is appended as a dated
addendum, never a silent overwrite — the verbatim layer is authoritative if the restructured
layer is ever wrong.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Three-layer note in `analysis-notes/` | Matches the `figure-caption` house convention for dictated material; sits with its two siblings; untouched by `/sync-manuscript` | Not under version control | **Chosen** |
| In-repo `docs/development/` note | Git history | Contradicts the manuscript folder's CLAUDE.md ("do not move the manuscript back into the code repo"); splits the trio across two roots | Rejected |
| Directly into `automated/drafting-source/` | Adjacent to the prose it will shape | That folder's CLAUDE.md forbids hand-curation there; `/sync-manuscript` owns it and would collide | Rejected |
| Restructure the `.tex` as we go | No intermediate artefact | Destroys the ability to diff intended vs. current; commits to changes before the argument is settled | Rejected |

### Artefacts and ownership

| Artefact | Location | Owner | Must NOT |
|----------|----------|-------|----------|
| Red line | `analysis-notes/manuscript-red-line_2026-08-17.md` | Hand-curated (this plan) | be written by `/sync-manuscript`; be moved into git |
| Structural baseline | `analysis-notes/manuscript-skeleton_2026-08-14.md` | Frozen 2026-08-14 | be edited — it is the diff target |
| Derivation ladder | `analysis-notes/results-derivation-ladder_2026-08-14.md` | Frozen 2026-08-14 | be edited |
| Delta table | `analysis-notes/manuscript-red-line-delta_<date>.md` (Phase 3) | Hand-curated | be merged into the red line — it churns, the red line does not |
| LaTeX sources | `automated/2026-07-02_TMLR/sections/*.tex` | `/sync-manuscript` | be touched by this plan |

Full folder path (no-special-character alias, use in commands):
`F:\liu-onedrive-nospecial-carac\_Teams\Gauss\04_Dissemination\Manuscripts\40_llm-population-fidelity-benchmark\`

---

## Implementation Plan

### Phase 1: Complete the dictation
**Goal:** all ten sections captured.

- [ ] 1.1 — Dictate Introduction and Related Work (the framing half: what gap, what prior work)
- [ ] 1.2 — Dictate Discussion and Limitations (the interpretation half)
- [ ] 1.3 — Dictate Conclusion, Abstract, Reproducibility (Abstract last — it summarises a
      spine that must already exist)
- [ ] 1.4 — Verify the TL;DR chain reads end-to-end with no broken handoffs

**Files modified:** `analysis-notes/manuscript-red-line_2026-08-17.md`

**Dependencies:** None

### Phase 2: Validate the inferred material
**Goal:** no passage in the red line is both load-bearing and unvalidated.

- [ ] 2.1 — Basil reviews the M4 analysis-techniques inventory; confirm / correct / cut per row
- [ ] 2.2 — Confirm or reject the inferred argument in M4 that reference status over a
      *distribution* confers no authority over *individuals*
- [ ] 2.3 — Re-check every transcription note against what was meant
- [ ] 2.4 — Clear resolved entries out of Open items

**Files modified:** `analysis-notes/manuscript-red-line_2026-08-17.md`

**Dependencies:** Phase 1 (later sections may add to the inventory)

### Phase 3: Diff intended against current
**Goal:** a per-section verdict on where the paper already matches the red line and where it does not.

- [ ] 3.1 — Table: section × (intended job | what the `.tex` currently does | verdict)
- [ ] 3.2 — Flag sections whose current content has no home in the intended flow
- [ ] 3.3 — Flag intended content with no current home (i.e. text that must be written)
- [ ] 3.4 — Cross-check against `manuscript-motivation-map.md` (in-repo) so the motivation
      audit and the structural delta do not contradict each other

**Files modified:** new `analysis-notes/manuscript-red-line-delta_<date>.md`

**Dependencies:** Phase 2

---

## Documentation Plan

- [ ] Keep the red line's own `## Change log` current — it is the versioning mechanism, since
      the folder is outside git
- [ ] No repo `README.md` / `CLAUDE.md` change: this plan adds no code, no command, no module

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Inferred passages harden into "decisions" simply by sitting in the file | High | High | Every inferred passage carries an explicit marker and an Open-items entry; Phase 2 exists solely to clear them |
| **5.3's richness claim has no measurement** — unmapped rate conflates *finer-grained* with *wrong* | High | High | Needs a classified sample of unmapped values (the `audit-unmapped` triage). Own plan; until then 5.3 must not assert the claim as a result |
| **No v2-grid cost data** — only the stale 8-model sweep | High | Med | Either regenerate before 5.3 is written, or drop the cost item. Publishing 5.3 numbers from a different experiment than 5.1/5.2 is worse than omitting them |
| Results regenerate mid-restructure, invalidating the delta | Med | Med | The delta is structural (does the section exist, what job does it do), not numeric; it survives a results refresh |
| Dictation drifts from the captured spine over multiple sessions | Med | Low | Verbatim layer is authoritative; re-dictation appends a dated addendum rather than overwriting |
| OneDrive sync conflict creates a duplicate copy | Low | Med | Single-author file; check the folder for `*-conflict*` copies before each session |

---

## References

- Red line: `analysis-notes/manuscript-red-line_2026-08-17.md` (external manuscript folder)
- Structural baseline: `analysis-notes/manuscript-skeleton_2026-08-14.md`
- Derivation ladder: `analysis-notes/results-derivation-ladder_2026-08-14.md`
- Motivation audit (in-repo): `docs/development/manuscript-motivation-map.md`
- Folder contract: `40_llm-population-fidelity-benchmark/CLAUDE.md`

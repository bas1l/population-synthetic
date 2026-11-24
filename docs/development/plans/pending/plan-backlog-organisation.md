# Plan: Organise the plan backlog and the branch landscape

**Date:** 2026-09-16
**Author:** Basil
**Status:** Draft
**Base Branch:** `dev`
**Branch:** `feature/plan-backlog-organisation`

> **Scope note.** A housekeeping plan. It changes plan documents (moves between `pending/`,
> `active/`, `completed/`, `archived/`) and git refs; it changes no code. The two code-adjacent
> items (the failing flow-default test and the uncommitted rm-ANOVA worktree) are decision gates,
> not fixes written here.
>
> **Base branch note.** The plan was written on `feature/publication-figure-presentation-layer`.
> That branch was merged into local `dev` on 2026-09-16 (PR process bypassed on Basil's
> authorization) and deleted, so the base is now `dev`.

---

## Overview

The plan folders no longer describe the repository. Nine of the twelve `pending/` documents
describe work that is already shipped, refer to modules that no longer exist, or name a base
branch that is gone. The figure work is now folded into one branch,
`feature/publication-figure-presentation-layer`, merged into local `dev` on 2026-09-16 without a
PR. Local `dev` is ahead of `origin/dev` and still carries one failing test. A worktree holds
uncommitted rm-ANOVA assumption-check work built on a commit that predates the gain forest. This
plan records the evidence, lists the decisions only Basil can take, and orders the work so each
step starts from a clean `dev`.

## Problem Statement

1. **`pending/` overstates the backlog.** A reader cannot tell a real queued feature from a
   May-2026 note about `src/population_synthetic/comparison/extractor.py`, which does not exist.
2. **Base branches that no longer exist.** `/plan-implement` reads `**Base Branch:**`; five
   pending plans would branch from a ref that is gone.
3. **Local `dev` carries one failing test and is unpushed.** The figure branch landed locally;
   pushing `dev` still needs `gh auth login` (token returns 401) or plain git credentials.
4. **Uncommitted statistics work sits on a stale base.** The rm-ANOVA worktree edits
   `stats_tests.py`, `builder.py`, `test_method_comparison.py` and `sub-packages.md`, all of which
   the gain forest also changed after that worktree's base commit.

## Goals

### In Scope
1. Classify every plan in `pending/`, `ideas/`, `active/` with evidence.
2. Move shipped/superseded plans to `completed/` or `archived/` with a one-line reason.
3. Make `dev` green after the local merge of `feature/publication-figure-presentation-layer`.
4. Decide the fate of the rm-ANOVA worktree and, if kept, bring it onto `dev`.
5. Delete merged or empty branches locally and on `origin`.
6. Order what remains and state what blocks each item.

### Out of Scope
- Implementing any remaining feature plan (each keeps its own `/plan-implement`).
- Rewriting a stale plan's content beyond its `Base Branch` line and a status note.
- Writing the rm-ANOVA feature itself; only its landing path is planned here.

## Success Criteria

- [ ] Every file in `pending/` describes work that is neither shipped nor referring to deleted modules.
- [ ] `active/` holds only plans whose branch exists.
- [ ] Every pending plan's `**Base Branch:**` names a branch that exists (`dev` by default).
- [x] `feature/publication-figure-presentation-layer` is merged into `dev` (locally, 2026-09-16).
- [ ] `pytest` passes on `dev`.
- [ ] The rm-ANOVA worktree is either merged/queued on a branch rebased onto `dev`, or explicitly discarded; no uncommitted work remains in `.claude/worktrees/`.
- [ ] `git branch -a` lists no branch that is 0 commits ahead of `dev`, except `dev`/`main`.

## Definitions

- **Shipped:** the plan's deliverable exists on `dev` (file, module or merge commit cited).
- **Superseded:** the plan's problem is solved by a different design already on `dev`, or the
  plan names files/scripts that no longer exist so it cannot be executed as written.
- **Stale base:** `**Base Branch:**` names a branch absent from `git branch -a`.
- **Blocked:** executable, but waiting on a named decision or upstream merge.
- **Ready:** executable today from `dev`, no open decision.

---

## Done on 2026-09-16

Evidence: `git log --oneline --graph -25`, `git branch -a`, `git worktree list`.

- Pair-grid significance ramp (`Blues_r`) and editable SVG text committed on
  `feature/method-pair-significance-grids` (`29d1817`, `fab61aa`); record plan
  `completed/pair-grid-significance-ramp-and-editable-svg.md` (`615992e`).
- Gain forest committed on a new `feature/method-gain-forest` (`c861598`, `bd42044`, `87106d1`,
  plan `0d3cc20`).
- `pending/transposed-reference-centred-grids.md` committed (`f6b2a94`). It reaches `dev` only
  with the figure PR.
- Folded with `--no-ff`: `method-gain-forest` (`5aa84ed`) → `method-pair-significance-grids`
  (`7ec7631`) → `figure-selection-04-figures` (`89aa93e`) →
  `publication-figure-presentation-layer`. The three child branches are deleted; their plans are in
  `completed/`. `figure-selection-04-figures.md` is *Completed (with open items)*: the manual GUI
  check (node last, unlocks after its nine upstreams, honours `bypass`) is unticked.
  `method-gain-forest.md`'s one open box is struck (Basil declined the `figure_selection.yaml`
  entry); `method-pair-significance-grids.md`'s is a conditional `CLAUDE.md` edit.
- `validation-attrition-and-cost-efficiency-processes.md` marked Completed and moved to
  `completed/` (`46e59c8`; merged via PR #18, `1264a4f`).
- Local `feature/paired-t-method-significance` deleted (PR #19 merged, `f3306d3`).

---

## Current inventory

Evidence gathered read-only on 2026-09-16 after the wrap-up.

### Active plans and open branches

| Plan / branch | Branch state | Open boxes | Real status | Evidence |
|---|---|---|---|---|
| `publication-figure-presentation-layer` | exists, 35 ahead of `dev`, 0 behind; contains the whole folded figure work | 1 | ready for PR, blocked on `gh auth` and the failing test | open box: very long attribute label at single-column width, untested (`wrap_to_width`/`fit_to_page` handle it in principle; no live attribute exercises it) |
| `feature/rm-anova-assumption-checks` (worktree `.claude/worktrees/agent-a591e644675bb0a90`) | at `1263298` (old pair-grids tip), 20 ahead of `dev`, all of them already on the figure branch | none written | **uncommitted work, no plan in the repository** | modified: `stats_tests.py` (+307), `builder.py`, `analyze_method_significance.py`, `test_method_comparison.py`, `comparison-metrics.md`, `sub-packages.md`; untracked: `plans/completed/rm-anova-assumption-checks.md`, `tests/test_rm_anova_assumptions.py`. Since `1263298` the figure branch changed `stats_tests.py`, `builder.py`, `test_method_comparison.py`, `sub-packages.md`: four of six files overlap. |

Failing test on the figure branch tip:
`tests/test_axis_facet_defaults.py::test_flow_default_selects_exactly_the_highest_version_strategies`
(1 failed, 16 passed). The committed `config/gui/flows/generate_parallel.yaml` selects only
`all_generate_evaluate_random_pick_v2`; the test expects all five v2 strategies. The working tree
additionally has uncommitted run-knob edits to that file (`n: 600 → 160`, model
`openrouter_qwen35_flash → openrouter_kimi_k3`), which must not be committed.

### Pending plans and the idea

| Plan | Base | Real status | Evidence |
|---|---|---|---|
| `fix-rent-substring-overmapping` | `dev` | **ready** (numbers stale) | `config/mapping/scb_native/housing_tenure.json:194` still has `"rent"` under `contains`, no parent guard. Measurements date from 2026-08-05; a later token pass (`5c68c99`, 2026-08-20) changed the file, so the 74-persona count must be re-measured in its Phase 1. |
| `transposed-reference-centred-grids` | `dev` | **blocked** on two decisions (below) and on the figure PR merging | plan's own *Sequencing* line; committed on the figure branch (`f6b2a94`) |
| `manuscript-red-line-dictation` | `dev` | ready, Basil-only (dictation) | 0/20 boxes; deliverable is in OneDrive, no code |
| `uniform-analysis-output-naming` | `feature/force-processing-analysis-tasks` (gone) | **stale base, largely superseded** | `completed/unify-analysis-task-naming.md` (2026-07-20) introduced `analysis_registry.yaml`, aligning task id = folder. The GUI "Compare Two Populations" output now goes to `03_Analysis/pairwise_comparison/comparison_report.json` (`score_fidelity.py:174`). Residual: `model_ranking/{country}_performance.*` filenames, now also a read contract in `cost_efficiency/loader.py:132`. |
| `report-unmapped` | `feature/prototype-istat-api` (gone) | **superseded** | targets `compare_all_pipelines.py` and `03_Analysis/{slug}.json` `unmapped` fields; neither exists. Replaced by `validate_mapped` (per-combo `__UNMAPPED__` CSVs) and the `audit-unmapped` skill (`completed/audit-unmapped-skill.md`). |
| `scb-population-attribute-source-audit` | `feature/sweden-employment-status-by-age` (gone) | **shipped, not moved** | `docs/reference/scb-pxweb-catalog/scb-source-audit.md` is its outcome; follow-up shipped as `completed/scb-source-improvements-implementation.md` (`1cbbd95`). |
| `investigate-international-statistical-apis` (+ `-findings`) | `feature/configurable-identity-pipeline` (gone) | **shipped, not moved** | Status line: "Investigation complete … 73 jurisdictions". Its one open box (open an implementation plan for a pilot country) is met by `completed/prototype-istat-api-access.md`, `italy-istat-population-generator.md`. |
| `investigate-unknown-unmatched-scb-labels` (+ `-findings`) | `feature/configurable-identity-pipeline` (gone) | **superseded** | built on `scripts/compare_populations.py`, `extract_population_from_pipeline.py`, `config/assets/scb_reference/category_mappings.json`; none exist. Replaced by the config-driven mapping tiers (`completed/native-highfidelity-mapping-sweden.md`, `unified-symmetric-mapping-config.md`) and the `audit-unmapped` skill. |
| `fix-identity-comparison-divergences` | none | **superseded** | fix locations `src/population_synthetic/comparison/extractor.py` and `category_mappings.json` do not exist; 2026-05-18 run on a retired strategy file. |
| `investigate-scb02-generation-issues` | none | **superseded as written** | asks about scb02 label mismatches through the same deleted `category_mappings.json`. One question may still be live: cross-check reference marginals against a fresh SCB API fetch; `real_population_stats` produces the marginals, but no drift check exists. |
| `ideas/empirical-multi-llm-comparison-studies` | none | idea, plan-ready (27/32) | not started |

---

## Decisions required from Basil

### 1. The failing flow-default test

- **Restore the five v2 strategies in the committed flow.** The test stays as the guard that the
  shipped default is the whole highest version. Cost: every ad-hoc single-strategy run leaves the
  flow file dirty, as today.
- **Weaken the test to "every selected strategy has the highest version".** A one-strategy run
  stays committable. Cost: the test no longer detects a flow that silently drops a method arm,
  which is the failure a sweep default most needs to catch.
- **Either way, the `n`/model knob edits stay uncommitted**: they are a run setting, unrelated to
  the figure PR.

### 2. The rm-ANOVA worktree

Its work is uncommitted, has a completed-plan file that was never committed, and four of its six
modified files were also changed on the figure branch after its base commit.

- **Commit in place, then rebase onto `dev`.** The figure branch is already on local `dev`, so
  this is the only remaining landing path. History stays a normal feature branch; conflicts are
  resolved once against the final shape of `stats_tests.py` and `builder.py`. Cost: the plan file
  must move from `completed/` to `active/` because nothing is merged yet.
- **Discard it.** Cost: loses roughly 365 changed lines plus a test file; only sensible if the
  assumption checks are no longer wanted.

Whichever is chosen, commit before any other git operation touches the worktree: removing the
worktree or its branch destroys the uncommitted edits.

### 3. Transposed reference-centred grids: the diverging-ramp exception

May the three reference-centred grids use a diverging colour ramp, as a second enumerated
exception to the figure-conventions "one ramp" rule?
- **Write the ADR, sanction the exception.** All four proof-of-concept figures ship. Cost: a
  second departure from the single-ramp rule; every future centred grid will cite it.
- **Refuse.** Only the transposed mapped-validity grid (sequential ramp) ships; the three centred
  grids stay in the `centred-heatmap` skill as proofs of concept.

### 4. Transposed reference-centred grids: add or replace figures

- **Replace existing stems.** `figure_selection.yaml` and manuscript figure numbers untouched.
  Cost: the model-as-row reading is gone.
- **Add new stems.** Both readings survive. Cost: new `n:` entries in `figure_selection.yaml`,
  two hardcoded counts in `tests/test_figure_selection.py` move, manuscript numbering shifts.

### 5. `uniform-analysis-output-naming`

- **Archive.** Accept `{country}_performance.*` as the name. Cost: one naming inconsistency stays.
- **Rewrite as a small plan on `dev`** renaming only the `model_ranking` outputs. Cost: touches
  the `cost_efficiency` read contract and `figure_selection.yaml` stems; forces a re-run of
  `model_ranking` and everything downstream of it.

### 6. `fix-rent-substring-overmapping`: timing relative to the manuscript numbers

- **Before the next sweep/re-analysis.** Published `housing_tenure` TV values and the pool size
  change once. Cost: the manuscript figures regenerate.
- **After submission.** Numbers stay frozen. Cost: a known, model-correlated bias on a scored
  axis stays in the published results and should be named as a limitation.

### 7. `investigate-scb02-generation-issues`

- **Archive outright.**
- **Archive, and capture the one live question** (reference-population drift against a fresh SCB
  fetch) as a new idea in `ideas/`.

---

## Technical Design

### Approach

Pure document and ref housekeeping, ordered so nothing is deleted before the evidence that it is
merged is re-checked (`git rev-list --count dev..<branch>` = 0), and so the one piece of
uncommitted work is committed before any branch operation near it.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|---|---|---|---|
| Phased, decision-gated clean-up (this plan) | Each step reversible, starts from a clean `dev` | Several steps wait on Basil | Chosen |
| Delete all stale plans outright | Fastest | Loses design history; irreversible outside git | Rejected |
| Leave `pending/` as is, fix only branches | No document churn | `/plan-implement` keeps reading dead bases | Rejected |

---

## Implementation Plan

### Phase 1: Hygiene that needs no decision
**Goal:** `pending/` holds only live plans.

- [ ] 1.1 Move `pending/scb-population-attribute-source-audit.md` → `completed/`, cite `scb-source-audit.md` and `1cbbd95`.
- [ ] 1.2 Move `pending/investigate-international-statistical-apis.md` and `-findings.md` → `completed/`, cite the ISTAT plans.
- [ ] 1.3 Move to `archived/` with a "Superseded by …" header line: `report-unmapped`, `investigate-unknown-unmatched-scb-labels` (+ findings), `fix-identity-comparison-divergences`.
- [ ] 1.4 Fix `Base Branch` to `dev` on any pending plan that survives with a dead base.

**Files Modified:** the plan files named above.

**Dependencies:** none. Can be done on `dev` independently of the figure PR.

### Phase 2: Land the figure branch
**Goal:** `dev` green after the local merge of `feature/publication-figure-presentation-layer`.

- [ ] 2.1 On `dev`: apply Decision 1 (flow file or test); confirm full `pytest` is green. Leave the `n`/model knob edits uncommitted.
- [ ] 2.2 Resolve the open box in `publication-figure-presentation-layer.md`: add a regression test for a very long attribute label at single-column width, or strike the box with a reason.
- [ ] 2.3 Run the manual GUI check recorded open in `completed/figure-selection-04-figures.md` (node last, unlocks after its nine upstreams, honours `bypass`); tick it and drop "(with open items)".
- [x] 2.4 ~~Open the PR with `/plan-pr`~~ — bypassed: merged into local `dev` with `--no-ff` on 2026-09-16 on Basil's authorization.
- [ ] 2.4b Push `dev` to `origin` once credentials work (`gh auth login`).
- [x] 2.5 `publication-figure-presentation-layer.md` moved to `completed/` (Completed with open items: 2.2).

**Files Modified:** `config/gui/flows/generate_parallel.yaml` or `tests/test_axis_facet_defaults.py`; possibly a test for label wrapping; the two plan files.

**Dependencies:** Decision 1.

### Phase 3: The rm-ANOVA worktree
**Goal:** no uncommitted work left in `.claude/worktrees/`.

- [ ] 3.1 Commit the worktree's edits and untracked files on `feature/rm-anova-assumption-checks` (or discard, per Decision 2).
- [ ] 3.2 If kept: move its plan file from `completed/` to `active/`, set Status In Progress and Base Branch `dev`.
- [ ] 3.3 If kept: rebase onto `dev`; resolve conflicts in `stats_tests.py`, `builder.py`, `test_method_comparison.py`, `sub-packages.md`; run `pytest`.
- [ ] 3.4 Remove the worktree (`git worktree remove`) once its branch holds everything.

**Dependencies:** Decision 2; Phase 2 merged for the default option.

### Phase 4: Quick fix
**Goal:** the rent over-mapping resolved at the chosen time.

- [ ] 4.1 `fix-rent-substring-overmapping`: re-measure against the current tier hash before trusting 74, then implement.

**Dependencies:** Phase 2 merged (clean `dev`); Decision 6.

### Phase 5: Blocked features
**Goal:** each blocked plan either executable or archived.

- [ ] 5.1 `transposed-reference-centred-grids`: if Decision 3 refuses the ADR, cut the plan to the mapped-validity grid only; apply Decision 4 to its stems section.
- [ ] 5.2 `uniform-analysis-output-naming`: archive, or rewrite on `dev` per Decision 5.

**Dependencies:** Phase 2 merged; Decisions 3, 4, 5.

### Phase 6: Investigations and ideas
**Goal:** the low-priority tail classified.

- [ ] 6.1 `investigate-scb02-generation-issues`: archive per Decision 7.
- [ ] 6.2 `manuscript-red-line-dictation`: Basil-driven, schedule independently of code work.
- [ ] 6.3 `empirical-multi-llm-comparison-studies`: promote with `/plan-create` when the literature section of the manuscript is next worked on.

**Dependencies:** none technically; lowest priority.

---

## Branch and remote hygiene

Read from `git branch -a`, `git ls-remote --heads origin` on 2026-09-16. Only delete a branch after
re-checking `git rev-list --count dev..<branch>` is 0.

- [ ] `origin/feature/paired-t-method-significance` (`730077d`): 0 ahead of `dev`, PR #19 merged: delete (`git push origin --delete`).
- [ ] `origin/feature/method-marginal-progression-charts` (`ff720b8`): 0 ahead of `dev`, plan in `completed/`: delete.
- [ ] Local `backup/enrich-preclean-refactor`: 0 ahead of `dev`: delete.
- [ ] Local `worktree-agent-a591e644675bb0a90`: points at `168b399`, the same commit as `main`, no unique work: delete once no worktree uses it (after Phase 3.4).
- [x] Local `feature/publication-figure-presentation-layer`: deleted after the local merge into `dev` (never pushed).
- [x] This plan's `**Base Branch:**`: reset to `dev`.
- [ ] `feature/rm-anova-assumption-checks` and its worktree: **keep** until Phase 3 completes.
- [ ] Local `main` is 280 behind `dev` (1 ahead = its own merge commit): refresh with `/publish-main` only when a release is intended; no action here.

---

## Testing Plan

### Manual Verification
- [ ] After Phase 1: `grep -n "Base Branch" docs/development/plans/pending/*.md` names only existing branches.
- [ ] After Phase 2: `pytest` green on `dev`.
- [ ] After Phase 3: `git worktree list` shows only the main worktree; `git -C <any remaining worktree> status --short` is empty.
- [ ] After hygiene: `git branch -a` shows no branch 0 ahead of `dev` other than `dev`/`main`.

---

## Documentation Plan

- [ ] No README/CLAUDE.md change: the plan moves are self-documenting via their status lines.
- [ ] Each archived plan gets a one-line "Superseded by …" header naming its replacement.

---

## Rollback Plan

1. Plan moves are single commits: revert the commit.
2. Branch deletions are recoverable from `git reflog` locally for 90 days; note each deleted
   branch's tip SHA in the commit message before `git push --delete`.
3. The rm-ANOVA work is the one irreversible risk: commit it before any worktree or branch
   removal, so a failed rebase can be aborted (`git rebase --abort`) without loss.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Removing the rm-ANOVA worktree or branch loses uncommitted statistics work | Med | High | Phase 3.1 commits first; hygiene keeps the branch until Phase 3 completes |
| rm-ANOVA and gain-forest edits conflict in `stats_tests.py`/`builder.py` | High | Med | Rebase once, after the figure PR merges, and run the full suite |
| Committing the flow-file run knobs with the Decision 1 fix | Med | Low | Stage the test/flow change by hunk; knob edits stay in the working tree |
| Archiving a plan whose idea is still wanted | Low | Low | Archive, don't delete; add the surviving question to `ideas/` |
| Rent fix shifts published numbers mid-drafting | Med | Med | Decision 6 makes the timing explicit |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|---|---|---|
| Phase 1 | under 1 hour | None |
| Phase 2 | 1-2 hours plus review | Decision 1, `gh auth login` |
| Phase 3 | 1-2 hours (conflict resolution) | Decision 2, Phase 2 |
| Phase 4 | half a day incl. re-measurement | Phase 2, Decision 6 |
| Phase 5 | per plan | Phase 2, Decisions 3-5 |
| Phase 6 | under 1 hour (excluding dictation) | Decision 7 |

---

## References

- PR #18 (validation attrition and cost efficiency), PR #19 (paired-t method significance)
- `docs/development/plans/active/publication-figure-presentation-layer.md`
- `docs/development/plans/completed/figure-selection-04-figures.md`
- `docs/development/plans/pending/transposed-reference-centred-grids.md`
- `docs/development/plans/pending/fix-rent-substring-overmapping.md`

# Idea: Empirical multi-LLM comparison studies collection

- **Slug:** empirical-multi-llm-comparison-studies
- **Created:** 2026-07-17
- **Status:** idea (refined, plan-ready — 27/32)
- **Related:** `docs/research/llm-comparison-methods/` dossier · [[project-llm-comparison-litdossier]] · [[project-paper-drafting]]

## 1. Goal & motivation
Assemble a curated collection of **already-published scientific articles that empirically tested many
different LLM models on a task and quantitatively compared their performance** — real experiments, not
metric/framework proposals. Motivation: learn the concrete *strategies* researchers use to quantify and
compare LLM performance head-to-head, as background/prior-art for the LLM-population-fidelity benchmark
manuscript.

## 2. Success criteria ("done")
- A merged, de-duplicated set of qualifying empirical comparison papers, each carrying the existing
  dossier metadata schema **plus** new comparison-specific fields (see §3).
- Every qualifying paper already in the 175-paper dossier is **tagged** as an empirical comparison study;
  a **fresh targeted sweep** adds new ones not yet present.
- Surfaced in the existing `index.html` explorer (filterable by the new "empirical comparison" flag and
  by the new fields) and reflected in `bibliography.json` / `.csv`.
- Edge cases handled: benchmark/leaderboard papers count; papers that only *propose* a metric without
  running models are excluded even if they mention many models.

## 3. Definitions (load-bearing terms)
- **Empirical multi-LLM comparison study** = a paper that *runs* **≥3 distinct LLM models** on one or more
  tasks and reports **quantitative** results comparing them. (Fewer than 3 → not "many".)
- **Qualifying types (in):** (a) head-to-head experiments, (b) benchmark/leaderboard multi-model
  evaluations (HELM/MMLU/arena-style), (c) application/domain case studies testing a handful of LLMs on a
  real task.
- **Excluded (out):** pure methodology / metric-proposal / framework papers that do **not** run an
  empirical multi-model comparison.
- **New per-paper fields to capture:** `models_compared` (list/count), `comparison_task(s)`,
  `winning/best model reported`, `evaluation_strategy` (how performance was quantified: metric +
  statistical method + judge), `is_empirical_comparison` (bool flag).

## 4. Constraints & conventions
- Reuse and extend the existing dossier at `docs/research/llm-comparison-methods/` — do **not** fork a new
  parallel corpus. `bibliography.json` stays the source of truth; regenerate `.csv`, per-category `.md`,
  and `index.html` from it.
- No fabricated metadata (same rule as the original sweep): leave fields empty if unverifiable; prefer
  metadata verified against arXiv / ACL / Semantic Scholar / publisher pages.
- Broad task/domain scope (not restricted to clinical/demographic).
- Enrichment via Semantic Scholar Graph API (abstracts, citation counts, edges), as already established.

## 5. Scope (in / out)
- **In:** empirical head-to-head studies, benchmark/leaderboard papers, application case studies; any task
  domain; the tagging pass over the existing 175 + a fresh sweep for new ones; merge into explorer.
- **Out:** pure metric/framework/methodology proposals with no model runs; single-model evaluations;
  building a brand-new separate site; re-verifying every pre-existing entry's metadata.

## 6. Decomposition (ordered steps)
1. **Re-tag pass** — classify each of the existing 175 entries as empirical-comparison (yes/no) + fill the
   new §3 fields where derivable from stored abstract/summary (LLM classification over the corpus).
2. **Fresh sweep** — targeted multi-angle web search for empirical multi-LLM comparison studies (by task
   family: reasoning, code, clinical, QA, generation, agents, multilingual, etc.), returning structured
   entries with the new fields.
3. **Merge & dedup** — fold new papers into `bibliography.json` by normalized title; keep the flag/fields.
4. **Enrich** — run Semantic Scholar enrichment on the new papers (abstracts, citations, edges).
5. **Regenerate** — rebuild `.csv`, per-category `.md`, `graph_data.json`, and `index.html`; add an
   "empirical comparison only" filter + new-field display to the explorer.

## 7. Architecture / module impact
- Touches only `docs/research/llm-comparison-methods/` (data + explorer) — no `src/` code.
- Explorer (`index.html`) gains: an `is_empirical_comparison` filter toggle and display of
  `models_compared` / `evaluation_strategy` in the detail drawer.
- Reuses the established pipeline: sweep (Workflow) → dedup/build (Python) → enrich (Semantic Scholar) →
  regenerate explorer (subagent). No new architectural boundaries.

## 8. Risks & unknowns
- **Fuzzy boundary** between "empirical comparison" and "methodology that includes experiments" — needs a
  crisp classifier rubric (the §3 ≥3-models + quantitative-comparison test).
- **Volume** — empirical multi-LLM comparisons are extremely numerous; the fresh sweep needs sensible
  caps + a note on what was left out (no silent truncation).
- **Metadata for the new fields** (`models_compared`, `winning model`) often requires reading beyond the
  abstract; may be partial for many papers → mark unknown rather than guess.
- **Open:** target size for the collection (no hard N set); whether to keep excluded methodology papers in
  the dossier (tagged out) or move them to a separate section.

---
_Refined via `/idea` (18/32 → 27/32). Promote with `/plan-create`._

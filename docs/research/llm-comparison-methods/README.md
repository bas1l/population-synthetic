# LLM Precision / Accuracy Comparison — Research Dossier

Techniques and methodologies from the scientific literature for comparing the **precision, accuracy, and overall performance of different LLMs across different task types**, plus a curated set of **empirical head-to-head studies** that actually run many LLMs on a task.

**264 papers** · **146 flagged as empirical multi-LLM comparison studies (⚑)** · 1,508 internal citation links · years 1952–2026.

## How this is organised

| File | Contents |
|------|----------|
| [`index.html`](index.html) | **Interactive explorer** — filterable library, citation/topic graph, timeline. Open in a browser (works offline). |
| [`bibliography.json`](bibliography.json) | Full machine-readable corpus — every field per entry. Source of truth. |
| [`graph_data.json`](graph_data.json) | Enriched nodes (abstracts, citation counts, empirical fields) + citation edges. |
| [`bibliography.csv`](bibliography.csv) | Flat spreadsheet view for sorting / filtering / tagging. |
| [`by-category/`](by-category/) | One markdown file per topic category (below). |

## The empirical-comparison layer

Each paper carries an `is_empirical_comparison` flag: **true** iff it actually *runs* ≥3 distinct LLMs on a task and reports quantitative results comparing them (head-to-head experiments, benchmark/leaderboard evaluations, or application case studies). Qualifying papers also carry `num_models`, `models_compared`, `comparison_tasks`, `evaluation_strategy` (metric + statistical method + any judge), and `best_model`. Filter the explorer to "empirical only" to see just these.

## Categories

| # | Category | Papers | Empirical ⚑ | File |
|---|----------|-------:|-----------:|------|
| 1 | Benchmark suites & holistic evaluation frameworks | 56 | 53 | [`01-benchmarks.md`](by-category/01-benchmarks.md) |
| 2 | Statistical methods for model comparison | 21 | 0 | [`02-statistics.md`](by-category/02-statistics.md) |
| 3 | Pairwise ranking (Elo / Bradley-Terry / Arena) | 13 | 6 | [`03-ranking.md`](by-category/03-ranking.md) |
| 4 | Item Response Theory & psychometrics | 16 | 0 | [`04-irt-psychometrics.md`](by-category/04-irt-psychometrics.md) |
| 5 | LLM-as-a-judge & automated evaluation | 16 | 5 | [`05-llm-judge.md`](by-category/05-llm-judge.md) |
| 6 | Text-generation metrics (BLEU/ROUGE/BERTScore/…) | 24 | 8 | [`06-generation-metrics.md`](by-category/06-generation-metrics.md) |
| 7 | Code-generation evaluation (pass@k, HumanEval, SWE-bench) | 21 | 15 | [`07-code-eval.md`](by-category/07-code-eval.md) |
| 8 | Calibration & uncertainty quantification | 15 | 2 | [`08-calibration.md`](by-category/08-calibration.md) |
| 9 | Reproducibility, prompt sensitivity & contamination | 15 | 5 | [`09-reproducibility.md`](by-category/09-reproducibility.md) |
| 10 | Clinical / medical LLM evaluation | 28 | 21 | [`10-clinical-medical.md`](by-category/10-clinical-medical.md) |
| 11 | Reasoning & mathematical evaluation | 21 | 18 | [`11-reasoning-math.md`](by-category/11-reasoning-math.md) |
| 12 | Multilingual, cross-task & meta-evaluation | 18 | 13 | [`12-multilingual-meta.md`](by-category/12-multilingual-meta.md) |

## Per-entry metadata schema

`title`, `authors`, `year`, `venue`, `doi_or_arxiv`, `url`, `s2_url`, `task_types[]`, `methods_metrics[]`, `summary`, `abstract`, `citationCount`, `influentialCitationCount`, `publicationDate`, `category`, and the empirical layer (`is_empirical_comparison`, `num_models`, `models_compared[]`, `comparison_tasks[]`, `evaluation_strategy`, `best_model`).

## Provenance

Two breadth-first web-search sweeps (broad methods + task-family empirical studies) → dedup by normalised title → LLM classification for the empirical flag → Semantic Scholar Graph API enrichment (abstracts, citation counts, reference edges). Metadata mostly verified against arXiv / ACL / Semantic Scholar; not every entry independently re-checked — spot-check before citing. ~13 papers unmatched on S2 (no abstract/citation).

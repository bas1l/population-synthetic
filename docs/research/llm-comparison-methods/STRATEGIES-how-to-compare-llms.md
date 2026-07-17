# How Researchers Decide Which LLM Is Better: Strategies Across 146 Empirical Studies

*A methodological synthesis of a 146-paper corpus (2020–2025) in which each study ran multiple LLMs on one or more tasks and compared them. Counts are tallied by keyword/pattern mining of each paper's `evaluation_strategy`, `methods_metrics`, `comparison_tasks`, and `title` fields. See Caveats for the reliability of these counts.*

---

## Executive summary

- **The dominant strategy is accuracy on a fixed ground-truth benchmark.** Some 97/146 papers (66%) mention accuracy / exact-match / F1, and it is the *primary* scoring basis for ~68/146 (47%). The modal paper runs 6 models on a static multiple-choice or short-answer benchmark, reports a single accuracy number per model, and declares the highest one the winner.
- **Execution-based scoring (pass@k) is the second pillar** (24/146, 16%) and is the rigor high-water mark for *closed* tasks: it scores against an objective oracle (unit tests) rather than string overlap.
- **Judged/preference methods are a substantial minority for open-ended tasks:** LLM-as-judge (16/146, 11%), human evaluation (21/146, 14%), and Elo/Bradley-Terry/pairwise battles (18/146, 12%). These cluster in the newest papers (2024–2025).
- **The single biggest methodological gap is statistical rigor.** Only ~3/146 papers (≈2%) report genuine inferential statistics tying a winner claim to uncertainty. Confidence intervals/bootstrap appear in 2 papers (1.4%), an actual significance test in ~2–3, and **multiple-comparison correction in 0 (0%)** — despite a median of 6 models compared (i.e., 15 pairwise contrasts) per paper. The overwhelming majority declare a winner from bare point estimates.
- **Robustness controls are rare.** Prompt-sensitivity handling appears in ~9 (6%), multiple runs/seeds in 7 (5%), contamination controls in 12 (8%), calibration in 11 (8%). Most rankings rest on a single prompt, single run, on benchmarks of unknown contamination status.
- **The most rigorous strategy in the corpus is crowdsourced pairwise preference aggregated by Bradley-Terry/Elo with bootstrap confidence intervals** (Chatbot Arena; Arena-Hard-Auto), which is the only approach that combines a defensible scoring signal for open-ended tasks *with* quantified uncertainty on the ranking.
- **Prompting protocol is usually unreported:** few-shot named in 25 (17%), zero-shot in 11 (8%), chain-of-thought in 21 (14%) — meaning ~2/3 of papers do not even state the shot/CoT regime under which the ranking was produced.

---

## The common strategy (the modal pipeline)

A "typical" paper in this corpus does the following, end to end:

1. **Picks a static benchmark with ground-truth labels** (MMLU-style multiple-choice, a QA set, a code set, a domain exam). Category mix in the corpus: benchmarks 53, clinical-medical 21, reasoning-math 18, code-eval 15, multilingual 13.
2. **Runs a handful of models** — median **6**, mean 9.9; 46% of papers compare ≤5 models, only 15/146 compare 21+.
3. **Scores each model with one automatic metric** — accuracy / exact-match / F1 (primary basis in 47% of papers), or pass@k for code (14%).
4. **Aggregates to a single number per model**, often macro-averaged across sub-tasks, and **ranks** — 27 papers (18%) frame the output explicitly as a leaderboard/aggregate score.
5. **Names the top-ranked model the winner** — 106/146 papers commit to a `best_model`.
6. **Reports point estimates only.** No confidence interval, no significance test, no correction for the many pairwise comparisons implied by the leaderboard. Prompt is fixed and typically singular; runs are typically single; contamination is usually unaddressed.

That pipeline is fast, reproducible, and cheap — and it is also where the corpus is methodologically weakest: the winner claim is a point comparison with no uncertainty attached.

---

## Taxonomy of strategies

Two axes structure the taxonomy: **(A) scoring basis** — how a single model's output is turned into a number — and **(B) aggregation/ranking + rigor** — how numbers become a winner. Percentages are of all 146 papers. Scoring-basis rows are non-exclusive (a paper can use several); the "primary basis" split (accuracy 47% / execution 14% / LLM-judge 8% / human 8% / pairwise-Elo 6% / reference-text 6% / other 11%) assigns each paper one dominant method.

### A. Scoring basis

| Strategy | Count | % | Best for | Key weakness | Example papers |
|---|---|---|---|---|---|
| **Accuracy / exact-match / F1 on ground-truth** | 97 | 66% | Closed tasks with a single correct answer (MCQ, classification, short QA); cheap, reproducible, objective | Doesn't fit open-ended generation; sensitive to prompt/option formatting; contamination-prone; a raw gap ≠ a significant gap | *Holistic Evaluation of Language Models* (2022); *Changing Answer Order Can Decrease MMLU Accuracy* (2024); *GSM-Symbolic* (2024) |
| **Execution-based / pass@k** | 24 | 16% | Code generation — scores against an objective oracle (unit tests), not surface text | Needs executable tasks + test suites; pass@k variance with sampling; test suites can be incomplete | *Evaluating LLMs Trained on Code* (Codex, 2021); *LiveCodeBench* (2024); *BigCodeBench* (2024); *CRUXEval* (2024) |
| **Human evaluation / expert preference** | 21 | 14% | Open-ended, safety-critical, and clinical outputs where correctness is judgment-laden | Expensive, slow, hard to reproduce; needs agreement reporting (only 4 papers report inter-rater agreement) | *Towards Expert-Level Medical QA* (Med-PaLM 2, 2023); *Chatbot Arena* (2024); *WritingBench* (2025) |
| **Elo / Bradley-Terry / pairwise battles** | 18 | 12% | Ranking many models on open-ended quality; produces a calibrated latent skill scale | Needs many comparisons; intransitivity/style bias; judge bias if pairs are LLM-scored | *Chatbot Arena* (2024); *Arena-Hard-Auto* (2024); *SKATE Tournament Eval* (2025); *Ranking LLMs without Ground Truth* (2024) |
| **LLM-as-judge** | 16 | 11% | Scalable proxy for human preference on open-ended tasks | Judge bias (position, verbosity, self-preference); needs validation against humans | *Arena-Hard-Auto* (2024); *LiveBench* (2024); *PARIKSHA* (2024); *MIRAGE / RAG for Medicine* (2024) |
| **Reference-based text metrics (BLEU/ROUGE/BERTScore)** | 14 | 10% | Translation, summarization, long-form generation with reference texts | Weak correlation with human quality; penalizes valid paraphrase; near-useless for reasoning | *LongBench* (2024); *IndicGenBench* (2024); *Multilingual MT with LLMs* (2024); *HelloBench* (2024) |
| **Calibration metrics (ECE/Brier)** | 11 | 8% | Assessing whether confidence matches correctness — orthogonal to accuracy | Not a standalone "which is better" signal; secondary axis | *Holistic Evaluation of Language Models* (2022); option-order calibration studies (2023) |

### B. Aggregation, ranking & rigor controls

| Strategy | Count | % | Best for | Key weakness | Example papers |
|---|---|---|---|---|---|
| **Leaderboard / single aggregate score / ranking** | 27 | 18% | Communicating an overall winner across many sub-tasks at a glance | Macro-average hides per-task reversals; ranking instability unquantified | *RewardBench* (2024); *MEDIC* (2024); *SKATE* (2025) |
| **Contamination controls** (live/held-out/decontaminated) | 12 | 8% | Guarding accuracy comparisons against train-set leakage | Still rare; most static-benchmark rankings uncontrolled | *LiveBench* (2024); *LiveCodeBench* (2024); *FrontierMath* (2024); *A Careful Examination of LLM Performance on GSM8k* (2024) |
| **Prompt-sensitivity / robustness controls** | 9 | 6% | Testing whether a ranking survives prompt/option reformatting | Rare; when applied, often *reveals* rankings are fragile | *PromptRobust/PromptBench* (2023); *Changing Answer Order…* (2024); *LLMs Are Not Robust Multiple Choice Selectors* (2023) |
| **Multiple runs / seeds / sampling variance** | 7 | 5% | Estimating run-to-run noise before declaring a gap real | Almost never done; single-run rankings dominate | *Codex* pass@k estimator (2021); self-consistency studies |
| **Significance testing** | ~2–3 | ~2% | Tying a winner claim to a hypothesis test | Nearly absent from the corpus | *Med-PaLM 2* (2023, blinded pairwise + significance) |
| **Confidence intervals / bootstrap** | 2 | 1.4% | Quantifying uncertainty on scores/rankings | Nearly absent | *Chatbot Arena* (2024); *Arena-Hard-Auto* (2024) |
| **Multiple-comparison correction** | 0 | 0% | Controlling false winners across many pairwise contrasts | **Not present anywhere** despite median 6 models (15 pairwise contrasts) | — |

### Head-to-head design (all 146)

- **Number of models compared:** median **6**, mean 9.9, range 0–60. Distribution: 2–3 models 31 papers; 4–5 models 36; 6–10 models 39; 11–20 models 25; 21+ models 15. So ~46% compare ≤5 models.
- **Prompting regime (as reported):** few-shot 25 (17%), zero-shot 11 (8%), chain-of-thought 21 (14%). The majority do not state the shot/CoT protocol — a reproducibility gap, since rankings are known to shift with shot count and CoT.
- **Era:** heavily 2023 (63) and 2024 (56); the rigorous pairwise/CI methods concentrate in 2024–2025.

---

## Statistical rigor analysis

This is the corpus's defining weakness. Going *beyond point estimates* is exceptional:

- **Confidence intervals / bootstrap: 2 papers (1.4%)** — *Chatbot Arena* (bootstrap CIs on Bradley-Terry/Elo, >240K votes, active pair sampling) and *Arena-Hard-Auto* (Bradley-Terry with reported confidence intervals and a model-separability analysis).
- **Genuine significance testing: ~2–3 papers (≈2%)** — *Med-PaLM 2* is the clearest: blinded physician pairwise preference ranking *with significance testing*. (Note: *HELM* explicitly states it runs **no** significance test; *Codex*'s "unbiased pass@k estimator" quantifies sampling estimation, not a between-model hypothesis test — so the naive keyword count of 4 overstates true significance testing.)
- **Multiple-comparison correction: 0 papers (0%)** — no Bonferroni/Holm/FDR/Nemenyi anywhere, even though the median paper's 6-model leaderboard implies 15 simultaneous pairwise comparisons. Every multi-model "winner" in the corpus is therefore uncorrected.
- **Inter-annotator agreement: 4 papers (3%)** and **human-correlation validation of automatic metrics: 9 papers (6%)** — so most judged/reference-metric rankings are not validated against, or reconciled with, human ground truth.

**Net finding:** roughly **3 of 146 papers (~2%)** attach quantified uncertainty to their winner claim. The other ~98% rank models on bare point estimates. Given documented prompt- and format-sensitivity (the robustness papers show accuracy swings of 13–75% from mere option reordering), a large share of "Model A beats Model B" conclusions in this literature are not demonstrably outside noise.

**Exemplars that do it right:**
- *Chatbot Arena* (2024) — pairwise human preference → Bradley-Terry/Elo → **bootstrap CIs**; the template for open-ended ranking with uncertainty.
- *Arena-Hard-Auto* (2024) — LLM-judge pairwise win-rate → **Bradley-Terry with CIs** + explicit separability/agreement-with-humans checks.
- *Med-PaLM 2* (2023) — blinded expert pairwise preference **with significance testing**.
- *Codex* (2021) — **unbiased pass@k estimator** (best-in-class handling of sampling variance for execution scoring, even if not a between-model test).
- *LiveBench / LiveCodeBench / FrontierMath* (2024) — best-in-class **contamination control** (the other axis of validity), removing a major confound from accuracy comparisons.

---

## "Which approach is better?" — a reasoned recommendation

No single method wins for all task types; the defensible choice depends on whether the task has an objective oracle. Tie each recommendation to what the strongest corpus papers actually did:

**1. Closed tasks with ground truth (MCQ, classification, short QA, math with checkable answers).**
Use **accuracy/exact-match**, but upgrade it the way almost no corpus paper does:
- Report **bootstrap confidence intervals** on each model's score and on score *differences* (as Chatbot Arena does for ratings).
- Apply **multiple-comparison correction** (Holm or Benjamini-Hochberg) across the pairwise contrasts — currently done by **zero** papers, yet mandatory once you compare a median of 6 models.
- **Control prompt sensitivity**: average over ≥3–5 prompt paraphrases and randomize option order (PromptBench; *Changing Answer Order Can Decrease MMLU Accuracy* show rankings flip otherwise).
- **Control contamination**: prefer live/held-out sets (LiveBench, FrontierMath) or report a decontamination check.
- **Average over multiple runs/seeds** at nonzero temperature and report the variance.

**2. Code and other executable tasks.**
Use **execution-based pass@k with the unbiased estimator** (Codex; BigCodeBench; LiveCodeBench). This is the corpus's most objective scoring signal — pair it with contamination-free/live problems and CIs on pass@k.

**3. Open-ended generation (writing, dialogue, summarization, clinical free-text, translation quality).**
Do **not** rely on BLEU/ROUGE/BERTScore as the arbiter (weak human correlation). Instead:
- Collect **pairwise preferences** and fit a **Bradley-Terry / Elo model with bootstrap CIs** (Chatbot Arena for humans; Arena-Hard-Auto for a validated LLM-judge proxy).
- If using an **LLM judge**, validate it against human preference and report agreement (PARIKSHA), and mitigate position/verbosity/self-preference bias.
- For high-stakes domains (clinical), use **blinded expert pairwise evaluation with significance testing and inter-rater agreement** (Med-PaLM 2).

**4. Always, regardless of task type:**
Report **per-task results alongside any aggregate** (macro-averages hide reversals), state the **prompting protocol** (shot count, CoT vs direct), and attach **uncertainty** to every winner claim. A ranking without a confidence interval and without prompt/seed/contamination controls — the corpus norm — should be read as a hypothesis, not a result.

**Bottom line:** the single most defensible pattern in the corpus is the Chatbot-Arena/Arena-Hard family — *pairwise comparison → Bradley-Terry/Elo → bootstrap CIs*, extended for closed tasks to *accuracy → bootstrap CIs → multiple-comparison correction → prompt/seed/contamination controls*. It is defensible precisely because it is the rare approach that quantifies whether the observed gap could be noise.

---

## Caveats

- The `evaluation_strategy` and `methods_metrics` fields are **LLM-extracted summaries** of each paper, not the papers themselves. They may omit or compress methods a paper actually used (e.g., a study may have computed CIs that the summary didn't mention), so counts for the rarer, easily-omitted practices (CIs, significance tests, seeds) are **lower bounds** and all figures are approximate.
- Counts come from **keyword/pattern matching** over those summary fields; wording variation causes both misses and false positives. Where the naive keyword count was misleading (e.g., "significance": HELM explicitly reports *none*; Codex's estimator is not a between-model test), the numbers above are hand-corrected and flagged.
- Scoring-basis categories are **non-exclusive** (a paper can use several methods); the "primary basis" split applies a priority rule and is one defensible assignment among several.
- The corpus skews to **2023–2024 benchmark/NLP papers**; the rigor picture would differ in, e.g., a pure statistics or psychometrics venue. Conclusions describe *this corpus*, not the entire field.
- Percentages are over all 146 papers unless stated; small-count rows (≤5 papers) should be read as "rare," not as precise rates.

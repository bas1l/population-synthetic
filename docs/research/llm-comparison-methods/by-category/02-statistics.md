# Statistical methods for model comparison

_21 papers (0 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### Approximate Statistical Tests for Comparing Supervised Classification Learning Algorithms (1998)

- **Authors:** Thomas G. Dietterich
- **Venue:** Neural Computation (MIT Press) · `10.1162/089976698300017197`
- **Citations:** 4,022 citations · 278 influential
- **URL:** https://direct.mit.edu/neco/article/10/7/1895/6224 · [S2](https://www.semanticscholar.org/paper/22f0579f212dfb568fbda317cba67c8654d84ccd)
- **Task types:** classification; algorithm comparison
- **Methods / metrics:** McNemar test; 5x2 cross-validation t-test; resampled paired t-test; Type I error / power analysis
- **Summary:** Classic study of Type I error and power for five tests comparing two supervised classifiers, showing many common tests badly underestimate error. Recommends McNemar's test when models can be trained only once and introduces the 5x2 cross-validated t-test as a more powerful alternative with acceptable Type I error. The reference underpinning paired classifier comparison methodology widely reused in NLP.

### Rank Analysis of Incomplete Block Designs: I. The Method of Paired Comparisons (1952)

- **Authors:** Ralph A. Bradley, Milton E. Terry
- **Venue:** Biometrika, Vol. 39, No. 3/4, pp. 324-345 (Oxford University Press) · `10.2307/2334029`
- **Citations:** 1,596 citations · 65 influential
- **URL:** https://www.jstor.org/stable/2334029 · [S2](https://www.semanticscholar.org/paper/d0da6b23e08524d9ff8550c84dcbafb24a37f829)
- **Task types:** paired comparison experiments; preference ranking
- **Methods / metrics:** Bradley-Terry model; logistic paired-comparison likelihood; maximum-likelihood strength estimation; significance testing for treatment differences
- **Summary:** The original Bradley-Terry paper, defining the probabilistic paired-comparison model in which each item has a latent strength and the probability that item i beats item j is a logistic function of their strength difference. Strengths are estimated by maximum likelihood over observed pairwise outcomes. This model is the statistical backbone of modern LLM leaderboards (Chatbot Arena, Arena-Hard, AlpacaEval) that convert pairwise preferences into a ranking.

### Are Emergent Abilities of Large Language Models a Mirage? (2023)

- **Authors:** Rylan Schaeffer, Brando Miranda, Sanmi Koyejo
- **Venue:** NeurIPS 2023 (Advances in Neural Information Processing Systems); preprint arXiv · `arXiv:2304.15004`
- **Citations:** 705 citations · 27 influential
- **URL:** https://arxiv.org/abs/2304.15004 · [S2](https://www.semanticscholar.org/paper/29c7f009df21d0112c48dec254ff80cc45fac3af)
- **Task types:** multi-task QA; arithmetic/reasoning; BIG-Bench tasks
- **Methods / metrics:** metric-choice analysis (linear vs nonlinear); exact-match accuracy vs continuous metrics; token edit distance; Brier score; effect of test-set size on estimates
- **Summary:** Argues that so-called emergent abilities are largely an artifact of the evaluation metric rather than a genuine phase change with scale. Nonlinear or discontinuous metrics (e.g., exact-match accuracy) manufacture apparent emergence, whereas linear/continuous metrics (e.g., token edit distance, Brier score) reveal smooth, predictable scaling. It also shows too-small test sets make small models look wholly incapable. Central to any discussion of whether measured LLM 'accuracy' jumps are real or measurement-induced.

### Show Your Work: Improved Reporting of Experimental Results (2019)

- **Authors:** Jesse Dodge, Suchin Gururangan, Dallas Card, Roy Schwartz, Noah A. Smith
- **Venue:** EMNLP 2019 (ACL) · `arXiv:1909.03004`
- **Citations:** 310 citations · 21 influential
- **URL:** https://aclanthology.org/D19-1224/ · [S2](https://www.semanticscholar.org/paper/0e4cd6bae6ac1017e7b1b9bd644375aee65b8372)
- **Task types:** classification; hyperparameter search; model comparison
- **Methods / metrics:** expected validation performance curves; order statistics; compute-budget accounting; validation-score distributions
- **Summary:** Shows that a single test-set score is insufficient for concluding which model is best because results depend heavily on the hyperparameter/compute budget. Introduces 'expected validation performance' as a function of the number of search trials, revealing that several published comparisons would flip under more or less compute. Recommends reporting validation-score distributions and budgets so future model comparisons are reproducible and fair.

### Tangled up in BLEU: Reevaluating the Evaluation of Automatic Machine Translation Evaluation Metrics (2020)

- **Authors:** Nitika Mathur, Timothy Baldwin, Trevor Cohn
- **Venue:** ACL 2020 · `arXiv:2006.06264`
- **Citations:** 304 citations · 25 influential
- **URL:** https://aclanthology.org/2020.acl-main.448/ · [S2](https://www.semanticscholar.org/paper/868207797e69df5055f5c3fd4aa78a33e5a7ca45)
- **Task types:** machine-translation; metric-meta-evaluation
- **Methods / metrics:** outlier sensitivity analysis; Pearson correlation robustness; Type I / Type II error quantification; pairwise system-difference thresholding; significance testing for metric claims
- **Summary:** Shows that standard meta-evaluation of metrics (correlation with human scores) is highly sensitive to outlier systems and the specific translations sampled, producing falsely confident conclusions about which metric is best. Proposes thresholding metric-based improvements against human judgments and quantifying Type I/II errors. Categorized as statistics for its rigorous treatment of significance and reliability in metric-driven model comparison.

### To Ship or Not to Ship: An Extensive Evaluation of Automatic Metrics for Machine Translation (2021)

- **Authors:** Tom Kocmi, Christian Federmann, Roman Grundkiewicz, Marcin Junczys-Dowmunt, Hitokazu Matsushita, Arul Menezes
- **Venue:** WMT 2021 (EMNLP) · `arXiv:2107.10821`
- **Citations:** 250 citations · 14 influential
- **URL:** https://aclanthology.org/2021.wmt-1.57/ · [S2](https://www.semanticscholar.org/paper/8b7bfd0d0998a3d5407b03882d1171d78bf98a65)
- **Task types:** machine-translation; metric-meta-evaluation
- **Methods / metrics:** pairwise system-accuracy of metrics vs human; largest collection of human judgments; decision-oriented metric evaluation; recommendation of COMET/embedding metrics over BLEU; significance and reliability analysis
- **Summary:** Evaluates automatic metrics by how reliably they reproduce human decisions about which MT system is better, using the then-largest collection of human judgments. Recommends pretrained/embedding metrics (e.g. COMET, BLEURT) over BLEU for shipping decisions and gives practical thresholds for trusting a metric-based system comparison. Categorized as statistics for its decision-theoretic, accuracy-based meta-evaluation of metrics.

### With Little Power Comes Great Responsibility (2020)

- **Authors:** Dallas Card, Peter Henderson, Urvashi Khandelwal, Robin Jia, Kyle Mahowald, Dan Jurafsky
- **Venue:** EMNLP 2020 (ACL) · `arXiv:2010.06595`
- **Citations:** 156 citations · 18 influential
- **URL:** https://aclanthology.org/2020.emnlp-main.745/ · [S2](https://www.semanticscholar.org/paper/186d26390779f7c54930e05812cfe85e6973961f)
- **Task types:** classification; machine translation; human evaluation; QA/NLU benchmarks
- **Methods / metrics:** statistical power analysis; type II error / sample-size estimation; effect size (MDE); Monte Carlo simulation; BLEU; accuracy
- **Summary:** Argues that statistical power has been largely ignored in NLP, so many published comparisons cannot reliably distinguish real gains from noise. A meta-analysis shows small GLUE test sets are underpowered for most SOTA comparisons, human-rating studies rarely detect small differences, and typical 2000-sentence MT test sets have only ~75% power to detect a 1-BLEU improvement. Provides power-analysis best practices and notebooks, giving practitioners a way to compute how many samples are needed to precisely resolve a claimed accuracy difference.

### Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations (2024)

- **Authors:** Evan Miller
- **Venue:** arXiv preprint (stat.AP / cs.CL) · `arXiv:2411.00640`
- **Citations:** 96 citations · 7 influential
- **URL:** https://arxiv.org/abs/2411.00640 · [S2](https://www.semanticscholar.org/paper/4ba6a858d4c77b8b6dcd2bcf8b159eb8c1353e6b)
- **Task types:** LLM benchmark evaluation; QA; model comparison
- **Methods / metrics:** standard errors / confidence intervals; clustered standard errors; paired differences; variance reduction; power and sample-size planning; central limit theorem
- **Summary:** Reframes LLM evaluations as scientific experiments whose questions are a sample from a larger population, and supplies ready-to-use formulas for standard errors, confidence intervals, and comparisons. Covers clustered standard errors for question groups, variance reduction (e.g., resampling and paired differencing), and power/sample-size planning for evals. A practical statistical toolkit for reporting precision and comparing LLMs rigorously.

### Replicability Analysis for Natural Language Processing: Testing Significance with Multiple Datasets (2017)

- **Authors:** Rotem Dror, Gili Baumer, Marina Bogomolov, Roi Reichart
- **Venue:** TACL 2017 (MIT Press) · `arXiv:1709.09500`
- **Citations:** 84 citations · 3 influential
- **URL:** https://aclanthology.org/Q17-1033/ · [S2](https://www.semanticscholar.org/paper/ecf189b8871403a3a4f646debe5139656c2a0f4c)
- **Task types:** dependency parsing; POS tagging; sentiment classification; word similarity; multi-dataset evaluation
- **Methods / metrics:** replicability analysis; multiple-comparison correction; Bonferroni vs. Holm/Fisher combining; partial conjunction hypotheses; count of significant datasets (k)
- **Summary:** Addresses the multiple-comparisons problem that arises when an algorithm is evaluated across many datasets, where naive per-dataset testing inflates false discoveries. Introduces replicability analysis to count on how many datasets one system is significantly better while controlling error, showing methods more powerful than Bonferroni. Demonstrated on dependency parsing, multilingual POS tagging, cross-domain sentiment, and word similarity.

### Efficient Multi-Prompt Evaluation of LLMs (PromptEval) (2024)

- **Authors:** Felipe Maia Polo, Ronald Xu, Lucas Weber, Mírian Silva, Onkar Bhardwaj, Leshem Choshen, Allysson F. M. de Oliveira, Yuekai Sun, Mikhail Yurochkin
- **Venue:** NeurIPS 2024 (Curran/NeurIPS) · `arXiv:2405.17202`
- **Citations:** 80 citations · 5 influential
- **URL:** https://arxiv.org/abs/2405.17202 · [S2](https://www.semanticscholar.org/paper/a1e2557fa6d5373c8f89b8c4d426168cdf31d7d5)
- **Task types:** multi-prompt LLM evaluation; MMLU/BBH reasoning; QA
- **Methods / metrics:** Item Response Theory (Rasch model); performance-distribution/quantile estimation; budget-constrained sampling; consistency guarantees; accuracy
- **Summary:** Because single-prompt scores are unstable, this work estimates a model's full performance distribution across many prompt templates under a limited evaluation budget. Uses an Item-Response-Theory-style Rasch model to borrow strength across prompts and examples, provably consistently estimating performance quantiles. On MMLU, BBH, and LMentry it recovers 100-template quantiles at the cost of ~2 single-prompt evaluations, enabling robust prompt-robust model comparison.

### deep-significance: Easy and Meaningful Statistical Significance Testing in the Age of Neural Networks (2022)

- **Authors:** Dennis Ulmer, Christian Hardmeier, Jes Frellsen
- **Venue:** arXiv preprint (also ML Evaluation Standards workshop, ICLR 2022) · `arXiv:2204.06815`
- **Citations:** 57 citations · 3 influential
- **URL:** https://arxiv.org/abs/2204.06815 · [S2](https://www.semanticscholar.org/paper/bcef143c672029431c316fe40235671879827aa7)
- **Task types:** deep model comparison; multi-seed evaluation
- **Methods / metrics:** Almost Stochastic Order (ASO); bootstrap test; permutation/randomization test; Bonferroni correction; bootstrap power analysis
- **Summary:** Presents an open-source library packaging significance testing for deep learning, centered on the Almost Stochastic Order (ASO) test over score distributions across random seeds. Bundles bootstrap and permutation tests, Bonferroni multiple-comparison correction, and bootstrap power analysis with PyTorch/TensorFlow/NumPy compatibility. Lowers the barrier to rigorously deciding whether one neural model reliably outperforms another.

### Position: Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints (2025)

- **Authors:** Sam Bowyer, Laurence Aitchison, Desi R. Ivanova
- **Venue:** ICML 2025 Spotlight Position Paper (PMLR) · `arXiv:2503.01747`
- **Citations:** 17 citations · 0 influential
- **URL:** https://arxiv.org/abs/2503.01747 · [S2](https://www.semanticscholar.org/paper/4ca76fd94f9227eb3c2cd717206734645932dc4e)
- **Task types:** LLM benchmark evaluation; small-benchmark QA; model comparison
- **Methods / metrics:** Clopper-Pearson / Wilson intervals; Bayesian credible intervals; coverage analysis; critique of CLT/normal-approximation; small-sample uncertainty quantification
- **Summary:** Demonstrates that Central-Limit-Theorem-based error bars, standard for large benchmarks, dramatically underestimate uncertainty on the small, specialized benchmarks now common in LLM evaluation, sometimes producing intervals outside [0,1] or collapsing to zero. Recommends alternative frequentist (e.g., Clopper-Pearson / Wilson) and Bayesian methods that are easy to implement and give valid coverage at small N. Directly targets how to report precision when comparing LLMs on few datapoints.

### Signal and Noise: A Framework for Reducing Uncertainty in Language Model Evaluation (2025)

- **Authors:** David Heineman, et al. (Allen Institute for AI)
- **Venue:** arXiv preprint · `arXiv:2508.13144`
- **Citations:** 17 citations · 1 influential
- **URL:** https://arxiv.org/abs/2508.13144 · [S2](https://www.semanticscholar.org/paper/3f0c849509de91ddf09835c9a09c5887830e03e6)
- **Task types:** benchmark-design; meta-evaluation; multi-task
- **Methods / metrics:** signal-to-noise ratio; relative dispersion; relative standard deviation; decision accuracy; subtask filtering; checkpoint averaging
- **Summary:** Defines quantitative signal (spread separating better from worse models) and noise (score variability under perturbation) metrics and their ratio (SNR), linking SNR directly to decision reliability and predictive accuracy of benchmark rankings. Proposes interventions—metric selection, filtering noisy subtasks, checkpoint averaging—to raise benchmark SNR. Provides a principled statistical basis for judging whether a leaderboard gap is real signal or noise.

### Please, Don't Forget the Difference and the Confidence Interval when Seeking for the State-of-the-Art Status (2022)

- **Authors:** Yves Bestgen
- **Venue:** LREC 2022 (ELRA) · `arXiv:2205.11134`
- **Citations:** 11 citations · 1 influential
- **URL:** https://aclanthology.org/2022.lrec-1.640/ · [S2](https://www.semanticscholar.org/paper/99eadf1d9a8c9200b2aa84ac3040514b26937f00)
- **Task types:** classification; system comparison; benchmark reporting
- **Methods / metrics:** bootstrap confidence intervals; effect size / score difference; critique of NHST; interval-based reporting
- **Summary:** Argues that chasing 'SOTA' status via significance stars is misleading and advocates reporting the effect size (the score difference) together with bootstrap confidence intervals. Shows how CIs communicate both the magnitude and the uncertainty of a system's advantage far better than a binary significant/not-significant verdict. A concise argument for interval-based reporting when comparing NLP system accuracy.

### Exact Paired-Permutation Testing for Structured Test Statistics (2022)

- **Authors:** Ran Zmigrod, Tim Vieira, Ryan Cotterell
- **Venue:** NAACL 2022 (ACL) · `arXiv:2205.01416`
- **Citations:** 8 citations · 1 influential
- **URL:** https://aclanthology.org/2022.naacl-main.360/ · [S2](https://www.semanticscholar.org/paper/631910c820c905cd0ed71b787e1d0d049b38f6ae)
- **Task types:** classification; structured prediction; sequence labeling
- **Methods / metrics:** exact paired-permutation test; randomization test; accuracy; F-measure; efficient dynamic-programming p-value
- **Summary:** Provides an efficient algorithm to compute the exact paired-permutation test for a class of structured metrics (including accuracy and F-measure) rather than relying on Monte Carlo approximation. Replaces the 2^N enumeration with a tractable exact computation, removing sampling error from the p-value. Enables rigorous, exact significance testing of the gap between two systems on standard NLP metrics.

### Dropping Just a Handful of Preferences Can Change Top Large Language Model Rankings (2026)

- **Authors:** et al.
- **Venue:** ICLR 2026 · `arXiv:2508.11847`
- **Citations:** 7 citations · 1 influential
- **URL:** https://arxiv.org/abs/2508.11847 · [S2](https://www.semanticscholar.org/paper/56ca286b3920897383678fc6c62de71eb18ffc93)
- **Task types:** human-preference pairwise comparison; leaderboard robustness analysis
- **Methods / metrics:** Bradley-Terry model; worst-case data-dropping robustness metric; influence-function / approximate maximum influence perturbation; identification of influential preferences; Chatbot Arena vs MT-bench comparison
- **Summary:** Proposes a method to measure how robust Bradley-Terry LLM rankings are to dropping a worst-case tiny fraction of preference data, and finds top-model rankings can be extremely fragile (e.g., removing 0.003% of Chatbot Arena preferences can change the top model). It also identifies the specific influential preferences responsible and shows expert-annotated MT-bench rankings are more robust than crowdsourced Arena. Quantifies statistical (in)stability of pairwise LLM leaderboards.

### Is Elo Rating Reliable? A Study Under Model Misspecification (2025)

- **Authors:** Shange Tang, Yuanhao Wang, Chi Jin
- **Venue:** arXiv preprint (stat.ML) · `arXiv:2502.10985`
- **Citations:** 4 citations · 0 influential
- **URL:** https://arxiv.org/abs/2502.10985 · [S2](https://www.semanticscholar.org/paper/fc38f3e60ee4e79437bee9186bebcd6e7165b096)
- **Task types:** LLM pairwise evaluation; game/matchup data ranking
- **Methods / metrics:** Elo rating; Bradley-Terry model; mElo / pairwise models; online gradient descent / no-regret analysis; win-rate prediction; ranking correlation; synthetic misspecification experiments
- **Summary:** Analyzes Elo's reliability when the data violate Bradley-Terry and stationarity assumptions, which the authors show is common in real matchup data. Surprisingly, Elo often out-predicts more expressive rating systems (mElo, pairwise models); the paper explains this by reinterpreting Elo as online gradient descent with no-regret guarantees and showing data sparsity favors Elo. Directly informs when Elo-based LLM rankings can be trusted.

### Statistical Significance Tests for Machine Translation Evaluation (2004)

- **Authors:** Philipp Koehn
- **Venue:** EMNLP 2004 (ACL)
- **Citations:** citations n/a
- **URL:** https://aclanthology.org/W04-3250/
- **Task types:** machine translation; system comparison
- **Methods / metrics:** paired bootstrap resampling; bootstrap confidence intervals; BLEU; p-value estimation
- **Summary:** The foundational paper introducing paired bootstrap resampling to test whether a difference in BLEU between two MT systems is statistically significant. Repeatedly resamples the test set with replacement to build an empirical distribution of the score difference and derive confidence intervals. Became the de facto significance-testing standard embedded in MT toolkits (Moses) for comparing system precision.

### The Hitchhiker's Guide to Testing Statistical Significance in Natural Language Processing (2018)

- **Authors:** Rotem Dror, Gili Baumer, Segev Shlomov, Roi Reichart
- **Venue:** ACL 2018 (ACL)
- **Citations:** citations n/a
- **URL:** https://aclanthology.org/P18-1128/
- **Task types:** classification; sequence labeling; machine translation; general NLP model comparison
- **Methods / metrics:** McNemar test; paired t-test / Wilcoxon signed-rank; bootstrap; permutation/randomization tests; sign test; test-selection decision protocol
- **Summary:** A practical protocol and survey for choosing significance tests in NLP, mapping test choice to task type, evaluation measure, and data assumptions (parametric vs. non-parametric, paired vs. unpaired). A survey of 2017 ACL/TACL papers finds significance testing is frequently omitted or misapplied. Serves as the standard decision guide for validly comparing two NLP systems' scores.

### An Empirical Investigation of Statistical Significance in NLP (2012)

- **Authors:** Taylor Berg-Kirkpatrick, David Burkett, Dan Klein
- **Venue:** EMNLP-CoNLL 2012 (ACL)
- **Citations:** citations n/a
- **URL:** https://aclanthology.org/D12-1091/
- **Task types:** parsing; machine translation; summarization; classification
- **Methods / metrics:** paired bootstrap; approximate randomization / permutation test; p-value vs. metric-gain analysis; BLEU; F1
- **Summary:** Empirically studies how paired significance tests behave for NLP systems, examining the relationship between observed metric gains and p-values and how well the i.i.d. assumption holds when test data is not truly independent. Finds that the magnitude of a metric improvement is a poor proxy for significance and characterizes when bootstrap/permutation tests agree. Guides interpretation of whether an accuracy/BLEU gap is real.

### Deep Dominance - How to Properly Compare Deep Neural Models (2019)

- **Authors:** Rotem Dror, Segev Shlomov, Roi Reichart
- **Venue:** ACL 2019 (ACL)
- **Citations:** citations n/a
- **URL:** https://aclanthology.org/P19-1266/
- **Task types:** deep model comparison; classification; sequence modeling
- **Methods / metrics:** Almost Stochastic Order (ASO); stochastic dominance / CDF comparison; epsilon violation ratio; multi-seed score distributions
- **Summary:** Because deep models' scores vary with seeds and initialization, comparing single scores or even means is inadequate. Introduces the Almost Stochastic Order (ASO) test, which compares the full empirical score distributions of two models via their CDFs and returns a violation ratio epsilon quantifying how far one model is from stochastically dominating the other. Provides a principled way to declare one model superior across many stochastic runs.

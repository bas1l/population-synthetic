# Item Response Theory & psychometrics

_16 papers (0 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### tinyBenchmarks: evaluating LLMs with fewer examples (2024)

- **Authors:** Felipe Maia Polo, Lucas Weber, Leshem Choshen, Yuekai Sun, Gongjun Xu, Mikhail Yurochkin
- **Venue:** ICML 2024 (Proceedings of Machine Learning Research, PMLR v235) · `arXiv:2402.14992`
- **Citations:** 268 citations · 30 influential
- **URL:** https://arxiv.org/abs/2402.14992 · [S2](https://www.semanticscholar.org/paper/4c0f88e80320885e8289a9af781a1101717104f2)
- **Task types:** QA; multiple-choice benchmarks; instruction-following; reasoning; LLM leaderboard evaluation; multiple-choice QA (MMLU); instruction-following (AlpacaEval); leaderboard estimation; multiple-choice QA; multi-task; efficient-evaluation
- **Methods / metrics:** Item Response Theory (2PL/3PL); latent ability estimation; item difficulty and discrimination; anchor-point selection; stratified sampling baseline; clustering baseline; mean absolute error of performance estimate; item response theory (IRT); anchor-point subset selection; performance estimation error bounds; clustering; MMLU/HELM accuracy reconstruction; Item Response Theory; gp-IRT estimator; performance estimation error; stratified sampling
- **Summary:** Landmark efficient-benchmarking paper showing that an LLM's score on large benchmarks (MMLU, HELM, Open LLM Leaderboard, AlpacaEval 2.0) can be estimated from ~100 curated 'tiny' examples with under 2% average error. It fits Item Response Theory models to leaderboard response matrices and uses the estimated item difficulty/discrimination plus latent ability to select and reweight anchor items, and compares IRT against stratified sampling and clustering. Enables cheap, frequent, apples-to-apples precision/accuracy comparison of models on standard benchmarks.

### Item response theory in AI: Analysing machine learning classifiers at the instance level (2019)

- **Authors:** Fernando Martínez-Plumed, Ricardo B. C. Prudêncio, Adolfo Martínez-Usó, José Hernández-Orallo
- **Venue:** Artificial Intelligence (Elsevier), vol. 271, pp. 18-42 · `10.1016/j.artint.2018.09.004`
- **Citations:** 137 citations · 4 influential
- **URL:** https://www.sciencedirect.com/science/article/pii/S0004370219300220 · [S2](https://www.semanticscholar.org/paper/f46cdf47ab7627cc40b166b7a471321d53b69ba2)
- **Task types:** supervised classification; dataset difficulty analysis; classifier characterization
- **Methods / metrics:** Item Response Theory; item/instance characteristic curves; difficulty, discrimination, guessing parameters; latent classifier ability; logistic IRT models
- **Summary:** Journal paper establishing the mapping of IRT onto machine-learning evaluation: instances are 'items' and classifiers are 'respondents', so instance characteristic curves yield per-instance difficulty, discrimination and guessing parameters. Shows how classifier ability and dataset-instance properties can be jointly estimated and used to characterise both models and datasets beyond aggregate accuracy. A key theoretical reference underpinning IRT-based model comparison.

### Evaluation Examples are not Equally Informative: How should that change NLP Leaderboards? (2021)

- **Authors:** Pedro Rodriguez, Joe Barrow, Alexander Hoyle, John P. Lalor, Robin Jia, Jordan Boyd-Graber
- **Venue:** ACL 2021 (59th Annual Meeting of the ACL); ACL Anthology · `10.18653/v1/2021.acl-long.346`
- **Citations:** 136 citations · 8 influential
- **URL:** https://aclanthology.org/2021.acl-long.346/ · [S2](https://www.semanticscholar.org/paper/30f233eecca2239ee1dd754914324092e53f8f19)
- **Task types:** QA (SQuAD); natural language inference; leaderboard ranking
- **Methods / metrics:** Bayesian Item Response Theory; latent ability and item difficulty/discrimination; ranking reliability; variational inference; information-theoretic item selection
- **Summary:** Foundational work re-imagining NLP leaderboards through a Bayesian IRT model where latent model skill and latent item difficulty jointly predict correctness. Demonstrates IRT-based rankings expose ranking instability, guide what to annotate, detect annotation errors and overfitting, and identify uninformative examples. Establishes IRT as a principled alternative to raw accuracy for comparing model ability.

### Building an Evaluation Scale using Item Response Theory (2016)

- **Authors:** John P. Lalor, Hao Wu, Hong Yu
- **Venue:** EMNLP 2016 (Conf. on Empirical Methods in NLP), pp. 648-657; ACL Anthology · `10.18653/v1/D16-1062`
- **Citations:** 115 citations · 5 influential
- **URL:** https://aclanthology.org/D16-1062/ · [S2](https://www.semanticscholar.org/paper/739bf9a7451712bca3094e626632dce0ae715224)
- **Task types:** recognizing textual entailment; natural language inference; test-set construction
- **Methods / metrics:** Item Response Theory; item characteristic curves; difficulty/discrimination estimation; latent ability scaling; human response calibration
- **Summary:** Early and highly-cited paper introducing IRT from psychometrics as a means for gold-standard test-set construction and NLP system evaluation, using human response patterns to estimate item difficulty and discrimination. Demonstrates the approach by building an IRT-scaled test set for Recognizing Textual Entailment and scoring systems on a latent-ability scale rather than raw accuracy. Seeds the modern line of IRT-for-NLP evaluation research.

### Making Sense of Item Response Theory in Machine Learning (2016)

- **Authors:** Fernando Martínez-Plumed, Ricardo B. C. Prudêncio, Adolfo Martínez-Usó, José Hernández-Orallo
- **Venue:** ECAI 2016 (22nd European Conf. on Artificial Intelligence), Frontiers in AI and Applications 285, pp. 1140-1148 · `10.3233/978-1-61499-672-9-1140`
- **Citations:** 85 citations · 2 influential
- **URL:** https://ebooks.iospress.nl/publication/44803 · [S2](https://www.semanticscholar.org/paper/9450a2264e28221bc3947cba64f97697febdad02)
- **Task types:** supervised classification; model diagnostics; dataset analysis
- **Methods / metrics:** Item Response Theory; classifier characteristic curves; difficulty/discrimination; latent ability estimation
- **Summary:** Conference precursor that first articulates how psychometric IRT concepts translate to machine-learning model evaluation, introducing 'classifier characteristic curves' and interpreting item difficulty/discrimination for ML datasets. Argues IRT offers a richer, instance-aware view of model ability than aggregate error rates. Widely cited as the conceptual bridge between psychometrics and ML evaluation.

### Anchor Points: Benchmarking Models with Much Fewer Examples (2024)

- **Authors:** Rajan Vivek, Kawin Ethayarajh, Diyi Yang, Douwe Kiela
- **Venue:** EACL 2024 (18th Conf. of the European Chapter of the ACL); ACL Anthology · `arXiv:2309.08638`
- **Citations:** 76 citations · 9 influential
- **URL:** https://aclanthology.org/2024.eacl-long.95/ · [S2](https://www.semanticscholar.org/paper/d4085ae0f004624a3141734d3a88a9ebbc803a55)
- **Task types:** multiple-choice benchmarks; QA; text classification; model ranking
- **Methods / metrics:** anchor point selection; correctness-pattern clustering; confidence/difficulty estimation; Kendall/Spearman rank correlation; performance-prediction error
- **Summary:** Introduces Anchor Point Selection, which finds small representative subsets of benchmark examples (cluster centroids in the space of models' correctness patterns) that reliably rank models and predict per-instance behaviour on the full set. Shows 1-30 anchor points outperform uniform sampling at ranking models across 87 model-prompt pairs, and connects the correctness-pattern geometry to IRT-style difficulty. A core reference for efficient, subset-based model comparison.

### Efficient Benchmarking (of Language Models) (2024)

- **Authors:** Yotam Perlitz, Elron Bandel, Ariel Gera, Ofir Arviv, Liat Ein-Dor, Eyal Shnarch, Noam Slonim, Michal Shmueli-Scheuer, Leshem Choshen
- **Venue:** NAACL 2024 (Conf. of the North American Chapter of the ACL); ACL Anthology · `arXiv:2308.11696`
- **Citations:** 66 citations · 3 influential
- **URL:** https://aclanthology.org/2024.naacl-long.139/ · [S2](https://www.semanticscholar.org/paper/9a4765547cb43ab221fe262df7405f6795557d8c)
- **Task types:** HELM scenarios; multi-task LLM benchmarking; model ranking
- **Methods / metrics:** Decision Impact on Reliability (DIoR); benchmark reliability; example subsampling; rank-correlation stability; compute-reliability trade-off
- **Summary:** Systematically studies the compute-reliability trade-off in LLM benchmarking and introduces the Decision Impact on Reliability (DIoR) measure to quantify how benchmark design choices affect ranking stability. Shows that reliable HELM rankings survive removing ~99% of examples, motivating principled example reduction. Complements IRT-based subset methods by formalizing when a reduced benchmark preserves correct model comparisons.

### Lost in Benchmarks? Rethinking Large Language Model Benchmarking with Item Response Theory (2025)

- **Authors:** Hongli Zhou, Hui Huang, Ziqing Zhao, Lvyuan Han, Huicheng Wang, Kehai Chen, Muyun Yang, et al.
- **Venue:** AAAI 2026 (Oral); preprint arXiv · `arXiv:2505.15055`
- **Citations:** 33 citations · 1 influential
- **URL:** https://arxiv.org/abs/2505.15055 · [S2](https://www.semanticscholar.org/paper/a43a21d3b8bcede381110da630421afca45c8e5d)
- **Task types:** multiple-choice benchmarks; QA; reasoning; benchmark quality auditing
- **Methods / metrics:** neural/Pseudo-Siamese IRT; item difficulty/discrimination/feasibility; latent ability estimation; benchmark reliability and validity; subset construction
- **Summary:** Introduces PSN-IRT (Pseudo-Siamese Network for Item Response Theory), a neural IRT architecture with a rich item-parameter set for auditing benchmark measurement quality. Analyzes 11 LLM benchmarks (41,871 items) and surfaces significant, varied shortcomings in their reliability and validity, then uses PSN-IRT to build more trustworthy, compact evaluation subsets. Advances neural IRT for both benchmark diagnosis and efficient model comparison.

### Fluid Language Model Benchmarking (2025)

- **Authors:** Valentin Hofmann, David Heineman, Ian Magnusson, Kyle Lo, Jesse Dodge, Maarten Sap, Pang Wei Koh, Chun Wang, Hannaneh Hajishirzi, Noah A. Smith
- **Venue:** COLM 2025 (Conference on Language Modeling) · `arXiv:2509.11106`
- **Citations:** 25 citations · 5 influential
- **URL:** https://arxiv.org/abs/2509.11106 · [S2](https://www.semanticscholar.org/paper/3f1e2ba485fb4c8a5f6da4178ab573e18af8c87e)
- **Task types:** multiple-choice benchmarks; QA; reasoning; adaptive LLM evaluation
- **Methods / metrics:** Item Response Theory; computerized adaptive testing; Fisher information item selection; latent ability estimation; validity/variance/saturation metrics; measurement efficiency
- **Summary:** Proposes Fluid Benchmarking, which fits an IRT model to existing LM evaluation results and then dynamically selects items per model via computerized adaptive testing (CAT), since an item's value depends on the model's ability level. Reports gains on four axes — efficiency, validity, variance, and benchmark saturation — e.g. higher validity and lower variance on MMLU with 50x fewer items. A state-of-the-art adaptive approach to precise, cheap LLM measurement.

### Adaptive Testing for LLM Evaluation: A Psychometric Alternative to Static Benchmarks (ATLAS) (2025)

- **Authors:** Peiyu Li, Xiuxiu Tang, Si Chen, Ying Cheng, Ronald Metoyer, Ting Hua, Nitesh V. Chawla
- **Venue:** preprint (arXiv) · `arXiv:2511.04689`
- **Citations:** 17 citations · 3 influential
- **URL:** https://arxiv.org/abs/2511.04689 · [S2](https://www.semanticscholar.org/paper/087ce2837a0d5562bc95a40e77a327a6d033366c)
- **Task types:** multiple-choice benchmarks; adaptive LLM evaluation; model discrimination
- **Methods / metrics:** Item Response Theory; computerized adaptive testing; Fisher information item selection; ability estimation precision; item-count reduction
- **Summary:** Presents ATLAS, an IRT-driven computerized-adaptive-testing framework that uses Fisher-information-guided item selection to estimate LLM ability while cutting required items by up to 90% at fixed precision. Shows adaptive testing can distinguish models with identical raw accuracies and reconstruct full benchmark performance patterns. A direct psychometric replacement for static benchmarks aimed at precise, discriminating model comparison.

### Learning Compact Representations of LLM Abilities via Item Response Theory (2025)

- **Authors:** Jianhao Chen, Chenxu Wang, Gengrui Zhang, Peng Ye, Lei Bai, Wei Hu, Yuzhong Qu, Shuyue Hu
- **Venue:** preprint (arXiv) · `arXiv:2510.00844`
- **Citations:** 5 citations · 2 influential
- **URL:** https://arxiv.org/abs/2510.00844 · [S2](https://www.semanticscholar.org/paper/801eee2a332989ca16e3eccc01d8d625f5bae26d)
- **Task types:** model routing; benchmark performance prediction; multi-benchmark evaluation
- **Methods / metrics:** multidimensional Item Response Theory; model ability vectors; query difficulty/discrimination; Mixture-of-Experts; performance prediction error; routing accuracy
- **Summary:** Models answer correctness as an interaction between low-dimensional model-ability vectors, query discrimination vectors, and query difficulty, learning all three jointly with a Mixture-of-Experts network. The resulting compact ability embeddings achieve state-of-the-art model routing and performance prediction on unseen benchmarks. Shows IRT-style latent factors give transferable, comparable representations of what each LLM is good at.

### JE-IRT: A Geometric Lens on LLM Abilities through Joint Embedding Item Response Theory (2025)

- **Authors:** Louie Hong Yao, Nicholas Jarvis, Tiffany Zhan, Saptarshi Ghosh, Linfeng Liu, Tianyu Jiang
- **Venue:** preprint (arXiv) · `arXiv:2509.22888`
- **Citations:** 2 citations · 0 influential
- **URL:** https://arxiv.org/abs/2509.22888 · [S2](https://www.semanticscholar.org/paper/cb010af0211e4465f71903410d89dbc318fac4b2)
- **Task types:** multiple-choice benchmarks; QA; topical/ skill diagnosis; model comparison
- **Methods / metrics:** joint-embedding Item Response Theory; geometric difficulty (embedding norm); directional semantic embedding; latent ability; out-of-distribution analysis
- **Summary:** Proposes a geometric IRT that jointly embeds LLMs and questions in a shared space where question-direction encodes semantics/topic and vector norm encodes difficulty, with correctness driven by their geometric interaction. Replaces a single global model ranking with topical specialization and lets new models be added by fitting one embedding, while explaining out-of-distribution behaviour via directional alignment. A modern neural/embedding extension of IRT for fine-grained ability comparison.

### Auditing LLM Benchmarks with Item Response Theory (2026)

- **Authors:** Sander Land, Daniel M. Bikel
- **Venue:** preprint (arXiv) · `arXiv:2605.30504`
- **Citations:** 0 citations · 0 influential
- **URL:** https://arxiv.org/abs/2605.30504 · [S2](https://www.semanticscholar.org/paper/bdf3031cb456354d1b0df2c51feb41f3bb16c05a)
- **Task types:** preference benchmarks; multiple-choice QA; reward-model evaluation; label-error detection
- **Methods / metrics:** Item Response Theory; item difficulty/discrimination residuals; mislabel detection precision; latent ability across 114 models
- **Summary:** Uses an IRT-based indicator over responses from 114 models to flag likely mislabeled examples across seven preference and multiple-choice benchmarks, reaching ~95% precision in the top-200 flagged items. Reveals labeling-heuristic and annotation errors and shows reward models often encode stylistic rather than factual preferences. Positions IRT as a data-quality auditing tool that makes model comparisons more trustworthy.

### Item Response Theory for Natural Language Processing (Tutorial) (2024)

- **Authors:** John P. Lalor, Pedro Rodriguez, João Sedoc, Jordan Boyd-Graber
- **Venue:** EACL 2024 Tutorials; ACL Anthology · `aclanthology.org/2024.eacl-tutorials.2`
- **Citations:** citations n/a
- **URL:** https://aclanthology.org/2024.eacl-tutorials.2/
- **Task types:** QA; NLI; leaderboard analysis; dataset construction; NLP evaluation methodology
- **Methods / metrics:** Item Response Theory (1PL/2PL/3PL); multidimensional IRT; neural IRT; latent ability; item difficulty/discrimination; response-pattern modeling
- **Summary:** A survey/tutorial consolidating a decade of IRT-for-NLP work: fitting IRT models to human and machine response patterns, estimating item difficulty/discrimination and model ability, and applying these to leaderboard analysis, dataset construction, error detection, and efficient evaluation. Serves as the canonical entry point and methodological reference for applying psychometric latent-trait models to NLP/LLM benchmarking. Includes multidimensional and neural IRT extensions.

### Item Response Scaling Laws: A Measurement Theory Approach for Efficient and Generalizable Neural Scaling Estimation (2026)

- **Authors:** Sang Truong, Yuheng Tu, Rylan Schaeffer, Sanmi Koyejo
- **Venue:** preprint (arXiv) · `arXiv:2606.07616`
- **Citations:** 0 citations · 0 influential
- **URL:** https://arxiv.org/abs/2606.07616 · [S2](https://www.semanticscholar.org/paper/bbdfd95c04c6ea39c0a279ce12f77b454503f533)
- **Task types:** multi-benchmark evaluation; performance/scaling prediction; reasoning; QA
- **Methods / metrics:** Item Response Theory; neural scaling laws; latent ability and item parameters; parameter-complexity reduction; cross-benchmark performance prediction
- **Summary:** Integrates Item Response Theory with neural scaling laws to estimate model performance across many benchmarks while reducing parameter complexity from O(M×N) to O(M+N) by sharing latent item and model parameters. Yields more efficient and generalizable scaling-law estimation that predicts benchmark accuracy from latent ability. Bridges psychometric measurement theory and scaling-law-based precision/accuracy forecasting.

### Efficient Safety Benchmarking via Item Response Theory (2026)

- **Authors:** Fabio Spagliardi, Mírian Silva, Ayan Datta, Aiden Zhou, Vamshi Bonagiri, Diogo Cruz
- **Venue:** preprint (arXiv) · `arXiv:2606.20626`
- **Citations:** 0 citations · 0 influential
- **URL:** https://arxiv.org/abs/2606.20626 · [S2](https://www.semanticscholar.org/paper/3c694c57fbab6739c695598e3dffbf42b7c40312)
- **Task types:** safety benchmarks; red-teaming evaluation; model ranking
- **Methods / metrics:** Item Response Theory; item informativeness/discrimination; adaptive item selection; evaluation-cost reduction; ranking-accuracy preservation
- **Summary:** Applies IRT to LLM safety evaluation, using estimated item difficulty/discrimination to identify the most informative safety-benchmark items and prune redundant ones. Reports 80-99.8% reductions in evaluation cost while preserving model ranking accuracy on safety benchmarks. Extends the efficient-benchmarking / anchor-item paradigm from capability to safety measurement.

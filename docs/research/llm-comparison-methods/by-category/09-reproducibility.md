# Reproducibility, prompt sensitivity & contamination

_15 papers (5 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design or: How I learned to start worrying about prompt formatting (2023)

- **Authors:** Melanie Sclar, Yejin Choi, Yulia Tsvetkov, Alane Suhr
- **Venue:** ICLR 2024; preprint arXiv · `arXiv:2310.11324`
- **Citations:** 834 citations · 44 influential
- **URL:** https://arxiv.org/abs/2310.11324 · [S2](https://www.semanticscholar.org/paper/17a6116e5bbd8b87082cbb2e795885567300c483)
- **Task types:** classification; multiple-choice QA; few-shot in-context learning
- **Methods / metrics:** FormatSpread; performance spread (best-worst format); accuracy range reporting; Thompson-sampling format search; cross-model rank correlation
- **⚑ Empirical multi-LLM comparison** — compared: LLaMA-2-13B; other open-source LLMs · strategy: Measures accuracy spread (best-minus-worst format) across semantically-equivalent prompt formats via FormatSpread, plus cross-model rank correlation of format performance across several LLMs
- **Summary:** Introduces FormatSpread, a method to measure how much LLM performance varies across semantically equivalent prompt formats. Finds spreads of up to 76 accuracy points from trivial formatting changes, with format rankings weakly correlated across models, undermining single-format comparisons. Recommends reporting a performance range across plausible formats rather than one arbitrary prompt.

### Fine-Tuning Pretrained Language Models: Weight Initializations, Data Orders, and Early Stopping (2020)

- **Authors:** Jesse Dodge, Gabriel Ilharco, Roy Schwartz, Ali Farhadi, Hannaneh Hajishirzi, Noah A. Smith
- **Venue:** arXiv preprint · `arXiv:2002.06305`
- **Citations:** 735 citations · 41 influential
- **URL:** https://arxiv.org/abs/2002.06305 · [S2](https://www.semanticscholar.org/paper/baf60d13c98916b77b09bc525ede1cd610ed1db5)
- **Task types:** fine-tuning; GLUE/NLU classification
- **Methods / metrics:** seed/initialization variance decomposition; expected (best) validation performance; early-stopping analysis; distribution over runs
- **Summary:** Quantifies the substantial run-to-run variance when fine-tuning BERT on GLUE, isolating weight initialization and training-data order as comparably large, partly independent sources of variability where best/worst seeds can differ by more than a point. Shows that single-run comparisons can yield incorrect conclusions and that expected-best-performance curves better characterize a method. Motivates reporting variance and multiple seeds in benchmark comparisons.

### Large Language Models Are Not Robust Multiple Choice Selectors (2023)

- **Authors:** Chujie Zheng, Hao Zhou, Fandong Meng, Jie Zhou, Minlie Huang
- **Venue:** ICLR 2024; preprint arXiv · `arXiv:2309.03882`
- **Citations:** 474 citations · 42 influential
- **URL:** https://arxiv.org/abs/2309.03882 · [S2](https://www.semanticscholar.org/paper/570e4fec8c8f1c96b76accbb07d40e0528aafb4a)
- **Task types:** multiple-choice QA (MMLU, ARC, etc.)
- **Methods / metrics:** option-permutation robustness test; selection-bias / token-bias quantification; PriDe debiasing; standard deviation of recall across positions; balanced accuracy
- **⚑ Empirical multi-LLM comparison** — 20 models · compared: 20 LLMs (specific names not enumerated in abstract) · strategy: Option-permutation robustness testing across 20 LLMs on 3 benchmarks, quantifying selection/token bias and reporting balanced accuracy and recall variance across option positions, with PriDe debiasing
- **Summary:** Demonstrates that LLMs harbor a selection bias, preferring specific option IDs (e.g., 'A') regardless of content, making MCQ scores unstable under option-position permutation. Attributes the bias mainly to token bias and proposes PriDe, a label-free debiasing method that estimates and removes the option-ID prior. Explains why multiple-choice benchmark accuracy can be fragile and how to correct it.

### PromptRobust (PromptBench): Towards Evaluating the Robustness of Large Language Models on Adversarial Prompts (2023)

- **Authors:** Kaijie Zhu, Jindong Wang, Jiaheng Zhou, Zichen Wang, Hao Chen, Yidong Wang, et al.
- **Venue:** preprint arXiv (later PromptBench library, JMLR 2024) · `arXiv:2306.04528`
- **Citations:** 310 citations · 15 influential
- **URL:** https://arxiv.org/abs/2306.04528 · [S2](https://www.semanticscholar.org/paper/a2ce9963f1f072d578b1a1f1b995fec75e8c2247)
- **Task types:** sentiment analysis; natural language inference; reading comprehension; machine translation; math problem solving
- **Methods / metrics:** multi-level adversarial prompt attacks; performance drop rate (PDR); attention-based robustness analysis; 4788-prompt benchmark across 8 tasks/13 datasets
- **⚑ Empirical multi-LLM comparison** — strategy: Robustness benchmark (PromptRobust/PromptBench) measuring Performance Drop Rate (PDR) of multiple LLMs under 4,788 adversarial prompt perturbations at character/word/sentence/semantic levels across 8 tasks and 13 datasets
- **Summary:** Systematically measures LLM robustness to adversarial prompt perturbations at character, word, sentence, and semantic levels, generating 4,788 adversarial prompts over 8 tasks and 13 datasets. Quantifies large performance drops from plausible, meaning-preserving perturbations (typos, synonyms) and analyzes which prompt properties confer robustness. Establishes a standardized robustness benchmark bearing directly on evaluation reliability.

### Large Language Models Sensitivity to The Order of Options in Multiple-Choice Questions (2023)

- **Authors:** Pouya Pezeshkpour, Estevam Hruschka
- **Venue:** NAACL 2024 Findings; preprint arXiv · `arXiv:2308.11483`
- **Citations:** 274 citations · 10 influential
- **URL:** https://arxiv.org/abs/2308.11483 · [S2](https://www.semanticscholar.org/paper/fd81018bc72b030545a2d3f3010f3758ec4d48c3)
- **Task types:** multiple-choice QA; few-shot in-context learning
- **Methods / metrics:** option-order permutation; accuracy gap (best vs worst ordering); positional-bias analysis; calibration/ensembling mitigation
- **⚑ Empirical multi-LLM comparison** — strategy: Accuracy gap between best and worst option orderings (approx 13-75%) measured across multiple LLMs and benchmarks; positional-bias analysis plus calibration/ensembling mitigation
- **Summary:** Finds LLMs exhibit performance gaps of roughly 13-75% across benchmarks when multiple-choice options are reordered, even with few-shot demonstrations, revealing positional bias rather than stable competence. Investigates which reorderings trigger the largest swings and proposes calibration strategies to reduce sensitivity. A foundational demonstration that MCQ evaluation reliability depends on option ordering.

### Proving Test Set Contamination in Black Box Language Models (2023)

- **Authors:** Yonatan Oren, Nicole Meister, Niladri Chatterji, Faisal Ladhak, Tatsunori B. Hashimoto
- **Venue:** ICLR 2024; preprint arXiv · `arXiv:2310.17623`
- **Citations:** 250 citations · 18 influential
- **URL:** https://arxiv.org/abs/2310.17623 · [S2](https://www.semanticscholar.org/paper/c871377b208814713c18e25633866323a2982136)
- **Task types:** contamination detection; black-box likelihood probing
- **Methods / metrics:** exchangeability hypothesis test; canonical vs shuffled log-likelihood; permutation testing; p-value / false-positive-rate guarantees
- **Summary:** Provides provable statistical guarantees of test-set contamination without access to weights or pretraining data, exploiting exchangeability: absent contamination, all orderings of a benchmark are equally likely. A model that assigns higher likelihood to the canonical ordering than to shuffled orderings betrays memorization. Delivers a rigorous hypothesis test for benchmark leakage in black-box models.

### Lessons from the Trenches on Reproducible Evaluation of Language Models (2024)

- **Authors:** Stella Biderman, Hailey Schoelkopf, et al. (30 authors, EleutherAI)
- **Venue:** preprint arXiv · `arXiv:2405.14782`
- **Citations:** 175 citations · 14 influential
- **URL:** https://arxiv.org/abs/2405.14782 · [S2](https://www.semanticscholar.org/paper/dfa0de5cae63eacd675339fc81b13479c51bb153)
- **Task types:** multi-task benchmark QA; log-likelihood scoring; generative tasks
- **Methods / metrics:** lm-eval harness; standardized prompt/scoring protocols; log-likelihood vs generation scoring; reporting best practices; versioned task definitions
- **Summary:** Distills three years of practical experience into best practices for reproducible LM evaluation, cataloguing pitfalls such as sensitivity to setup, incomparable scoring choices, and lack of transparency. Presents the Language Model Evaluation Harness (lm-eval) as open infrastructure for independent, reproducible, extensible evaluation. A pragmatic playbook for making accuracy numbers comparable across labs.

### Stop Uploading Test Data in Plain Text: Practical Strategies for Mitigating Data Contamination by Evaluation Benchmarks (2023)

- **Authors:** Alon Jacovi, Avi Caciularu, Omer Goldman, Yoav Goldberg
- **Venue:** EMNLP 2023; preprint arXiv · `arXiv:2305.10160`
- **Citations:** 165 citations · 8 influential
- **URL:** https://arxiv.org/abs/2305.10160 · [S2](https://www.semanticscholar.org/paper/fc30093e9f55ae1c0a1d2c4c4e5341998adede66)
- **Task types:** benchmark curation; evaluation protocol design
- **Methods / metrics:** public-key encryption of test data; canary strings; training-exclusion controls; no-derivative licensing; contamination-avoidance guidelines
- **Summary:** Argues that publishing benchmarks as plain text guarantees eventual contamination via web-crawled pretraining and proposes concrete mitigations: encrypt public test data with licensing that forbids derivative redistribution, demand training-exclusion controls from closed API providers, and avoid items that co-occur with their solutions online. A prevention-focused counterpart to detection work.

### Task Contamination: Language Models May Not Be Few-Shot Anymore (2023)

- **Authors:** Changmao Li, Jeffrey Flanigan
- **Venue:** AAAI 2024; preprint arXiv · `arXiv:2312.16337`
- **Citations:** 144 citations · 4 influential
- **URL:** https://arxiv.org/abs/2312.16337 · [S2](https://www.semanticscholar.org/paper/a7b20c1bba14d4cd2b317138496d35d47142d30f)
- **Task types:** zero-shot/few-shot classification; chronological benchmark analysis
- **Methods / metrics:** chronological performance analysis; training-data inspection; membership inference; task-example extraction; pre- vs post-cutoff accuracy gap
- **Summary:** Shows LLMs perform markedly better on datasets released before their training cutoff than on later ones, indicating zero/few-shot gains partly reflect task contamination rather than genuine in-context learning. Uses chronological analysis plus training-data inspection, membership inference, and task-example extraction as complementary detectors. Cautions that reported few-shot 'abilities' can be contamination artifacts.

### Benchmark Data Contamination of Large Language Models: A Survey (2024)

- **Authors:** Cheng Xu, Shuhao Guan, Derek Greene, M-Tahar Kechadi
- **Venue:** preprint arXiv · `arXiv:2406.04244`
- **Citations:** 134 citations · 4 influential
- **URL:** https://arxiv.org/abs/2406.04244 · [S2](https://www.semanticscholar.org/paper/0fad9dd4f0ea41732594f90209907bfad1ba506e)
- **Task types:** survey / meta-analysis; benchmark QA
- **Methods / metrics:** contamination detection taxonomy; n-gram overlap; membership-inference style probes; dynamic/time-sensitive evaluation; mitigation strategy catalog
- **Summary:** Comprehensive survey of benchmark data contamination (BDC), where evaluation items leak into pretraining corpora and inflate reported scores. Organizes detection methods and mitigation strategies and reviews alternative, contamination-resistant assessment paradigms. A reference map for understanding how contamination threatens the validity of leaderboard accuracy.

### We Need to Talk About Random Splits (2021)

- **Authors:** Anders Søgaard, Sebastian Ebert, Jasmijn Bastings, Katja Filippova
- **Venue:** EACL 2021 (ACL) · `arXiv:2005.00636`
- **Citations:** 112 citations · 9 influential
- **URL:** https://aclanthology.org/2021.eacl-main.156/ · [S2](https://www.semanticscholar.org/paper/d0fcdf47561ff742c9a72495102f16646eca43b7)
- **Task types:** classification; sequence labeling; generalization evaluation
- **Methods / metrics:** random vs. standard vs. adversarial data splits; cross-validation variance analysis; worst-case/biased splitting; generalization-error estimation
- **Summary:** Responds to the call for random train/test splits by showing that both standard and random splits produce overly optimistic, low-variance performance estimates that understate error on genuinely new in-domain data. Recommends multiple independent test sets, or failing that, multiple biased/adversarial splits (e.g., train-short/test-long) to obtain more realistic generalization estimates. Directly bears on the validity and variance of benchmark comparisons.

### Investigating Data Contamination for Pre-training Language Models (2024)

- **Authors:** Minhao Jiang, Ken Liu, Ming Zhong, et al.
- **Venue:** preprint arXiv · `arXiv:2401.06059`
- **Citations:** 108 citations · 5 influential
- **URL:** https://arxiv.org/abs/2401.06059 · [S2](https://www.semanticscholar.org/paper/b2fda33b7c122c044a7faa185d250d59ce9e4453)
- **Task types:** pretraining experiments; benchmark QA; reasoning/GSM8K-style
- **Methods / metrics:** controlled contamination injection; n-gram overlap analysis; text vs ground-truth contamination; memorization measurement; downstream accuracy inflation
- **Summary:** Studies contamination at the pretraining level by deliberately injecting evaluation data into pretraining runs, distinguishing text contamination from ground-truth (answer) contamination. Shows n-gram-based definitions can miss real contamination and quantifies how memorization inflates downstream benchmark scores. Clarifies why naive overlap checks give false assurance about benchmark integrity.

### Data Contamination Quiz: A Tool to Detect and Estimate Contamination in Large Language Models (2023)

- **Authors:** Shahriar Golchin, Mihai Surdeanu
- **Venue:** Transactions of the Association for Computational Linguistics (TACL), MIT Press; preprint arXiv · `arXiv:2311.06233`
- **Citations:** 50 citations · 6 influential
- **URL:** https://arxiv.org/abs/2311.06233 · [S2](https://www.semanticscholar.org/paper/9ad167529a6365e37825ddea5d29ab2f17651959)
- **Task types:** contamination detection; multiple-choice probing
- **Methods / metrics:** Data Contamination Quiz (DCQ); perturbation-based multiple choice; exact-wording selection rate; contamination magnitude estimation
- **Summary:** Frames contamination detection as a multiple-choice quiz: the original dataset instance is presented alongside three perturbed paraphrases, and a model exposed during training gravitates toward the exact original wording. Uses this signal to both detect and estimate the degree of contamination in black-box LLMs like GPT-4. Provides a lightweight, prompt-only auditing method for benchmark leakage.

### Changing Answer Order Can Decrease MMLU Accuracy (2024)

- **Authors:** Vipul Gupta, David Pantoja, Candace Ross, Adina Williams, Megan Ung
- **Venue:** preprint arXiv · `arXiv:2406.19470`
- **Citations:** 50 citations · 0 influential
- **URL:** https://arxiv.org/abs/2406.19470 · [S2](https://www.semanticscholar.org/paper/ac0274865cfcce83bd52c654fe8a61e6d6f5eb1a)
- **Task types:** multiple-choice QA (MMLU)
- **Methods / metrics:** answer-order permutation; accuracy delta under shuffling; ranking-shift analysis; per-model sensitivity quantification
- **⚑ Empirical multi-LLM comparison** — strategy: Accuracy on MMLU measured before/after shuffling answer-option contents; per-model accuracy delta and ranking-shift analysis across all explored models
- **Summary:** Shows that merely shuffling the answer options in MMLU measurably changes model accuracy and shifts relative rankings, exposing the instability of a widely used leaderboard benchmark. Quantifies per-model sensitivity and separates genuine knowledge from position-driven artifacts. Concrete evidence that reported MMLU scores are not robust to benign presentation changes.

### A Framework for Few-Shot Language Model Evaluation (lm-evaluation-harness) (2023)

- **Authors:** Leo Gao, Jonathan Tow, Baber Abbasi, Stella Biderman, et al.
- **Venue:** Zenodo software release (EleutherAI) · `10.5281/zenodo.5371628`
- **Citations:** citations n/a
- **URL:** https://github.com/EleutherAI/lm-evaluation-harness
- **Task types:** multi-task benchmarking; question answering; reasoning; perplexity; generation; log-likelihood scoring
- **Methods / metrics:** standardized few-shot evaluation harness; log-likelihood / generation / perplexity request types; YAML-configured task definitions; reproducible identical-input evaluation; backend for HuggingFace Open LLM Leaderboard
- **Summary:** The lm-evaluation-harness is the open-source de facto standard framework for running language models over hundreds of benchmark tasks on identical inputs and code, ensuring results are reproducible and comparable across labs. It underpins the HuggingFace Open LLM Leaderboard and is used by NVIDIA, Cohere and BigScience. By fixing prompts, scoring rules and few-shot setup, it removes a major source of non-comparability in reported LLM accuracy.

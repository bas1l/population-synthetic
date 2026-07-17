# LLM-as-a-judge & automated evaluation

_16 papers (5 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena (2023)

- **Authors:** Lianmin Zheng, Wei-Lin Chiang, Ying Sheng, Siyuan Zhuang, et al.
- **Venue:** NeurIPS 2023 Datasets and Benchmarks Track · `arXiv:2306.05685`
- **Citations:** 9,801 citations · 1266 influential
- **URL:** https://arxiv.org/abs/2306.05685 · [S2](https://www.semanticscholar.org/paper/a0a79dad89857a96f8f71b14238e5237cbfc4787)
- **Task types:** open-ended multi-turn chat; instruction following; pairwise and single-answer grading; preference evaluation; multi-turn dialogue; writing; roleplay; reasoning; math; coding; STEM/social-science QA; open-ended chat; multi-turn instruction following; preference judgment; instruction-following; open-ended QA; human-preference judgment
- **Methods / metrics:** LLM-as-a-judge (GPT-4) scoring; agreement rate with human preferences (>80%); position/verbosity/self-enhancement bias analysis; MT-Bench multi-turn question set; Elo from Chatbot Arena votes; LLM-as-a-judge pairwise comparison; single-answer grading; GPT-4 judge; agreement with human preference (~80%); Elo/Chatbot-Arena correlation; LLM-as-a-judge (pairwise & single-answer grading); MT-Bench; Chatbot Arena Elo; human-judge agreement (>80%); position bias; verbosity bias; self-enhancement bias; LLM-as-a-judge; pairwise & single-answer grading; agreement rate; win-rate; bias analysis (position/verbosity/self-enhancement)
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: GPT-4; GPT-3.5; Claude; LLaMA variants; Vicuna variants · strategy: LLM-as-a-judge (GPT-4) pairwise and single-answer grading plus Chatbot Arena Elo, validated by ~80% agreement with human preferences and analysis of position/verbosity/self-enhancement biases. · best: GPT-4
- **Summary:** This paper introduces MT-Bench and formalizes using strong LLMs as automated judges, showing GPT-4 agrees with human preferences at ~80%, matching inter-human agreement. It systematically characterizes judge biases (position, verbosity, self-enhancement) and proposes mitigations, establishing the methodological basis for scalable preference-based comparison. It is the foundational reference for LLM-judge evaluation of model quality where exact-match accuracy does not apply.

### A Survey on LLM-as-a-Judge (2024)

- **Authors:** Jiawei Gu, Xuhui Jiang, Zhichao Shi, et al.
- **Venue:** Preprint (arXiv) · `arXiv:2411.15594`
- **Citations:** 1,553 citations · 128 influential
- **URL:** https://arxiv.org/abs/2411.15594 · [S2](https://www.semanticscholar.org/paper/e24424283c02fbe7f641e5b3490d7bb059f8355a)
- **Task types:** survey; evaluation methodology; bias and reliability taxonomy
- **Methods / metrics:** taxonomy of judging paradigms (pointwise/pairwise/listwise); bias mitigation strategies; consistency & reliability meta-evaluation; human-agreement metrics; prompt/ensemble/fine-tuning enhancement methods
- **Summary:** Comprehensive survey organizing the LLM-as-a-judge field: what to judge, how to judge, judging paradigms, and how to build reliable judges. Catalogs biases (position, verbosity, self-enhancement), mitigation and calibration strategies, meta-evaluation benchmarks, and open challenges, serving as an orienting map for automated model-based evaluation.

### Large Language Models are not Fair Evaluators (2023)

- **Authors:** Peiyi Wang, Lei Li, Liang Chen, et al.
- **Venue:** ACL 2024 (preprint arXiv 2023) · `arXiv:2305.17926`
- **Citations:** 1,105 citations · 70 influential
- **URL:** https://arxiv.org/abs/2305.17926 · [S2](https://www.semanticscholar.org/paper/38d64919ba526868a850a0e5f6239d4c474b7e7e)
- **Task types:** pairwise response comparison; preference judgment; bias diagnosis
- **Methods / metrics:** position bias quantification; Multiple Evidence Calibration; Balanced Position Calibration; Human-in-the-Loop Calibration; balanced position diversity entropy; human win/tie/lose annotation
- **Summary:** Demonstrates that GPT-4/ChatGPT judges can have their verdicts flipped simply by swapping candidate order, exposing systematic position bias. Proposes a calibration framework (multiple-evidence generation, balanced position aggregation, entropy-based human escalation) that measurably reduces bias and improves alignment with human judgment. A core reference on judge reliability and debiasing.

### Length-Controlled AlpacaEval: A Simple Way to Debias Automatic Evaluators (2024)

- **Authors:** Yann Dubois, Balázs Galambosi, Percy Liang, Tatsunori B. Hashimoto
- **Venue:** arXiv preprint (COLM 2024) · `arXiv:2404.04475`
- **Citations:** 870 citations · 235 influential
- **URL:** https://arxiv.org/abs/2404.04475 · [S2](https://www.semanticscholar.org/paper/eb375712bd37250c350ecd3f559e1879e87eb3e5)
- **Task types:** instruction-following; automatic pairwise evaluation; instruction following; win-rate comparison; automatic preference evaluation
- **Methods / metrics:** LLM auto-annotator pairwise win rate; length-controlled win rate (regression/GLM debiasing); Spearman correlation with Chatbot Arena (0.93->0.98); length-gameability reduction; AlpacaEval win-rate; length-controlled win-rate; generalized linear model regression debiasing; counterfactual length control; correlation with Chatbot Arena
- **Summary:** Addresses length bias in AlpacaEval's automatic pairwise evaluator by estimating a length-controlled win rate via a regression that answers the counterfactual of equal output length. The debiased metric raises correlation with Chatbot Arena human rankings from 0.93 to 0.98 while resisting length-based gaming, at under $10 and a few minutes per model. A widely used statistical correction for automatic pairwise LLM ranking.

### LLM Evaluators Recognize and Favor Their Own Generations (2024)

- **Authors:** Arjun Panickssery, Samuel R. Bowman, Shi Feng
- **Venue:** NeurIPS 2024 (preprint arXiv) · `arXiv:2404.13076`
- **Citations:** 588 citations · 34 influential
- **URL:** https://arxiv.org/abs/2404.13076 · [S2](https://www.semanticscholar.org/paper/5c7f465d162aade4a4c0eefb02fd7aadeebdaf58)
- **Task types:** self-evaluation; summarization judging; bias diagnosis
- **Methods / metrics:** self-recognition probing; self-preference bias measurement; linear correlation of self-recognition vs self-preference; controlled fine-tuning interventions
- **Summary:** Shows that GPT-4 and Llama-2 can distinguish their own outputs from others' and that this self-recognition ability is linearly correlated with self-preference bias when acting as judges. Establishes a causal-style link between recognition and biased self-favoring, a key reliability concern when using an LLM to compare outputs that include its own.

### Prometheus: Inducing Fine-grained Evaluation Capability in Language Models (2023)

- **Authors:** Seungone Kim, Jamin Shin, Yejin Cho, et al.
- **Venue:** ICLR 2024 (preprint arXiv) · `arXiv:2310.08491`
- **Citations:** 560 citations · 52 influential
- **URL:** https://arxiv.org/abs/2310.08491 · [S2](https://www.semanticscholar.org/paper/9ebf47129c15f61f4b77bbfe305c522480c20347)
- **Task types:** rubric-based scoring; reference-guided evaluation; fine-grained direct assessment
- **Methods / metrics:** open evaluator LM (Llama-2 fine-tune); Feedback Collection dataset; score-rubric + reference answer conditioning; chain-of-thought feedback-then-score; Pearson correlation with GPT-4 and humans
- **Summary:** Builds Prometheus, an open evaluator LM fine-tuned on a large synthetic Feedback Collection to perform customizable rubric-based scoring with reference answers. Matches GPT-4's fine-grained evaluation correlation while being transparent, cheap and version-controllable. Positions open judge models as a viable alternative to proprietary evaluators and reward models.

### Prometheus 2: An Open Source Language Model Specialized in Evaluating Other Language Models (2024)

- **Authors:** Seungone Kim, Juyoung Suk, Shayne Longpre, et al.
- **Venue:** EMNLP 2024 (preprint arXiv) · `arXiv:2405.01535`
- **Citations:** 467 citations · 68 influential
- **URL:** https://arxiv.org/abs/2405.01535 · [S2](https://www.semanticscholar.org/paper/ecdd53eaab7455daea27609b07a418a21aa7ad35)
- **Task types:** direct assessment scoring; pairwise ranking; reward modeling
- **Methods / metrics:** Mistral-based evaluator LM; weight merging for direct + relative grading; Feedback + Preference Collection training; agreement with human/GPT-4 judges; reward-model use for RLHF
- **Summary:** Second-generation open evaluator that unifies absolute (direct-assessment) and relative (pairwise) grading in one model by merging weights of separately trained evaluators. Closes much of the gap to GPT-4 on both formats and functions as an open reward model, addressing transparency, controllability and cost concerns of proprietary judges.

### RewardBench: Evaluating Reward Models for Language Modeling (2024)

- **Authors:** Nathan Lambert, Valentina Pyatkin, Jacob Morrison, et al.
- **Venue:** Preprint (arXiv); Allen Institute for AI · `arXiv:2403.13787`
- **Citations:** 449 citations · 69 influential
- **URL:** https://arxiv.org/abs/2403.13787 · [S2](https://www.semanticscholar.org/paper/8e9088c102b3714ae4e5cac7ced93a59804bfc7c)
- **Task types:** reward modeling; chat/reasoning/safety preference; pairwise chosen-vs-rejected classification
- **Methods / metrics:** prompt-chosen-rejected trios benchmark; reward-model accuracy; out-of-distribution & refusal probes; coverage across chat/reasoning/safety; comparison of classifier vs DPO reward models
- **⚑ Empirical multi-LLM comparison** — 15 models · strategy: Reward-model accuracy on prompt-chosen-rejected trios, reported as a leaderboard across chat/reasoning/safety subsets including OOD and refusal probes; compares classifier (MLE) and DPO-based reward models.
- **Summary:** First systematic benchmark for reward models, the classifier cousins of LLM judges, using curated chosen/rejected prompt trios spanning chat, reasoning and safety including adversarial and OOD cases. Reveals what preferences and failure modes are embedded in RLHF reward models and provides a standard scoreboard for model-based preference evaluators.

### PandaLM: An Automatic Evaluation Benchmark for LLM Instruction Tuning Optimization (2023)

- **Authors:** Yidong Wang, Zhuohao Yu, Zhengran Zeng, et al.
- **Venue:** ICLR 2024 (preprint arXiv) · `arXiv:2306.05087`
- **Citations:** 396 citations · 38 influential
- **URL:** https://arxiv.org/abs/2306.05087 · [S2](https://www.semanticscholar.org/paper/ccd94602e3acecf999d0c9ba62b1a8bc02e9f696)
- **Task types:** instruction tuning evaluation; pairwise response comparison; hyperparameter selection
- **Methods / metrics:** fine-tuned judge LLM (PandaLM-7B); pairwise win/tie/lose classification; F1 vs GPT-3.5/GPT-4 agreement; human-annotated test set; reproducible/private evaluation
- **Summary:** Trains PandaLM, an open fine-tuned judge model that compares two LLM outputs and picks the better one based on correctness plus subjective factors (clarity, conciseness, instruction adherence). PandaLM-7B recovers ~94% of GPT-3.5 and ~88% of GPT-4 judging F1 while being reproducible and privacy-preserving. Enables cheap, offline model comparison for instruction-tuning optimization.

### JudgeLM: Fine-tuned Large Language Models are Scalable Judges (2023)

- **Authors:** Lianghui Zhu, Xinggang Wang, Xinlong Wang
- **Venue:** ICLR 2025 Spotlight (preprint arXiv) · `arXiv:2310.17631`
- **Citations:** 378 citations · 27 influential
- **URL:** https://arxiv.org/abs/2310.17631 · [S2](https://www.semanticscholar.org/paper/69ecf88a0d9752db7dc32b4917ee24b4974cea18)
- **Task types:** open-ended answer comparison; scalable pairwise judging; bias mitigation
- **Methods / metrics:** fine-tuned judge LLMs (7B/13B/33B); GPT-4-generated judgment training data; swap augmentation; reference support / reference drop; position/knowledge/format bias analysis; agreement with GPT-4
- **Summary:** Fine-tunes scalable judge models (up to 33B) on a large GPT-4-judged dataset and introduces a dedicated judge benchmark. Identifies position, knowledge and format biases in fine-tuned judges and mitigates them via swap augmentation, reference support and reference drop, reaching high agreement with GPT-4 at far lower cost. A practical recipe for automated model-output comparison at scale.

### JudgeBench: A Benchmark for Evaluating LLM-based Judges (2024)

- **Authors:** Sijun Tan, Siyuan Zhuang, Kyle Montgomery, et al.
- **Venue:** ICLR 2025 (preprint arXiv) · `arXiv:2410.12784`
- **Citations:** 287 citations · 42 influential
- **URL:** https://arxiv.org/abs/2410.12784 · [S2](https://www.semanticscholar.org/paper/088ab579bf490691eea7ac92e122ee11c9b9d131)
- **Task types:** knowledge QA; reasoning; math; coding; judge meta-evaluation
- **Methods / metrics:** objective-correctness-labeled response pairs; judge accuracy vs ground truth; comparison of prompted judges, fine-tuned judges, reward models; difficulty via factual/logical correctness
- **⚑ Empirical multi-LLM comparison** — 10 models · compared: GPT-4o · strategy: Judge accuracy measured against objective ground-truth correctness labels; a collection of prompted judges, fine-tuned judges, multi-agent judges, and reward models scored on the benchmark (many performing near random guessing).
- **Summary:** Argues that measuring judges by human-preference agreement is inadequate for hard tasks, and instead builds JudgeBench: challenging response pairs with objectively verifiable correct answers across knowledge, reasoning, math and coding. Shows many strong LLM judges and reward models perform near chance, providing an objective meta-evaluation of judge reliability.

### Aligning with Human Judgement: The Role of Pairwise Preference in Large Language Model Evaluators (2024)

- **Authors:** Yinhong Liu, Han Zhou, Zhijiang Guo, et al.
- **Venue:** COLM 2024 (preprint arXiv) · `arXiv:2403.16950`
- **Citations:** 174 citations · 10 influential
- **URL:** https://arxiv.org/abs/2403.16950 · [S2](https://www.semanticscholar.org/paper/aae01e933690e1f060b8bc5e3ecbef785630d0f9)
- **Task types:** preference evaluation; ranking aggregation; human-agreement calibration
- **Methods / metrics:** pairwise vs pointwise judging comparison; PairS (uncertainty-guided pairwise ranking search); human-agreement / correlation metrics; transitivity and calibration analysis
- **Summary:** Analyzes why LLM evaluators misalign with human judgment and shows pairwise preference judging, aggregated well, aligns better than direct scoring. Introduces PairS, an uncertainty-guided search that produces globally consistent rankings from pairwise LLM comparisons, improving human agreement while addressing intransitivity and calibration in judge outputs.

### Style Over Substance: Evaluation Biases for Large Language Models (2023)

- **Authors:** Minghao Wu, Alham Fikri Aji
- **Venue:** COLING 2024 (preprint arXiv 2023) · `arXiv:2307.03025`
- **Citations:** 78 citations · 3 influential
- **URL:** https://arxiv.org/abs/2307.03025 · [S2](https://www.semanticscholar.org/paper/7ace46ab8e71c4304682ab126b1212deb54b9b03)
- **Task types:** answer quality judging; bias diagnosis; multi-dimensional evaluation
- **Methods / metrics:** deliberately flawed-answer probes (factual errors vs length/grammar); Multi-Elo rating system; independent dimension scoring; human vs LLM judge comparison
- **Summary:** Curates intentionally flawed machine answers and finds both human and LLM judges rate factually wrong but fluent/long answers above short or grammatically poor ones — style trumps substance. Proposes a Multi-Elo scheme that scores factual accuracy separately from style, improving judgment quality. A canonical demonstration of verbosity/style bias in model-based evaluation.

### FELM: Benchmarking Factuality Evaluation of Large Language Models (2023)

- **Authors:** Shiqi Chen, Yiran Zhao, Jinghan Zhang, I-Chun Chern, Siyang Gao, Pengfei Liu, Junxian He
- **Venue:** NeurIPS 2023 Datasets and Benchmarks · `arXiv:2310.00741`
- **Citations:** 74 citations · 5 influential
- **URL:** https://arxiv.org/abs/2310.00741 · [S2](https://www.semanticscholar.org/paper/837a3c0417fb677d4f22c346b345a450ec417f2c)
- **Task types:** factuality; llm-as-judge
- **Methods / metrics:** balanced accuracy / F1 of error detection; segment-level annotation agreement
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: GPT-3.5 (ChatGPT); GPT-4; Vicuna; retrieval/CoT-augmented LLMs · strategy: Compare several LLM factuality evaluators against human error annotations using detection accuracy/F1; retrieval and CoT ablations. · best: GPT-4
- **Summary:** Provides fine-grained, segment-level factuality annotations across world-knowledge, math, and reasoning domains, then compares several LLM-based factuality evaluators (vanilla LLMs vs retrieval- and chain-of-thought-augmented variants) at detecting factual errors. Finds current LLM judges are far from satisfactory at faithfully detecting factual errors, with retrieval giving modest gains.

### WritingBench: A Comprehensive Benchmark for Generative Writing (2025)

- **Authors:** Yuning Wu, Jiahao Mei, Ming Yan, Chenliang Li, Shaopeng Lai, Yuran Ren, Zijia Wang, Ji Zhang, Mengyue Wu, Qin Jin, Fei Huang
- **Venue:** arXiv (cs.CL) · `arXiv:2503.05244`
- **Citations:** 72 citations · 11 influential
- **URL:** https://arxiv.org/abs/2503.05244 · [S2](https://www.semanticscholar.org/paper/123df211ca36cf7c85ba0b392168f048549db683)
- **Task types:** writing quality; long-form generation
- **Methods / metrics:** query-dependent criteria score; fine-tuned critic model; human validation
- **⚑ Empirical multi-LLM comparison** — 20 models · compared: GPT-4o; Claude 3.5; Gemini 1.5; DeepSeek; Qwen2.5; Llama-3; WritingBench-7B critic-trained model · strategy: Query-dependent LLM-generated instance-specific criteria scored by a fine-tuned critic model (criteria-aware), validated against human judgments; models ranked by criteria scores. · best: GPT-4o (among general models)
- **Summary:** A benchmark spanning 6 writing domains and 100 subdomains that evaluates many LLMs on generative writing quality using a query-dependent, instance-specific criteria framework and a fine-tuned critic model. Compares proprietary and open models; a 7B model trained on curated data surpasses GPT-4o. Models are scored on style, format, and length dimensions.

### Investigating Non-Transitivity in LLM-as-a-Judge (2025)

- **Authors:** Yi Xu, Laura Ruis, Tim Rocktäschel, Robert Kirk
- **Venue:** ICML 2025 (PMLR v267) · `arXiv:2502.14074`
- **Citations:** 34 citations · 2 influential
- **URL:** https://arxiv.org/abs/2502.14074 · [S2](https://www.semanticscholar.org/paper/5997e69e637ba532b287124af85e48e02b98f432)
- **Task types:** instruction-following; open-ended chat; pairwise judging (AlpacaEval)
- **Methods / metrics:** LLM-as-a-judge pairwise comparison; round-robin tournament; Bradley-Terry model; Swiss-Wise Iterative Matchmaking (Swim) tournaments; Spearman/Kendall correlation with Chatbot Arena; non-transitivity diagnosis
- **Summary:** Shows LLM judges exhibit non-transitive preferences, making baseline-anchored pairwise rankings (e.g., AlpacaEval) sensitive to the chosen baseline. It demonstrates that round-robin tournaments combined with Bradley-Terry modeling yield more reliable rankings (raising Spearman/Kendall correlation with Chatbot Arena), and proposes Swiss-style matchmaking to recover similar reliability at lower compute. Central to designing transitive, tournament-based LLM ranking.

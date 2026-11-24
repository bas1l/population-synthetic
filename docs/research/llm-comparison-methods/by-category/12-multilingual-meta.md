# Multilingual, cross-task & meta-evaluation

_18 papers (13 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### A Survey on Evaluation of Large Language Models (2023)

- **Authors:** Yupeng Chang, Xu Wang, Jindong Wang, Yuan Wu, et al.
- **Venue:** ACM TIST 2024 (arXiv preprint 2023) · `arXiv:2307.03109`
- **Citations:** 3,562 citations · 130 influential
- **URL:** https://arxiv.org/abs/2307.03109 · [S2](https://www.semanticscholar.org/paper/888728745dbb769e29ed475d4f7661eebe1a71cf)
- **Task types:** survey; question answering; reasoning; generation; robustness; ethics/bias; domain evaluation; knowledge; safety; multilingual; domain-specific
- **Methods / metrics:** taxonomy of what/where/how to evaluate; benchmark and metric catalog; task-level and society-level evaluation framing; success-case and failure-case synthesis; taxonomy of metrics; automatic vs human evaluation; accuracy/F1/BLEU/ROUGE catalog; benchmark inventory
- **Summary:** This widely cited survey organizes LLM evaluation along three axes: what to evaluate, where to evaluate, and how to evaluate, cataloging benchmarks, tasks and protocols. It maps the metric and benchmark landscape that practitioners use to compare model accuracy and reliability. As a meta-reference it situates individual benchmark suites within a coherent evaluation taxonomy.

### COMET: A Neural Framework for MT Evaluation (2020)

- **Authors:** Ricardo Rei, Craig Stewart, Ana C. Farinha, Alon Lavie
- **Venue:** EMNLP 2020 · `arXiv:2009.09025`
- **Citations:** 1,626 citations · 453 influential
- **URL:** https://aclanthology.org/2020.emnlp-main.213/ · [S2](https://www.semanticscholar.org/paper/9e67b9758520e49016ab66bafb974d2e1ed762d1)
- **Task types:** machine-translation
- **Methods / metrics:** cross-lingual pretrained encoder (XLM-R); source+hypothesis+reference joint representation; regression to human scores (DA, HTER, MQM); estimator and translation-ranking models; WMT Metrics correlation
- **Summary:** Introduces COMET, a neural, source-aware MT evaluation framework that encodes source, hypothesis, and reference with a cross-lingual pretrained model and regresses to human quality judgments (Direct Assessment, HTER, MQM). Achieves state-of-the-art correlation on the WMT 2019 Metrics task and remains robust for high-quality systems. Categorized as multilingual-meta because it is trained and benchmarked across many language pairs and is now a primary metric for ranking MT systems.

### C-Eval: A Multi-Level Multi-Discipline Chinese Evaluation Suite for Foundation Models (2023)

- **Authors:** Yuzhen Huang, Yuzhuo Bai, Zhihao Zhu, et al. (Junxian He)
- **Venue:** NeurIPS 2023 · `arXiv:2305.08322`
- **Citations:** 886 citations · 101 influential
- **URL:** https://arxiv.org/abs/2305.08322 · [S2](https://www.semanticscholar.org/paper/236c7dafea3df7ecffb5f18ec780d12f2f27d4b0)
- **Task types:** knowledge benchmark; multiple-choice QA; multilingual
- **Methods / metrics:** average accuracy; answer-only vs chain-of-thought accuracy
- **⚑ Empirical multi-LLM comparison** — 11 models · compared: GPT-4; ChatGPT; Claude-v1.3; text-davinci-003; LLaMA-65B; ChatGLM-6B; MOSS; Chinese-Alpaca-13B; BLOOMZ-7B; GLM-130B · strategy: Few-shot (and CoT) accuracy over 52 subjects, per-model average accuracy leaderboard split by discipline and difficulty; no LLM judge. · best: GPT-4 (only model above 60% average accuracy)
- **Summary:** C-Eval is a Chinese knowledge benchmark spanning 52 disciplines and four difficulty levels, on which the most advanced English- and Chinese-oriented LLMs are comprehensively evaluated. Only GPT-4 exceeds 60% average accuracy. A multi-model, multilingual knowledge/exam comparison.

### How Good Are GPT Models at Machine Translation? A Comprehensive Evaluation (2023)

- **Authors:** Amr Hendy, Mohamed Abdelrehim, Amr Sharaf, Vikas Raunak, Mohamed Gabr, Hitokazu Matsushita, Young Jin Kim, Mohamed Afify, Hany Hassan Awadalla
- **Venue:** arXiv (Microsoft) · `arXiv:2302.09210`
- **Citations:** 600 citations · 41 influential
- **URL:** https://arxiv.org/abs/2302.09210 · [S2](https://www.semanticscholar.org/paper/ae3d869719c15099889c02c03b922516b3b60aa0)
- **Task types:** machine-translation
- **Methods / metrics:** BLEU; COMET; ChrF; human evaluation
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: ChatGPT; text-davinci-003 (GPT-3.5); text-davinci-002; Microsoft Translator (baseline); WMT-best (baseline) · strategy: Automatic MT metrics (COMET, BLEU, ChrF) plus human evaluation across 18 high/low-resource directions, benchmarked against commercial and WMT-best systems. · best: ChatGPT/GPT-3.5 (best for high-resource directions)
- **Summary:** Comprehensive MT evaluation of three GPT models (ChatGPT, text-davinci-003/GPT-3.5, text-davinci-002) across 18 translation directions covering high- and low-resource and non-English-centric pairs, compared against SOTA research and commercial systems. Uses automatic metrics and human evaluation. Finds GPT models very competitive for high-resource languages but limited for low-resource ones, with a hybrid GPT+commercial approach improving quality.

### CodeGeeX: A Pre-Trained Model for Code Generation with Multilingual Benchmarking on HumanEval-X (2023)

- **Authors:** Qinkai Zheng, Xiao Xia, Xu Zou, Yuxiao Dong, Shan Wang, Yufei Xue, Zihan Wang, Lei Shen, Andi Wang, Yang Li, Teng Su, Zhilin Yang, Jie Tang
- **Venue:** KDD 2023 · `arXiv:2303.17568`
- **Citations:** 568 citations · 38 influential
- **URL:** https://arxiv.org/abs/2303.17568 · [S2](https://www.semanticscholar.org/paper/bafe023fb072045dc0cd50316382a61c8dcb9fae)
- **Task types:** multilingual code generation; code translation
- **Methods / metrics:** pass@k
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: CodeGeeX-13B; InCoder-6.7B; CodeGen-Multi-16B · strategy: Execution-based pass@k on HumanEval-X across 5 languages for generation and translation; models of similar scale compared. · best: CodeGeeX-13B
- **Summary:** Introduces the CodeGeeX-13B multilingual model and the HumanEval-X benchmark (HumanEval hand-ported to 5 languages for generation and translation), then compares CodeGeeX against InCoder-6.7B and CodeGen-Multi-16B by pass@k. CodeGeeX outperforms multilingual code models of similar scale across languages, providing a multi-model multilingual code-generation and translation comparison.

### MEGA: Multilingual Evaluation of Generative AI (2023)

- **Authors:** Kabir Ahuja, Harshita Diddee, Rishav Hada, et al.
- **Venue:** EMNLP 2023 · `arXiv:2303.12528`
- **Citations:** 418 citations · 32 influential
- **URL:** https://arxiv.org/abs/2303.12528 · [S2](https://www.semanticscholar.org/paper/62ad7ea9467bbcdbfe325b9ee561cab3908e4583)
- **Task types:** classification; QA; NLI; sequence-labeling; multilingual; cross-lingual
- **Methods / metrics:** accuracy; F1; cross-lingual transfer gap; monolingual vs translate-test prompting; per-language stratified comparison
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: ChatGPT; GPT-4; PaLM2 · strategy: Accuracy and F1 per-language across 16 datasets/70 languages, generative LLMs compared against fine-tuned SOTA non-autoregressive baselines
- **Summary:** First comprehensive multilingual benchmarking of generative LLMs (ChatGPT, GPT-4, PaLM2) across 16 NLP datasets and 70 typologically diverse languages, compared against fine-tuned SOTA baselines. It quantifies the high-resource vs. low-resource performance gap and analyzes prompting/translation strategies, providing a cross-lingual protocol for comparing model accuracy across languages and tasks. Key reference for multilingual meta-evaluation of generative models.

### Is ChatGPT A Good Translator? Yes With GPT-4 As The Engine (2023)

- **Authors:** Wenxiang Jiao, Wenxuan Wang, Jen-tse Huang, Xing Wang, Shuming Shi, Zhaopeng Tu
- **Venue:** arXiv (Tencent AI Lab) · `arXiv:2301.08745`
- **Citations:** 403 citations · 25 influential
- **URL:** https://arxiv.org/abs/2301.08745 · [S2](https://www.semanticscholar.org/paper/780c99d13537370f63c03feeb1343bed9d98a4f9)
- **Task types:** machine-translation
- **Methods / metrics:** BLEU; human evaluation; hallucination/mistranslation error analysis
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: ChatGPT (GPT-3.5); ChatGPT (GPT-4); Google Translate; DeepL; Tencent TranSmart · strategy: Automatic BLEU plus human evaluation across language pairs and domains, comparing LLM engines to commercial MT systems, with pivot-prompting ablation and error-type analysis. · best: ChatGPT with GPT-4 engine
- **Summary:** Evaluates ChatGPT (GPT-3.5 and GPT-4 engines) against Google Translate, DeepL and Tencent TranSmart across multiple language pairs and domains (biomedical, Reddit, spoken). Uses automatic metrics plus error analysis. ChatGPT rivals commercial systems on high-resource European languages but lags on low-resource/distant languages; GPT-4 and pivot prompting close the gap, making it comparable to commercial products.

### Aya Model: An Instruction Finetuned Open-Access Multilingual Language Model (2024)

- **Authors:** Ahmet Üstün, Viraat Aryabumi, Zheng-Xin Yong, Wei-Yin Ko, Daniel D'souza, et al.
- **Venue:** ACL 2024 · `arXiv:2402.07827`
- **Citations:** 383 citations · 34 influential
- **URL:** https://arxiv.org/abs/2402.07827 · [S2](https://www.semanticscholar.org/paper/2296629527ebbd6f8c897df7cf5cdbac3f0cc15b)
- **Task types:** multilingual-nlp-suite; generation
- **Methods / metrics:** accuracy; GPT-4-judged win rates; human evaluation; toxicity/bias metrics
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: Aya-101; mT0; BLOOMZ · strategy: Discriminative accuracy plus generative evaluation via human and GPT-4-simulated win rates across held-out and in-distribution multilingual tasks, benchmarked against mT0 and BLOOMZ. · best: Aya-101
- **Summary:** Introduces Aya, a massively multilingual instruction-tuned model covering 101 languages, and benchmarks it against mT0 and BLOOMZ across discriminative and generative tasks in up to 99 languages using automatic metrics, human evaluation and simulated win rates. Aya outperforms mT0 and BLOOMZ on the majority of tasks while covering roughly double the languages; also reports toxicity/bias/safety evaluations.

### Evaluating Large Language Models: A Comprehensive Survey (2023)

- **Authors:** Zishan Guo, Renren Jin, Chuang Liu, Yufei Huang, et al.
- **Venue:** arXiv preprint · `arXiv:2310.19736`
- **Citations:** 315 citations · 12 influential
- **URL:** https://arxiv.org/abs/2310.19736 · [S2](https://www.semanticscholar.org/paper/45a476cb04cccee74b9ddabce4d58d928be99f7d)
- **Task types:** survey; knowledge and reasoning; alignment; safety; specialized/domain LLMs; benchmark review
- **Methods / metrics:** taxonomy: knowledge & capability, alignment, safety evaluation; benchmark and protocol catalog; metric aggregation review; risk and limitation analysis
- **Summary:** This comprehensive survey categorizes LLM evaluation into knowledge-and-capability, alignment, and safety dimensions, reviewing benchmarks and metrics under each. It consolidates how accuracy, calibration and behavioral risks are measured across the field. It serves as a structured meta-reference for choosing evaluation methods when comparing LLM precision and reliability.

### Multilingual Machine Translation with Large Language Models: Empirical Results and Analysis (2024)

- **Authors:** Wenhao Zhu, Hongyi Liu, Qingxiu Dong, Jingjing Xu, Shujian Huang, Lingpeng Kong, Jiajun Chen, Lei Li
- **Venue:** Findings of NAACL 2024 · `arXiv:2304.04675`
- **Citations:** 285 citations · 7 influential
- **URL:** https://arxiv.org/abs/2304.04675 · [S2](https://www.semanticscholar.org/paper/dfd8944d39b378489b878d6e105d040fa0e524db)
- **Task types:** machine-translation
- **Methods / metrics:** BLEU; COMET; resource-level analysis
- **⚑ Empirical multi-LLM comparison** — 8 models · compared: ChatGPT (GPT-3.5); GPT-4; XGLM; OPT-175B; BLOOMZ; Falcon-7B; NLLB (baseline); Google Translate (baseline) · strategy: Automatic MT metrics (BLEU, COMET) per translation direction across 102 languages, compared against supervised NLLB and Google Translate baselines, with win-rate/direction-count analysis by resource level. · best: GPT-4
- **Summary:** Empirically evaluates eight popular LLMs (including ChatGPT/GPT-3.5, GPT-4, XGLM, OPT-175B, BLOOMZ, Falcon) on massive multilingual machine translation spanning 102 languages against supervised baselines NLLB and Google Translate. Reports per-direction translation quality and analyzes resource-level effects. GPT-4 was the strongest LLM, beating NLLB in 40.9% of directions but still trailing commercial systems, especially for low-resource languages.

### MultiPL-E: A Scalable and Polyglot Approach to Benchmarking Neural Code Generation (2023)

- **Authors:** Federico Cassano, John Gouwar, Daniel Nguyen, et al.
- **Venue:** IEEE Transactions on Software Engineering (2023); arXiv 2022 · `arXiv:2208.08227`
- **Citations:** 164 citations · 16 influential
- **URL:** https://arxiv.org/abs/2208.08227 · [S2](https://www.semanticscholar.org/paper/780f7eebde16b1ae5843df3a79a7772899ef6a71)
- **Task types:** code-generation; multilingual-code; cross-language transfer
- **Methods / metrics:** pass@k; execution-based tests; benchmark translation compilers; cross-language accuracy comparison
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: Codex; CodeGen; InCoder · strategy: Execution-based pass@k on parallel multilingual benchmarks, comparing per-language accuracy · best: Codex
- **Summary:** A system that translates unit-test-driven benchmarks (HumanEval and MBPP) into 18 additional programming languages via per-language compilers for signatures, types, and tests, producing the first massively multilingual execution-based code benchmark. It enables comparing a model's pass@k accuracy across languages on parallel problems, exposing language-dependent precision differences.

### MultiPL-E: A Scalable and Extensible Approach to Benchmarking Neural Code Generation (2022)

- **Authors:** Federico Cassano, John Gouwar, Daniel Nguyen, Sydney Nguyen, Luna Phipps-Costin, Donald Pinckney, Ming-Ho Yee, Yangtian Zi, Carolyn Jane Anderson, Molly Q Feldman, Arjun Guha, Michael Greenberg, Abhinav Jangda
- **Venue:** IEEE TSE 2023 · `arXiv:2208.08227`
- **Citations:** 164 citations · 16 influential
- **URL:** https://arxiv.org/abs/2208.08227 · [S2](https://www.semanticscholar.org/paper/780f7eebde16b1ae5843df3a79a7772899ef6a71)
- **Task types:** multilingual function-level code generation
- **Methods / metrics:** pass@k; cross-language transfer
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: Codex; CodeGen; InCoder · strategy: Execution-based pass@k on machine-translated HumanEval/MBPP across 18 languages; 3 models compared per language. · best: Codex
- **Summary:** Translates HumanEval and MBPP into 18 programming languages and benchmarks Codex, CodeGen and InCoder across all of them, measuring cross-language generalization by pass@k. Reveals substantial performance variation across languages and models, with Codex strongest overall. Provides a reusable multilingual multi-model evaluation harness.

### From LLM to NMT: Advancing Low-Resource Machine Translation with Claude (2024)

- **Authors:** Maxim Enis, Mark Hopkins
- **Venue:** arXiv · `arXiv:2404.13813`
- **Citations:** 90 citations · 7 influential
- **URL:** https://arxiv.org/abs/2404.13813 · [S2](https://www.semanticscholar.org/paper/468aac061dfee2fda4410420bd43c09f7fc68854)
- **Task types:** machine-translation
- **Methods / metrics:** chrF++; BLEU; resource-level/contamination analysis
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: Claude 3 Opus; GPT-4; NLLB-54B; Google Translate · strategy: Automatic MT metrics (chrF++, BLEU) on FLORES-200 and new low-resource benchmarks comparing LLMs vs NMT systems, plus distillation experiments measuring downstream NMT gains. · best: Claude 3 Opus (best LLM translator)
- **Summary:** Benchmarks Claude 3 Opus against other LLMs (e.g., GPT-4) and dedicated MT systems NLLB-54B and Google Translate on low-resource machine translation, including a new FLORES-200-based benchmark. Finds Claude 3 Opus exhibits stronger MT competence than other LLMs, and knowledge-distilling Claude-generated data into NMT achieves SOTA on Yoruba-English, matching or surpassing NLLB-54B and Google Translate.

### MMLU-ProX: A Multilingual Benchmark for Advanced Large Language Model Evaluation (2025)

- **Authors:** Weihao Xuan, et al.
- **Venue:** EMNLP 2025 (Main) · `arXiv:2503.10497`
- **Citations:** 71 citations · 9 influential
- **URL:** https://arxiv.org/abs/2503.10497 · [S2](https://www.semanticscholar.org/paper/4fd7dfbb3400ce60cdedfb679185c35f41bdde62)
- **Task types:** multiple-choice QA; reasoning; multilingual; cross-lingual
- **Methods / metrics:** multiple-choice accuracy; chain-of-thought prompting; parallel-item cross-lingual comparison; per-language accuracy gap
- **⚑ Empirical multi-LLM comparison** — 36 models · strategy: Multiple-choice accuracy with chain-of-thought prompting on 11,829 parallel questions per language; per-language accuracy gaps across 36 SOTA models
- **Summary:** Extends MMLU-Pro to 29 typologically diverse languages with 11,829 parallel questions each (plus a 658-question lite set), enabling direct cross-linguistic comparison via semi-automatic translation with expert validation. Evaluates 36 SOTA models and quantifies multilingual disparities (gaps up to 24.3% in low-resource languages). Provides a controlled, parallel benchmark for ranking models' multilingual reasoning precision.

### A Survey on Large Language Model Benchmarks (2025)

- **Authors:** Shiwen Ni, et al.
- **Venue:** arXiv preprint · `arXiv:2508.15361`
- **Citations:** 40 citations · 4 influential
- **URL:** https://arxiv.org/abs/2508.15361 · [S2](https://www.semanticscholar.org/paper/e9ed347f829b6270a74df9f3a6b20e29361549c8)
- **Task types:** survey; general capability benchmarking; domain-specific benchmarking; target-specific (safety/bias/robustness) benchmarking; general-capability; domain-specific; safety/reliability; agents; multilingual
- **Methods / metrics:** taxonomy of 283 benchmarks into general / domain-specific / target-specific; benchmark-design and contamination discussion; coverage and gap analysis; evaluation-metric catalog; benchmark taxonomy; contamination analysis; bias diagnosis; coverage mapping
- **Summary:** This 2025 survey systematically reviews 283 representative LLM benchmarks, classifying them into general-capability, domain-specific, and target-specific categories. It provides an up-to-date map of the benchmark landscape and discusses design pitfalls such as contamination and metric choice. As a recent meta-reference it helps practitioners select and compare benchmarks for measuring model accuracy across capabilities and domains.

### PARIKSHA: A Large-Scale Investigation of Human-LLM Evaluator Agreement on Multilingual and Multi-Cultural Data (2024)

- **Authors:** Ishaan Watts, Varun Gumma, Aditya Yadavalli, Vivek Seshadri, Manohar Swaminathan, Sunayana Sitaram
- **Venue:** EMNLP 2024 · `arXiv:2406.15053`
- **Citations:** 36 citations · 0 influential
- **URL:** https://arxiv.org/abs/2406.15053 · [S2](https://www.semanticscholar.org/paper/3bc7877cc7e49af87f0b3f2e525aace6b49d0bd1)
- **Task types:** multilingual QA; instruction-following; human-preference judgment; cross-cultural evaluation
- **Methods / metrics:** human-LLM agreement; pairwise & rating evaluation; Elo/leaderboard construction; inter-annotator agreement
- **⚑ Empirical multi-LLM comparison** — 30 models · compared: GPT-4o; Llama-3 70B · strategy: 90K human + 30K LLM-as-judge evaluations (pairwise and direct assessment) building Elo/leaderboards across 30 models and 10 Indic languages, plus human-LLM agreement · best: GPT-4o / Llama-3 70B
- **Summary:** Conducts large-scale human and LLM-as-judge evaluation across 10 Indic languages and many model pairs, measuring evaluator agreement and leaderboard stability in multilingual, multicultural settings. It exposes where automatic judges diverge from humans across languages and how that affects cross-lingual rankings. Key evidence base for reliability of multilingual LLM-judge leaderboards.

### MEXA: Multilingual Evaluation of English-Centric LLMs via Cross-Lingual Alignment (2024)

- **Authors:** Amir Hossein Kargaran, et al.
- **Venue:** arXiv preprint (later NAACL 2025) · `arXiv:2410.05873`
- **Citations:** 27 citations · 4 influential
- **URL:** https://arxiv.org/abs/2410.05873 · [S2](https://www.semanticscholar.org/paper/cc519a5f0dc093141679eceaab42093e6508d784)
- **Task types:** multilingual understanding; cross-lingual alignment; representation probing
- **Methods / metrics:** embedding alignment score; parallel-sentence probing; correlation with downstream accuracy; per-language capability estimation
- **⚑ Empirical multi-LLM comparison** — compared: Llama; Gemma; Mistral; OLMo · strategy: Downstream multilingual task accuracy across model families correlated (Pearson ~0.90) with the proposed cross-lingual alignment (MEXA) proxy score
- **Summary:** Introduces a cross-lingual-alignment metric that estimates an English-centric LLM's multilingual capability by measuring the alignment of its internal representations between English and other languages using parallel sentences. MEXA scores correlate with downstream multilingual task performance, offering a cheap proxy to rank models' language coverage without full multilingual benchmarks. Useful for scalable multilingual model comparison.

### AI Cartography: Mapping the Latent Landscape of AI Benchmark Ecosystems (2026)

- **Authors:** et al.
- **Venue:** arXiv preprint · `arXiv:2605.25272`
- **Citations:** 0 citations · 0 influential
- **URL:** https://arxiv.org/abs/2605.25272 · [S2](https://www.semanticscholar.org/paper/21e8bd7b5072438bfe506c4aa23b56169f0e09f0)
- **Task types:** meta-evaluation; benchmark-analysis; multi-task
- **Methods / metrics:** latent-factor / low-rank embedding; benchmark correlation analysis; dimensionality reduction; coverage/redundancy mapping
- **Summary:** Analyzes the structure of the broad benchmark ecosystem, embedding many benchmarks and models into a shared latent space to reveal redundancy, coverage gaps, and correlation clusters among evaluations. This latent-factor view informs which benchmarks add independent signal when aggregating a leaderboard versus which merely duplicate existing axes. Relevant to principled cross-task aggregation and meta-benchmark design.

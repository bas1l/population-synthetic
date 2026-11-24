# Code-generation evaluation (pass@k, HumanEval, SWE-bench)

_21 papers (15 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### Evaluating Large Language Models Trained on Code (2021)

- **Authors:** Mark Chen, Jerry Tworek, Heewoo Jun, et al.
- **Venue:** arXiv preprint (OpenAI) · `arXiv:2107.03374`
- **Citations:** 10,543 citations · 1600 influential
- **URL:** https://arxiv.org/abs/2107.03374 · [S2](https://www.semanticscholar.org/paper/acbdbf49f9bc3f151b93d9ca9a06009f4f6eb269)
- **Task types:** code-generation; docstring-to-code; Python function synthesis
- **Methods / metrics:** pass@k; unbiased pass@k estimator; execution-based unit-test evaluation; temperature sampling; BLEU (as contrast)
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: Codex; GPT-3; GPT-J · strategy: Execution-based functional correctness via unit tests, reported as pass@k with an unbiased estimator · best: Codex
- **Summary:** Introduces Codex (the model behind GitHub Copilot) and, critically for evaluation, the HumanEval benchmark of 164 hand-written Python problems with unit tests, plus the pass@k functional-correctness metric and its unbiased estimator. This paper established execution-based evaluation as the standard for code LLMs, replacing surface-form match metrics. It is the foundational reference for measuring code-generation accuracy and the sampling-based precision of a model at k attempts.

### Program Synthesis with Large Language Models (2021)

- **Authors:** Jacob Austin, Augustus Odena, Maxwell Nye, et al.
- **Venue:** arXiv preprint (Google Research) · `arXiv:2108.07732`
- **Citations:** 4,074 citations · 615 influential
- **URL:** https://arxiv.org/abs/2108.07732 · [S2](https://www.semanticscholar.org/paper/a38e0f993e4805ba8a9beae4c275c91ffcec01df)
- **Task types:** code-generation; natural-language-to-code; math word problems to code
- **Methods / metrics:** functional correctness via asserts; pass rate / fraction solved; few-shot vs fine-tuning comparison; scaling analysis; human feedback repair
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: dense LMs 244M-137B parameters (few-shot and fine-tuned) · strategy: Functional correctness (fraction of problems solved via asserts), analyzed as log-linear scaling across model sizes and few-shot vs fine-tuned regimes · best: Largest fine-tuned model
- **Summary:** Introduces MBPP (Mostly Basic Programming Problems, 974 entry-level Python tasks with 3 asserts each) and MathQA-Python, and studies how synthesis accuracy scales log-linearly with model size in few-shot and fine-tuned regimes. MBPP is, alongside HumanEval, one of the two most-used execution-based code benchmarks. The paper also analyzes human-in-the-loop repair and the effect of prompting on functional correctness.

### SWE-bench: Can Language Models Resolve Real-World GitHub Issues? (2023)

- **Authors:** Carlos E. Jimenez, John Yang, Alexander Wettig, et al.
- **Venue:** ICLR 2024 · `arXiv:2310.06770`
- **Citations:** 2,975 citations · 472 influential
- **URL:** https://arxiv.org/abs/2310.06770 · [S2](https://www.semanticscholar.org/paper/94a5f96308729e31c1ffbc0f0618db87795092fe)
- **Task types:** issue-resolution; repository-level-code-editing; bug-fixing; software-engineering
- **Methods / metrics:** % resolved; FAIL_TO_PASS / PASS_TO_PASS test execution; patch application; execution-based end-to-end evaluation
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: Claude 2; GPT-4; GPT-3.5; SWE-Llama · strategy: Execution-based % resolved via FAIL_TO_PASS / PASS_TO_PASS test suites after patch application · best: Claude 2
- **Summary:** Introduces SWE-bench, 2,294 real GitHub issue/pull-request tasks across 12 Python repositories, where a model must edit a full codebase so the repository's hidden test suite passes (FAIL_TO_PASS and PASS_TO_PASS checks). It shifts execution-based evaluation from isolated functions to repository-level software engineering; the strongest models initially resolved under 2%, making it a demanding, contamination-resistant correctness benchmark.

### Competition-Level Code Generation with AlphaCode (2022)

- **Authors:** Yujia Li, David Choi, Junyoung Chung, et al.
- **Venue:** Science (Vol. 378), DeepMind · `arXiv:2203.07814`
- **Citations:** 2,338 citations · 193 influential
- **URL:** https://arxiv.org/abs/2203.07814 · [S2](https://www.semanticscholar.org/paper/5cbe278b65a81602a864184bbca37de91448a5f5)
- **Task types:** code-generation; competitive-programming; algorithmic-reasoning
- **Methods / metrics:** n@k / 10@k metric; solve rate; sample filtering and clustering; false-positive-rate analysis; large-scale sampling
- **Summary:** AlphaCode reached median-competitor ranking (top 54.3%) on Codeforces contests via massive sampling plus behavior-based filtering and clustering. For evaluation, it introduces the CodeContests dataset and the 10@k / n@k metrics (percentage solved using at most k submissions from n samples) and rigorously addresses false-positive rates in test-based judging, an important precision concern when many samples are drawn.

### Is Your Code Generated by ChatGPT Really Correct? Rigorous Evaluation of Large Language Models for Code Generation (EvalPlus / HumanEval+) (2023)

- **Authors:** Jiawei Liu, Chunqiu Steven Xia, Yuyao Wang, Lingming Zhang
- **Venue:** NeurIPS 2023 · `arXiv:2305.01210`
- **Citations:** 1,947 citations · 189 influential
- **URL:** https://arxiv.org/abs/2305.01210 · [S2](https://www.semanticscholar.org/paper/b45ec1cb2ba6b2d1ac24723fa836aee06a3db97a)
- **Task types:** code-generation; test-suite-augmentation; Python function synthesis
- **Methods / metrics:** pass@k; HumanEval+ / MBPP+; mutation-based test generation; coverage-guided fuzzing; false-acceptance reduction; ranking-stability analysis
- **⚑ Empirical multi-LLM comparison** — 26 models · compared: GPT-4; ChatGPT; WizardCoder-CodeLlama; Phind-CodeLlama · strategy: Execution-based pass@k under augmented (80x) test suites; ranking-stability analysis showing rank flips vs original benchmarks · best: GPT-4
- **Summary:** Shows that HumanEval's sparse tests over-accept incorrect code, then builds EvalPlus, augmenting benchmarks with up to 80x more tests via LLM-seeded, type-aware mutation and coverage-guided fuzzing (yielding HumanEval+ and MBPP+). Under the stronger tests, top models' pass@k drops 19-29% and rankings flip, demonstrating that evaluator test-suite adequacy is decisive for measuring true code-generation accuracy.

### LiveCodeBench: Holistic and Contamination Free Evaluation of Large Language Models for Code (2024)

- **Authors:** Naman Jain, King Han, Alex Gu, et al.
- **Venue:** ICLR 2025 · `arXiv:2403.07974`
- **Citations:** 1,827 citations · 292 influential
- **URL:** https://arxiv.org/abs/2403.07974 · [S2](https://www.semanticscholar.org/paper/afe0998d191f3ea8490c7df100a3ffc5dcc62c5e)
- **Task types:** code-generation; competitive-programming; self-repair; code-execution; test-output-prediction
- **Methods / metrics:** pass@1; time-segmented evaluation; contamination detection; multi-scenario scoring; elo/percentile analysis
- **⚑ Empirical multi-LLM comparison** — 52 models · compared: 18 base LLMs; 34 instruction-tuned LLMs · strategy: Time-segmented, contamination-free pass@1 with overfitting/contamination detection across platforms
- **Summary:** Continuously harvests new problems from LeetCode, AtCoder and Codeforces with release timestamps, enabling time-segmented, contamination-free evaluation and empirical detection of benchmark overfitting across 50+ LLMs. Beyond generation it scores self-repair, code execution, and test-output prediction, arguing that time-windowed measurement yields more reliable accuracy estimates than saturated static benchmarks.

### StarCoder: may the source be with you! (2023)

- **Authors:** Raymond Li, Loubna Ben Allal, Yangtian Zi, et al. (BigCode)
- **Venue:** TMLR 2023 · `arXiv:2305.06161`
- **Citations:** 1,254 citations · 114 influential
- **URL:** https://arxiv.org/abs/2305.06161 · [S2](https://www.semanticscholar.org/paper/3e4085e5869f1b7959707a1e1d7d273b6057eb4e)
- **Task types:** multilingual code generation; fill-in-the-middle
- **Methods / metrics:** pass@1; pass@k
- **⚑ Empirical multi-LLM comparison** — 8 models · compared: StarCoder; StarCoderBase; code-cushman-001; CodeGen-16B-Multi; InCoder-6.7B; LLaMA; CodeGeeX; PaLM-Coder · strategy: Execution-based pass@1/pass@k on HumanEval, MBPP, MultiPL-E and DS-1000 comparing StarCoder against a broad panel of open and closed code LLMs. · best: StarCoder (among open models)
- **Summary:** Presents the 15.5B StarCoder/StarCoderBase code models and benchmarks them against a broad set of open and closed code LLMs, including OpenAI code-cushman-001, CodeGen, InCoder, LLaMA and Python-fine-tuned models, using HumanEval pass@1 and MultiPL-E across many languages. StarCoder reaches ~40% pass@1 on HumanEval and outperforms every open multilingual code model and Python-specialized fine-tunes, constituting a large multi-model comparison.

### Measuring Coding Challenge Competence With APPS (2021)

- **Authors:** Dan Hendrycks, Steven Basart, Saurav Kadavath, et al.
- **Venue:** NeurIPS 2021 Datasets & Benchmarks Track · `arXiv:2105.09938`
- **Citations:** 1,172 citations · 190 influential
- **URL:** https://arxiv.org/abs/2105.09938 · [S2](https://www.semanticscholar.org/paper/1ccd031f28dccfb226f6c0c588c93a97a50bf95f)
- **Task types:** code-generation; competitive-programming; natural-language-to-code
- **Methods / metrics:** strict accuracy (all tests pass); test case average; execution-based evaluation; difficulty stratification
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: GPT-2; GPT-Neo; GPT-3 · strategy: Execution-based test-case average and strict accuracy (all tests pass), stratified by difficulty
- **Summary:** Presents APPS, 10,000 coding problems (introductory to competition level) with 131,777 test cases and 232,421 human solutions, graded by running the generated code against test cases. Introduces the 'test case average' and 'strict accuracy' (all test cases pass) metrics for measuring end-to-end problem-solving, providing a difficulty-stratified execution-based benchmark that captures accuracy across a competence spectrum.

### A Systematic Evaluation of Large Language Models of Code (PolyCoder) (2022)

- **Authors:** Frank F. Xu, Uri Alon, Graham Neubig, Vincent J. Hellendoorn
- **Venue:** DL4C@ICLR 2022 / MAPS@PLDI 2022 · `arXiv:2202.13169`
- **Citations:** 880 citations · 48 influential
- **URL:** https://arxiv.org/abs/2202.13169 · [S2](https://www.semanticscholar.org/paper/b32a6f6ef7dd775e0f876b4713ceccebc56e651e)
- **Task types:** code generation; language modeling
- **Methods / metrics:** pass@k; perplexity per language
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: Codex; GPT-J; GPT-Neo; GPT-NeoX-20B; CodeParrot; PolyCoder · strategy: HumanEval pass@k plus held-out per-language perplexity across 12 languages; 6 models compared. · best: Codex (overall); PolyCoder best on C
- **Summary:** Provides one of the first systematic multi-model comparisons of code LLMs, evaluating Codex, GPT-J, GPT-Neo, GPT-NeoX-20B and CodeParrot alongside the authors' new PolyCoder (2.7B). Uses HumanEval pass@k and multilingual perplexity across 12 languages; Codex leads overall while PolyCoder surprisingly beats all, including Codex, on C. Establishes early open-vs-closed code-model baselines.

### BigCodeBench: Benchmarking Code Generation with Diverse Function Calls and Complex Instructions (2024)

- **Authors:** Terry Yue Zhuo, Minh Chien Vu, Jenny Chim, et al.
- **Venue:** ICLR 2025 · `arXiv:2406.15877`
- **Citations:** 590 citations · 65 influential
- **URL:** https://arxiv.org/abs/2406.15877 · [S2](https://www.semanticscholar.org/paper/f2e0b3d6a02dac33872f0a0b42affdcf454715cb)
- **Task types:** code-generation; tool-use / library-function-calling; instruction-following
- **Methods / metrics:** calibrated pass@k; high-coverage test suites; branch-coverage-verified evaluation; execution-based grading
- **⚑ Empirical multi-LLM comparison** — 60 models · compared: 60 LLMs (incl. proprietary and open code models) · strategy: Calibrated pass@k on high-branch-coverage (~99%) execution-based test suites, vs human baseline
- **Summary:** A benchmark of practical tasks requiring compositional use of 723 function calls across 139 standard and external libraries, with high-branch-coverage test suites (avg ~99% branch coverage) for reliable execution-based grading, plus an instruction-tuned split. Evaluating 60 LLMs, it finds top models reach only ~60% vs 97% human performance, exposing precision gaps in complex, tool-using code generation.

### DS-1000: A Natural and Reliable Benchmark for Data Science Code Generation (2023)

- **Authors:** Yuhang Lai, Chengxi Li, Yiming Wang, et al.
- **Venue:** ICML 2023 (PMLR v202) · `arXiv:2211.11501`
- **Citations:** 557 citations · 73 influential
- **URL:** https://arxiv.org/abs/2211.11501 · [S2](https://www.semanticscholar.org/paper/8a4fc5f00cd4aca61e148e46a2125c3a406719f1)
- **Task types:** code-generation; data-science; code-completion; code-insertion
- **Methods / metrics:** multi-criteria pass rate; execution-based tests; surface-form API constraints; false-acceptance-rate measurement; perturbation against memorization
- **Summary:** A benchmark of 1,000 realistic data-science problems over seven Python libraries (NumPy, Pandas, etc.), sourced from StackOverflow and perturbed to defend against memorization. Its multi-criteria evaluation combines execution-based functional-correctness tests with surface-form constraints (allowed/forbidden APIs), achieving very high reliability: only 1.8% of accepted solutions are actually wrong, directly quantifying evaluator precision.

### RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems (2024)

- **Authors:** Tianyang Liu, Canwen Xu, Julian McAuley
- **Venue:** ICLR 2024 · `arXiv:2306.03091`
- **Citations:** 399 citations · 21 influential
- **URL:** https://arxiv.org/abs/2306.03091 · [S2](https://www.semanticscholar.org/paper/f97413a497d47c739d41d237917e6566154647b4)
- **Task types:** code-completion; repository-level-code; cross-file-retrieval; next-line-prediction
- **Methods / metrics:** exact match; edit similarity; retrieval accuracy (acc@k); cross-file context evaluation
- **Summary:** A repository-level benchmark for Python and Java with three linked tasks: RepoBench-R (retrieving relevant cross-file snippets), RepoBench-C (next-line prediction with in-file and cross-file context), and RepoBench-P (the end-to-end retrieval+completion pipeline). It measures cross-file context handling with exact-match, edit-similarity, and retrieval accuracy, targeting realistic multi-file completion rather than isolated functions.

### CRUXEval: A Benchmark for Code Reasoning, Understanding and Execution (2024)

- **Authors:** Alex Gu, Baptiste Rozière, Hugh Leather, Armando Solar-Lezama, Gabriel Synnaeve, Sida I. Wang
- **Venue:** ICML 2024 (PMLR v235) · `arXiv:2401.03065`
- **Citations:** 314 citations · 57 influential
- **URL:** https://arxiv.org/abs/2401.03065 · [S2](https://www.semanticscholar.org/paper/4701914bc77dedef9e0a001687277103fb3ddfc6)
- **Task types:** code-reasoning; input-prediction; output-prediction; execution-simulation
- **Methods / metrics:** pass@1; input/output prediction accuracy; chain-of-thought evaluation; execution-grounded scoring
- **⚑ Empirical multi-LLM comparison** — 20 models · compared: GPT-4; Code Llama 34B · strategy: Execution-grounded pass@1 on input/output prediction, with and without chain-of-thought · best: GPT-4
- **Summary:** Introduces 800 short Python functions each with an input-output pair, defining two execution-reasoning tasks: CRUXEval-I (predict an input yielding a given output) and CRUXEval-O (simulate execution to predict output). It decouples code-execution reasoning from generation and shows high HumanEval scores do not transfer, offering a complementary axis for measuring model understanding precision.

### ClassEval: A Manually-Crafted Benchmark for Evaluating LLMs on Class-level Code Generation (2023)

- **Authors:** Xueying Du, Mingwei Liu, Kaixin Wang, et al.
- **Venue:** arXiv preprint (Fudan University) · `arXiv:2308.01861`
- **Citations:** 249 citations · 33 influential
- **URL:** https://arxiv.org/abs/2308.01861 · [S2](https://www.semanticscholar.org/paper/e539218e2f6054ed002da6d6efc96d73221c22dc)
- **Task types:** class-level-code-generation; code-generation; multi-method synthesis
- **Methods / metrics:** class-level pass@k; method-level pass@k; execution-based tests; generation-strategy comparison
- **⚑ Empirical multi-LLM comparison** — 11 models · compared: GPT-4; GPT-3.5; Instruct-StarCoder; Instruct-CodeGen; WizardCoder · strategy: Execution-based class-level and method-level pass@k, compared across holistic/incremental/compositional generation strategies · best: GPT-4
- **Summary:** The first class-level code-generation benchmark: 100 manually crafted Python classes (with methods, fields and dependencies) evaluated by executing per-class test suites. It shows method-level ability does not predict class-level ability and compares holistic vs incremental vs compositional generation strategies, extending execution-based correctness measurement to multi-method, stateful units.

### AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding Agents (2024)

- **Authors:** Harsh Trivedi, Tushar Khot, Mareike Hartmann, ... Ashish Sabharwal, Niranjan Balasubramanian
- **Venue:** ACL 2024 (Best Resource Paper) · `arXiv:2407.18901`
- **Citations:** 239 citations · 37 influential
- **URL:** https://arxiv.org/abs/2407.18901 · [S2](https://www.semanticscholar.org/paper/19430ba54cc873dc5061bb53601fc576486d5a3c)
- **Task types:** interactive code generation; tool use; API orchestration
- **Methods / metrics:** task goal completion (TGC); scenario goal completion (SGC); state-based unit tests
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: GPT-4o; GPT-4-turbo; Llama-3-70B; Claude-3; DeepSeek-Coder; Gemini-1.5 · strategy: State-based unit tests programmatically verify task-goal completion and detect unintended state changes; reports task and scenario completion rates. · best: GPT-4o
- **Summary:** AppWorld simulates 9 everyday apps operable via 457 APIs with simulated users, and 750 tasks requiring interactive code generation. Several LLM agents are compared with robust state-based unit tests checking goal completion and absence of collateral changes. GPT-4o leads at ~49% on normal tasks and ~30% on challenge tasks, with other models at least 16 points lower.

### EvoCodeBench: An Evolving Code Generation Benchmark Aligned with Real-World Code Repositories (2024)

- **Authors:** Jia Li, Ge Li, Xuanming Zhang, Yihong Dong, Zhi Jin
- **Venue:** NeurIPS 2024 (Datasets & Benchmarks) · `arXiv:2404.00599`
- **Citations:** 94 citations · 3 influential
- **URL:** https://arxiv.org/abs/2404.00599 · [S2](https://www.semanticscholar.org/paper/f3c339ab479cbd4782807bf47254961bc60bf293)
- **Task types:** repository-level code generation
- **Methods / metrics:** pass@1; pass@k; recall of reference dependencies
- **⚑ Empirical multi-LLM comparison** — 10 models · compared: GPT-4; GPT-3.5; DeepSeek Coder; StarCoder2; Code Llama; Gemma; Qwen1.5; and 3 others · strategy: Execution-based pass@1/pass@k on repository-aligned tasks with periodic refresh to avoid contamination; 10 models ranked. · best: GPT-4 (~20.73% pass@1)
- **Summary:** Presents EvoCodeBench, an evolving repository-aligned benchmark (275 samples) designed to avoid contamination, and evaluates 10 LLMs including GPT-4, GPT-3.5, DeepSeek Coder, StarCoder2, Code Llama, Gemma and Qwen1.5. Scored by pass@1/pass@k, even the best model GPT-4 reaches only ~20.73%, showing repository-level real-world generation remains hard.

### Quantifying Contamination in Evaluating Code Generation Capabilities of Language Models (2024)

- **Authors:** Martin Riddell, Ansong Ni, Arman Cohan
- **Venue:** ACL 2024 · `arXiv:2403.04811`
- **Citations:** 71 citations · 7 influential
- **URL:** https://arxiv.org/abs/2403.04811 · [S2](https://www.semanticscholar.org/paper/6bf28ebbb8df92582bc53a7fe49016e0caa4c074)
- **Task types:** code-generation; contamination-analysis; benchmark-auditing
- **Methods / metrics:** surface-level string overlap; semantic similarity matching; contaminated-vs-clean accuracy gap; pass@1 comparison
- **Summary:** Systematically measures overlap between HumanEval/MBPP solutions and large pretraining corpora using surface-level and semantic matching, then shows model accuracy is significantly higher on the contaminated subsets than on clean ones. It provides quantitative evidence that data contamination biases reported code-generation accuracy, informing how to read and compare benchmark scores across models.

### CoderEval: A Benchmark of Pragmatic Code Generation with Generative Pre-trained Models (2023)

- **Authors:** Hao Yu, Bo Shen, Dezhi Ran, Jiaxin Zhang, Qi Zhang, Yuchi Ma, Guangtai Liang, Ying Li, Qianxiang Wang, Tao Xie
- **Venue:** ICSE 2024 · `arXiv:2302.00288`
- **Citations:** 67 citations · 8 influential
- **URL:** https://arxiv.org/abs/2302.00288 · [S2](https://www.semanticscholar.org/paper/6ab8aca8f631f42760a86cc614dfd7208b3fe58e)
- **Task types:** pragmatic/context-dependent code generation
- **Methods / metrics:** pass@1 functional correctness; performance by context-dependency level
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: Codex; CodeGen; PanGu-Coder · strategy: Execution-based functional correctness on a self-contained platform across six context-dependency levels; 3 industrial models compared. · best: Codex
- **Summary:** Introduces CoderEval (230 Python + 230 Java pragmatic tasks organized by six levels of context dependency) and compares three industrial code models, Codex, CodeGen and PanGu-Coder, plus ChatGPT, on non-standalone functions requiring project context. Functional correctness is measured via a self-contained execution platform, showing all models drop substantially on context-dependent code versus standalone functions.

### On Leakage of Code Generation Evaluation Datasets (2024)

- **Authors:** Alexandre Matton, Tom Sherborne, Dennis Aumiller, et al.
- **Venue:** Findings of EMNLP 2024 · `arXiv:2407.07565`
- **Citations:** 46 citations · 6 influential
- **URL:** https://arxiv.org/abs/2407.07565 · [S2](https://www.semanticscholar.org/paper/3f37462afde6c573d78abfc5da73c93ec0998713)
- **Task types:** code-generation; contamination-analysis; benchmark-auditing
- **Methods / metrics:** n-gram/embedding overlap detection; leakage quantification; held-out clean set; synthetic-data contamination analysis
- **Summary:** Analyzes three contamination pathways for code benchmarks: direct leakage of test problems into training data, indirect leakage via synthetic data distillation, and overfitting from model selection on the eval set. It quantifies overlap in popular pretraining corpora and releases a less-contaminated held-out set, providing methodology for interpreting whether reported HumanEval/MBPP accuracy is genuine or inflated.

### NaturalCodeBench: Examining Coding Performance Mismatch on HumanEval and Natural User Prompts (2024)

- **Authors:** Shudan Zhang, Hanlin Zhao, Xiao Liu, Qinkai Zheng, Zehan Qi, Xiaotao Gu, Xiaohan Zhang, Yuxiao Dong, Jie Tang
- **Venue:** ACL 2024 (Findings) · `arXiv:2405.04520`
- **Citations:** 25 citations · 0 influential
- **URL:** https://arxiv.org/abs/2405.04520 · [S2](https://www.semanticscholar.org/paper/5e28dfa5537a53e662039f59c6f6d0f6f29301af)
- **Task types:** natural-prompt code generation
- **Methods / metrics:** pass@1; benchmark-vs-real-prompt correlation
- **⚑ Empirical multi-LLM comparison** — 39 models · compared: GPT-4; GPT-3.5; Claude; DeepSeek Coder; Code Llama; StarCoder; WizardCoder; ChatGLM/CodeGeeX; and other LLMs · strategy: Execution-based pass@1 on 402 real-user problems with human-verified test cases; 39 models ranked and correlated against HumanEval. · best: GPT-4
- **Summary:** Builds NaturalCodeBench from 402 real user coding prompts (Python and Java across 6 domains) and evaluates 39 LLMs, showing that models with similar HumanEval scores diverge sharply on natural prompts. Scored by pass@1 with a semi-automated test-construction pipeline; GPT-4 leads but remains far from satisfactory, evidencing benchmark-vs-reality mismatch.

### The Fault in our Stars: Quality Assessment of Code Generation Benchmarks (2024)

- **Authors:** Mohammed Latif Siddiq, Simantika Dristi, Joy Saha, Joanna C. S. Santos
- **Venue:** IEEE SCAM 2024 · `arXiv:2404.10155`
- **Citations:** 20 citations · 0 influential
- **URL:** https://arxiv.org/abs/2404.10155 · [S2](https://www.semanticscholar.org/paper/7d8975d0f424e2dd37fd6fa93989784ce15824b4)
- **Task types:** benchmark-quality-assessment; code-generation; test-suite-auditing
- **Methods / metrics:** prompt-quality analysis; test-suite adequacy checks; coding-style/linter checks; reliability/validity assessment
- **Summary:** An empirical quality audit of widely used code-generation benchmarks (HumanEval, MBPP and others), finding prevalent prompt-quality issues, style inconsistencies, and buggy or weak reference tests that undermine measurement validity. It documents how such defects distort pass@k comparisons and argues for quality controls, making it a key methodological reference on the reliability of code-eval statistics.

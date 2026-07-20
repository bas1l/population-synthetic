# Reasoning & mathematical evaluation

_21 papers (18 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### Chain-of-Thought Prompting Elicits Reasoning in Large Language Models (2022)

- **Authors:** Jason Wei, Xuezhi Wang, Dale Schuurmans, et al.
- **Venue:** NeurIPS 2022 · `arXiv:2201.11903`
- **Citations:** 20,191 citations · 1351 influential
- **URL:** https://arxiv.org/abs/2201.11903 · [S2](https://www.semanticscholar.org/paper/1b6e810ce0afd0dd093f789d2b2742d047e316d5)
- **Task types:** arithmetic reasoning; commonsense reasoning; symbolic reasoning
- **Methods / metrics:** few-shot chain-of-thought prompting; GSM8K / SVAMP / ASDiv / commonsense benchmarks; solve-rate accuracy; emergent-ability scaling curves vs model size
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: GPT-3; LaMDA; PaLM · strategy: Solve-rate/accuracy with vs without few-shot chain-of-thought prompting, reported per model across scales; emergent-ability scaling curves vs model size · best: PaLM 540B
- **Summary:** Shows that prompting models with a few worked reasoning-chain exemplars sharply improves multi-step reasoning, with gains emerging only at sufficient model scale. Establishes chain-of-thought as the dominant evaluation and elicitation protocol for reasoning benchmarks. The scale-vs-accuracy curves it introduces are a core methodology for comparing when reasoning ability appears across models.

### Training Verifiers to Solve Math Word Problems (2021)

- **Authors:** Karl Cobbe, Vineet Kosaraju, Mohammad Bavarian, et al.
- **Venue:** arXiv preprint (OpenAI) · `arXiv:2110.14168`
- **Citations:** 9,682 citations · 2145 influential
- **URL:** https://arxiv.org/abs/2110.14168 · [S2](https://www.semanticscholar.org/paper/d6045d2ccc9c09ca1671348de86d07da6bc28eea)
- **Task types:** grade-school math word problems; arithmetic reasoning; QA
- **Methods / metrics:** GSM8K benchmark (8.5K problems); final-answer accuracy; verifier reranking / solution verification; test-time sampling + best-of-N; outcome-based verification scaling
- **Summary:** Introduces GSM8K, an 8.5K-problem dataset of linguistically diverse grade-school math word problems that became a de-facto standard for comparing LLM arithmetic reasoning. Proposes training a verifier to rank sampled candidate solutions, showing verification scales better with data than finetuning. Its held-out final-answer accuracy metric enables clean, contamination-conscious cross-model precision comparisons.

### Large Language Models are Zero-Shot Reasoners (2022)

- **Authors:** Takeshi Kojima, Shixiang Shane Gu, Machel Reid, Yutaka Matsuo, Yusuke Iwasawa
- **Venue:** NeurIPS 2022 · `arXiv:2205.11916`
- **Citations:** 7,545 citations · 495 influential
- **URL:** https://arxiv.org/abs/2205.11916 · [S2](https://www.semanticscholar.org/paper/e7ad08848d5d7c5c47673ffe0da06af443643bda)
- **Task types:** arithmetic reasoning; symbolic reasoning; logical reasoning
- **Methods / metrics:** zero-shot chain-of-thought ('Let's think step by step'); GSM8K / MultiArith / SVAMP / AQuA accuracy; zero-shot vs few-shot comparison
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: InstructGPT (text-davinci-002); PaLM 540B; GPT-3 · strategy: Zero-shot chain-of-thought accuracy ('Let's think step by step') vs standard zero-shot, reported per model across reasoning benchmarks
- **Summary:** Shows a single trigger phrase, 'Let's think step by step,' elicits large zero-shot reasoning gains without any exemplars across arithmetic, symbolic, and logical tasks. Establishes zero-shot-CoT as a baseline elicitation protocol used in nearly all reasoning evaluations. Comparing zero-shot vs few-shot CoT accuracy is now standard for isolating prompting effects when benchmarking models.

### Self-Consistency Improves Chain of Thought Reasoning in Language Models (2023)

- **Authors:** Xuezhi Wang, Jason Wei, Dale Schuurmans, et al.
- **Venue:** ICLR 2023 · `arXiv:2203.11171`
- **Citations:** 7,208 citations · 934 influential
- **URL:** https://arxiv.org/abs/2203.11171 · [S2](https://www.semanticscholar.org/paper/5f19ae1135a9500940978104ec15a5b8751bc7d2)
- **Task types:** arithmetic reasoning; commonsense reasoning; symbolic reasoning
- **Methods / metrics:** self-consistency decoding (sample-and-marginalize); majority vote over reasoning paths; GSM8K / SVAMP / AQuA / ARC accuracy; diverse-path sampling
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: UL2; GPT-3; LaMDA; PaLM · strategy: Majority-vote accuracy over multiple sampled reasoning paths (self-consistency) vs greedy chain-of-thought decoding, reported per model across benchmarks
- **Summary:** Replaces greedy chain-of-thought decoding with sampling many reasoning paths and taking the majority-vote answer, yielding large accuracy gains across arithmetic and commonsense benchmarks. Establishes sampling-based aggregation as a standard evaluation-time technique. Comparing greedy vs self-consistency accuracy is now a routine axis when benchmarking reasoning precision.

### Measuring Mathematical Problem Solving With the MATH Dataset (2021)

- **Authors:** Dan Hendrycks, Collin Burns, Saurav Kadavath, et al.
- **Venue:** NeurIPS 2021 Datasets & Benchmarks Track · `arXiv:2103.03874`
- **Citations:** 5,884 citations · 1336 influential
- **URL:** https://arxiv.org/abs/2103.03874 · [S2](https://www.semanticscholar.org/paper/57d1e7ac339e783898f2c3b1af55737cbeee9fc5)
- **Task types:** competition mathematics; step-by-step derivation; problem solving
- **Methods / metrics:** MATH benchmark (12.5K competition problems); difficulty/subject stratification (5 levels, 7 subjects); exact-match answer accuracy; step-by-step solution supervision
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: GPT-2; GPT-3 · strategy: Exact-match final-answer accuracy across model sizes, stratified by subject and difficulty level; scaling comparison of accuracy vs model size
- **Summary:** Presents MATH, 12,500 challenging competition-level math problems each with a full worked solution, stratified by subject and difficulty. Demonstrates that scaling model size yields only slow accuracy gains, establishing a hard ceiling benchmark. The subject/difficulty stratification supports fine-grained accuracy comparison across models rather than a single aggregate score.

### Tree of Thoughts: Deliberate Problem Solving with Large Language Models (2023)

- **Authors:** Shunyu Yao, Dian Yu, Jeffrey Zhao, et al.
- **Venue:** NeurIPS 2023 · `arXiv:2305.10601`
- **Citations:** 4,478 citations · 297 influential
- **URL:** https://arxiv.org/abs/2305.10601 · [S2](https://www.semanticscholar.org/paper/2f3822eb380b5e753a6d579f31dfc3ec4c4a0820)
- **Task types:** search-based problem solving; planning; puzzle solving (Game of 24, crosswords)
- **Methods / metrics:** tree-of-thoughts search framework; self-evaluation of intermediate states; BFS/DFS over thoughts + backtracking; task success-rate comparison vs CoT
- **Summary:** Generalizes chain-of-thought into a search tree of intermediate 'thoughts' with self-evaluation, lookahead, and backtracking, sharply improving success on tasks requiring exploration (e.g., Game of 24). Establishes deliberate inference-time search as an evaluation dimension. Comparing CoT vs ToT success rates isolates how much of a model's reasoning gap is solvable by better search.

### Let's Verify Step by Step (2023)

- **Authors:** Hunter Lightman, Vineet Kosaraju, Yura Burda, et al.
- **Venue:** arXiv preprint (OpenAI); ICLR 2024 · `arXiv:2305.20050`
- **Citations:** 3,868 citations · 500 influential
- **URL:** https://arxiv.org/abs/2305.20050 · [S2](https://www.semanticscholar.org/paper/be8db99310602d66bba64bcf41a572c45816fbfc)
- **Task types:** competition mathematics; step-level solution verification
- **Methods / metrics:** process reward models (PRM) vs outcome reward models (ORM); step-level human labels (PRM800K, 800K labels); best-of-N reranking accuracy on MATH; active learning for label efficiency
- **Summary:** Demonstrates that process supervision (rewarding each reasoning step) substantially outperforms outcome supervision for MATH problem solving, reaching 78% on a MATH subset via PRM-guided reranking. Releases PRM800K, 800K step-level human labels. Its step-level scoring reframes reasoning evaluation from final-answer correctness toward verifying the reasoning trace itself.

### GPQA: A Graduate-Level Google-Proof Q&A Benchmark (2023)

- **Authors:** David Rein, Betty Li Hou, Asa Cooper Stickland, Jackson Petty, et al. (incl. Samuel R. Bowman)
- **Venue:** COLM 2024 (arXiv preprint 2023) · `arXiv:2311.12022`
- **Citations:** 2,981 citations · 534 influential
- **URL:** https://arxiv.org/abs/2311.12022 · [S2](https://www.semanticscholar.org/paper/210b0a3d76e93079cc51b03c4115fde545eea966)
- **Task types:** graduate-level multiple-choice question answering; biology; physics; chemistry; expert reasoning; graduate-level science QA; expert reasoning (biology/physics/chemistry)
- **Methods / metrics:** 448 expert-written multiple-choice questions; multiple-choice accuracy; expert vs non-expert human baselines; Google-proof difficulty validation; open-book non-expert control; expert vs non-expert validation (65% vs 34%); Google-proof difficulty control
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: GPT-4; GPT-3.5-turbo; Llama-2-70B-chat · strategy: Few-shot and CoT accuracy of 3 LLMs (with/without web search) on 448 expert MCQs, benchmarked against expert and non-expert humans. · best: GPT-4 (39%)
- **Summary:** GPQA provides 448 hard, expert-authored biology/physics/chemistry questions that domain PhDs answer at 65% while skilled non-experts with web access reach only 34% (Google-proof). Its extreme difficulty (GPT-4 baseline ~39%) gives a high-headroom, contamination-resistant accuracy signal for frontier reasoning models. It has become a standard hard-science reasoning benchmark for separating top-tier models.

### Challenging BIG-Bench Tasks and Whether Chain-of-Thought Can Solve Them (BIG-Bench Hard) (2022)

- **Authors:** Mirac Suzgun, Nathan Scales, Nathanael Scharli, Sebastian Gehrmann, Yi Tay, et al.
- **Venue:** ACL Findings 2023 (arXiv preprint 2022) · `arXiv:2210.09261`
- **Citations:** 2,039 citations · 282 influential
- **URL:** https://arxiv.org/abs/2210.09261 · [S2](https://www.semanticscholar.org/paper/663a41c866d49ce052801fbc88947d39764cad29)
- **Task types:** multi-step reasoning; arithmetic; logical deduction; algorithmic reasoning; symbolic manipulation
- **Methods / metrics:** 23-task hard subset of BIG-bench; chain-of-thought vs answer-only prompting; accuracy vs average human-rater baseline; few-shot prompting
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: PaLM (multiple scales); Codex (code-davinci-002) · strategy: Accuracy on 23-task hard subset compared under chain-of-thought vs answer-only prompting and across model scales, benchmarked against average human-rater baseline. · best: Codex (code-davinci-002)
- **Summary:** BIG-Bench Hard distills 23 BIG-bench tasks on which prior models failed to beat the average human rater, creating a compact, discriminating reasoning benchmark. It shows chain-of-thought prompting lets models surpass human raters on many of these tasks, quantifying the accuracy gain from CoT. BBH is now a standard component of LLM reasoning leaderboards for comparing model reasoning precision.

### Challenging BIG-Bench Tasks and Whether Chain-of-Thought Can Solve Them (2022)

- **Authors:** Mirac Suzgun, Nathan Scales, Nathanael Schärli, et al.
- **Venue:** arXiv preprint (later ACL Findings 2023) · `arXiv:2210.09261`
- **Citations:** 2,039 citations · 282 influential
- **URL:** https://arxiv.org/abs/2210.09261 · [S2](https://www.semanticscholar.org/paper/663a41c866d49ce052801fbc88947d39764cad29)
- **Task types:** multi-step reasoning; symbolic reasoning; algorithmic reasoning
- **Methods / metrics:** BIG-Bench Hard (23 tasks); chain-of-thought vs answer-only prompting; human-rater baseline comparison; emergent scaling analysis
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: PaLM; Codex (code-davinci-002) · strategy: Task accuracy with chain-of-thought vs answer-only prompting, benchmarked against average human-rater baseline; CoT x model-scale interaction analysis
- **Summary:** Curates BIG-Bench Hard, 23 tasks where prior LMs failed to beat average human raters, and shows chain-of-thought prompting lets large models surpass humans on most of them. Reveals CoT-dependent emergent performance on tasks with otherwise flat scaling. BBH has become a core discriminative reasoning benchmark for ranking frontier models.

### MathVista: Evaluating Mathematical Reasoning of Foundation Models in Visual Contexts (2023)

- **Authors:** Pan Lu, Hritik Bansal, Tony Xia, Kai-Wei Chang, Jianfeng Gao, et al.
- **Venue:** ICLR 2024 · `arXiv:2310.02255`
- **Citations:** 1,735 citations · 232 influential
- **URL:** https://arxiv.org/abs/2310.02255 · [S2](https://www.semanticscholar.org/paper/8946891e94831adc8cddb0d32311cce2445c96d2)
- **Task types:** visual mathematical reasoning; figure/diagram QA
- **Methods / metrics:** accuracy; human baseline comparison; program/chain-of-thought prompting
- **⚑ Empirical multi-LLM comparison** — 12 models · compared: GPT-4V; Bard; GPT-4 (CoT/PoT augmented); LLaVA; InstructBLIP; Multimodal-Bard; Chain-of-Thought GPT-4 · strategy: Accuracy of 12 LLMs/LMMs on visual math questions, compared against a human baseline and ranked head-to-head. · best: GPT-4V (49.9%)
- **Summary:** A visual mathematical-reasoning benchmark aggregating 31 datasets, on which 12 foundation models (LLMs and LMMs) are evaluated head-to-head. GPT-4V leads at 49.9% overall accuracy, outperforming the next-best (Bard) by 15.1 points but trailing humans by 10.4 points, giving a clear multi-model ranking on visual math.

### OlympiadBench: A Challenging Benchmark for Promoting AGI with Olympiad-Level Bilingual Multimodal Scientific Problems (2024)

- **Authors:** Chaoqun He, Renjie Luo, Yuzhuo Bai, et al.
- **Venue:** ACL 2024 (Main) · `arXiv:2402.14008`
- **Citations:** 1,195 citations · 141 influential
- **URL:** https://arxiv.org/abs/2402.14008 · [S2](https://www.semanticscholar.org/paper/bcf2c7e3f4ed64c8294c35a59220a26dd4f40060)
- **Task types:** olympiad mathematics; olympiad physics; bilingual multimodal reasoning
- **Methods / metrics:** 8,476 olympiad-level problems (EN/ZH, text+diagram); expert step-by-step annotations; answer-accuracy + step-level error attribution; multimodal problem evaluation
- **⚑ Empirical multi-LLM comparison** — compared: GPT-4V · strategy: Answer accuracy (average score %) plus step-level error attribution over top-tier models on 8,476 bilingual multimodal problems · best: GPT-4V
- **Summary:** Presents OlympiadBench, 8,476 olympiad-level bilingual math and physics problems, many multimodal with diagrams, each carrying expert step-by-step solutions. Enables fine-grained error analysis showing top models still fail most problems. Its expert-annotated reasoning traces support step-level evaluation and difficulty-graded comparison of frontier reasoning models.

### Faith and Fate: Limits of Transformers on Compositionality (2023)

- **Authors:** Nouha Dziri, Ximing Lu, Melanie Sclar, et al.
- **Venue:** NeurIPS 2023 (Spotlight) · `arXiv:2305.18654`
- **Citations:** 646 citations · 54 influential
- **URL:** https://arxiv.org/abs/2305.18654 · [S2](https://www.semanticscholar.org/paper/7d97c17a75beb89f938eaac1d3ca60ac2245fb2e)
- **Task types:** multi-digit multiplication; logic grid puzzles; dynamic-programming reasoning
- **Methods / metrics:** compositional-complexity scaling analysis; computation-graph / subgraph-matching probing; accuracy vs problem-complexity curves; error propagation analysis
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: GPT-3; ChatGPT (GPT-3.5); GPT-4 · strategy: Accuracy vs problem-complexity scaling curves with computation-graph/subgraph-matching probing and error-propagation analysis, compared across models
- **Summary:** Systematically tests transformers on compositional tasks and shows performance collapses from near-perfect to zero as complexity grows, arguing models rely on linearized subgraph matching rather than genuine multi-step computation. Provides a diagnostic methodology using computation graphs. Its complexity-scaling curves give a principled way to compare where different models break down on structured reasoning.

### GSM-Symbolic: Understanding the Limitations of Mathematical Reasoning in Large Language Models (2024)

- **Authors:** Iman Mirzadeh, Keivan Alizadeh, Hooman Shahrokhi, et al. (Apple)
- **Venue:** arXiv preprint (Apple ML Research) · `arXiv:2410.05229`
- **Citations:** 584 citations · 50 influential
- **URL:** https://arxiv.org/abs/2410.05229 · [S2](https://www.semanticscholar.org/paper/05506581cade1a8ef6372616cec20b81a3d5c366)
- **Task types:** grade-school math word problems; robustness stress-testing
- **Methods / metrics:** symbolic-template question generation; numeric/name perturbation; distractor-clause injection (GSM-NoOp); accuracy-drop and variance analysis under perturbation
- **⚑ Empirical multi-LLM comparison** — 20 models · compared: SOTA open-source LLMs; SOTA closed-source LLMs · strategy: Final-answer accuracy and variance across template instantiations; accuracy drop under numeric/name perturbation and distractor-clause injection (GSM-NoOp), compared across many SOTA models
- **Summary:** Builds GSM-Symbolic, a template-generated variant of GSM8K that regenerates questions with altered values, names, and added irrelevant clauses to test robustness. Finds systematic accuracy drops and high variance, arguing reported GSM8K scores overstate genuine reasoning. Its perturbation-and-variance methodology is a rigorous way to compare model reliability beyond a single fixed test set.

### Evaluating the Logical Reasoning Ability of ChatGPT and GPT-4 (2023)

- **Authors:** Hanmeng Liu, Ruoxi Ning, Zhiyang Teng, Jian Liu, Qiji Zhou, Yue Zhang
- **Venue:** arXiv (cs.CL) · `arXiv:2304.03439`
- **Citations:** 335 citations · 14 influential
- **URL:** https://arxiv.org/abs/2304.03439 · [S2](https://www.semanticscholar.org/paper/85cc48276c69924d3e92ddb38facb7d92be9a4a6)
- **Task types:** logical reasoning; reading-comprehension reasoning; NLI
- **Methods / metrics:** accuracy; in-distribution vs out-of-distribution accuracy; zero-shot vs fine-tuned comparison
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: GPT-4; ChatGPT (gpt-3.5-turbo); text-davinci-003; RoBERTa (fine-tuned baseline) · strategy: Zero-shot accuracy of GPT-4/ChatGPT vs a fine-tuned RoBERTa baseline on multiple logical-reasoning datasets, including OOD generalization tests. · best: GPT-4
- **Summary:** Benchmarks ChatGPT, GPT-4 and a supervised RoBERTa baseline (plus text-davinci) on logical-reasoning datasets LogiQA, ReClor and AR-LSAT, alongside a new out-of-distribution set and the LogiEval prompt suite. GPT-4 achieves the best accuracy on most datasets but performance drops sharply on out-of-distribution and NLI data, giving a quantitative multi-model logical-reasoning comparison.

### SciBench: Evaluating College-Level Scientific Problem-Solving Abilities of Large Language Models (2023)

- **Authors:** Xiaoxuan Wang, Ziniu Hu, Pan Lu, Yanqiao Zhu, Jieyu Zhang, Satyen Subramaniam, Arjun R. Loomba, Shichang Zhang, Yizhou Sun, Wei Wang
- **Venue:** ICML 2024 / arXiv · `arXiv:2307.10635`
- **Citations:** 252 citations · 19 influential
- **URL:** https://arxiv.org/abs/2307.10635 · [S2](https://www.semanticscholar.org/paper/4993258852711c4e3d0011325ac3db680eae84f4)
- **Task types:** scientific problem solving; quantitative reasoning
- **Methods / metrics:** answer accuracy; error-type breakdown across 10 problem-solving skills
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: GPT-4; GPT-3.5-turbo; Claude-2; LLaMA-2-7B; LLaMA-2-70B; Mistral-7B · strategy: Multiple open and proprietary LLMs solve open-ended college science problems under several prompting strategies (few-shot, CoT, tool-augmented); scored by accuracy plus a manual error-category analysis. · best: GPT-4 (highest, but best overall score only 43.22%)
- **Summary:** SciBench evaluates open and proprietary LLMs (GPT-4, GPT-3.5, Claude-2, LLaMA-2-7B/70B, Mistral) on open-ended college-level math, chemistry, and physics problems under varied prompting strategies. Accuracy is measured alongside a ten-category error analysis. Even the best model (GPT-4) reaches only 43.22%, and no single prompting strategy consistently wins.

### FrontierMath: A Benchmark for Evaluating Advanced Mathematical Reasoning in AI (2024)

- **Authors:** Elliot Glazer, Ege Erdil, Tamay Besiroglu, et al. (Epoch AI)
- **Venue:** arXiv preprint (Epoch AI) · `arXiv:2411.04872`
- **Citations:** 221 citations · 14 influential
- **URL:** https://arxiv.org/abs/2411.04872 · [S2](https://www.semanticscholar.org/paper/e7fadf3ba6f389d9db67fe578c466e7f9610e0fc)
- **Task types:** research-level mathematics; number theory / analysis / algebraic geometry
- **Methods / metrics:** expert-crafted unpublished problems; automated answer verification (SymPy-checkable); contamination-resistant design; solve-rate (<2% SOTA)
- **⚑ Empirical multi-LLM comparison** — strategy: Solve-rate (% of problems solved with automated SymPy-checkable answer verification) across current SOTA frontier models
- **Summary:** A benchmark of hundreds of original, unpublished research-level math problems vetted by expert mathematicians, with automated verification to resist contamination. Frontier models solve under 2%, exposing a wide capability gap and giving substantial headroom for future comparison. Its expert-crafted, auto-verifiable design is a template for durable, high-ceiling reasoning benchmarks.

### A Careful Examination of Large Language Model Performance on Grade School Arithmetic (2024)

- **Authors:** Hugh Zhang, Jeff Da, Dean Lee, et al.
- **Venue:** arXiv preprint (Scale AI) · `arXiv:2405.00332`
- **Citations:** 214 citations · 10 influential
- **URL:** https://arxiv.org/abs/2405.00332 · [S2](https://www.semanticscholar.org/paper/ef62f95c16f668f031d649799cbd79081c6d2b0f)
- **Task types:** grade-school arithmetic; data-contamination auditing
- **Methods / metrics:** GSM1k held-out benchmark (mirrors GSM8K); accuracy-gap (GSM8K vs GSM1k); overfitting/contamination detection; human-difficulty matching
- **⚑ Empirical multi-LLM comparison** — 15 models · compared: leading open-source LLMs; leading closed-source LLMs · strategy: Accuracy gap between GSM8K and held-out GSM1k, Spearman correlation between memorization probability and gap, systematic overfitting/contamination detection across model families
- **Summary:** Commissions GSM1k, a fresh benchmark built to match GSM8K's style and difficulty, and finds accuracy drops up to 13% with several model families showing systematic overfitting to GSM8K. Provides direct evidence of benchmark contamination inflating reported scores. The GSM8K-minus-GSM1k gap is a reusable methodology for auditing whether measured accuracy reflects real reasoning.

### A Careful Examination of Large Language Model Performance on Grade School Arithmetic (GSM1k) (2024)

- **Authors:** Hugh Zhang, Jeff Da, Dean Lee, Vaughn Robinson, Summer Yue, et al. (Scale AI)
- **Venue:** NeurIPS 2024 Datasets & Benchmarks Track · `arXiv:2405.00332`
- **Citations:** 214 citations · 10 influential
- **URL:** https://arxiv.org/abs/2405.00332 · [S2](https://www.semanticscholar.org/paper/ef62f95c16f668f031d649799cbd79081c6d2b0f)
- **Task types:** math; reasoning; contamination analysis
- **Methods / metrics:** accuracy; GSM8K-minus-GSM1k accuracy gap; overfitting gap
- **⚑ Empirical multi-LLM comparison** — 25 models · compared: GPT-4; Claude; Gemini; Llama-2/3; Mistral/Mixtral; Phi; Gemma; Qwen · strategy: Compare each model's GSM8K vs held-out GSM1k accuracy; the accuracy gap quantifies overfitting/contamination across families. · best: Frontier models (GPT-4 / Claude / Gemini) show least overfitting
- **Summary:** Builds GSM1k, a held-out GSM8K clone, and evaluates many leading open- and closed-source LLM families to detect benchmark contamination/overfitting. Several model families show systematic overfitting (accuracy drops up to 8%), while frontier models (GPT-4, Claude, Gemini) show minimal drop; a quantitative cross-model comparison of generalization.

### Chain-of-Thought Hub: A Continuous Effort to Measure Large Language Models' Reasoning Performance (2023)

- **Authors:** Yao Fu, Litu Ou, Mingyu Chen, et al.
- **Venue:** arXiv preprint · `arXiv:2305.17306`
- **Citations:** 133 citations · 8 influential
- **URL:** https://arxiv.org/abs/2305.17306 · [S2](https://www.semanticscholar.org/paper/ea75117f34b168a20f2a4309ac2eb685ca6b1436)
- **Task types:** math reasoning; science QA; symbolic reasoning; code; knowledge
- **Methods / metrics:** aggregated evaluation suite (GSM8K, MATH, BBH, MMLU, TheoremQA, HumanEval, C-Eval); chain-of-thought accuracy; cross-model leaderboarding; open vs closed model comparison
- **⚑ Empirical multi-LLM comparison** — 8 models · compared: GPT-4; Claude-v1.3; PaLM-2; GPT-3.5-Turbo; LLaMA-65B; code-davinci-002 · strategy: Chain-of-thought accuracy aggregated across multiple reasoning benchmarks into a continuously-updated leaderboard; cross-model ranking, open vs closed comparison · best: GPT-4
- **Summary:** Assembles an open-source suite of challenging reasoning benchmarks into a single leaderboard to continuously track and compare LLM reasoning across math, science, symbols, knowledge, and code. Provides a reproducible harness and finds clear scale-reasoning correlation. Directly aimed at standardizing multi-benchmark model comparison rather than reporting isolated scores.

### Gemini: A Family of Highly Capable Multimodal Models (2023)

- **Authors:** Gemini Team, Google (Rohan Anil, Sebastian Borgeaud, et al.)
- **Venue:** arXiv (Google technical report) · `arXiv:2312.11805`
- **Citations:** citations n/a
- **URL:** https://arxiv.org/abs/2312.11805
- **Task types:** reasoning; math; multitask knowledge; code; multimodal
- **Methods / metrics:** accuracy; pass@1; few-shot and CoT prompting; uncertainty-routed CoT
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: Gemini Ultra; Gemini Pro; Gemini Nano; GPT-4; GPT-3.5; PaLM 2 · strategy: Few-shot / chain-of-thought accuracy on standard math and reasoning benchmarks, compared against GPT-4 and PaLM 2 baselines reported side-by-side. · best: Gemini Ultra
- **Summary:** Introduces the Gemini Ultra/Pro/Nano family and benchmarks them head-to-head against GPT-4, GPT-3.5 and PaLM 2 on reasoning and math suites. Gemini Ultra reported state-of-the-art on 30 of 32 benchmarks and was the first model to exceed human-expert MMLU, also leading on GSM8K, MATH and BIG-Bench-Hard. Provides quantitative accuracy comparisons across models.

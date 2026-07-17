# Benchmark suites & holistic evaluation frameworks

_56 papers (53 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### Measuring Massive Multitask Language Understanding (MMLU) (2021)

- **Authors:** Dan Hendrycks, Collin Burns, Steven Basart, Andy Zou, Mantas Mazeika, Dawn Song, Jacob Steinhardt
- **Venue:** ICLR 2021 · `arXiv:2009.03300`
- **Citations:** 8,879 citations · 1685 influential
- **URL:** https://arxiv.org/abs/2009.03300 · [S2](https://www.semanticscholar.org/paper/814a4f680b9ba6baba23b93499f4b48af1a27678)
- **Task types:** multiple-choice question answering; STEM; humanities; social science; professional/medical/legal knowledge; multi-task; multiple-choice QA; knowledge; reasoning
- **Methods / metrics:** 57-subject multiple-choice accuracy; few-shot (5-shot) and zero-shot evaluation; per-subject and macro-average accuracy; human-expert comparison; multiple-choice accuracy; few-shot prompting; macro-average across subjects
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: GPT-3 (multiple sizes); GPT-2; UnifiedQA; T5 · strategy: 57-subject multiple-choice accuracy with per-subject and macro-average, few-shot/zero-shot prompting, compared against human-expert accuracy. · best: largest GPT-3
- **Summary:** MMLU measures multitask accuracy across 57 subjects spanning STEM, humanities, social sciences and professional domains using ~15,900 multiple-choice questions. It became the de facto standard for reporting a single comparable knowledge-and-reasoning accuracy score for LLMs. Its per-subject breakdown supports fine-grained comparison of where one model is more accurate than another.

### Measuring Massive Multitask Language Understanding (2021)

- **Authors:** Dan Hendrycks, Collin Burns, Steven Basart, et al.
- **Venue:** ICLR 2021 · `arXiv:2009.03300`
- **Citations:** 8,879 citations · 1685 influential
- **URL:** https://arxiv.org/abs/2009.03300 · [S2](https://www.semanticscholar.org/paper/814a4f680b9ba6baba23b93499f4b48af1a27678)
- **Task types:** multitask knowledge QA; elementary mathematics; STEM/humanities/law
- **Methods / metrics:** MMLU benchmark (57 subjects); few-shot multiple-choice accuracy; per-subject and macro-average accuracy; calibration/error analysis
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: GPT-3; GPT-2; UnifiedQA; T5 · strategy: Few-shot multiple-choice accuracy, per-subject and macro-average across 57 tasks, plus calibration/error analysis, compared across models · best: GPT-3 (175B)
- **Summary:** Introduces MMLU, a 57-subject multiple-choice test spanning STEM, humanities, social science, and law, that became the canonical broad knowledge-and-reasoning leaderboard metric. Reports per-subject accuracy revealing lopsided model competence and poor calibration. Its macro-averaged and per-domain accuracy is one of the most widely cited single numbers for model-vs-model comparison.

### GLUE: A Multi-Task Benchmark and Analysis Platform for Natural Language Understanding (2018)

- **Authors:** Alex Wang, Amanpreet Singh, Julian Michael, Felix Hill, Omer Levy, Samuel R. Bowman
- **Venue:** ICLR 2019 / EMNLP 2018 BlackboxNLP Workshop · `arXiv:1804.07461`
- **Citations:** 8,741 citations · 1428 influential
- **URL:** https://arxiv.org/abs/1804.07461 · [S2](https://www.semanticscholar.org/paper/451d4a16e425ecbf38c4b1cca0dcf5d9bec8255c)
- **Task types:** natural language inference; sentiment analysis; paraphrase detection; linguistic acceptability; textual entailment; text classification
- **Methods / metrics:** 9-task aggregate GLUE score; per-task accuracy / F1 / Matthews correlation / Pearson-Spearman; hand-crafted diagnostic test suite for linguistic analysis; public leaderboard
- **Summary:** GLUE assembles nine diverse NLU tasks (MNLI, QQP, QNLI, SST-2, MRPC, RTE, CoLA, etc.) into a single benchmark with a shared leaderboard and a hand-crafted diagnostic set for linguistic analysis. Its aggregate score gave the field its first widely adopted single comparable NLU metric. It established the multi-task leaderboard paradigm later inherited by nearly all LLM benchmark suites.

### Think You Have Solved Question Answering? Try ARC, the AI2 Reasoning Challenge (2018)

- **Authors:** Peter Clark, Isaac Cowhey, Oren Etzioni, et al.
- **Venue:** arXiv preprint (Allen Institute for AI) · `arXiv:1803.05457`
- **Citations:** 5,085 citations · 636 influential
- **URL:** https://arxiv.org/abs/1803.05457 · [S2](https://www.semanticscholar.org/paper/88bb0a28bb58d847183ec505dda89b63771bb495)
- **Task types:** multiple-choice science QA; knowledge + reasoning
- **Methods / metrics:** ARC Challenge / Easy split (7,787 questions); retrieval- and co-occurrence-based partitioning; multiple-choice accuracy; baseline solver comparison
- **Summary:** Introduces the ARC grade-school science QA benchmark, deliberately splitting off a Challenge Set of questions that defeat retrieval and word-co-occurrence baselines. Widely adopted (e.g., in the Open LLM Leaderboard) as a standard reasoning-knowledge benchmark. Its adversarial Challenge/Easy partition is an early template for building discriminative benchmarks that separate genuine reasoning from surface matching.

### Lost in the Middle: How Language Models Use Long Contexts (2023)

- **Authors:** Nelson F. Liu, Kevin Lin, John Hewitt, Ashwin Paranjape, Michele Bevilacqua, Fabio Petroni, Percy Liang
- **Venue:** TACL 2024 · `arXiv:2307.03172`
- **Citations:** 4,305 citations · 271 influential
- **URL:** https://arxiv.org/abs/2307.03172 · [S2](https://www.semanticscholar.org/paper/1733eb7792f7a43dd21f51f4d1017a1bffd217b5)
- **Task types:** open-domain QA; long-context retrieval
- **Methods / metrics:** accuracy / exact match by gold-document position
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: GPT-3.5-Turbo; GPT-3.5-Turbo-16k; Claude-1.3; MPT-30B-Instruct; LongChat-13B-16k · strategy: Controlled positional experiments varying the location of the relevant document; accuracy curves compared across models to isolate the middle-context degradation effect. · best: GPT-3.5-Turbo (strongest but still exhibits U-shaped degradation)
- **Summary:** Empirically analyzes several long-context LLMs on multi-document QA and key-value retrieval, showing a U-shaped 'lost in the middle' performance curve as relevant information moves to the center of the context. Compares GPT-3.5-Turbo, Claude, MPT-30B, and LongChat, quantifying how retrieval position degrades QA accuracy across models.

### TruthfulQA: Measuring How Models Mimic Human Falsehoods (2021)

- **Authors:** Stephanie Lin, Jacob Hilton, Owain Evans
- **Venue:** ACL 2022 · `arXiv:2109.07958`
- **Citations:** 3,613 citations · 481 influential
- **URL:** https://arxiv.org/abs/2109.07958 · [S2](https://www.semanticscholar.org/paper/77d956cdab4508d569ae5741549b78e715fd0749)
- **Task types:** knowledge/truthfulness QA
- **Methods / metrics:** % truthful; % truthful and informative; GPT-judge automated classifier
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: GPT-3 (multiple sizes); GPT-Neo/GPT-J; GPT-2; UnifiedQA (T5-based) · strategy: Human evaluation of truthfulness/informativeness plus a fine-tuned 'GPT-judge' automated metric; compared across model families and sizes to reveal inverse scaling. · best: GPT-3 (largest) - highest but only 58% truthful
- **Summary:** TruthfulQA presents 817 questions across 38 categories designed to elicit imitative falsehoods, and evaluates four model families across many sizes (GPT-3, GPT-Neo/J, GPT-2, UnifiedQA/T5). The best model was truthful on only 58% vs 94% for humans, and larger models were often less truthful (inverse scaling). A multi-model truthfulness knowledge benchmark.

### SuperGLUE: A Stickier Benchmark for General-Purpose Language Understanding Systems (2019)

- **Authors:** Alex Wang, Yada Pruksachatkun, Nikita Nangia, Amanpreet Singh, Julian Michael, Felix Hill, Omer Levy, Samuel R. Bowman
- **Venue:** NeurIPS 2019 · `arXiv:1905.00537`
- **Citations:** 2,845 citations · 333 influential
- **URL:** https://arxiv.org/abs/1905.00537 · [S2](https://www.semanticscholar.org/paper/d9f6ada77448664b71128bb19df15765336974a6)
- **Task types:** question answering; coreference resolution; word sense disambiguation; natural language inference; reading comprehension; causal reasoning
- **Methods / metrics:** 8-task aggregate SuperGLUE score; per-task accuracy / F1 / exact match; human-performance baselines; public leaderboard and toolkit
- **Summary:** SuperGLUE succeeds GLUE with a harder set of eight NLU tasks after models surpassed non-expert human performance on GLUE, restoring headroom for measuring progress. It pairs each task with human baselines so model accuracy can be compared against a human reference point. Its design directly informed how difficulty and saturation are managed in later LLM benchmark suites.

### Beyond the Imitation Game: Quantifying and Extrapolating the Capabilities of Language Models (BIG-bench) (2022)

- **Authors:** Aarohi Srivastava, Abhinav Rastogi, et al. (444 authors)
- **Venue:** arXiv preprint / TMLR 2023 · `arXiv:2206.04615`
- **Citations:** 2,561 citations · 184 influential
- **URL:** https://arxiv.org/abs/2206.04615 · [S2](https://www.semanticscholar.org/paper/bd1331b233e84bab7eba503abc60b31ac08e7881)
- **Task types:** reasoning; commonsense; math; linguistics; social bias; code; question answering; multi-task; common-sense; social-bias
- **Methods / metrics:** 204-task collaborative benchmark; scaling-curve analysis across model sizes; aggregate normalized preferred metric; human-rater baselines; few-shot and zero-shot evaluation; multiple-choice accuracy; exact-match; BLEU/ROUGE; scaling curves; aggregate normalized score
- **⚑ Empirical multi-LLM comparison** — 10 models · compared: OpenAI GPT models; Google dense transformers (PaLM-style); Switch sparse transformers · strategy: 204-task benchmark using aggregate normalized preferred metric plus per-task accuracy/exact-match/BLEU-ROUGE, compared across model sizes and against human-rater baselines via scaling curves.
- **Summary:** BIG-bench is a 204-task benchmark contributed by 450+ authors across 132 institutions, deliberately targeting tasks believed to lie beyond current model capabilities. It quantifies how accuracy scales with model size and contrasts model performance against human raters, enabling extrapolation of capabilities. Its breadth and standardized per-task metrics let researchers compare models on a common, diverse capability surface.

### MMLU-Pro: A More Robust and Challenging Multi-Task Language Understanding Benchmark (2024)

- **Authors:** Yubo Wang, Xueguang Ma, Ge Zhang, et al.
- **Venue:** NeurIPS 2024 Datasets and Benchmarks Track · `arXiv:2406.01574`
- **Citations:** 1,904 citations · 219 influential
- **URL:** https://arxiv.org/abs/2406.01574 · [S2](https://www.semanticscholar.org/paper/1406bb4cb6801bc4767b661308118c888a9b09da)
- **Task types:** multiple-choice question answering; reasoning; STEM; multi-task; multitask knowledge + reasoning QA; STEM problem solving
- **Methods / metrics:** 10-option multiple-choice accuracy (vs 4 in MMLU); chain-of-thought vs direct-answer comparison; prompt-sensitivity analysis over 24 prompt styles; distractor-hardening and noise removal; 10-option multiple choice (vs 4); reasoning-focused question curation; prompt-sensitivity analysis (24 prompt styles); CoT vs direct accuracy gap; discriminative-power comparison
- **⚑ Empirical multi-LLM comparison** — 10 models · compared: GPT-4; GPT-3.5; Llama-2; Gemini; Mixtral · strategy: 10-option multiple-choice accuracy, CoT vs direct-answer gap, and prompt-sensitivity analysis over 24 prompt styles; discriminative-power comparison across models.
- **Summary:** MMLU-Pro extends MMLU by expanding each item to 10 answer options, injecting harder reasoning-focused questions, and removing trivial/noisy items, dropping accuracy 16-33% and separating models more cleanly. Crucially it reduces score sensitivity to prompt variation from 4-5% to ~2%, improving the statistical stability of reported accuracy. This makes cross-model precision comparisons more reliable and less confounded by prompt luck.

### ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs (2023)

- **Authors:** Yujia Qin, Shihao Liang, Yining Ye, ... Zhiyuan Liu, Maosong Sun
- **Venue:** ICLR 2024 · `arXiv:2307.16789`
- **Citations:** 1,888 citations · 258 influential
- **URL:** https://arxiv.org/abs/2307.16789 · [S2](https://www.semanticscholar.org/paper/0bfc804e31eecfd77f45e4ee7f4d629fffdcd628)
- **Task types:** tool use; function calling; API call generation
- **Methods / metrics:** pass rate; win rate; LLM-as-judge (GPT-4)
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: GPT-4; ChatGPT (gpt-3.5-turbo); Text-Davinci-003; Claude-2; ToolLLaMA-7B · strategy: ToolEval automatic evaluation with GPT-4 as LLM judge; metrics are pass rate and pairwise win rate over solution paths. · best: GPT-4 (ToolLLaMA comparable to ChatGPT)
- **Summary:** ToolLLM introduces ToolBench (16,464 real-world REST APIs across 49 categories) and ToolEval, an automatic GPT-4-judged evaluator. Multiple models are compared on single- and multi-tool instruction following and unseen-API generalization, reporting pass rate and win rate. ToolLLaMA (fine-tuned) reaches performance comparable to ChatGPT, while GPT-4 leads overall.

### RealToxicityPrompts: Evaluating Neural Toxic Degeneration in Language Models (2020)

- **Authors:** Samuel Gehman, Suchin Gururangan, Maarten Sap, Yejin Choi, Noah A. Smith
- **Venue:** EMNLP 2020 Findings · `arXiv:2009.11462`
- **Citations:** 1,771 citations · 240 influential
- **URL:** https://arxiv.org/abs/2009.11462 · [S2](https://www.semanticscholar.org/paper/399e7d8129c60818ee208f236c8dda17e876d21f)
- **Task types:** toxicity
- **Methods / metrics:** expected maximum toxicity; probability of toxicity; Perspective API scores
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: GPT-1; GPT-2; GPT-3; CTRL; CTRL-Wiki · strategy: Toxicity classifier scoring of generations across LMs and mitigation methods; expected-max-toxicity and toxicity-probability metrics.
- **Summary:** Introduces 100K naturally occurring prompts and measures toxic degeneration across several pretrained LMs (GPT-1, GPT-2 across sizes, GPT-3, CTRL, CTRL-Wiki) using the Perspective API toxicity classifier. All models could be prompted into toxic generations, and the paper compares controllable-generation and detoxification methods, finding none fully failsafe.

### WebArena: A Realistic Web Environment for Building Autonomous Agents (2023)

- **Authors:** Shuyan Zhou, Frank F. Xu, Hao Zhu, ... Uri Alon, Graham Neubig
- **Venue:** ICLR 2024 · `arXiv:2307.13854`
- **Citations:** 1,651 citations · 212 influential
- **URL:** https://arxiv.org/abs/2307.13854 · [S2](https://www.semanticscholar.org/paper/e41482f4ee984f17382f6cdd900df094d928be06)
- **Task types:** web agent tasks; tool use; long-horizon navigation
- **Methods / metrics:** success rate; functional correctness
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: GPT-4; GPT-3.5-turbo; text-bison-001 (PaLM-2) · strategy: Execution-based functional correctness / task success rate on 812 tasks; human performance baseline. · best: GPT-4
- **Summary:** WebArena is a reproducible, self-hosted web environment with fully functional e-commerce, forum, GitLab and CMS sites plus 812 long-horizon tasks. GPT-4, GPT-3.5 and PaLM-2 (text-bison) agents are compared with functional-correctness success checks. The best agent (GPT-4) reaches only 14.41% end-to-end success versus 78.24% for humans.

### LongBench: A Bilingual, Multitask Benchmark for Long Context Understanding (2024)

- **Authors:** Yushi Bai, Xin Lv, Jiajie Zhang, Hongchang Lyu, Jiankai Tang, Zhidian Huang, Zhengxiao Du, Xiao Liu, Aohan Zeng, Lei Hou, Yuxiao Dong, Jie Tang, Juanzi Li
- **Venue:** ACL 2024 · `arXiv:2308.14508`
- **Citations:** 1,452 citations · 350 influential
- **URL:** https://arxiv.org/abs/2308.14508 · [S2](https://www.semanticscholar.org/paper/b31a5884a8ebe96b6300839b28608b97f8f8ef76)
- **Task types:** summarization; long-context understanding; QA
- **Methods / metrics:** ROUGE; F1; accuracy
- **⚑ Empirical multi-LLM comparison** — 8 models · compared: GPT-3.5-Turbo-16k; ChatGLM2-6B-32k; LongChat-7B-16k; Vicuna-7B-16k; XGen-7B; InternLM-7B; Llama2-7B-chat-4k · strategy: Standardized automatic metrics per task (ROUGE for summarization, F1/accuracy elsewhere); models ranked by aggregate and per-task scores. · best: GPT-3.5-Turbo-16k
- **Summary:** A bilingual multitask long-context benchmark covering six task categories including summarization, evaluating eight LLMs under standardized automatic metrics. GPT-3.5-Turbo-16k outperforms open-source models but still degrades on longer contexts. Summarization performance is quantified per model, enabling direct cross-model ranking.

### BloombergGPT: A Large Language Model for Finance (2023)

- **Authors:** Shijie Wu, Ozan Irsoy, Steven Lu, Vadim Dabravolski, Mark Dredze, Sebastian Gehrmann, Prabhanjan Kambadur, David Rosenberg, Gideon Mann
- **Venue:** arXiv (cs.LG) · `arXiv:2303.17564`
- **Citations:** 1,383 citations · 72 influential
- **URL:** https://arxiv.org/abs/2303.17564 · [S2](https://www.semanticscholar.org/paper/83edcfbb206ddad38a971d605da09390604248ea)
- **Task types:** financial sentiment; NER; financial QA; general benchmarks
- **Methods / metrics:** accuracy; F1; per-task scores
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: BloombergGPT-50B; GPT-NeoX-20B; OPT-66B; BLOOM-176B; GPT-3 (175B, external results) · strategy: Head-to-head evaluation of a 50B finance-trained model against similarly sized open LLMs (GPT-NeoX, OPT-66B, BLOOM) and GPT-3 on financial and general benchmarks, scored by accuracy/F1. · best: BloombergGPT (best on financial tasks without sacrificing general performance)
- **Summary:** BloombergGPT trains a 50B-parameter finance LLM and compares it head-to-head with GPT-NeoX-20B, OPT-66B, BLOOM-176B, and GPT-3 on financial NLP tasks (sentiment, NER, QA) and standard general benchmarks. Performance is quantified via accuracy/F1 per task. BloombergGPT outperforms the comparably sized open models on finance tasks while remaining competitive on general benchmarks.

### Mind2Web: Towards a Generalist Agent for the Web (2023)

- **Authors:** Xiang Deng, Yu Gu, Boyuan Zheng, ... Huan Sun, Yu Su
- **Venue:** NeurIPS 2023 (Spotlight) · `arXiv:2306.06070`
- **Citations:** 1,267 citations · 189 influential
- **URL:** https://arxiv.org/abs/2306.06070 · [S2](https://www.semanticscholar.org/paper/58f8925a8b87054ad0635a6398a7fe24935b1604)
- **Task types:** web agent tasks; action prediction; tool use
- **Methods / metrics:** element accuracy; operation F1; step success rate; task success rate
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: GPT-4; GPT-3.5-turbo; Flan-T5-XL; Flan-T5-Base · strategy: Element accuracy, operation F1, step success rate and overall task success rate under three generalization splits. · best: GPT-4
- **Summary:** Mind2Web offers 2,000+ open-ended tasks from 137 real websites across 31 domains for generalist web agents. Using the MindAct framework (small LM candidate ranking + LLM action prediction), GPT-3.5, GPT-4 and Flan-T5 variants are compared on element selection, operation prediction and step/task success. GPT-4 achieves the best step success but overall task success remains low, showing large headroom.

### GAIA: A Benchmark for General AI Assistants (2023)

- **Authors:** Gregoire Mialon, Clementine Fourrier, Craig Swift, Thomas Wolf, Yann LeCun, Thomas Scialom
- **Venue:** ICLR 2024 (arXiv preprint 2023) · `arXiv:2311.12983`
- **Citations:** 990 citations · 182 influential
- **URL:** https://arxiv.org/abs/2311.12983 · [S2](https://www.semanticscholar.org/paper/ab8169d6e4dfabfe7c30ebec1bb871bf3e1551cd)
- **Task types:** tool use; web browsing; multi-modal reasoning; file/document understanding; multi-step question answering; agentic tasks
- **Methods / metrics:** 466 real-world questions with unambiguous ground-truth answers; exact-match scoring (no LLM judge needed); three difficulty levels; human vs model accuracy gap analysis
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: GPT-4 (with plugins); GPT-4 (no tools); GPT-4 + AutoGPT; GPT-3.5 · strategy: Quasi-exact-match accuracy on 466 questions across three levels; AI systems compared against human respondents. · best: GPT-4 with plugins
- **Summary:** GAIA poses 466 real-world questions requiring reasoning, multimodality, web browsing and tool use, with unambiguous answers unlikely to appear verbatim in training data. The stark human-vs-model gap (92% human vs 15% GPT-4-with-plugins) provides a clean, high-headroom accuracy comparison for agentic assistants. Because answers are exact-match verifiable, it enables objective, judge-free scoring of general-assistant precision.

### OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments (2024)

- **Authors:** Tianbao Xie, Danyang Zhang, Jixuan Chen, ... Victor Zhong, Tao Yu
- **Venue:** NeurIPS 2024 · `arXiv:2404.07972`
- **Citations:** 912 citations · 149 influential
- **URL:** https://arxiv.org/abs/2404.07972 · [S2](https://www.semanticscholar.org/paper/ff3e4f7c2481fb6df539f02be5945235101cbc19)
- **Task types:** computer-use agent; GUI grounding; tool use
- **Methods / metrics:** success rate; execution-based verification
- **⚑ Empirical multi-LLM comparison** — 9 models · compared: GPT-4V; GPT-4o; Gemini-Pro; Claude-3-Opus; Qwen-VL-Max; CogAgent; Mixtral; GPT-4 (a11y tree) · strategy: Execution-based success rate via task-specific setup and verification scripts over real OS states; human baseline for comparison. · best: GPT-4V / GPT-4o
- **Summary:** OSWorld is a scalable real-OS environment (Ubuntu/Windows/macOS) with 369 open-ended computer tasks spanning web and desktop apps and multi-app workflows, evaluated by execution-based checks. Multiple LLM/VLM agents (GPT-4V, GPT-4o, Gemini, Claude-3, open VLMs) are compared on success rate. The best model reaches only 12.24% versus 72.36% for humans.

### AGIEval: A Human-Centric Benchmark for Evaluating Foundation Models (2023)

- **Authors:** Wanjun Zhong, Ruixiang Cui, Yiduo Guo, et al. (Nan Duan)
- **Venue:** NAACL 2024 Findings (arXiv 2023) · `arXiv:2304.06364`
- **Citations:** 864 citations · 65 influential
- **URL:** https://arxiv.org/abs/2304.06364 · [S2](https://www.semanticscholar.org/paper/68c834c19cd126bbd6d25a3572d7205cfed76271)
- **Task types:** knowledge/exam QA; reasoning
- **Methods / metrics:** accuracy (few-shot and zero-shot, with/without CoT)
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: GPT-4; ChatGPT; text-davinci-003 · strategy: Zero/few-shot accuracy on human-exam questions compared across three LLMs and against human test-taker performance; no LLM judge. · best: GPT-4 (surpasses average human on several exams)
- **Summary:** AGIEval evaluates foundation models on standardized human exams (college entrance, LSAT, math competitions, lawyer qualification). GPT-4, ChatGPT, and text-davinci-003 are compared, with GPT-4 exceeding average human performance on several exams (95% SAT Math). A multi-model human-centric knowledge/reasoning benchmark.

### τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains (2024)

- **Authors:** Shunyu Yao, Noah Shinn, Pedram Razavi, Karthik Narasimhan
- **Venue:** arXiv (Sierra) · `arXiv:2406.12045`
- **Citations:** 811 citations · 118 influential
- **URL:** https://arxiv.org/abs/2406.12045 · [S2](https://www.semanticscholar.org/paper/70aa016c1f68fd5c0261f26ad20017b8307650af)
- **Task types:** tool use; function calling; multi-turn user interaction
- **Methods / metrics:** pass^1 / pass^k reliability; database state match; LLM user simulator
- **⚑ Empirical multi-LLM comparison** — 12 models · compared: GPT-4o; GPT-4-turbo; GPT-4; GPT-3.5-turbo; Claude-3-Opus; Claude-3-Sonnet; Claude-3-Haiku; Mistral-Large; Gemini-1.5 · strategy: Execution-based comparison of final database state vs annotated goal; user simulated by an LLM; reliability measured with pass^k over repeated trials. · best: GPT-4o
- **Summary:** τ-bench emulates dynamic conversations between an LLM-simulated user and a tool-using agent under domain policies in retail and airline domains. Multiple function-calling models are evaluated by comparing the final database state to annotated goals, with a novel pass^k metric for reliability across trials. Even the best model (GPT-4o) solves under 50% of tasks and is highly inconsistent (pass^8 < 25% in retail).

### BBQ: A Hand-Built Bias Benchmark for Question Answering (2021)

- **Authors:** Alicia Parrish, Angelica Chen, Nikita Nangia, Vishakh Padmakumar, Jason Phang, Jana Thompson, Phu Mon Htut, Samuel R. Bowman
- **Venue:** ACL 2022 Findings · `arXiv:2110.08193`
- **Citations:** 803 citations · 138 influential
- **URL:** https://arxiv.org/abs/2110.08193 · [S2](https://www.semanticscholar.org/paper/7d5c661fa9a4255ee087e861f820564ea2e2bd6b)
- **Task types:** bias; fairness
- **Methods / metrics:** bias score; accuracy in ambiguous vs disambiguated contexts
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: UnifiedQA (multiple sizes); RoBERTa-QA; DeBERTaV3-QA · strategy: Bias-score and accuracy differentials across social categories, compared across several QA models/sizes.
- **Summary:** A hand-built social-bias QA benchmark spanning nine protected dimensions, testing whether models rely on stereotypes under-informatively and whether biases override correct answers when context is informative. Multiple UnifiedQA-scale models and fine-tuned RoBERTa/DeBERTa QA systems are compared via a bias score; models achieved up to 3.4 (and 5+ for gender) points higher accuracy when the correct answer aligned with a social bias.

### Benchmarking Large Language Models in Retrieval-Augmented Generation (RGB) (2023)

- **Authors:** Jiawei Chen, Hongyu Lin, Xianpei Han, Le Sun
- **Venue:** AAAI 2024 · `arXiv:2309.01431`
- **Citations:** 586 citations · 23 influential
- **URL:** https://arxiv.org/abs/2309.01431 · [S2](https://www.semanticscholar.org/paper/28e2ecb4183ebc0eec504b12dddc677f8aef8745)
- **Task types:** RAG evaluation; open-domain QA
- **Methods / metrics:** answer accuracy; rejection rate; error detection/correction rate
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: ChatGPT (gpt-3.5-turbo); ChatGLM-6B; ChatGLM2-6B; Vicuna-7B; Qwen-7B-Chat; BELLE-7B; Llama-2-7B-chat · strategy: Per-ability accuracy over retrieved contexts with controlled noise ratios; exact-match/accuracy scoring compared across the six LLMs; no LLM judge. · best: ChatGPT (gpt-3.5-turbo) (strongest overall, still limited)
- **Summary:** Introduces RGB, a bilingual (English/Chinese) RAG benchmark testing four core abilities: noise robustness, negative rejection, information integration, and counterfactual robustness. Six representative LLMs are evaluated head-to-head, revealing they struggle with rejecting no-answer cases, integrating multiple documents, and resisting misinformation. A clear multi-model RAG comparison.

### API-Bank: A Comprehensive Benchmark for Tool-Augmented LLMs (2023)

- **Authors:** Minghao Li, Yingxiu Zhao, Bowen Yu, ... Fei Huang, Yongbin Li
- **Venue:** EMNLP 2023 · `arXiv:2304.08244`
- **Citations:** 532 citations · 44 influential
- **URL:** https://arxiv.org/abs/2304.08244 · [S2](https://www.semanticscholar.org/paper/19c222d1f18317d58cc85491f37479bc0dc49f41)
- **Task types:** tool use; function calling; API planning
- **Methods / metrics:** accuracy; ROUGE-L; correctness score
- **⚑ Empirical multi-LLM comparison** — 10 models · compared: GPT-4; GPT-3.5-turbo; GPT-3 (davinci); ChatGLM-6B; Alpaca-7B; Lynx-7B; LLaMA-7B; Vicuna-13B · strategy: Correctness of API calls (accuracy) and ROUGE-L for generated responses across three ability levels; models ranked by points. · best: GPT-4
- **Summary:** API-Bank provides 73 API tools and 314 tool-use dialogues (753 API calls) plus a training set, and evaluates LLMs on planning, retrieving and calling APIs. Several models are compared, with GPT-4 strongest at planning; the trained Lynx model surpasses Alpaca by 26+ points and approaches GPT-3.5.

### HaluEval: A Large-Scale Hallucination Evaluation Benchmark for Large Language Models (2023)

- **Authors:** Junyi Li, Xiaoxue Cheng, Wayne Xin Zhao, Jian-Yun Nie, Ji-Rong Wen
- **Venue:** EMNLP 2023 · `arXiv:2305.11747`
- **Citations:** 500 citations · 35 influential
- **URL:** https://arxiv.org/abs/2305.11747 · [S2](https://www.semanticscholar.org/paper/e0384ba36555232c587d4a80d527895a095a9001)
- **Task types:** hallucination
- **Methods / metrics:** hallucination detection accuracy; human annotation
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: ChatGPT; GPT-3 (davinci); text-davinci; Alpaca; Vicuna; Llama · strategy: Classification accuracy on distinguishing hallucinated vs correct samples, compared across several LLMs; augmentation ablations (knowledge, reasoning). · best: ChatGPT
- **Summary:** Builds a 35K-example benchmark of generated and human-annotated hallucinated samples across QA, dialogue, and summarization, then evaluates the ability of several LLMs to recognize hallucinations. ChatGPT was found to fabricate unverifiable content in ~19.5% of responses, and multiple LLMs struggled to detect hallucinations; adding external knowledge or reasoning steps improved detection accuracy.

### From Crowdsourced Data to High-Quality Benchmarks: Arena-Hard and BenchBuilder Pipeline (2024)

- **Authors:** Tianle Li, Wei-Lin Chiang, Evan Frick, Lisa Dunlap, et al.
- **Venue:** arXiv preprint (OpenReview KfTf9vFvSn) · `arXiv:2406.11939`
- **Citations:** 479 citations · 102 influential
- **URL:** https://arxiv.org/abs/2406.11939 · [S2](https://www.semanticscholar.org/paper/05f02b4ed43d01f3efbbdcb454cc17b333f74817)
- **Task types:** challenging instruction-following prompts; automatic pairwise judging; automatic benchmark construction; win-rate comparison; open-ended instruction following
- **Methods / metrics:** LLM-as-a-judge (GPT-4) pairwise; Bradley-Terry / win-rate against baseline; separability metric; confidence intervals; agreement/correlation with Chatbot Arena human ranking; BenchBuilder prompt curation; BenchBuilder auto-curation pipeline; Arena-Hard-Auto benchmark; GPT-4 judge win-rate; separability and confidence-interval metrics; agreement/correlation with Chatbot Arena rankings
- **⚑ Empirical multi-LLM comparison** — strategy: Builds Arena-Hard-Auto and runs a leaderboard-style multi-model evaluation using GPT-4 LLM-as-judge pairwise win-rate vs a baseline (Bradley-Terry), reporting model separability with confidence intervals and ~98.6% correlation of model rankings with Chatbot Arena human preferences.
- **Summary:** Presents Arena-Hard-Auto and the BenchBuilder pipeline that mines challenging prompts from crowdsourced Chatbot Arena data to build a cheap automatic benchmark. It defines explicit metrics for a benchmark's separability (ability to confidently distinguish models) and agreement with human preference rankings, achieving ~98.6% correlation with Chatbot Arena at ~$20. Key methodology for validating automatic pairwise rankers against human leaderboards.

### LegalBench: A Collaboratively Built Benchmark for Measuring Legal Reasoning in Large Language Models (2023)

- **Authors:** Neel Guha, Julian Nyarko, Daniel E. Ho, Christopher Ré, Adam Chilton, et al.
- **Venue:** NeurIPS 2023 Datasets and Benchmarks / arXiv · `arXiv:2308.11462`
- **Citations:** 457 citations · 22 influential
- **URL:** https://arxiv.org/abs/2308.11462 · [S2](https://www.semanticscholar.org/paper/0aa5f3e94fab50e3c19870880fdaf245bfebdfae)
- **Task types:** legal reasoning; classification; QA
- **Methods / metrics:** accuracy/exact-match per task; balanced accuracy
- **⚑ Empirical multi-LLM comparison** — 20 models · compared: GPT-4; GPT-3.5-turbo; Claude-1; LLaMA-2-70B; Flan-T5-XXL; OPT; Cohere Command; Vicuna-13B; WizardLM; MPT-30B; Incite · strategy: Prompted (few-shot) evaluation of 20 open and commercial LLMs across 162 expert-authored legal tasks, scored by per-task accuracy/exact-match and aggregated by reasoning category. · best: GPT-4 (strongest overall, though far from expert reliability)
- **Summary:** LegalBench is a collaboratively built benchmark of 162 legal-reasoning tasks used to evaluate 20 open-source and commercial LLMs (GPT-4, GPT-3.5, Claude, LLaMA-2, Flan-T5, OPT, Cohere, Vicuna, MPT, and others). Each model is prompted per task and scored by accuracy/exact-match, then aggregated across six reasoning categories. GPT-4 leads but the paper stresses that no model reaches reliable legal-professional performance.

### FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation (2023)

- **Authors:** Tu Vu, Mohit Iyyer, Xuezhi Wang, et al. (Thang Luong)
- **Venue:** ACL 2024 Findings (arXiv 2023) · `arXiv:2310.03214`
- **Citations:** 392 citations · 46 influential
- **URL:** https://arxiv.org/abs/2310.03214 · [S2](https://www.semanticscholar.org/paper/be177300487b6d0f25e6cade9a31900454b13281)
- **Task types:** open-domain QA; retrieval-augmented QA
- **Methods / metrics:** strict/relaxed accuracy (human judged); hallucination rate
- **⚑ Empirical multi-LLM comparison** — 8 models · compared: GPT-4; GPT-3.5; ChatGPT; PaLM; PaLMChat; Flan-PaLM; Google (T5-based); Vicuna · strategy: Two-mode human evaluation (strict and relaxed correctness) over 50K+ judgments comparing base LLMs vs search-augmented FreshPrompt across models. · best: GPT-4 + FreshPrompt (largest gains, best accuracy)
- **Summary:** Introduces FreshQA (fast-changing and false-premise questions) and benchmarks a diverse array of closed and open LLMs with 50K+ human judgments under a two-mode correctness/hallucination protocol. The proposed FreshPrompt search augmentation is tested across models. A multi-model open-domain QA comparison focused on current-knowledge freshness.

### TrustLLM: Trustworthiness in Large Language Models (2024)

- **Authors:** Yue Huang, Lichao Sun, Haoran Wang, et al. (70 authors)
- **Venue:** ICML 2024 / arXiv · `arXiv:2401.05561`
- **Citations:** 351 citations · 32 influential
- **URL:** https://arxiv.org/abs/2401.05561 · [S2](https://www.semanticscholar.org/paper/fb4dc0178e5d7347b1615c48caf05347b6e5eb48)
- **Task types:** truthfulness; safety; bias; robustness
- **Methods / metrics:** per-dimension accuracy/refusal rates; aggregate trustworthiness scores
- **⚑ Empirical multi-LLM comparison** — 16 models · compared: GPT-4; ChatGPT; Llama2; Vicuna; ChatGLM; PaLM2; Mistral; Baichuan · strategy: Multi-dimension scoring over 30+ datasets, ranking 16 LLMs; proprietary vs open-source comparison. · best: GPT-4
- **Summary:** Evaluates 16 mainstream LLMs across six trustworthiness dimensions (truthfulness, safety, fairness, robustness, privacy, machine ethics) using over 30 datasets. Proprietary models generally scored higher on trustworthiness than open-source ones, though some open models were competitive, and several models were over-calibrated toward safety (refusing benign requests), quantified via per-dimension aggregate scores.

### Humanity's Last Exam (2025)

- **Authors:** Long Phan, Alice Gatti, Ziwen Han, Dan Hendrycks, et al. (CAIS & Scale AI)
- **Venue:** arXiv; Nature 2025 (DOI 10.1038/s41586-025-09962-4) · `arXiv:2501.14249 / DOI:10.1038/s41586-025-09962-4`
- **Citations:** 348 citations · 42 influential
- **URL:** https://arxiv.org/abs/2501.14249 · [S2](https://www.semanticscholar.org/paper/a5524d085ac586d531021dcb1ec156eaf942b109)
- **Task types:** frontier reasoning; math; science; multimodal QA
- **Methods / metrics:** accuracy; calibration / RMS calibration error; automated grading
- **⚑ Empirical multi-LLM comparison** — 8 models · compared: OpenAI o1; GPT-4o; Claude 3.5 Sonnet; Gemini 1.5/2.0; DeepSeek-R1; Grok-2; o3-mini · strategy: Automated accuracy and calibration scoring of frontier reasoning models on 2,500 expert questions, ranked head-to-head. · best: Reasoning models (o1 / DeepSeek-R1) highest but still low single-digit-to-teens accuracy
- **Summary:** A 2,500-question expert-authored multimodal benchmark spanning mathematics, sciences and humanities at the frontier of human knowledge. Frontier LLMs (GPT-4o, o1, Claude 3.5 Sonnet, Gemini, DeepSeek-R1, Grok) are compared and all score low accuracy with poor calibration, quantifying the gap to expert humans and ranking reasoning models.

### MINT: Evaluating LLMs in Multi-turn Interaction with Tools and Language Feedback (2023)

- **Authors:** Xingyao Wang, Zihan Wang, Jiateng Liu, Yangyi Chen, Lifan Yuan, Hao Peng, Heng Ji
- **Venue:** ICLR 2024 · `arXiv:2309.10691`
- **Citations:** 340 citations · 17 influential
- **URL:** https://arxiv.org/abs/2309.10691 · [S2](https://www.semanticscholar.org/paper/12b233752c7097ea6525622bed238ae2d2193c5a)
- **Task types:** tool use; multi-turn interaction; reasoning; code
- **Methods / metrics:** success rate; tool-use gain; feedback gain; LLM feedback simulator
- **⚑ Empirical multi-LLM comparison** — 20 models · compared: GPT-4; GPT-3.5-turbo; Claude-2; Claude-instant; LLaMA-2-70B; Vicuna-33B; CodeLlama-34B; Lemur-70B; WizardLM; Baichuan · strategy: Success rate across k interaction turns with and without tools/feedback; GPT-4 simulates user language feedback; improvement-per-turn deltas compared across 20 models. · best: GPT-4
- **Summary:** MINT benchmarks 20 open- and closed-source LLMs on multi-turn tasks where agents call Python tools and receive GPT-4-simulated natural-language feedback. It measures success-rate gains from tool use (1-8% per turn) and from language feedback (2-17%), finding that better single-turn performance does not guarantee better multi-turn performance and that RLHF can reduce feedback-leveraging ability.

### The Belebele Benchmark: a Parallel Reading Comprehension Dataset in 122 Language Variants (2024)

- **Authors:** Lucas Bandarkar, Davis Liang, Benjamin Muller, Mikel Artetxe, Satya Narayan Shukla, Donald Husa, Naman Goyal, Abhinandan Krishnan, Luke Zettlemoyer, Madian Khabsa
- **Venue:** ACL 2024 · `arXiv:2308.16884`
- **Citations:** 334 citations · 50 influential
- **URL:** https://arxiv.org/abs/2308.16884 · [S2](https://www.semanticscholar.org/paper/fe6670cfc0d0dfe184afc8e003df51333d3a750e)
- **Task types:** reading-comprehension
- **Methods / metrics:** accuracy per language; resource-tier stratification
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: GPT-3.5-turbo; Llama-1; Llama-2; Falcon; XLM-V; InfoXLM · strategy: Zero/few-shot and fine-tuned evaluation of MLMs vs LLMs on parallel MCQ reading comprehension, accuracy reported per language variant and stratified by resource tier. · best: GPT-3.5-turbo (highest overall among evaluated LLMs)
- **Summary:** Introduces a parallel multiple-choice machine reading comprehension benchmark over 122 language variants (built on FLORES-200 passages) and evaluates multiple multilingual MLMs and LLMs including GPT-3.5-turbo and Llama-family models. Reports per-language accuracy, finding smaller balanced-multilingual MLMs understand far more languages than larger English-centric LLMs, while GPT-3.5-turbo leads on high-resource languages.

### Measuring Short-Form Factuality in Large Language Models (SimpleQA) (2024)

- **Authors:** Jason Wei, Nguyen Karina, Hyung Won Chung, Yunxin Joy Jiao, Spencer Papay, Amelia Glaese, John Schulman, William Fedus
- **Venue:** arXiv (OpenAI) · `arXiv:2411.04368`
- **Citations:** 332 citations · 63 influential
- **URL:** https://arxiv.org/abs/2411.04368 · [S2](https://www.semanticscholar.org/paper/3f99d8e6dada94f5bcfc650be3aab7a24e39bab3)
- **Task types:** factuality; calibration
- **Methods / metrics:** correct/incorrect/not-attempted rates; F-score of correctness vs attempted
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: GPT-4o; GPT-4; o1-preview; Claude 3.5 Sonnet; GPT-4o-mini · strategy: LLM-graded short-form QA with a not-attempted option; models ranked by correctness and calibration.
- **Summary:** SimpleQA is a benchmark of short fact-seeking questions with a grading scheme of correct / incorrect / not-attempted, used to compare OpenAI frontier models and other LLMs on factual accuracy and calibrated abstention. It rewards attempting only when confident, quantifying both factual precision and over-confidence/hallucination tendencies across models.

### MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries (2024)

- **Authors:** Yixuan Tang, Yi Yang
- **Venue:** arXiv (COLM 2024) · `arXiv:2401.15391`
- **Citations:** 301 citations · 42 influential
- **URL:** https://arxiv.org/abs/2401.15391 · [S2](https://www.semanticscholar.org/paper/4e71624e90960cb003e311a0fe3b8be4c2863239)
- **Task types:** RAG evaluation; multi-hop QA
- **Methods / metrics:** answer accuracy; retrieval hit@k / MRR
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: GPT-4; PaLM; Llama-2-70B · strategy: Two-stage evaluation: embedding-model retrieval metrics (hit-rate/MRR) then per-LLM answer accuracy given gold/retrieved evidence; compared across the three LLMs. · best: GPT-4 (best but still unsatisfactory on multi-hop)
- **Summary:** MultiHop-RAG builds a news-based knowledge base with multi-hop queries, ground-truth answers, and supporting evidence, then benchmarks retrieval embeddings and several LLMs (GPT-4, PaLM, Llama-2-70B) for multi-hop reasoning over retrieved evidence. Existing RAG pipelines perform poorly, establishing a multi-model multi-hop RAG comparison.

### PIXIU: A Large Language Model, Instruction Data and Evaluation Benchmark for Finance (2023)

- **Authors:** Qianqian Xie, Weiguang Han, Xiao Zhang, Yanzhao Lai, Min Peng, Alejandro Lopez-Lira, Jimin Huang
- **Venue:** NeurIPS 2023 Datasets and Benchmarks / arXiv · `arXiv:2306.05443`
- **Citations:** 289 citations · 24 influential
- **URL:** https://arxiv.org/abs/2306.05443 · [S2](https://www.semanticscholar.org/paper/109929be7890ef982fb3b6be0d78609cfab1ea13)
- **Task types:** financial sentiment; classification; NER; financial QA; stock movement prediction
- **Methods / metrics:** accuracy; F1; Matthews correlation; entity F1
- **⚑ Empirical multi-LLM comparison** — 7 models · compared: FinMA-7B; FinMA-30B; GPT-4; ChatGPT; BLOOM; OPT-66B; LLaMA · strategy: The FLARE benchmark evaluates the fine-tuned FinMA models against general LLM baselines (GPT-4, ChatGPT, BLOOM, OPT, LLaMA) on 9 financial datasets, scored with accuracy/F1/MCC. · best: GPT-4 strong on many tasks; FinMA-30B competitive/best on several fine-tuned financial tasks
- **Summary:** PIXIU introduces the FinMA finance LLM and the FLARE benchmark, comparing FinMA-7B/30B against GPT-4, ChatGPT, BLOOM, OPT-66B, and LLaMA across five financial NLP tasks plus stock-movement prediction over nine datasets. Models are scored with accuracy, F1, and MCC. GPT-4 is strong broadly while fine-tuned FinMA leads on several financial tasks.

### FinanceBench: A New Benchmark for Financial Question Answering (2023)

- **Authors:** Pranab Islam, Anand Kannappan, Douwe Kiela, Rebecca Qian, Nino Scherrer, Bertie Vidgen
- **Venue:** arXiv (cs.CL) · `arXiv:2311.11944`
- **Citations:** 244 citations · 38 influential
- **URL:** https://arxiv.org/abs/2311.11944 · [S2](https://www.semanticscholar.org/paper/89ed7fd00319d45269906a9b05e10c8680bf9cec)
- **Task types:** domain QA; RAG evaluation
- **Methods / metrics:** answer accuracy (human review); refusal/hallucination rate; evidence-retrieval correctness
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: GPT-4-Turbo; Llama-2-70B/13B-chat; Claude-2 · strategy: Manual expert review of 2,400 answers across 16 model/augmentation configurations (closed-book, vector-store RAG, long-context); accuracy and refusal rates compared across the three model families. · best: GPT-4-Turbo with long-context (best relative, still high failure rate)
- **Summary:** FinanceBench poses 10,231 open-book questions about public companies grounded in filings, and evaluates 16 configurations of GPT-4-Turbo, Llama-2, and Claude-2 with vector stores and long-context prompts via manual review of 2,400 answers. GPT-4-Turbo with retrieval failed or refused on 81% of a hard sample, exposing large limitations. A multi-model financial QA / RAG case study.

### SafetyBench: Evaluating the Safety of Large Language Models (2023)

- **Authors:** Zhexin Zhang, Leqi Lei, Lindong Wu, Rui Sun, Yongkang Huang, Chong Long, Xiao Liu, Xuanyu Lei, Jie Tang, Minlie Huang
- **Venue:** ACL 2024 · `arXiv:2309.07045`
- **Citations:** 236 citations · 12 influential
- **URL:** https://arxiv.org/abs/2309.07045 · [S2](https://www.semanticscholar.org/paper/9b9a4fa3ed510fc6eb1bf831979235f3d9f8b556)
- **Task types:** safety; toxicity; bias
- **Methods / metrics:** accuracy (zero-shot and few-shot)
- **⚑ Empirical multi-LLM comparison** — 25 models · compared: GPT-4; ChatGPT; Llama2; Vicuna; ChatGLM2; InternLM; Baichuan; Qwen · strategy: Accuracy-based ranking of 25 bilingual LLMs on MC safety questions. · best: GPT-4
- **Summary:** A multiple-choice safety benchmark of 11,435 questions across 7 safety categories (in Chinese and English) used to test 25 popular LLMs in zero-shot and few-shot settings. Models are ranked by accuracy; GPT-4 showed a substantial performance advantage, and the study finds safety understanding correlates with safety generation ability.

### FinBen: A Holistic Financial Benchmark for Large Language Models (2024)

- **Authors:** Qianqian Xie, et al. (33 co-authors)
- **Venue:** NeurIPS 2024 Datasets and Benchmarks / arXiv · `arXiv:2402.12659`
- **Citations:** 178 citations · 8 influential
- **URL:** https://arxiv.org/abs/2402.12659 · [S2](https://www.semanticscholar.org/paper/b39aba9b515723745c994aa0fbd80a566c268282)
- **Task types:** financial QA; information extraction; forecasting; trading/decision-making
- **Methods / metrics:** accuracy; F1; task-specific scores; trading returns/Sharpe
- **⚑ Empirical multi-LLM comparison** — 15 models · compared: GPT-4; ChatGPT; Gemini; LLaMA-2; FinMA; and other open LLMs · strategy: Zero/few-shot evaluation of 15 representative LLMs across 36 datasets (24 financial tasks), plus agent-based stock-trading tests, scored with per-task metrics and trading performance. · best: GPT-4 (best on information extraction and stock trading; Gemini best on text generation and forecasting)
- **Summary:** FinBen benchmarks 15 representative LLMs (GPT-4, ChatGPT, Gemini, LLaMA-2, FinMA, and others) on 36 datasets covering 24 financial tasks plus a stock-trading agent evaluation. Performance is quantified with task-specific metrics and trading returns. GPT-4 excels at information extraction and trading while Gemini leads text generation and forecasting; all struggle with advanced reasoning.

### Global MMLU: Understanding and Addressing Cultural and Linguistic Biases in Multilingual Evaluation (2024)

- **Authors:** Shivalika Singh, Angelika Romanou, Clémentine Fourrier, David I. Adelani, et al.
- **Venue:** arXiv (Cohere For AI et al.) · `arXiv:2412.03304`
- **Citations:** 176 citations · 26 influential
- **URL:** https://arxiv.org/abs/2412.03304 · [S2](https://www.semanticscholar.org/paper/4379bdfe184318eb50b11f5529005448d4be44ff)
- **Task types:** knowledge-qa
- **Methods / metrics:** accuracy per language; culturally-sensitive vs agnostic subset ranking shifts
- **⚑ Empirical multi-LLM comparison** — 14 models · strategy: Multiple-choice accuracy across 42 languages for open and proprietary models, with rank-stability analysis across culturally-sensitive versus culturally-agnostic question subsets (exact model roster listed in the paper).
- **Summary:** Releases an improved multilingual MMLU across 42 languages with culturally-sensitive vs culturally-agnostic subsets, and evaluates a suite of state-of-the-art open and proprietary LLMs. Reports per-language accuracy and shows model rankings shift depending on the evaluation subset, quantifying cultural/linguistic bias in multilingual benchmarking.

### LiveBench: A Challenging, Contamination-Free LLM Benchmark (2024)

- **Authors:** Colin White, Samuel Dooley, Manley Roberts, et al.
- **Venue:** ICLR 2025 (Spotlight) · `arXiv:2406.19314`
- **Citations:** 174 citations · 12 influential
- **URL:** https://arxiv.org/abs/2406.19314 · [S2](https://www.semanticscholar.org/paper/774d01e152003f342596031c0c0fbf1936dee41a)
- **Task types:** math; coding; reasoning; data analysis; instruction following; language comprehension
- **Methods / metrics:** objective verifiable ground-truth scoring (no LLM judge); monthly question refresh to prevent contamination; six task categories; aggregate and per-category accuracy
- **⚑ Empirical multi-LLM comparison** — 40 models · compared: closed-source frontier models; open-source models 0.5B-405B · strategy: Objective verifiable ground-truth scoring (no LLM judge), aggregate and per-category accuracy across six task categories, with monthly contamination-free refresh.
- **Summary:** LiveBench builds contamination-free questions from recently released math competitions, arXiv papers, news and datasets, refreshing roughly one-sixth of items monthly so training-set leakage cannot inflate scores. Every question has a verifiable objective answer, allowing automatic scoring without an LLM judge and thus removing judge bias from comparisons. Its continual refresh makes reported accuracy trustworthy and comparable over time as models evolve.

### LiveBench: A Challenging, Contamination-Limited LLM Benchmark (2024)

- **Authors:** Colin White, Samuel Dooley, Manley Roberts, Micah Goldblum, et al.
- **Venue:** ICLR 2025 (Spotlight) · `arXiv:2406.19314`
- **Citations:** 174 citations · 12 influential
- **URL:** https://arxiv.org/abs/2406.19314 · [S2](https://www.semanticscholar.org/paper/774d01e152003f342596031c0c0fbf1936dee41a)
- **Task types:** math; reasoning; code; language understanding
- **Methods / metrics:** accuracy; objective ground-truth auto-scoring (no LLM judge); monthly-refreshed task sets
- **⚑ Empirical multi-LLM comparison** — 40 models · compared: GPT-4o; GPT-4-Turbo; Claude-3.5 Sonnet; Claude-3 Opus; Gemini-1.5; Llama-3-405B/70B; Qwen2; Mistral; Command R+ · strategy: Objective automatically-scored ground-truth tasks (contamination-limited) across dozens of models, avoiding LLM/human judges. · best: GPT-4o / top closed models (still <70%)
- **Summary:** A continuously-refreshed benchmark drawing from recent competitions, arXiv papers and news to limit contamination, with objective automatic ground-truth scoring across math, reasoning, coding, language and data-analysis. Evaluates dozens of closed and open models (0.5B-405B); top models score below 70%, and results are compared against other judges/benchmarks.

### SciEval: A Multi-Level Large Language Model Evaluation Benchmark for Scientific Research (2023)

- **Authors:** Liangtai Sun, Yang Han, Zihan Zhao, Da Ma, Zhennan Shen, Baocai Chen, Lu Chen, Kai Yu
- **Venue:** AAAI 2024 / arXiv · `arXiv:2308.13149`
- **Citations:** 168 citations · 9 influential
- **URL:** https://arxiv.org/abs/2308.13149 · [S2](https://www.semanticscholar.org/paper/f53a955ea1812fb0481504fdfd8febcb2a553a45)
- **Task types:** scientific QA (objective and subjective)
- **Methods / metrics:** accuracy; separate scoring for dynamic (leakage-resistant) questions
- **⚑ Empirical multi-LLM comparison** — 12 models · compared: GPT-4; ChatGPT; Claude; LLaMA/Alpaca/Vicuna family; Galactica; and other open LLMs · strategy: Many advanced LLMs are evaluated on multi-level scientific questions (basic knowledge, understanding, application, reasoning) with a dynamic subset to control for data leakage; scored by accuracy. · best: GPT-4 (state-of-the-art among evaluated LLMs)
- **Summary:** SciEval evaluates a dozen-plus advanced LLMs (GPT-4, ChatGPT, Claude, LLaMA/Vicuna family, Galactica, and others) on physics, chemistry, and biology questions structured by Bloom's taxonomy, including a dynamic subset to resist data leakage. Models are compared by accuracy on objective and subjective items. GPT-4 achieves state-of-the-art, though all models leave large room for improvement on dynamic questions.

### M3Exam: A Multilingual, Multimodal, Multilevel Benchmark for Examining Large Language Models (2023)

- **Authors:** Wenxuan Zhang, Sharifah Mahani Aljunied, Chang Gao, Yew Ken Chia, Lidong Bing
- **Venue:** NeurIPS 2023 (Datasets & Benchmarks) · `arXiv:2306.05179`
- **Citations:** 140 citations · 7 influential
- **URL:** https://arxiv.org/abs/2306.05179 · [S2](https://www.semanticscholar.org/paper/89689059d0cdcb52d7fbb6007ab953db22936a90)
- **Task types:** exam-qa; multimodal
- **Methods / metrics:** accuracy per language and education level
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: GPT-3.5-turbo; GPT-4; Claude; Vicuna; BLOOM · strategy: Zero-shot prompting on official exam questions; accuracy reported per language and per education level across models, plus multimodal subset analysis. · best: GPT-4
- **Summary:** Benchmark of 12,317 real human exam questions across 9 languages and three education levels (with ~23% multimodal) used to compare multiple LLMs including GPT-3.5, GPT-4, Claude, Vicuna and BLOOM. Reports per-language and per-level accuracy; GPT-4 performs best overall but all models struggle with low-resource and non-Latin-script languages and complex multimodal questions.

### LawBench: Benchmarking Legal Knowledge of Large Language Models (2023)

- **Authors:** Zhiwei Fei, Xiaoyu Shen, Dawei Zhu, Fengzhe Zhou, Zhuo Han, Songyang Zhang, Kai Chen, Zongwen Shen, Jidong Ge
- **Venue:** arXiv (cs.CL) · `arXiv:2309.16289`
- **Citations:** 132 citations · 7 influential
- **URL:** https://arxiv.org/abs/2309.16289 · [S2](https://www.semanticscholar.org/paper/9099ee08e59cc33ed1c88d4708cf5c931bf46dc4)
- **Task types:** single/multi-label classification; regression; extraction; generation
- **Methods / metrics:** per-task accuracy; F1; ROUGE; normalized aggregate score
- **⚑ Empirical multi-LLM comparison** — 51 models · compared: GPT-4; ChatGPT; 20 multilingual LLMs; 22 Chinese-oriented LLMs; 9 legal-specific LLMs · strategy: Zero/few-shot evaluation of 51 LLMs on 20 Chinese legal tasks organized by three cognitive levels, scored with task-specific metrics (accuracy, F1, ROUGE) and normalized into an aggregate ranking. · best: GPT-4 (surpasses others by a significant margin)
- **Summary:** LawBench evaluates 51 distinct LLMs (20 multilingual, 22 Chinese-oriented, 9 legal-specific) on 20 Chinese legal tasks spanning memorization, comprehension, and application. Models are scored per task with accuracy/F1/ROUGE and aggregated; GPT-4 is best by a wide margin, but all models remain far from reliable legal use.

### CRAG -- Comprehensive RAG Benchmark (2024)

- **Authors:** Xiao Yang, Kai Sun, Hao Xin, Yushi Sun, Nikita Bhalla, et al.
- **Venue:** NeurIPS 2024 Datasets & Benchmarks · `arXiv:2406.04744`
- **Citations:** 127 citations · 10 influential
- **URL:** https://arxiv.org/abs/2406.04744 · [S2](https://www.semanticscholar.org/paper/ec1bec009e68a4df478aaf11e3615e5587768990)
- **Task types:** RAG evaluation; open-domain QA
- **Methods / metrics:** accuracy; hallucination rate; truthfulness score
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: GPT-4-Turbo; GPT-3.5-Turbo; Llama-3-70B; Llama-3-8B; Mixtral-8x7B; Claude-3 · strategy: Accuracy and hallucination scored (including a truthfulness scoring rubric penalizing wrong answers) across LLMs and RAG modes; comparison of direct, straightforward-RAG, and SOTA-industry setups. · best: GPT-4-Turbo with RAG (best but still ~63% hallucination-free ceiling)
- **Summary:** CRAG provides 4,409 factual QA pairs with mock web and knowledge-graph search APIs across five domains and eight question categories including long-tail and rapidly changing facts. Multiple advanced LLMs and RAG configurations are evaluated, with most achieving <=34% accuracy and straightforward RAG reaching only ~44%. A multi-model empirical RAG benchmark exposing gaps on dynamic and long-tail facts.

### HalluLens: LLM Hallucination Benchmark (2025)

- **Authors:** Yejin Bang, Ziwei Ji, Alan Schelten, Anthony Hartshorn, Tara Fowler, Cheng Zhang, Nicola Cancedda, Pascale Fung
- **Venue:** arXiv (Meta AI) · `arXiv:2504.17550`
- **Citations:** 113 citations · 9 influential
- **URL:** https://arxiv.org/abs/2504.17550 · [S2](https://www.semanticscholar.org/paper/51fe85e30a4c9d66a3fa127946d1f87a6fabeac7)
- **Task types:** hallucination
- **Methods / metrics:** extrinsic/intrinsic hallucination rates; false-refusal rate
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: Llama-3.1; GPT-4o; Claude-3.5; Mistral · strategy: Dynamically generated tasks scored for extrinsic vs intrinsic hallucination, compared across multiple LLMs.
- **Summary:** Proposes a unified hallucination benchmark distinguishing extrinsic and intrinsic hallucination, with dynamic test-set generation to mitigate data leakage, and evaluates multiple frontier LLMs. Reports per-model extrinsic/intrinsic hallucination rates to enable consistent cross-model comparison over time.

### SeaEval for Multilingual Foundation Models: From Cross-Lingual Alignment to Cultural Reasoning (2024)

- **Authors:** Bin Wang, Zhengyuan Liu, Xin Huang, Fangkai Jiao, Yang Ding, AiTi Aw, Nancy F. Chen
- **Venue:** NAACL 2024 · `arXiv:2309.04766`
- **Citations:** 108 citations · 5 influential
- **URL:** https://arxiv.org/abs/2309.04766 · [S2](https://www.semanticscholar.org/paper/05be16afbd1dec2f5dad0949686c3fbe9d44f466)
- **Task types:** multilingual-nlp-suite; reasoning; cultural-reasoning
- **Methods / metrics:** accuracy; cross-lingual consistency; cross-lingual/paraphrase brittleness analysis
- **⚑ Empirical multi-LLM comparison** — 7 models · compared: ChatGPT (GPT-3.5); GPT-4; LLaMA-2; Baichuan; Vicuna; ChatGLM; Flan-T5 · strategy: Accuracy plus consistency metrics over semantically equivalent multilingual/paraphrased queries across open and closed models, with brittleness and exposure-bias analysis. · best: GPT-4
- **Summary:** Benchmarks multiple open and closed multilingual foundation models (e.g., ChatGPT/GPT-4 and open LLMs such as LLaMA-2 and Baichuan) on classic NLP tasks, reasoning, and cross-lingual/cultural comprehension. Reports accuracy and consistency across semantically equivalent multilingual questions, exposing instruction brittleness, exposure bias, and inconsistent cross-lingual performance.

### BUFFET: Benchmarking Large Language Models for Few-shot Cross-lingual Transfer (2023)

- **Authors:** Akari Asai, Sneha Kudugunta, Xinyan Velocity Yu, Terra Blevins, Hila Gonen, Machel Reid, Yulia Tsvetkov, Sebastian Ruder, Hannaneh Hajishirzi
- **Venue:** arXiv (later NAACL 2024) · `arXiv:2305.14857`
- **Citations:** 96 citations · 11 influential
- **URL:** https://arxiv.org/abs/2305.14857 · [S2](https://www.semanticscholar.org/paper/c1c98ef93fb6474837961ef300cf3d8e7d3a0cd0)
- **Task types:** cross-lingual-transfer; multilingual-nlp-suite
- **Methods / metrics:** task-specific accuracy/F1 per language; ICL vs fine-tuning comparison
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: ChatGPT; BLOOM; mT5-base; mT0 · strategy: Unified seq2seq few-shot evaluation across 15 tasks/54 languages comparing in-context learning versus fine-tuning; per-language metrics aggregated across models and transfer methods. · best: mT5-base (fine-tuned) over ChatGPT (ICL) in many settings
- **Summary:** Unifies 15 tasks across 54 languages in a seq2seq format to benchmark multiple multilingual LLMs (e.g., ChatGPT, BLOOM, mT5, mT0) under in-context learning versus fine-tuning for few-shot cross-lingual transfer. Reports per-language performance and finds ChatGPT with ICL often underperforms much smaller fine-tuned mT5-base, highlighting persistent cross-lingual transfer gaps.

### T-Eval: Evaluating the Tool Utilization Capability of Large Language Models Step by Step (2023)

- **Authors:** Zehui Chen, Weihua Du, Wenwei Zhang, ... Kai Chen, Feng Zhao
- **Venue:** ACL 2024 · `arXiv:2312.14033`
- **Citations:** 95 citations · 9 influential
- **URL:** https://arxiv.org/abs/2312.14033 · [S2](https://www.semanticscholar.org/paper/caf60d1120c2d5a894098f01b51d2e2ad32301d7)
- **Task types:** tool use; function calling; agent planning
- **Methods / metrics:** per-capability accuracy; aggregate tool-use score
- **⚑ Empirical multi-LLM comparison** — 15 models · compared: GPT-4; GPT-3.5-turbo; Claude-2; LLaMA-2-70B; Vicuna-13B; InternLM-20B; Qwen-14B; Baichuan2-13B; ChatGLM3-6B · strategy: Per-dimension format and content scores across six disentangled sub-tasks aggregated into an overall tool-utilization score; models ranked. · best: GPT-4
- **Summary:** T-Eval decomposes tool-use evaluation into six sub-capabilities (instruction following, planning, reasoning, retrieval, understanding, review) for fine-grained multi-model comparison. It benchmarks a broad set of proprietary and open LLMs, isolating where each fails rather than reporting a single holistic score. GPT-4 tops the aggregate while open models lag, especially on planning and review.

### GTA: A Benchmark for General Tool Agents (2024)

- **Authors:** Jize Wang, Zerun Ma, Yining Li, Songyang Zhang, Cailian Chen, Kai Chen, Xinyi Le
- **Venue:** NeurIPS 2024 (Datasets & Benchmarks) · `arXiv:2407.08713`
- **Citations:** 90 citations · 11 influential
- **URL:** https://arxiv.org/abs/2407.08713 · [S2](https://www.semanticscholar.org/paper/47440dfd5444fe03ef1ffd97f88101f69c4c6628)
- **Task types:** tool use; function calling; multimodal reasoning
- **Methods / metrics:** tool selection accuracy; argument accuracy; answer accuracy; step-by-step scoring
- **⚑ Empirical multi-LLM comparison** — 16 models · compared: GPT-4; GPT-4o; GPT-3.5-turbo; Claude-3-Opus; Gemini-1.5-Pro; LLaMA-3-70B; Qwen1.5-72B; Mixtral-8x7B; Yi-34B; Deepseek-67B · strategy: Fine-grained metrics: instruction-following (InstAcc), tool-selection accuracy, argument accuracy (ArgAcc), and end-to-end answer/task accuracy. · best: GPT-4
- **Summary:** GTA offers 229 human-written real-world queries with implicit tool-use needs and deployed multimodal tools (perception, operation, logic, creativity). It benchmarks 16 mainstream LLMs with step-by-step and end-to-end metrics for tool selection, argument accuracy and task completion. GPT-4 leads but completes under 50% of tasks, while most models finish below 25%.

### MEGAVERSE: Benchmarking Large Language Models Across Languages, Modalities, Models and Tasks (2024)

- **Authors:** Sanchit Ahuja, Divyanshu Aggarwal, Varun Gumma, Ishaan Watts, Ashutosh Sathe, Millicent Ochieng, Rishav Hada, Prachi Jain, Maxamed Axmed, Kalika Bali, Sunayana Sitaram
- **Venue:** Findings of NAACL 2024 · `arXiv:2311.07463`
- **Citations:** 81 citations · 3 influential
- **URL:** https://arxiv.org/abs/2311.07463 · [S2](https://www.semanticscholar.org/paper/71c3c3c262239adb89b41d4c80e342cd24f11ef3)
- **Task types:** multilingual-nlp-suite; multimodal
- **Methods / metrics:** accuracy; F1; per-dataset win counts
- **⚑ Empirical multi-LLM comparison** — 7 models · compared: GPT-3.5-turbo; GPT-4; PaLM2; Gemini-Pro; Mistral; Llama2; Gemma · strategy: Prompt-based evaluation over 22 datasets/83 languages, per-dataset accuracy compared across 7 LLMs with dataset-win-count ranking and contamination discussion. · best: GPT-4
- **Summary:** Extends MEGA to seven LLMs (GPT-3.5-turbo, GPT-4, PaLM2, Gemini-Pro, Mistral, Llama2, Gemma) plus three multimodal models across 22 datasets covering 83 languages including low-resource African languages. Reports per-dataset/per-language performance; GPT-4 outperformed PaLM2 and Gemini-Pro on more datasets, with larger models generally better on low-resource languages.

### IndicGenBench: A Multilingual Benchmark to Evaluate Generation Capabilities of LLMs on Indic Languages (2024)

- **Authors:** Harman Singh, Nitish Gupta, Shikhar Bharadwaj, Dinesh Tewari, Partha Talukdar
- **Venue:** ACL 2024 · `arXiv:2404.16816`
- **Citations:** 70 citations · 7 influential
- **URL:** https://arxiv.org/abs/2404.16816 · [S2](https://www.semanticscholar.org/paper/7d61b2dc1893638e0846263489c940496c01a89d)
- **Task types:** summarization; machine-translation; question-answering
- **Methods / metrics:** ROUGE; chrF; BLEU; token-F1 per language
- **⚑ Empirical multi-LLM comparison** — 7 models · compared: GPT-3.5; GPT-4; PaLM-2; mT5; Gemma; BLOOM; LLaMA · strategy: One/few-shot prompting on multi-way parallel Indic data; task-appropriate generation metrics (ROUGE, chrF, F1) reported per language and compared across 7 LLMs. · best: PaLM-2 (largest)
- **Summary:** Evaluates seven LLMs (GPT-3.5, GPT-4, PaLM-2, mT5, Gemma, BLOOM, LLaMA) on user-facing generation tasks across 29 Indic languages (13 scripts, 4 families): cross-lingual summarization, machine translation, and cross-lingual QA. Reports per-language generation metrics; the largest PaLM-2 performs best on most tasks, but a substantial gap versus English persists across all languages.

### FinEval: A Chinese Financial Domain Knowledge Evaluation Benchmark for Large Language Models (2023)

- **Authors:** Xin Guo, Haotian Xia, Zhaowei Liu, et al.; Zhongyu Wei, Yun Chen, Weining Shen, Liwen Zhang
- **Venue:** arXiv (cs.CL) · `arXiv:2308.09975`
- **Citations:** 69 citations · 4 influential
- **URL:** https://arxiv.org/abs/2308.09975 · [S2](https://www.semanticscholar.org/paper/3b88526a0f0337e3a6b632b4af8fd0882eb4b470)
- **Task types:** multiple-choice financial knowledge QA; agent tasks
- **Methods / metrics:** weighted average accuracy; zero-shot and five-shot with chain-of-thought
- **⚑ Empirical multi-LLM comparison** — 19 models · compared: Claude 3.5-Sonnet; GPT-4; ChatGPT; Chinese LLMs (e.g., Qwen, ChatGLM, Baichuan); and other open LLMs · strategy: Zero-shot and five-shot (with CoT) evaluation of many LLMs on 8,351 Chinese financial questions across four domains, scored by weighted average accuracy. · best: Claude 3.5-Sonnet (highest weighted average 72.9 zero-shot)
- **Summary:** FinEval evaluates a large set of LLMs (GPT-4, ChatGPT, Claude 3.5-Sonnet, and Chinese models such as Qwen/ChatGLM/Baichuan) on 8,351 Chinese financial-domain questions spanning academic, industry, security, and agent knowledge. Models are compared by weighted-average accuracy under zero-shot and five-shot chain-of-thought settings. Claude 3.5-Sonnet achieves the top weighted average score of 72.9.

### SciAssess: Benchmarking LLM Proficiency in Scientific Literature Analysis (2024)

- **Authors:** Hengxing Cai, et al. (22 co-authors)
- **Venue:** arXiv (cs.CL) · `arXiv:2403.01976`
- **Citations:** 62 citations · 1 influential
- **URL:** https://arxiv.org/abs/2403.01976 · [S2](https://www.semanticscholar.org/paper/95d19f8ede34cd712a09ae3b86bed2b338bd9a48)
- **Task types:** scientific literature comprehension; extraction; reasoning
- **Methods / metrics:** task-specific accuracy / extraction and reasoning scores
- **⚑ Empirical multi-LLM comparison** — 11 models · compared: GPT-4; GPT-3.5; Claude; Gemini; and open scientific/general LLMs · strategy: 11 LLMs are evaluated on multi-domain scientific-literature tasks spanning memorization, comprehension, and analysis/reasoning, scored with task-specific metrics under quality-controlled data. · best: GPT-4 (strongest among the 11 evaluated)
- **Summary:** SciAssess benchmarks 11 LLMs (GPT-4, GPT-3.5, Claude, Gemini, and open models) on scientific-literature analysis across biology, chemistry, materials, and medicine, organized into memorization, comprehension, and analysis/reasoning levels. Comparative performance is reported with task-specific metrics. Proprietary frontier models lead, but all show clear gaps in higher-level analysis and reasoning.

### HALoGEN: Fantastic LLM Hallucinations and Where to Find Them (2025)

- **Authors:** Abhilasha Ravichander, Shrusti Ghela, David Wadden, Yejin Choi
- **Venue:** arXiv (ACL 2025) · `arXiv:2501.08292`
- **Citations:** 43 citations · 3 influential
- **URL:** https://arxiv.org/abs/2501.08292 · [S2](https://www.semanticscholar.org/paper/7486325fbf143d1dab5a99094da23a0a7dc7e41b)
- **Task types:** hallucination; factuality
- **Methods / metrics:** hallucination rate of atomic facts; automatic verifiers against knowledge sources
- **⚑ Empirical multi-LLM comparison** — 14 models · compared: GPT-4; Llama; Mistral; OLMo; Falcon · strategy: Decompose generations into atomic units, verify each against high-quality sources; per-domain hallucination rates compared across 14 models.
- **Summary:** A hallucination benchmark spanning nine domains (programming, scientific attribution, summarization, etc.) with automatic atomic-fact verifiers, applied to ~150,000 generations from 14 language models. Even the best models hallucinated up to 86% of atomic facts in some domains; introduces a Type A/B/C error taxonomy for classifying hallucination sources.

### HelloBench: Evaluating Long Text Generation Capabilities of Large Language Models (2024)

- **Authors:** Haoran Que, Feiyu Duan, Liqun He, Yutao Mou, Wangchunshu Zhou, Jiaheng Liu, Wenge Rong, Zekun Moore Wang, Jian Yang, Ge Zhang, Junran Peng, Zhaoxiang Zhang, Songyang Zhang, Kai Chen
- **Venue:** arXiv (cs.CL) · `arXiv:2409.16191`
- **Citations:** 42 citations · 5 influential
- **URL:** https://arxiv.org/abs/2409.16191 · [S2](https://www.semanticscholar.org/paper/079e6a2003e8e6ef1d346fbc22daf4399eaf6a4e)
- **Task types:** long-form generation; summarization
- **Methods / metrics:** HelloEval; ROUGE; BLEU; LLM-as-judge; human correlation
- **⚑ Empirical multi-LLM comparison** — 30 models · compared: GPT-4; Claude 3; Gemini; Qwen; LLaMA 3; Mistral; GLM-4 · strategy: Hierarchical Long Text Evaluation (HelloEval, human-aligned checklist) benchmarked against ROUGE/BLEU, LLM-as-a-judge, and human evaluation (correlation with human ratings). · best: GPT-4-class models (top HelloEval)
- **Summary:** Benchmarks around 30 mainstream LLMs on long-form text generation across five subtasks (open-ended QA, summarization, chat, text completion, heuristic generation). Introduces HelloEval, a hierarchical evaluation aligned with human judgment, and compares it against ROUGE/BLEU and LLM-as-a-judge. Finds most current LLMs cannot generate coherent text beyond ~4,000 words; models ranked by HelloEval.

### Holistic Evaluation of Language Models (2022)

- **Authors:** Percy Liang, Rishi Bommasani, Tony Lee, et al.
- **Venue:** arXiv preprint / TMLR 2023 (Stanford CRFM) · `arXiv:2211.09110`
- **Citations:** 10 citations · 0 influential
- **URL:** https://arxiv.org/abs/2211.09110 · [S2](https://www.semanticscholar.org/paper/29abcf865613287c661385c39401424f709a3fda)
- **Task types:** question answering; summarization; sentiment; toxicity detection; information retrieval; reasoning; text classification
- **Methods / metrics:** multi-metric evaluation (accuracy, calibration, robustness, fairness, bias, toxicity, efficiency); standardized 16 core scenarios x 7 metrics matrix; few-shot prompting; expected calibration error; perturbation-based robustness
- **⚑ Empirical multi-LLM comparison** — 30 models · compared: GPT-3; OPT; BLOOM; GPT-J; T5; Anthropic-LM; Cohere; TNLG · strategy: Standardized 30-model x 42-scenario grid scored on 7 metrics (accuracy, calibration, robustness, fairness, bias, toxicity, efficiency); descriptive multi-metric comparison, no significance test or LLM judge.
- **Summary:** HELM introduces a top-down, multi-metric framework that evaluates language models across 16 core scenarios and 7 metrics (accuracy, calibration, robustness, fairness, bias, toxicity, efficiency) rather than a single accuracy number. By reporting all metrics for all models on a common grid (30 models, 42 scenarios), it makes model precision and accuracy directly and transparently comparable, exposing trade-offs a single-metric leaderboard hides. It is a living benchmark designed for reproducible, apples-to-apples comparison across vendors.

### Holistic Evaluation of Language Models (HELM) (2022)

- **Authors:** Percy Liang, Rishi Bommasani, Tony Lee, et al.
- **Venue:** Transactions on Machine Learning Research (TMLR) 2023; preprint arXiv · `arXiv:2211.09110`
- **Citations:** 10 citations · 0 influential
- **URL:** https://arxiv.org/abs/2211.09110 · [S2](https://www.semanticscholar.org/paper/29abcf865613287c661385c39401424f709a3fda)
- **Task types:** QA; summarization; information retrieval; sentiment; toxicity detection; reasoning; information-retrieval; toxicity/bias; language-modeling
- **Methods / metrics:** standardized scenarios × metrics taxonomy; accuracy; calibration (ECE); robustness (perturbations); fairness/bias metrics; efficiency; full prompt/completion release; calibration; robustness; fairness; bias; toxicity; standardized few-shot adaptation; multi-metric aggregation
- **⚑ Empirical multi-LLM comparison** — 30 models · compared: open, limited-access, and closed models (30 prominent LMs; specific names not enumerated in abstract) · strategy: Standardized multi-metric evaluation (accuracy, calibration/ECE, robustness, fairness, bias, toxicity, efficiency) over 16 core + 26 targeted scenarios under standardized few-shot adaptation, with all prompts/completions released
- **Summary:** Establishes a reproducible, transparent framework that evaluates LLMs across a two-dimensional taxonomy of scenarios and metrics, reporting accuracy, calibration, robustness, fairness, bias, toxicity, and efficiency together rather than accuracy alone. Standardizes prompts and adaptation and publicly releases all raw prompts and completions for reproducibility. Foundational for multi-metric, standardized cross-model comparison.

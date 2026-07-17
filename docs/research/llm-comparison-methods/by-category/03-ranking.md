# Pairwise ranking (Elo / Bradley-Terry / Arena)

_13 papers (6 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### Chatbot Arena: An Open Platform for Evaluating LLMs by Human Preference (2024)

- **Authors:** Wei-Lin Chiang, Lianmin Zheng, Ying Sheng, Anastasios N. Angelopoulos, Tianle Li, et al.
- **Venue:** ICML 2024 · `arXiv:2403.04132`
- **Citations:** 1,379 citations · 192 influential
- **URL:** https://arxiv.org/abs/2403.04132 · [S2](https://www.semanticscholar.org/paper/53f4fb0e9972989194368faf288ff8e3cba5bd60)
- **Task types:** open-ended chat; pairwise preference comparison; instruction following; general assistant evaluation; instruction-following; human-preference QA; crowdsourced pairwise preference; live model ranking; open-ended human-preference pairwise comparison; open-ended dialogue; human-preference judgment
- **Methods / metrics:** crowdsourced pairwise battles; Elo / Bradley-Terry rating; confidence intervals on rankings; active sampling of model pairs; statistical detection of anomalous users; pairwise human preference votes; Elo rating; Bradley-Terry MLE; confidence intervals; active/adaptive sampling; anomaly detection; Bradley-Terry / Elo rating; crowdsourced pairwise votes (>240K); active sampling for pair selection; anomalous-user detection; Bradley-Terry model; bootstrap confidence intervals; active sampling; pairwise win-rate; crowdsourced vote analysis; maximum likelihood estimation; win-rate
- **⚑ Empirical multi-LLM comparison** — 20 models · compared: GPT-4; Claude; Llama; Vicuna; PaLM/Bard · strategy: Crowdsourced pairwise human-preference battles (>240K votes) aggregated via Bradley-Terry/Elo with bootstrap confidence intervals, active pair sampling, and anomalous-user detection.
- **Summary:** Chatbot Arena crowdsources anonymous pairwise LLM battles and aggregates hundreds of thousands of human votes into Elo/Bradley-Terry ratings with statistical confidence intervals. It provides a live, preference-based ranking that complements static accuracy benchmarks and captures alignment with human judgment. Its rating methodology (with efficient pair sampling and rank confidence estimation) is the reference approach for statistically grounded LLM leaderboards.

### AgentBench: Evaluating LLMs as Agents (2023)

- **Authors:** Xiao Liu, Hao Yu, Hanchen Zhang, Yifan Xu, ... Yuxiao Dong, Jie Tang
- **Venue:** ICLR 2024 · `arXiv:2308.03688`
- **Citations:** 1,052 citations · 72 influential
- **URL:** https://arxiv.org/abs/2308.03688 · [S2](https://www.semanticscholar.org/paper/5dbf93a68b7fda600521f046dea35ea8ba9e884f)
- **Task types:** agentic tool use; interactive decision-making; web tasks; embodied tasks
- **Methods / metrics:** success rate; environment reward; overall agent score
- **⚑ Empirical multi-LLM comparison** — 27 models · compared: GPT-4; GPT-3.5-turbo; Claude-2; Claude; Claude-instant; text-davinci-003; text-davinci-002; ChatGLM2-6B; LLaMA-2-70B; Vicuna-13B; WizardLM-30B; Koala-13B; OpenChat-13B; Dolly-12B · strategy: Per-environment success rate / reward aggregated into an overall agent score; multi-turn interactive rollouts with exact-match or environment-defined goal checks; models ranked API vs open-source. · best: GPT-4
- **Summary:** AgentBench is a multi-dimensional benchmark that evaluates LLMs as autonomous agents across 8 distinct interactive environments (OS, database, knowledge graph, card game, lateral-thinking puzzles, house-holding/ALFWorld, web-shopping/WebShop, web-browsing/Mind2Web). It runs 25+ commercial and open-source models and quantifies each with a per-environment success/reward score aggregated into an overall agent score. Top commercial models (GPT-4 highest) substantially outperform open-source models up to 70B, with long-horizon reasoning and instruction-following the main bottlenecks.

### AgentBoard: An Analytical Evaluation Board of Multi-turn LLM Agents (2024)

- **Authors:** Chang Ma, Junlei Zhang, Zhihao Zhu, ... Lingpeng Kong, Junxian He
- **Venue:** NeurIPS 2024 (Oral) · `arXiv:2401.13178`
- **Citations:** 251 citations · 33 influential
- **URL:** https://arxiv.org/abs/2401.13178 · [S2](https://www.semanticscholar.org/paper/cf270bea2fba82bcff83f380c1f100d346b14ecf)
- **Task types:** agentic tool use; embodied tasks; web tasks; games
- **Methods / metrics:** progress rate; success rate
- **⚑ Empirical multi-LLM comparison** — 9 models · compared: GPT-4; GPT-3.5-turbo; Claude-2; Claude-instant; Text-Davinci-003; DeepSeek-67B; Llama2-70B; Vicuna-13B; CodeLlama-34B; Lemur-70B · strategy: Fine-grained progress rate plus success rate over multi-turn partially observable rollouts; per-capability analytical breakdown and model ranking. · best: GPT-4
- **Summary:** AgentBoard is a benchmark and analysis toolkit for multi-turn LLM agents across embodied, web, tool and game tasks, introducing a fine-grained progress-rate metric alongside success rate. It compares a broad set of proprietary and open models under partially observable, multi-round settings, revealing that open models trail GPT-4 markedly and that progress rate exposes partial competence success rate hides.

### Open-LLM-Leaderboard: From Multi-choice to Open-style Questions for LLMs Evaluation, Benchmark, and Arena (2024)

- **Authors:** Aidar Myrzakhan, Sondos Mahmoud Bsharat, Zhiqiang Shen
- **Venue:** arXiv (cs.CL) · `arXiv:2406.07545`
- **Citations:** 93 citations · 3 influential
- **URL:** https://arxiv.org/abs/2406.07545 · [S2](https://www.semanticscholar.org/paper/9b8c2f2507c3aaf4edd450116d3c19573aafc4c5)
- **Task types:** open-ended QA; knowledge
- **Methods / metrics:** open-style accuracy vs human ground truth; elimination of selection bias; leaderboard ranking
- **⚑ Empirical multi-LLM comparison** — 15 models · compared: GPT-4o; GPT-4; GPT-3.5; Claude 3; Gemini; Llama-3; Mistral; Qwen · strategy: Convert MC items to open-style questions; validate free-form answers against human-annotated ground truth to rank models without selection-bias artifacts. · best: GPT-4o
- **Summary:** Argues multiple-choice evaluation suffers selection bias and random-guessing, and rebuilds a leaderboard using open-style questions with automated answer validation against human-annotated ground truth. Empirically ranks many commercial and open LLMs (GPT-4o/4/3.5, Claude 3, Gemini, Llama, Mistral, etc.) on the open-style benchmark and a companion arena. A reproducible multi-model ranking study.

### Elo Uncovered: Robustness and Best Practices in Language Model Evaluation (2023)

- **Authors:** Meriem Boubdir, Edward Kim, Beyza Ermis, Sara Hooker, Marzieh Fadaee
- **Venue:** GEM Workshop, EMNLP 2023 · `arXiv:2311.17295`
- **Citations:** 86 citations · 3 influential
- **URL:** https://arxiv.org/abs/2311.17295 · [S2](https://www.semanticscholar.org/paper/e8b22bf8a78401b3807bcd46fa7c88d0c07f58ba)
- **Task types:** open-ended generation; A-vs-B pairwise comparison
- **Methods / metrics:** Elo rating; reliability axiom; transitivity axiom; hyperparameter (K-factor / order) sensitivity; volatility analysis
- **Summary:** Examines whether the Elo system, designed for dynamic-skill games, is appropriate for constant-skill entities like LLMs. Through two axioms (reliability and transitivity) it demonstrates that individual Elo computations are volatile and order/hyperparameter-sensitive, and that the axioms are not always satisfied. It provides best-practice recommendations and cautions for comparative Elo-based LLM evaluation.

### The Leaderboard Illusion (2025)

- **Authors:** Shivalika Singh, et al. (Cohere Labs, Princeton, MIT, Stanford et al.)
- **Venue:** preprint arXiv · `arXiv:2504.20879`
- **Citations:** 55 citations · 2 influential
- **URL:** https://arxiv.org/abs/2504.20879 · [S2](https://www.semanticscholar.org/paper/dc3b7ca920f25223101ba36227a894d37c238df1)
- **Task types:** human-preference pairwise evaluation; leaderboard auditing; human-preference ranking; meta-evaluation; leaderboard-auditing
- **Methods / metrics:** Elo/Bradley-Terry ranking audit; selective-disclosure / best-of-N bias analysis; sampling-rate asymmetry; data-access quantification; overfitting-to-leaderboard analysis; Bradley-Terry/Elo analysis; sampling-rate audit; overfitting/contamination analysis; win-rate bias quantification
- **Summary:** Audits Chatbot Arena and documents systematic distortions: undisclosed private pre-release testing lets select providers submit many variants and retain only the best score (selective disclosure / best-of-N bias), plus large sampling and data-access asymmetries favoring a few proprietary labs. Shows these practices bias Arena rankings and overfit models to the leaderboard. Core reading on leaderboard reproducibility and gameability.

### Prediction-Powered Ranking of Large Language Models (2024)

- **Authors:** Ivi Chatzi, Eleni Straitouri, Suhas Thejaswi, Manuel Gomez Rodriguez
- **Venue:** NeurIPS 2024 · `arXiv:2402.17826`
- **Citations:** 27 citations · 0 influential
- **URL:** https://arxiv.org/abs/2402.17826 · [S2](https://www.semanticscholar.org/paper/30c1f450040b65c23f758dbdee7f1daffe278eef)
- **Task types:** human-preference pairwise comparison; model-judged pairwise comparison
- **Methods / metrics:** prediction-powered inference; Bradley-Terry / preference-based ranking; rank-set (set of possible ranking positions); coverage guarantees; human-vs-model preference mismatch quantification
- **Summary:** Provides a statistically rigorous framework for ranking LLMs by human-preference alignment while quantifying the uncertainty introduced when a strong LLM stands in for scarce human pairwise comparisons. Using prediction-powered inference, it outputs a rank-set (a coverage-guaranteed set of possible ranking positions) for each model from a small human-labeled set plus a large model-labeled set. Directly targets the reliability of judge-based pairwise LLM rankings.

### Improving Your Model Ranking on Chatbot Arena by Vote Rigging (2025)

- **Authors:** Rui Min, Tianyu Pang, Chao Du, Qian Liu, Minhao Cheng, Min Lin
- **Venue:** ICML 2025 · `arXiv:2501.17858`
- **Citations:** 15 citations · 3 influential
- **URL:** https://arxiv.org/abs/2501.17858 · [S2](https://www.semanticscholar.org/paper/7bb70c705fe877973650929afceb3d8c0dedce74)
- **Task types:** crowdsourced pairwise voting; leaderboard manipulation / robustness
- **Methods / metrics:** Elo rating mechanism; target-only vs omnipresent rigging strategies; vote/watermark model identification; influence on ranking from ~hundreds of rigged votes; analysis over ~1.7M historical votes
- **Summary:** Demonstrates that crowdsourced Chatbot Arena rankings can be adversarially manipulated: exploiting the Elo update mechanism, an 'omnipresent' rigging strategy lets any new vote influence a target model's rank, shifting rankings with only hundreds of rigged votes among 1.7M. It exposes robustness/security vulnerabilities in Elo-based human-preference leaderboards and motivates defenses. Important for the trustworthiness of pairwise LLM ranking platforms.

### Ranking Large Language Models without Ground Truth (2024)

- **Authors:** et al. (IBM Research)
- **Venue:** ACL Findings 2024 (arXiv preprint) · `arXiv:2402.14860`
- **Citations:** 14 citations · 0 influential
- **URL:** https://arxiv.org/abs/2402.14860 · [S2](https://www.semanticscholar.org/paper/686ae002a4eeb91d56a4530e4d36077118d170ba)
- **Task types:** QA; summarization; reference-free ranking; multi-task
- **Methods / metrics:** triplet/round-robin ranking; reference-free scoring; rank correlation (Kendall/Spearman); consistency-based aggregation
- **⚑ Empirical multi-LLM comparison** — strategy: Reference-free triplet ranking recovering model orderings, evaluated via rank correlation (Kendall/Spearman) against ground-truth-based rankings
- **Summary:** Proposes reference-free methods to rank LLMs without gold labels by exploiting triplets of models and a mutual-evaluation / consistency signal, recovering rankings that correlate strongly with ground-truth-based ones. Offers a low-cost alternative for ordering models across tasks where reference answers are unavailable. Relevant to aggregating rankings under label-scarce, heterogeneous conditions.

### Ranking Unraveled: Recipes for LLM Rankings in Head-to-Head AI Combat (2025)

- **Authors:** Roland Daynauth, Christopher Clarke, Krisztian Flautner, Lingjia Tang, Jason Mars
- **Venue:** ACL 2025 (Proceedings of the 63rd Annual Meeting of the ACL) · `arXiv:2411.14483`
- **Citations:** 8 citations · 2 influential
- **URL:** https://arxiv.org/abs/2411.14483 · [S2](https://www.semanticscholar.org/paper/46a18205b04eda9b0b1e9832ca3380fb895973b8)
- **Task types:** open-ended chat; human-preference pairwise evaluation
- **Methods / metrics:** Elo rating; Bradley-Terry; ranking robustness/consistency principles; sample-efficiency analysis; rank correlation
- **Summary:** Provides a systematic study of pairwise ranking algorithms for LLMs in head-to-head settings, formally defining principles (e.g., robustness, consistency) that an effective ranking method should satisfy. It empirically compares ranking-construction recipes (Elo and Bradley-Terry variants) and quantifies factors affecting ranking accuracy and data efficiency, offering practical guidance for building reliable LLM leaderboards.

### SKATE, a Scalable Tournament Eval: Weaker LLMs Differentiate Between Stronger Ones Using Verifiable Challenges (2025)

- **Authors:** et al.
- **Venue:** arXiv preprint · `arXiv:2508.06111`
- **Citations:** 1 citations · 0 influential
- **URL:** https://arxiv.org/abs/2508.06111 · [S2](https://www.semanticscholar.org/paper/f7e5f2cf6e10c963431513ccd0891f529e154056)
- **Task types:** verifiable challenge generation; model-vs-model competition; self-play evaluation
- **Methods / metrics:** tournament evaluation; TrueSkill rating; verifiable challenges; self-preferencing detection; scalable pairwise differentiation
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: six frontier LLMs (unnamed) · strategy: Runs a tournament (SKATE) where models set and solve verifiable code-output-prediction challenges against each other, aggregated with a TrueSkill rating; evaluates six frontier LLMs and reports their relative rankings plus self-preferencing behavior.
- **Summary:** Introduces SKATE, a scalable tournament evaluation in which models pose and attempt verifiable challenges against each other, aggregated with a TrueSkill-based rating system. Evaluating six frontier LLMs, it finds even weaker models can reliably differentiate and rank stronger ones, and surfaces self-preferencing behavior. Demonstrates TrueSkill applied to competitive, self-generated LLM tournaments.

### Tournament Evaluation of Large Language Models ()

- **Authors:** —
- **Venue:** OpenReview (submission id 5ZpN6W5uRm)
- **Citations:** citations n/a
- **URL:** https://openreview.net/forum?id=5ZpN6W5uRm
- **Task types:** benchmark-derived pairwise tasks; model-vs-model competition
- **Methods / metrics:** automatically constructed tournaments; Elo; Glicko; TrueSkill; Bradley-Terry; data-efficiency vs benchmark-based evaluation; rating-system comparison
- **Summary:** Proposes evaluating LLMs via tournament-style model competitions constructed automatically from existing benchmarks, and directly compares four rating systems (Elo, Glicko, TrueSkill, Bradley-Terry) for aggregating match outcomes. Reports that auto-constructed tournaments give reliable relative-performance rankings using a fraction of the data required by conventional benchmark scoring. (Author/venue metadata could not be verified from the search results.)

### TrueSkill: A Bayesian Skill Rating System (2006)

- **Authors:** Ralf Herbrich, Tom Minka, Thore Graepel
- **Venue:** NeurIPS 2006 (Advances in Neural Information Processing Systems 19)
- **Citations:** citations n/a
- **URL:** https://papers.nips.cc/paper/3079-trueskilltm-a-bayesian-skill-rating-system
- **Task types:** multiplayer game skill rating; team/pairwise outcome ranking
- **Methods / metrics:** Bayesian skill rating; Gaussian skill belief (mean mu, variance sigma); factor-graph approximate message passing (expectation propagation); draw modeling; convergence-speed vs Elo
- **Summary:** The original TrueSkill paper: a Bayesian generalization of Elo that maintains a Gaussian belief over each player's skill and updates it via approximate message passing on a factor graph. It models draws, teams, and many competitors, and tracks uncertainty for faster convergence than Elo. It is the foundational rating system now widely adapted for tournament-style LLM ranking (e.g., SKATE and tournament-eval frameworks).

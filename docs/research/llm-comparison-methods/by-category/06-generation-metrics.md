# Text-generation metrics (BLEU/ROUGE/BERTScore/…)

_24 papers (8 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### BLEU: a Method for Automatic Evaluation of Machine Translation (2002)

- **Authors:** Kishore Papineni, Salim Roukos, Todd Ward, Wei-Jing Zhu
- **Venue:** Proceedings of ACL 2002 (Association for Computational Linguistics) · `10.3115/1073083.1073135`
- **Citations:** 33,838 citations · 6720 influential
- **URL:** https://aclanthology.org/P02-1040/ · [S2](https://www.semanticscholar.org/paper/d7da009f457917aa381619facfa5ffae9329a6e9)
- **Task types:** machine-translation
- **Methods / metrics:** modified n-gram precision; brevity penalty; geometric mean of n-gram precisions; corpus-level BLEU; correlation with human judgment
- **Summary:** Introduces BLEU, the foundational automatic text-generation metric based on modified n-gram precision against one or more human references plus a brevity penalty. Claimed high correlation with human judgment at the system level while being fast, cheap, and language-independent. It became the de facto standard for comparing MT (and later most NLG) systems, making it the reference point against which nearly all later metrics and critiques are measured.

### BERTScore: Evaluating Text Generation with BERT (2020)

- **Authors:** Tianyi Zhang, Varsha Kishore, Felix Wu, Kilian Q. Weinberger, Yoav Artzi
- **Venue:** ICLR 2020 (preprint 2019) · `arXiv:1904.09675`
- **Citations:** 9,038 citations · 1616 influential
- **URL:** https://arxiv.org/abs/1904.09675 · [S2](https://www.semanticscholar.org/paper/295065d942abca0711300b2b4c39829551060578)
- **Task types:** machine-translation; image-captioning; summarization; text-generation
- **Methods / metrics:** token-level contextual embedding cosine similarity (BERT); greedy matching precision/recall/F1; IDF importance weighting; correlation with human judgment; adversarial paraphrase robustness
- **Summary:** Introduces BERTScore, an embedding-based metric that greedily matches candidate and reference tokens by cosine similarity of contextual BERT embeddings, yielding precision, recall, and F1 with optional IDF weighting. Evaluated on 363 MT and captioning systems, it correlates better with human judgment and gives stronger model-selection performance than n-gram metrics, and is more robust to adversarial paraphrases. It is a standard soft-semantic metric for comparing generation-model quality.

### G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment (2023)

- **Authors:** Yang Liu, Dan Iter, Yichong Xu, Shuohang Wang, Ruochen Xu, Chenguang Zhu
- **Venue:** EMNLP 2023 (ACL Anthology 2023.emnlp-main.153) · `arXiv:2303.16634`
- **Citations:** 2,713 citations · 372 influential
- **URL:** https://arxiv.org/abs/2303.16634 · [S2](https://www.semanticscholar.org/paper/381ab7a640f5b46b62f7e08d1af4a8e0d3eadd55)
- **Task types:** text summarization; dialogue generation; natural language generation quality scoring; summarization; dialogue-generation; natural-language-generation
- **Methods / metrics:** chain-of-thought prompting; form-filling scoring paradigm; probability-weighted score aggregation; Spearman/Kendall correlation with human judgments; comparison vs BLEU/ROUGE/BERTScore; LLM-as-judge (GPT-4); chain-of-thought auto-generated evaluation steps; form-filling scoring with probability-weighted scores; Spearman/Kendall correlation with human; analysis of self-preference bias
- **Summary:** Proposes G-Eval, a GPT-4-based framework that uses auto-generated chain-of-thought evaluation steps plus a form-filling paradigm to score NLG outputs, with probability-weighted averaging to smooth integer scores. Achieves Spearman 0.514 with human judgments on summarization, far exceeding reference-based metrics. A widely adopted reference-free, model-based generation metric.

### BLEURT: Learning Robust Metrics for Text Generation (2020)

- **Authors:** Thibault Sellam, Dipanjan Das, Ankur P. Parikh
- **Venue:** ACL 2020 · `arXiv:2004.04696`
- **Citations:** 1,943 citations · 377 influential
- **URL:** https://aclanthology.org/2020.acl-main.704/ · [S2](https://www.semanticscholar.org/paper/4ae52766028e69186052ea8f33a137fbbbdb986a)
- **Task types:** machine-translation; data-to-text; text-generation
- **Methods / metrics:** BERT-based learned regression metric; synthetic-pair pre-training (mask-filling, backtranslation, word dropping); fine-tuning on human ratings; WMT Metrics correlation; robustness to distribution shift
- **Summary:** Presents BLEURT, a learned BERT-based metric fine-tuned to predict human quality ratings, using a novel pre-training scheme over millions of synthetic reference-candidate pairs to generalize from scarce, possibly biased human data. Achieves state-of-the-art correlation on WMT Metrics tasks and WebNLG and stays robust under distribution shift. It exemplifies trained metrics that directly optimize agreement with human judgment for model comparison.

### FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation (2023)

- **Authors:** Sewon Min, Kalpesh Krishna, Xinxi Lyu, Mike Lewis, Wen-tau Yih, Pang Wei Koh, Mohit Iyyer, Luke Zettlemoyer, Hannaneh Hajishirzi
- **Venue:** EMNLP 2023 · `arXiv:2305.14251`
- **Citations:** 1,454 citations · 234 influential
- **URL:** https://arxiv.org/abs/2305.14251 · [S2](https://www.semanticscholar.org/paper/bd5deadc58ee45b5e004378ba1d54a96bc947b4a)
- **Task types:** long-form generation; factuality
- **Methods / metrics:** FActScore; human atomic-fact annotation
- **⚑ Empirical multi-LLM comparison** — 13 models · compared: InstructGPT; ChatGPT; GPT-4; PerplexityAI; Vicuna; Alpaca; MPT; Dolly; StableLM; Oasst; Falcon · strategy: FActScore = percentage of atomic facts supported by a reliable knowledge source, computed by an automatic estimator validated against human annotation (<2% error); models ranked by FActScore. · best: GPT-4
- **Summary:** Evaluates factual precision of long-form biography generation across 13 language models (with initial human evaluation of InstructGPT, ChatGPT, and retrieval-augmented PerplexityAI) using the atomic-fact FActScore metric validated by human annotation. Finds GPT-4 and ChatGPT more factual than public models, with Vicuna and Alpaca best among open models. Provides quantitative cross-model factuality ranking.

### BARTScore: Evaluating Generated Text as Text Generation (2021)

- **Authors:** Weizhe Yuan, Graham Neubig, Pengfei Liu
- **Venue:** NeurIPS 2021 · `arXiv:2106.11520`
- **Citations:** 1,100 citations · 160 influential
- **URL:** https://openreview.net/forum?id=5Ya8PbvpZ9 · [S2](https://www.semanticscholar.org/paper/a6a7724763d8adba466519489b0b9d209e7f2d15)
- **Task types:** summarization; machine-translation; data-to-text; text-generation
- **Methods / metrics:** seq2seq (BART) log-likelihood as score; reference-based and reference-free/source-based variants; faithfulness/factuality, informativeness, fluency evaluation; prompt-augmented scoring; correlation with human judgment
- **Summary:** Formulates evaluation as a text-generation problem: BARTScore uses a pretrained seq2seq model's log-likelihood of generating the target from source/reference (or vice versa) as the quality score, requiring no additional training. Covers multiple quality facets (faithfulness, informativeness, fluency) via direction and prompts and outperforms prior metrics on many datasets. A widely used unsupervised metric for cross-model quality comparison.

### SummEval: Re-evaluating Summarization Evaluation (2021)

- **Authors:** Alexander R. Fabbri, Wojciech Kryściński, Bryan McCann, Caiming Xiong, Richard Socher, Dragomir Radev
- **Venue:** TACL 9, MIT Press · `arXiv:2007.12626`
- **Citations:** 1,017 citations · 171 influential
- **URL:** https://aclanthology.org/2021.tacl-1.24/ · [S2](https://www.semanticscholar.org/paper/781b9a445d1878ee4744546f2b8c7466e3cbbd1a)
- **Task types:** summarization
- **Methods / metrics:** benchmark of 14+ automatic metrics; expert and crowd human annotations (coherence, consistency, fluency, relevance); metric-human correlation; reproducibility toolkit; 23-model output collection
- **Summary:** A large-scale re-evaluation of summarization metrics: benchmarks 14+ automatic metrics against consistent expert/crowd human annotations across 23 models on CNN/DailyMail, releasing a unified toolkit and annotations. Finds many widely used metrics correlate weakly and inconsistently with human quality dimensions. A standard reference dataset and diagnosis for how metric choice affects summarization-model comparison.

### CodeBLEU: a Method for Automatic Evaluation of Code Synthesis (2020)

- **Authors:** Shuo Ren, Daya Guo, Shuai Lu, et al.
- **Venue:** arXiv preprint (Microsoft) · `arXiv:2009.10297`
- **Citations:** 882 citations · 123 influential
- **URL:** https://arxiv.org/abs/2009.10297 · [S2](https://www.semanticscholar.org/paper/f23a0e443fe931aa2fed932421bf47c1a4fcf619)
- **Task types:** code-generation; code-translation; code-refinement
- **Methods / metrics:** CodeBLEU; n-gram BLEU; weighted keyword match; AST match; data-flow match; correlation with human scores
- **Summary:** Proposes CodeBLEU, a match-based metric that augments n-gram BLEU with weighted keyword matching, abstract-syntax-tree (AST) subtree matching, and data-flow semantic matching. Designed for cases where execution is unavailable (code translation, refinement, text-to-code), it correlates better with human quality judgments than BLEU or exact accuracy, and remains a widely reported reference-based precision metric for code.

### Benchmarking Large Language Models for News Summarization (2023)

- **Authors:** Tianyi Zhang, Faisal Ladhak, Esin Durmus, Percy Liang, Kathleen McKeown, Tatsunori B. Hashimoto
- **Venue:** TACL / arXiv · `arXiv:2301.13848`
- **Citations:** 819 citations · 25 influential
- **URL:** https://arxiv.org/abs/2301.13848 · [S2](https://www.semanticscholar.org/paper/a4a41319d5805a29316f24ed9519f09db77d4c29)
- **Task types:** summarization
- **Methods / metrics:** human Likert ratings; ROUGE; faithfulness
- **⚑ Empirical multi-LLM comparison** — 10 models · compared: GPT-3 (Instruct variants); T0; GLM; OPT; Cohere; Anthropic (early); fine-tuned BRIO/PEGASUS baselines · strategy: Human evaluation (Likert faithfulness/quality) on freshly collected freelance-writer reference summaries, plus automatic metrics (ROUGE); models ranked by human ratings. · best: Instruction-tuned GPT-3 (Instruct-Davinci)
- **Summary:** Human evaluation of ten LLMs on zero-shot news summarization, spanning different pretraining schemes, prompts, and scales. Fresh high-quality reference summaries were collected from freelance writers, and the study finds instruction tuning (not scale) drives summarization quality, with the best LLM summaries rated comparable to human-written ones. Quantitative human ratings compare models head-to-head on faithfulness and quality.

### MoverScore: Text Generation Evaluating with Contextualized Embeddings and Earth Mover Distance (2019)

- **Authors:** Wei Zhao, Maxime Peyrard, Fei Liu, Yang Gao, Christian M. Meyer, Steffen Eger
- **Venue:** EMNLP-IJCNLP 2019 · `arXiv:1909.02622`
- **Citations:** 731 citations · 99 influential
- **URL:** https://aclanthology.org/D19-1053/ · [S2](https://www.semanticscholar.org/paper/635cb6fb865e86c108c5d1d895aeac0e759eb199)
- **Task types:** machine-translation; summarization; image-captioning; data-to-text
- **Methods / metrics:** Word Mover's Distance / Earth Mover's Distance; contextualized (BERT/ELMo) embeddings; soft n-gram alignment; IDF weighting; correlation with human judgment
- **Summary:** Proposes MoverScore, which measures semantic distance between candidate and reference via Earth Mover's Distance over contextualized embeddings, allowing soft many-to-many token alignment (a generalization of BERTScore's hard matching). Validated across MT, summarization, captioning, and data-to-text, showing that combining contextual representations with a distance measure yields the strongest, most generalizable correlation with human judgment.

### Why We Need New Evaluation Metrics for NLG (2017)

- **Authors:** Jekaterina Novikova, Ondřej Dušek, Amanda Cercas Curry, Verena Rieser
- **Venue:** EMNLP 2017 · `arXiv:1707.06875`
- **Citations:** 527 citations · 45 influential
- **URL:** https://aclanthology.org/D17-1238/ · [S2](https://www.semanticscholar.org/paper/0d441ab58a1027cb64084ad065cfea5e15b8e74c)
- **Task types:** data-to-text; natural-language-generation
- **Methods / metrics:** word-based and grammar-based metrics; metric-human correlation analysis; system-level vs sentence-level correlation; error-detection analysis
- **Summary:** Empirically shows that a broad range of word-based and grammar-based automatic metrics only weakly reflect human judgments of data-driven end-to-end NLG output, and that metric performance is data- and system-specific. Finds metrics more reliable at the system level and useful mainly for flagging poor outputs. A key motivation for the shift toward learned and embedding-based metrics.

### News Summarization and Evaluation in the Era of GPT-3 (2022)

- **Authors:** Tanya Goyal, Junyi Jessy Li, Greg Durrett
- **Venue:** arXiv (cs.CL) · `arXiv:2209.12356`
- **Citations:** 501 citations · 35 influential
- **URL:** https://arxiv.org/abs/2209.12356 · [S2](https://www.semanticscholar.org/paper/83851f1a32d41975582ca62355858ab5e34738f7)
- **Task types:** summarization
- **Methods / metrics:** human pairwise preference; ROUGE; reference-free metrics
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: GPT-3 (davinci variants); PEGASUS; BRIO; T0 · strategy: 1K human pairwise preference judgments plus reference-based and reference-free automatic metrics; finding that metrics cannot reliably rank GPT-3. · best: GPT-3
- **Summary:** Compares prompt-based GPT-3 against multiple fine-tuned summarization systems (e.g., PEGASUS, BRIO, T0) on generic and keyword-based news summarization. Roughly 1K human pairwise comparisons show humans overwhelmingly prefer GPT-3 summaries, and the study demonstrates that standard automatic metrics fail to track this preference. Quantitative human preference is the deciding signal across models.

### A Structured Review of the Validity of BLEU (2018)

- **Authors:** Ehud Reiter
- **Venue:** Computational Linguistics 44(3), MIT Press · `10.1162/coli_a_00322`
- **Citations:** 459 citations · 18 influential
- **URL:** https://aclanthology.org/J18-3002/ · [S2](https://www.semanticscholar.org/paper/814db99ccf6b88d6af5b406b0c344b64c0a710b7)
- **Task types:** machine-translation; natural-language-generation
- **Methods / metrics:** structured literature review; meta-analysis of 284 metric-human correlations; construct/criterion validity assessment; diagnostic vs evaluative use distinction
- **Summary:** A structured meta-review of 284 reported correlations assessing whether BLEU is a valid proxy for real-world utility and user satisfaction. Concludes BLEU is defensible for diagnostic MT-system evaluation but not for use outside MT, for scoring individual texts, or for scientific hypothesis testing. Provides an evidence-based validity framework directly relevant to using metrics for rigorous model comparison.

### Repairing the Cracked Foundation: A Survey of Obstacles in Evaluation Practices for Generated Text (2023)

- **Authors:** Sebastian Gehrmann, Elizabeth Clark, Thibault Sellam
- **Venue:** Journal of Artificial Intelligence Research (JAIR); preprint 2022 · `arXiv:2202.06935`
- **Citations:** 244 citations · 13 influential
- **URL:** https://arxiv.org/abs/2202.06935 · [S2](https://www.semanticscholar.org/paper/e4e9d556e9725a5fdb2e133b61243ff7c1ca8aeb)
- **Task types:** natural-language-generation; summarization; machine-translation; data-to-text
- **Methods / metrics:** survey/taxonomy of automatic and human evaluation flaws; metric-human correlation critique; dataset and reporting-standard analysis; recommendations for evaluation protocols
- **Summary:** A broad survey cataloguing two decades of known problems in NLG evaluation, both automatic metrics and human evaluations, and why fixes are rarely adopted. Argues that surface-based metrics increasingly fail as neural outputs become indistinguishable on surface features, and lays out concrete recommendations for more valid, reproducible evaluation. A comprehensive reference for the limits of metric-based model comparison.

### Evaluating Open-Domain Question Answering in the Era of Large Language Models (2023)

- **Authors:** Ehsan Kamalloo, Nouha Dziri, Charles L. A. Clarke, Davood Rafiei
- **Venue:** ACL 2023 · `arXiv:2305.06984`
- **Citations:** 188 citations · 7 influential
- **URL:** https://arxiv.org/abs/2305.06984 · [S2](https://www.semanticscholar.org/paper/6bef46eccb4c7f521e4f255a01595ebf9994ae22)
- **Task types:** open-domain QA; evaluation-metric analysis
- **Methods / metrics:** human judgment; exact match / lexical match; regex match; BEM / automated evaluators
- **⚑ Empirical multi-LLM comparison** — 12 models · compared: InstructGPT (zero-shot & few-shot); GPT-3; FiD; DPR; EMDR2; R2-D2; RAG · strategy: Human annotation of correctness compared against lexical, regex, and model-based automatic metrics across multiple QA systems; quantifies metric failure rates rather than proposing a single new metric. · best: InstructGPT few-shot (state-of-the-art under human evaluation)
- **Summary:** Manually evaluates several open-domain QA systems including LLMs on NQ-open and shows lexical-match metrics drastically underestimate generative models; InstructGPT's human-judged accuracy rises ~60% over lexical scoring. Compares extractive, retrieval-augmented, and LLM systems and analyzes automated evaluators, quantifying the metric-vs-human gap across models.

### BooookScore: A Systematic Exploration of Book-Length Summarization in the Era of LLMs (2024)

- **Authors:** Yapei Chang, Kyle Lo, Tanya Goyal, Mohit Iyyer
- **Venue:** ICLR 2024 · `arXiv:2310.00785`
- **Citations:** 184 citations · 18 influential
- **URL:** https://arxiv.org/abs/2310.00785 · [S2](https://www.semanticscholar.org/paper/65fe385a665480b41fafc56d76a3bd72e92e8886)
- **Task types:** summarization; long-form generation
- **Methods / metrics:** BooookScore; human coherence annotation
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: GPT-4; Claude 2; GPT-3.5-Turbo; LLaMA 2; Mixtral · strategy: Human fine-grained coherence annotation (1,193 annotations, 8 error types) plus automatic BooookScore metric; models ranked by proportion of error-free sentences. · best: GPT-4 (tied with Claude 2)
- **Summary:** Compares five LLMs on book-length (100k+ token) summarization using two aggregation strategies, with 1,193 human coherence annotations over 100 recent books and an automatic BooookScore metric validated against them. GPT-4 and Claude 2 lead; Mixtral matches GPT-3.5-Turbo while LLaMA 2 lags. Models are ranked quantitatively on coherence error rate.

### BLEU might be Guilty but References are not Innocent (2020)

- **Authors:** Markus Freitag, David Grangier, Isaac Caswell
- **Venue:** EMNLP 2020 · `arXiv:2004.06063`
- **Citations:** 167 citations · 10 influential
- **URL:** https://aclanthology.org/2020.emnlp-main.5/ · [S2](https://www.semanticscholar.org/paper/213e471bacff5c0852943988fcb955797f1e591f)
- **Task types:** machine-translation
- **Methods / metrics:** reference collection/paraphrasing study; translationese bias analysis; multi-reference BLEU/metric correlation; paraphrased-reference metrics; correlation with human judgment for high-quality systems
- **Summary:** Demonstrates that poor metric-human correlation, especially for high-quality MT systems, stems partly from low-diversity translationese references, not only the metric. Introduces paraphrased references that substantially improve correlation across metrics. Shows that reference quality is a confound in any reference-based model comparison, an important caveat when ranking near-human systems.

### LongWriter: Unleashing 10,000+ Word Generation from Long Context LLMs (2024)

- **Authors:** Yushi Bai, Jiajie Zhang, Xin Lv, Linzhi Zheng, Siqi Zhu, Lei Hou, Yuxiao Dong, Jie Tang, Juanzi Li
- **Venue:** arXiv (cs.CL) / ICLR 2025 · `arXiv:2408.07055`
- **Citations:** 147 citations · 33 influential
- **URL:** https://arxiv.org/abs/2408.07055 · [S2](https://www.semanticscholar.org/paper/14ba95d4344aea719be0425f4b214d5bd42aabfb)
- **Task types:** long-form generation; writing quality
- **Methods / metrics:** length-following score; GPT-4 quality judge; win-rate
- **⚑ Empirical multi-LLM comparison** — 8 models · compared: GPT-4o; Claude 3.5; Gemini 1.5; GLM-4; LLaMA-3.1; LongWriter-9B; Qwen2 · strategy: LongBench-Write automatic scoring of output-length adherence (S_l) and quality (S_q via GPT-4 judge across six dimensions); models ranked on combined score. · best: LongWriter-9B (DPO)
- **Summary:** Introduces LongBench-Write, a benchmark for ultra-long (up to 10,000+ word) generation, and evaluates multiple proprietary and open LLMs on output length adherence and quality. Their trained 9B model (AgentWrite + DPO) surpasses much larger proprietary models. Models are scored with automatic length and quality metrics plus GPT-4 judging.

### Summarization is (Almost) Dead (2023)

- **Authors:** Xiao Pu, Mingqi Gao, Xiaojun Wan
- **Venue:** arXiv (cs.CL) · `arXiv:2309.09558`
- **Citations:** 75 citations · 4 influential
- **URL:** https://arxiv.org/abs/2309.09558 · [S2](https://www.semanticscholar.org/paper/aa0b3306f7dd827a6fb8487aeb39d832fdcb97a0)
- **Task types:** summarization
- **Methods / metrics:** human preference; factual consistency; hallucination rate
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: GPT-3.5 / ChatGPT; GPT-4; fine-tuned BART; fine-tuned PEGASUS; T5-family baselines · strategy: Human preference judgments (LLM vs human vs fine-tuned) plus hallucination/factual-consistency error analysis; models compared by win-rate and error counts. · best: LLM (ChatGPT/GPT-4-class) summaries
- **Summary:** Evaluates LLM zero-shot summarization across five summarization tasks against human-written and fine-tuned-model summaries using human preference judgments. LLM-generated summaries are preferred by human evaluators and show better factual consistency and fewer extrinsic hallucinations. Compares several LLMs and fine-tuned baselines quantitatively via preference and error rates.

### ProxyQA: An Alternative Framework for Evaluating Long-Form Text Generation with Large Language Models (2024)

- **Authors:** Haochen Tan, Zhijiang Guo, Zhan Shi, Lu Xu, Zhili Liu, Yunlong Feng, Xiaoguang Li, Yasheng Wang, Lifeng Shang, Qun Liu, Linqi Song
- **Venue:** ACL 2024 · `arXiv:2401.15042`
- **Citations:** 24 citations · 1 influential
- **URL:** https://arxiv.org/abs/2401.15042 · [S2](https://www.semanticscholar.org/paper/d891face4565ef3970c1a0965d8126456651f81e)
- **Task types:** long-form generation
- **Methods / metrics:** proxy-question accuracy; human alignment
- **⚑ Empirical multi-LLM comparison** — 10 models · compared: GPT-4; GPT-3.5-Turbo; Claude; Llama-2; Vicuna; WizardLM; Mistral · strategy: Proxy-question answering accuracy (evaluator LLM answers pre-annotated proxy-questions from generated long text), validated for self-consistency and alignment with human evaluation; models ranked by proxy accuracy. · best: GPT-4
- **Summary:** Proposes an evaluation framework using human-curated meta-questions and pre-annotated proxy-questions to assess long-form generation (reports, articles) and benchmarks multiple LLMs by an evaluator's accuracy in answering proxy-questions from generated content. Shows the metric aligns closely with human judgment. Multiple contemporary LLMs are compared quantitatively on long-form quality.

### Reference-free Evaluation Metrics for Text Generation: A Survey (2025)

- **Authors:** Takumi Ito, Kees van Deemter, Jun Suzuki
- **Venue:** arXiv preprint · `arXiv:2501.12011`
- **Citations:** 13 citations · 0 influential
- **URL:** https://arxiv.org/abs/2501.12011 · [S2](https://www.semanticscholar.org/paper/d59902d1d13487e99360f095f19952dc6e2ac8d6)
- **Task types:** natural-language-generation; dialogue-generation; summarization; machine-translation
- **Methods / metrics:** taxonomy of reference-free/quality-estimation metrics; LLM-based and embedding-based scoring survey; metric-human correlation review; applications beyond model evaluation (training signal, filtering)
- **Summary:** A recent (2025) survey of reference-free text-generation metrics, which score outputs without human gold references, spanning quality-estimation, embedding-based, and LLM-based approaches across the full breadth of NLG tasks. Organizes the design space, their validity relative to human judgment, and uses beyond evaluation (e.g. as training or filtering signals). A current map of where automatic model-comparison metrics are heading after BLEU/ROUGE.

### ROUGE: A Package for Automatic Evaluation of Summaries (2004)

- **Authors:** Chin-Yew Lin
- **Venue:** Text Summarization Branches Out, ACL Workshop 2004
- **Citations:** citations n/a
- **URL:** https://aclanthology.org/W04-1013/
- **Task types:** summarization
- **Methods / metrics:** ROUGE-N n-gram recall overlap; ROUGE-L longest common subsequence; ROUGE-W weighted LCS; ROUGE-S skip-bigram; recall/precision/F against reference summaries
- **Summary:** Defines the ROUGE family of recall-oriented overlap metrics (ROUGE-N, ROUGE-L, ROUGE-W, ROUGE-S) comparing a candidate summary to human reference summaries. ROUGE is the standard automatic metric for summarization and a common building block for cross-system comparison. Its recall orientation and reliance on surface overlap make it a frequent target of the human-correlation critiques listed below.

### METEOR: An Automatic Metric for MT Evaluation with Improved Correlation with Human Judgments (2005)

- **Authors:** Satanjeev Banerjee, Alon Lavie
- **Venue:** ACL 2005 Workshop on Intrinsic and Extrinsic Evaluation Measures for MT/Summarization
- **Citations:** citations n/a
- **URL:** https://aclanthology.org/W05-0909/
- **Task types:** machine-translation
- **Methods / metrics:** unigram alignment (surface, stem, synonym matching); harmonic mean of precision and recall (recall-weighted); fragmentation/chunk penalty; sentence-level correlation with human judgment
- **Summary:** Proposes METEOR, which improves on BLEU by aligning unigrams via exact, stemmed, and synonym matches and computing a recall-weighted F-score with a fragmentation penalty for word order. Reports higher sentence-level correlation with human judgments than BLEU and NIST. It remains a widely reported complement to BLEU/ROUGE in model-comparison tables and addresses BLEU's precision-only, recall-blind weakness.

### Re-evaluating the Role of BLEU in Machine Translation Research (2006)

- **Authors:** Chris Callison-Burch, Miles Osborne, Philipp Koehn
- **Venue:** EACL 2006
- **Citations:** citations n/a
- **URL:** https://aclanthology.org/E06-1032/
- **Task types:** machine-translation
- **Methods / metrics:** counterexample analysis; BLEU-vs-human correlation; system-ranking disagreement; critique of n-gram metric validity
- **Summary:** An early, influential critique showing that a higher BLEU score is neither necessary nor sufficient for genuine translation-quality improvement, with concrete counterexamples where BLEU and human rankings diverge. Argues BLEU is biased toward systems using similar technology and correlates poorly across paradigms. Foundational for the argument that metric-based model comparisons can be misleading.

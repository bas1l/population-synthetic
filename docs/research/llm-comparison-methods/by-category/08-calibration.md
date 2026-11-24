# Calibration & uncertainty quantification

_15 papers (2 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### On Calibration of Modern Neural Networks (2017)

- **Authors:** Chuan Guo, Geoff Pleiss, Yu Sun, Kilian Q. Weinberger
- **Venue:** ICML 2017 (PMLR) · `arXiv:1706.04599`
- **Citations:** 8,764 citations · 1519 influential
- **URL:** https://arxiv.org/abs/1706.04599 · [S2](https://www.semanticscholar.org/paper/d65ce2b8300541414bfe51d03906fca72e93523c)
- **Task types:** image-classification; reliability-assessment
- **Methods / metrics:** expected calibration error (ECE); reliability diagrams; temperature scaling; Platt scaling; negative log-likelihood
- **Summary:** The foundational modern-calibration paper: shows deep networks are systematically overconfident and that a single-parameter temperature-scaling post-hoc fit recovers calibration cheaply. Introduces the now-standard toolkit (ECE, reliability diagrams) used to quantify whether a model's stated confidence matches its empirical accuracy. This machinery underpins essentially all subsequent LLM confidence/precision evaluation.

### Language Models (Mostly) Know What They Know (2022)

- **Authors:** Saurav Kadavath, Tom Conerly, Amanda Askell, et al.
- **Venue:** arXiv preprint (Anthropic) · `arXiv:2207.05221`
- **Citations:** 1,773 citations · 158 influential
- **URL:** https://arxiv.org/abs/2207.05221 · [S2](https://www.semanticscholar.org/paper/142ebbf4760145f591166bde2564ac70c001e927)
- **Task types:** QA; multiple-choice; true-false; self-evaluation
- **Methods / metrics:** P(True) self-evaluation; P(IK) 'I-know' probability; reliability diagrams; ECE; calibration-vs-scale analysis
- **Summary:** Demonstrates that large models are well-calibrated on multiple-choice/true-false questions in the right format, and can self-evaluate via P(True) and predict answerability via P(IK). Establishes model-internal probabilities as a usable accuracy signal and shows calibration improves with scale. A cornerstone reference for using self-reported confidence to assess LLM correctness.

### Detecting Hallucinations in Large Language Models Using Semantic Entropy (2024)

- **Authors:** Sebastian Farquhar, Jannik Kossen, Lorenz Kuhn, Yarin Gal
- **Venue:** Nature 630 (Nature Portfolio) · `10.1038/s41586-024-07421-0`
- **Citations:** 1,452 citations · 153 influential
- **URL:** https://www.nature.com/articles/s41586-024-07421-0 · [S2](https://www.semanticscholar.org/paper/f82f49c20c6acc69f884f05e3a9f1ceea91061ce)
- **Task types:** open-ended QA; generation; hallucination-detection; clinical
- **Methods / metrics:** semantic entropy; entailment clustering; AUROC/AURAC; rejection-accuracy curves
- **Summary:** Nature-published extension of semantic entropy that detects confabulations (arbitrary, wrong generations) by measuring meaning-level uncertainty across sampled answers, generalizing across datasets and tasks including biomedical QA. Enables selective answering that raises accuracy by abstaining on high-entropy queries. High-visibility validation of entropy-based UQ as a precision safeguard.

### SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for Generative Large Language Models (2023)

- **Authors:** Potsawee Manakul, Adian Liusie, Mark J. F. Gales
- **Venue:** EMNLP 2023 · `arXiv:2303.08896`
- **Citations:** 1,069 citations · 117 influential
- **URL:** https://arxiv.org/abs/2303.08896 · [S2](https://www.semanticscholar.org/paper/7c1707db9aafd209aa93db3251e7ebd593d55876)
- **Task types:** generation; fact-checking; hallucination-detection
- **Methods / metrics:** sampling-based self-consistency; BERTScore agreement; NLI-based contradiction; QA-based consistency; AUC-PR for hallucination
- **Summary:** A zero-resource, black-box method that samples multiple responses and flags facts where samples disagree as likely hallucinations, on the premise that known facts yield consistent samples. Provides sentence-level factuality/confidence scores without external databases or logits. Widely used as a reference consistency-based confidence signal for assessing generation accuracy.

### Can LLMs Express Their Uncertainty? An Empirical Evaluation of Confidence Elicitation in LLMs (2024)

- **Authors:** Miao Xiong, Zhiyuan Hu, Xinyang Lu, et al.
- **Venue:** ICLR 2024 · `arXiv:2306.13063`
- **Citations:** 1,026 citations · 139 influential
- **URL:** https://arxiv.org/abs/2306.13063 · [S2](https://www.semanticscholar.org/paper/8f7297454d7f44365b9bcda5ebb9439a43daf5e6)
- **Task types:** QA; commonsense-reasoning; arithmetic; failure-prediction
- **Methods / metrics:** verbalized confidence; consistency-based confidence; hybrid aggregation; ECE; AUROC/AUPRC failure prediction
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: GPT-4; LLaMA 2 Chat · strategy: Black-box benchmark of confidence-elicitation methods (verbalized, consistency, hybrid) across 5 LLMs and 5 datasets, measured by ECE for calibration and AUROC/AUPRC for failure prediction; also compared to white-box methods
- **Summary:** A systematic black-box benchmark decomposing confidence elicitation into prompting, sampling, and aggregation, evaluated on calibration and failure prediction across five datasets and five LLMs (incl. GPT-4). Finds LLMs are highly overconfident when verbalizing, and consistency/hybrid methods beat naive verbalization. A strong baseline framework for comparing confidence-estimation methods.

### Semantic Uncertainty: Linguistic Invariances for Uncertainty Estimation in Natural Language Generation (2023)

- **Authors:** Lorenz Kuhn, Yarin Gal, Sebastian Farquhar
- **Venue:** ICLR 2023 (Oral) · `arXiv:2302.09664`
- **Citations:** 829 citations · 158 influential
- **URL:** https://arxiv.org/abs/2302.09664 · [S2](https://www.semanticscholar.org/paper/507465f8d46489a68a527cb5304d76bdb6c31ed9)
- **Task types:** open-ended QA; generation; hallucination-detection
- **Methods / metrics:** semantic entropy; bidirectional-entailment clustering; predictive entropy; AUROC for correctness prediction
- **Summary:** Defines semantic entropy, which clusters semantically-equivalent generations before computing entropy, so uncertainty reflects meaning rather than surface form. More predictive of QA correctness than token-level entropy baselines, and unsupervised/single-model. A key UQ metric for free-form generation where standard ECE does not directly apply.

### Just Ask for Calibration: Strategies for Eliciting Calibrated Confidence Scores from Language Models Fine-Tuned with Human Feedback (2023)

- **Authors:** Katherine Tian, Eric Mitchell, Allan Zhou, et al.
- **Venue:** EMNLP 2023 · `arXiv:2305.14975`
- **Citations:** 810 citations · 119 influential
- **URL:** https://arxiv.org/abs/2305.14975 · [S2](https://www.semanticscholar.org/paper/ab4ce5dda7ad4d9032995c9c049a89d65723c6aa)
- **Task types:** QA; verbalized-confidence; RLHF-model-evaluation
- **Methods / metrics:** verbalized probability elicitation; prompting strategies; ECE; AUROC selective accuracy; Brier score
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: GPT-4; ChatGPT; Claude · strategy: Compares verbalized-confidence elicitation strategies against model conditional probabilities across several RLHF LLMs, quantified via Expected Calibration Error (ECE), Brier score, and AUROC selective accuracy
- **Summary:** Shows RLHF-tuned models have distorted conditional probabilities, but the right prompting makes their verbalized probabilities substantially better calibrated than logits. Systematically compares elicitation strategies for extracting trustworthy confidence from closed chat models. A go-to reference for measuring and improving precision of RLHF/commercial LLM confidence.

### Teaching Models to Express Their Uncertainty in Words (2022)

- **Authors:** Stephanie Lin, Jacob Hilton, Owain Evans
- **Venue:** Transactions on Machine Learning Research (TMLR) · `arXiv:2205.14334`
- **Citations:** 772 citations · 65 influential
- **URL:** https://arxiv.org/abs/2205.14334 · [S2](https://www.semanticscholar.org/paper/374dd173491a59a10bbb2b3519ebcfe3649f529d)
- **Task types:** QA; arithmetic; verbalized-confidence
- **Methods / metrics:** verbalized (natural-language) confidence; calibration under distribution shift; ECE; MSE of stated probabilities
- **Summary:** Introduces 'verbalized confidence': fine-tuning GPT-3 to state calibrated uncertainty in words (e.g. '90% confident') rather than via logits, and shows this generalizes under distribution shift. Seminal for the black-box paradigm where you elicit a probability from text output and check it against accuracy. Directly motivates precision/accuracy assessment for API-only models.

### Generating with Confidence: Uncertainty Quantification for Black-box Large Language Models (2023)

- **Authors:** Zhen Lin, Shubhendu Trivedi, Jimeng Sun
- **Venue:** Transactions on Machine Learning Research (TMLR) · `arXiv:2305.19187`
- **Citations:** 321 citations · 42 influential
- **URL:** https://arxiv.org/abs/2305.19187 · [S2](https://www.semanticscholar.org/paper/ad934a9344f68fcc0b9aa704102aa48c39c5b591)
- **Task types:** open-ended QA; generation; selective-generation
- **Methods / metrics:** semantic dispersion; similarity-graph confidence measures; uncertainty vs confidence separation; AUROC/AUARC for selective NLG
- **Summary:** Separates uncertainty (dispersion over a fixed input) from confidence (trust in a specific generation) for black-box LLMs, proposing sampling-and-similarity measures that need only text outputs. Finds semantic dispersion strongly predicts response quality, enabling selective NLG that filters unreliable answers. Practical toolkit for precision assessment without model internals.

### A Survey of Confidence Estimation and Calibration in Large Language Models (2024)

- **Authors:** Jiahui Geng, Fengyu Cai, Yuxia Wang, Heinz Koeppl, Preslav Nakov, Iryna Gurevych
- **Venue:** NAACL 2024 (ACL Anthology) · `arXiv:2311.08298`
- **Citations:** 288 citations · 13 influential
- **URL:** https://aclanthology.org/2024.naacl-long.366/ · [S2](https://www.semanticscholar.org/paper/6aa6003c7d7b3d275ae981aa6200014968c32430)
- **Task types:** survey; QA; generation; reasoning
- **Methods / metrics:** taxonomy of confidence estimators; logit/verbalized/consistency methods; ECE; calibration under fine-tuning/RLHF
- **Summary:** A structured survey organizing confidence-estimation and calibration methods for LLMs by access level (white/gray/black-box) and by task, and cataloguing metrics such as ECE and selective-prediction curves. Maps how fine-tuning and RLHF affect calibration and where methods fail. A practical entry point for choosing a precision-assessment method.

### Calibrated Language Models Must Hallucinate (2024)

- **Authors:** Adam Tauman Kalai, Santosh S. Vempala
- **Venue:** STOC 2024 (ACM Symposium on Theory of Computing) · `10.1145/3618260.3649777`
- **Citations:** 181 citations · 10 influential
- **URL:** https://arxiv.org/abs/2311.14648 · [S2](https://www.semanticscholar.org/paper/1460d33f547ee40c560174dc0f6898f4802f4cf8)
- **Task types:** theory; generation; factual-QA
- **Methods / metrics:** statistical calibration condition; Good-Turing missing-mass estimate; hallucination lower bound; monofact rate
- **Summary:** A theoretical result proving that any generative LM satisfying a natural calibration condition must hallucinate 'arbitrary' facts at a rate lower-bounded by the fraction of facts seen once in training (a Good-Turing estimate), independent of architecture or data quality. Formalizes a fundamental tension between being calibrated and being factual. Essential context for interpreting calibration vs accuracy trade-offs.

### To Believe or Not to Believe Your LLM: Iterative Prompting for Estimating Epistemic Uncertainty (2024)

- **Authors:** Yasin Abbasi-Yadkori, Ilja Kuzborskij, András György, Csaba Szepesvári
- **Venue:** NeurIPS 2024 (Google DeepMind) · `arXiv:2406.02543`
- **Citations:** 153 citations · 6 influential
- **URL:** https://arxiv.org/abs/2406.02543 · [S2](https://www.semanticscholar.org/paper/5322cd631e69ae484038b13ac320194afaccdc3b)
- **Task types:** QA; single-answer; multi-answer; hallucination-detection
- **Methods / metrics:** information-theoretic epistemic/aleatoric decomposition; iterative prompting; mutual-information bound; hallucination detection rate
- **Summary:** Derives an information-theoretic metric that isolates epistemic uncertainty (lack of knowledge) from aleatoric uncertainty (legitimate answer multiplicity) using only iterative prompting on prior responses. Flags outputs as unreliable when epistemic uncertainty is high, working for both single- and multi-answer questions. A principled black-box criterion for when to trust an LLM's answer.

### A Survey on Uncertainty Quantification of Large Language Models: Taxonomy, Open Research Challenges, and Future Directions (2024)

- **Authors:** Ola Shorinwa, Zhiting Mei, Justin Lidard, Allen Z. Ren, Anirudha Majumdar
- **Venue:** arXiv preprint (Princeton) · `arXiv:2412.05563`
- **Citations:** 138 citations · 5 influential
- **URL:** https://arxiv.org/abs/2412.05563 · [S2](https://www.semanticscholar.org/paper/eac37c416c89a8eafd655dee639344379e2df33e)
- **Task types:** survey; QA; generation; reasoning; decision-making
- **Methods / metrics:** UQ taxonomy (input/reasoning/parameter/prediction); epistemic vs aleatoric; calibration metrics; conformal & sampling-based UQ
- **Summary:** A comprehensive 2024 survey giving a taxonomy of LLM uncertainty sources (input ambiguity, reasoning-path divergence, decoding stochasticity) that extend the classical aleatoric/epistemic split, and reviewing calibration, conformal, and consistency-based estimators plus evaluation metrics. Frames open challenges for reliable, calibrated LLM deployment. Useful as the broad-scope companion reference for the field.

### ConU: Conformal Uncertainty in Large Language Models with Correctness Coverage Guarantees (2024)

- **Authors:** Zhiyuan Wang, Jinhao Duan, Lu Cheng, et al.
- **Venue:** Findings of EMNLP 2024 · `arXiv:2407.00499`
- **Citations:** 69 citations · 2 influential
- **URL:** https://arxiv.org/abs/2407.00499 · [S2](https://www.semanticscholar.org/paper/bbc8eb04cbfa9f221dcd63d45ffd460b88a0ac01)
- **Task types:** open-ended QA; generation; selective-prediction
- **Methods / metrics:** conformal prediction; nonconformity score aligned with correctness; distribution-free coverage guarantee; prediction-set size / coverage rate
- **Summary:** Applies split conformal prediction to black-box LLM generation, building a nonconformity score tied to correctness so that prediction sets contain a correct answer at a user-specified rate with finite-sample guarantees. Turns heuristic confidence into rigorously calibrated coverage. Represents the conformal/distribution-free branch of LLM precision assessment.

### Verified Uncertainty Calibration (2019)

- **Authors:** Ananya Kumar, Percy Liang, Tengyu Ma
- **Venue:** NeurIPS 2019 (Spotlight)
- **Citations:** citations n/a
- **URL:** https://proceedings.neurips.cc/paper/2019/hash/f8c0c968632845cd133308b1a494967f-Abstract.html
- **Task types:** classification; recalibration
- **Methods / metrics:** scaling-binning calibrator; debiased calibration-error estimator; RMS calibration error; sample-complexity bounds
- **Summary:** Shows that popular recalibrators (Platt/temperature scaling) are less calibrated than reported and that their calibration error cannot be reliably estimated with standard binning. Proposes the scaling-binning calibrator plus a debiased estimator with O(1/eps^2) sample complexity, letting practitioners actually measure and certify calibration error. Central to trustworthy precision claims because it corrects the measurement of ECE itself.

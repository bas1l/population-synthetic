# Clinical / medical LLM evaluation

_28 papers (21 empirical multi-LLM comparisons ⚑) · part of the [LLM comparison-methods dossier](../README.md)_

---

### Large Language Models Encode Clinical Knowledge (2023)

- **Authors:** Karan Singhal et al.
- **Venue:** Nature (Springer Nature) · `arXiv:2212.13138 / 10.1038/s41586-023-06291-2`
- **Citations:** 4,663 citations · 209 influential
- **URL:** https://www.nature.com/articles/s41586-023-06291-2 · [S2](https://www.semanticscholar.org/paper/6052486bc9144dc1730c12bf35323af3792a1fd0)
- **Task types:** medical QA; USMLE-style MCQA; consumer health QA; long-form clinical answer generation
- **Methods / metrics:** MultiMedQA benchmark; multiple-choice accuracy; human expert pairwise/axis rating; instruction prompt tuning; factuality/harm/bias rubric
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: PaLM 540B; Flan-PaLM; Med-PaLM · strategy: Multiple-choice accuracy across MultiMedQA plus multi-axis human expert rating (factuality, comprehension, reasoning, harm, bias); compares PaLM/Flan-PaLM (multiple scales) and Med-PaLM against prior SOTA · best: Med-PaLM / Flan-PaLM (67.6% on MedQA)
- **Summary:** Introduces MultiMedQA, a benchmark aggregating six medical QA datasets (MedQA, MedMCQA, PubMedQA, MMLU clinical topics, LiveQA, MedicationQA) plus the new HealthSearchQA, and Med-PaLM/Flan-PaLM. Flan-PaLM reaches 67.6% on MedQA (USMLE-style), and instruction prompt tuning yields Med-PaLM. Its lasting contribution is a multi-axis human evaluation rubric (factuality, comprehension, reasoning, harm, bias) that lets clinicians and models be compared on the same open-ended answers, moving medical LLM evaluation beyond multiple-choice accuracy.

### Performance of ChatGPT on USMLE: Potential for AI-Assisted Medical Education Using Large Language Models (2023)

- **Authors:** Tiffany H. Kung et al.
- **Venue:** PLOS Digital Health (PLOS) · `10.1371/journal.pdig.0000198`
- **Citations:** 3,499 citations · 125 influential
- **URL:** https://journals.plos.org/digitalhealth/article?id=10.1371/journal.pdig.0000198 · [S2](https://www.semanticscholar.org/paper/cf1f26e7cbed3958b3c2870656568c299fece6e3)
- **Task types:** USMLE exam QA; medical reasoning explanation; medical education
- **Methods / metrics:** exam accuracy; answer concordance scoring; insight/explanation qualitative rating
- **Summary:** Early influential evaluation showing ChatGPT performs at or near the 60% USMLE passing threshold across Steps 1, 2CK, and 3 without specialized training, with concordant, plausible reasoning. Beyond accuracy, it scores answer explanation quality and concordance, establishing a widely cited methodology for judging medical exam competence and reasoning transparency of general-purpose LLMs.

### What Disease Does This Patient Have? A Large-Scale Open Domain Question Answering Dataset from Medical Exams (MedQA) (2021)

- **Authors:** Di Jin et al.
- **Venue:** Applied Sciences (MDPI); dataset preprint arXiv:2009.13081 · `arXiv:2009.13081 / 10.3390/app11146421`
- **Citations:** 1,877 citations · 325 influential
- **URL:** https://arxiv.org/abs/2009.13081 · [S2](https://www.semanticscholar.org/paper/fc97c3f375c7228a1df7caa5c0ce5d2a6a171bd7)
- **Task types:** open-domain medical QA; USMLE MCQA; multilingual medical QA; retrieval-based QA
- **Methods / metrics:** MedQA benchmark; accuracy; document retrieval + reader baselines; IR-ES / max-pooling baselines
- **Summary:** Introduces MedQA, the foundational open-domain medical exam QA dataset with 61,097 questions drawn from US (USMLE), Mainland China, and Taiwan medical licensing exams across three languages. Provides both free-text retrieval and multiple-choice settings with a large document collection for retrieval. MedQA (US/USMLE split) has become the de facto benchmark for reporting and comparing medical LLM accuracy.

### PubMedQA: A Dataset for Biomedical Research Question Answering (2019)

- **Authors:** Qiao Jin, Bhuwan Dhingra, Zhengping Liu, William W. Cohen, Xinghua Lu
- **Venue:** EMNLP-IJCNLP 2019 (ACL Anthology) · `10.18653/v1/D19-1259 / arXiv:1909.06146`
- **Citations:** 1,760 citations · 226 influential
- **URL:** https://aclanthology.org/D19-1259/ · [S2](https://www.semanticscholar.org/paper/0c3c4c88c7b07596221ac640c7b7102686e3eae3)
- **Task types:** biomedical research QA; yes/no/maybe classification; reasoning over abstracts
- **Methods / metrics:** PubMedQA benchmark; accuracy / macro-F1; human-performance baseline; fine-tuned BioBERT baselines
- **Summary:** Introduces PubMedQA, a yes/no/maybe biomedical QA dataset built from PubMed abstracts (1k expert-labeled, 61.2k unlabeled, 211.3k generated) requiring reasoning over quantitative research findings. Best model reaches 68.1% vs 78.0% single-human accuracy. A staple component of medical LLM benchmark suites for evaluating evidence-grounded reasoning and factual consistency.

### Capabilities of GPT-4 on Medical Challenge Problems (2023)

- **Authors:** Harsha Nori et al.
- **Venue:** arXiv preprint (Microsoft Research / OpenAI) · `arXiv:2303.13375`
- **Citations:** 1,311 citations · 88 influential
- **URL:** https://arxiv.org/abs/2303.13375 · [S2](https://www.semanticscholar.org/paper/348a1efa54376fa39053e5e25d52bd0eb6a0ba68)
- **Task types:** USMLE exam QA; medical MCQA; calibration analysis
- **Methods / metrics:** exam accuracy; GPT-4 vs GPT-3.5 vs Med-PaLM comparison; probability calibration; prompt-strategy ablation
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: GPT-4; GPT-3.5; Med-PaLM; Flan-PaLM · strategy: Exam/benchmark accuracy plus probability-calibration analysis; head-to-head GPT-4 vs GPT-3.5 vs fine-tuned Med-PaLM/Flan-PaLM · best: GPT-4 (~86% USMLE)
- **Summary:** Systematic evaluation of GPT-4 (without domain fine-tuning) on USMLE self-assessment and sample exams plus the MultiMedQA benchmark suite. Zero-shot GPT-4 scores ~86% on USMLE, exceeding the passing threshold by ~20 points and outperforming GPT-3.5 and the fine-tuned Flan-PaLM/Med-PaLM. The paper also probes calibration, prompt sensitivity, and failure modes, providing a reference head-to-head comparison of general-purpose vs medically fine-tuned models on standardized medical exams.

### Toward Expert-Level Medical Question Answering with Large Language Models (Med-PaLM 2) (2025)

- **Authors:** Karan Singhal et al.
- **Venue:** Nature Medicine (Springer Nature) · `arXiv:2305.09617 / 10.1038/s41591-024-03423-7`
- **Citations:** 796 citations · 69 influential
- **URL:** https://arxiv.org/abs/2305.09617 · [S2](https://www.semanticscholar.org/paper/ea72fb2a0d340f9d14fbcf300cd5f5fbbe1050bb)
- **Task types:** medical QA; USMLE MCQA; adversarial long-form QA; consumer health QA
- **Methods / metrics:** ensemble refinement prompting; pairwise human ranking; MedQA/MedMCQA/PubMedQA accuracy; adversarial safety evaluation
- **Summary:** Presents Med-PaLM 2, which reaches 86.5% on MedQA (USMLE) via base model improvements, medical-domain fine-tuning, and ensemble refinement prompting. Beyond accuracy, it introduces new adversarial long-form question sets and multi-dimensional physician and lay-rater pairwise evaluations, showing Med-PaLM 2 answers are preferred over physician answers on several axes. A key methodological reference for expert-level comparison and rubric-based long-form clinical answer scoring.

### Towards Expert-Level Medical Question Answering with Large Language Models (2023)

- **Authors:** Karan Singhal, Tao Tu, Juraj Gottweis, Rory Sayres, Ellery Wulczyn, Le Hou, Kevin Clark, Stephen Pfohl, et al.
- **Venue:** arXiv preprint; published in Nature Medicine (2025) · `arXiv:2305.09617`
- **Citations:** 796 citations · 69 influential
- **URL:** https://arxiv.org/abs/2305.09617 · [S2](https://www.semanticscholar.org/paper/ea72fb2a0d340f9d14fbcf300cd5f5fbbe1050bb)
- **Task types:** medical QA; USMLE-style multiple choice; long-form answer generation
- **Methods / metrics:** accuracy; human physician pairwise preference; statistical significance (p<0.001)
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: Med-PaLM 2; Med-PaLM; GPT-4; Flan-PaLM · strategy: Multiple-choice accuracy plus blinded physician pairwise preference ranking with significance testing; Med-PaLM 2 compared against Med-PaLM, GPT-4 and Flan-PaLM. · best: Med-PaLM 2
- **Summary:** Presents Med-PaLM 2 and benchmarks it against Med-PaLM, GPT-4 and Flan-PaLM on MedQA, MedMCQA, PubMedQA and MMLU clinical topics. Med-PaLM 2 reaches 86.5% on MedQA (a >19% gain over Med-PaLM) and, in a human evaluation over 1,066 consumer questions, physicians preferred its answers to physician-written ones on eight of nine axes (p<0.001).

### Adapted Large Language Models Can Outperform Medical Experts in Clinical Text Summarization (2024)

- **Authors:** Dave Van Veen, Cara Van Uden, Louis Blankemeier, Jean-Benoit Delbrouck, Asad Aali, Christian Bluethgen, Anuj Pareek, Malgorzata Polacin, Eduardo Pontes Reis, Anna Seehofnerova, Nidhi Rohatgi, Poonam Hosamani, William Collins, Neera Ahuja, Curtis P. Langlotz, Jason Hom, Sergios Gatidis, John Pauly, Akshay S. Chaudhari
- **Venue:** Nature Medicine · `arXiv:2309.07430`
- **Citations:** 785 citations · 27 influential
- **URL:** https://arxiv.org/abs/2309.07430 · [S2](https://www.semanticscholar.org/paper/007c3d9b8dab341d2c77c4ee764fd921f7f14956)
- **Task types:** summarization; clinical text
- **Methods / metrics:** BLEU/ROUGE/BERTScore; MEDCON; physician reader study
- **⚑ Empirical multi-LLM comparison** — 8 models · compared: GPT-3.5; GPT-4; FLAN-T5; FLAN-UL2; Llama-2; Vicuna; Alpaca; Med-PaLM-class · strategy: Syntactic/semantic/conceptual NLP metrics plus clinical reader study with 10 physicians scoring completeness, correctness, conciseness; head-to-head vs expert summaries. · best: GPT-4 (adapted, in-context)
- **Summary:** Adapts and compares eight LLMs across four clinical summarization tasks (radiology reports, patient questions, progress notes, doctor-patient dialogue) using both NLP metrics and a ten-physician reader study. Best adapted models match or exceed human expert summaries on completeness, correctness, and conciseness (equivalent 45% / superior 36%). Multiple models are ranked quantitatively.

### MedMCQA: A Large-Scale Multi-Subject Multi-Choice Dataset for Medical Domain Question Answering (2022)

- **Authors:** Ankit Pal, Logesh Kumar Umapathi, Malaikannan Sankarasubbu
- **Venue:** Proceedings of CHIL 2022 (PMLR) · `arXiv:2203.14371`
- **Citations:** 774 citations · 69 influential
- **URL:** https://arxiv.org/abs/2203.14371 · [S2](https://www.semanticscholar.org/paper/741776172685b9717159a9fcd21841461bb33b14)
- **Task types:** medical MCQA; subject-level reasoning; explanation-grounded QA
- **Methods / metrics:** MedMCQA benchmark; accuracy; per-subject/topic breakdown; transformer baselines
- **Summary:** Introduces MedMCQA, a 194k-question multiple-choice benchmark from Indian medical entrance exams (AIIMS, NEET-PG) spanning 2.4k topics and 21 subjects, each with explanations. Its scale and subject breadth make it a core component of medical LLM evaluation suites (part of MultiMedQA) and a standard axis for comparing factual recall and reasoning across models.

### Benchmarking Retrieval-Augmented Generation for Medicine (MIRAGE / MedRAG) (2024)

- **Authors:** Guangzhi Xiong, Qiao Jin, Zhiyong Lu, Aidong Zhang
- **Venue:** ACL 2024 Findings · `arXiv:2402.13178`
- **Citations:** 557 citations · 48 influential
- **URL:** https://arxiv.org/abs/2402.13178 · [S2](https://www.semanticscholar.org/paper/b798cf6af813638fab09a8af6ad0f3df6c241485)
- **Task types:** medical QA; RAG evaluation
- **Methods / metrics:** accuracy
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: GPT-4; GPT-3.5; Mixtral-8x7B; Llama-2-70B-chat; PMC-LLaMA-13B; MEDITRON-70B · strategy: Zero-shot accuracy across 41 corpus x retriever x LLM combinations under a fixed RAG protocol; per-model accuracy comparison plus scaling and context-position analyses; no LLM judge. · best: GPT-4 with MedRAG (highest accuracy backbone)
- **Summary:** MIRAGE aggregates 7,663 questions from five medical QA datasets and systematically evaluates six backbone LLMs across 41 combinations of corpora and retrievers (the MedRAG toolkit), using 1.8T+ prompt tokens. MedRAG improves accuracy by up to 18% over chain-of-thought and surfaces log-linear scaling and lost-in-the-middle effects. A domain case-study RAG comparison across multiple LLMs.

### Can Generalist Foundation Models Outcompete Special-Purpose Tuning? Case Study in Medicine (Medprompt) (2023)

- **Authors:** Harsha Nori, Yin Tat Lee, Sheng Zhang, Dean Carignan, Richard Edgar, Nicolo Fusi, et al.
- **Venue:** arXiv preprint (cs.CL) · `arXiv:2311.16452`
- **Citations:** 537 citations · 59 influential
- **URL:** https://arxiv.org/abs/2311.16452 · [S2](https://www.semanticscholar.org/paper/bde9da9a39a065588d7f4573936731510d6f4f29)
- **Task types:** medical QA; USMLE-style multiple choice
- **Methods / metrics:** accuracy; error-rate reduction
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: GPT-4 + Medprompt; Med-PaLM 2; BioGPT · strategy: Multiple-choice accuracy across the nine MultiMedQA datasets comparing prompt-engineered GPT-4 (Medprompt) against specialist models Med-PaLM 2 and BioGPT. · best: GPT-4 with Medprompt
- **Summary:** Shows that GPT-4 with a general prompting strategy (Medprompt) outperforms specialist medical models such as Med-PaLM 2 and BioGPT across the nine MultiMedQA benchmark datasets. Medprompt achieves SOTA on all nine datasets, cuts MedQA error rate by 27% over prior best specialist methods, and surpasses 90% on MedQA for the first time.

### BioMistral: A Collection of Open-Source Pretrained Large Language Models for Medical Domains (2024)

- **Authors:** Yanis Labrak, Adrien Bazoge, Emmanuel Morin, Pierre-Antoine Gourraud, Mickael Rouvier, Richard Dufour
- **Venue:** Findings of ACL 2024 · `arXiv:2402.10373`
- **Citations:** 507 citations · 58 influential
- **URL:** https://arxiv.org/abs/2402.10373 · [S2](https://www.semanticscholar.org/paper/13b8934468665ecb586f491d7f9f6c460cb095e5)
- **Task types:** medical QA; USMLE-style multiple choice; multilingual QA
- **Methods / metrics:** accuracy; multilingual evaluation
- **⚑ Empirical multi-LLM comparison** — 7 models · compared: BioMistral 7B; Mistral 7B Instruct; MedAlpaca; PMC-LLaMA; MediTron; BioMedGPT-LM; GPT-3.5 · strategy: Multiple-choice accuracy across 10 medical QA tasks in English and 8 languages, comparing BioMistral against open-source medical LLMs and proprietary models. · best: BioMistral (best among open-source medical models)
- **Summary:** Introduces BioMistral (Mistral further pretrained on PubMed Central) and runs the first large-scale multilingual medical benchmark, comparing it against Mistral, MedAlpaca, PMC-LLaMA, MediTron, BioMedGPT and proprietary models on 10 English medical QA tasks translated into 8 languages. BioMistral shows superior performance to existing open-source medical models and competitive results against proprietary counterparts.

### MedAlpaca -- An Open-Source Collection of Medical Conversational AI Models and Training Data (2023)

- **Authors:** Tianyu Han, Lisa C. Adams, Jens-Michalis Papaioannou, Paul Grundmann, Tom Oberhauser, Alexei Figueroa, Alexander Löser, Daniel Truhn, Keno K. Bressem
- **Venue:** arXiv preprint (cs.CL) · `arXiv:2304.08247`
- **Citations:** 461 citations · 54 influential
- **URL:** https://arxiv.org/abs/2304.08247 · [S2](https://www.semanticscholar.org/paper/90e41626b8c78600da70c4350c67c3a10525cb37)
- **Task types:** medical QA; USMLE-style multiple choice; conversational medical QA
- **Methods / metrics:** accuracy
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: MedAlpaca 7B; MedAlpaca 13B; LLaMA; Alpaca / ChatGLM baselines · strategy: Multiple-choice accuracy on USMLE-style exams comparing MedAlpaca fine-tuned variants against base LLaMA/Alpaca models and fine-tuning configurations. · best: MedAlpaca (fine-tuned variant)
- **Summary:** Introduces MedAlpaca medical conversational models and benchmarks fine-tuned variants against base LLaMA and Alpaca on USMLE-style medical exam questions. Compares multiple model sizes and fine-tuning/LoRA configurations, reporting accuracy on the medical licensing examinations that certify physicians.

### Capabilities of Gemini Models in Medicine (Med-Gemini) (2024)

- **Authors:** Khaled Saab et al.
- **Venue:** arXiv preprint (Google Research / DeepMind) · `arXiv:2404.18416`
- **Citations:** 401 citations · 30 influential
- **URL:** https://arxiv.org/abs/2404.18416 · [S2](https://www.semanticscholar.org/paper/6d227a30452f773cea678fa8872ed43566c4f394)
- **Task types:** medical MCQA; multimodal medical QA; long-context clinical reasoning; medical dialogue
- **Methods / metrics:** MedQA/MultiMedQA accuracy; uncertainty-guided web search; self-training with search; GPT-4 head-to-head comparison; multimodal benchmark suite
- **⚑ Empirical multi-LLM comparison** — 3 models · compared: Med-Gemini; GPT-4; GPT-4V · strategy: Accuracy across 14 benchmarks (text/multimodal/long-context) with new SOTA on 10; direct head-to-head against the GPT-4 model family on every comparable benchmark · best: Med-Gemini (91.1% MedQA)
- **Summary:** Introduces Med-Gemini, a family of medically specialized multimodal, long-context models with self-training and web-search integration. Reports state-of-the-art on 10 of 14 medical benchmarks spanning text, multimodal, and long-context tasks and surpasses the GPT-4 family on every directly comparable benchmark, including a relabeled MedQA. Notable for uncertainty-guided search and for benchmarking long-context and multimodal clinical reasoning, not just MCQA.

### Capabilities of Gemini Models in Medicine (2024)

- **Authors:** Khaled Saab, Tao Tu, Wei-Hung Weng, et al. (Google/DeepMind)
- **Venue:** arXiv preprint (cs.AI) · `arXiv:2404.18416`
- **Citations:** 401 citations · 30 influential
- **URL:** https://arxiv.org/abs/2404.18416 · [S2](https://www.semanticscholar.org/paper/6d227a30452f773cea678fa8872ed43566c4f394)
- **Task types:** medical QA; multimodal medical VQA; long-context clinical tasks
- **Methods / metrics:** accuracy; relative improvement margin
- **⚑ Empirical multi-LLM comparison** — 4 models · compared: Med-Gemini; Gemini 1.0/1.5; GPT-4; GPT-4V · strategy: Accuracy across 14 text and multimodal medical benchmarks with an uncertainty-guided search inference strategy, compared head-to-head against GPT-4 and GPT-4V. · best: Med-Gemini
- **Summary:** Evaluates Med-Gemini variants against the GPT-4 family (including GPT-4V) across 14 medical benchmarks spanning text, multimodal, and long-context tasks. Med-Gemini reaches 91.1% on MedQA (USMLE) via uncertainty-guided search, sets new SOTA on 10 of 14 benchmarks, and surpasses GPT-4 on every directly comparable benchmark, beating GPT-4V on multimodal tasks by a 44.5% average relative margin.

### MEDITRON-70B: Scaling Medical Pretraining for Large Language Models (2023)

- **Authors:** Zeming Chen et al.
- **Venue:** arXiv preprint (EPFL LiGHT) · `arXiv:2311.16079`
- **Citations:** 396 citations · 46 influential
- **URL:** https://arxiv.org/abs/2311.16079 · [S2](https://www.semanticscholar.org/paper/ff5f0c5b6905a8c4b361a625b450e9ab417fa854)
- **Task types:** medical MCQA; USMLE-style QA; biomedical QA
- **Methods / metrics:** MedQA/MedMCQA/PubMedQA/MMLU accuracy; chain-of-thought; self-consistency; domain continued pretraining
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: MEDITRON-70B; MEDITRON-7B; Llama-2; GPT-3.5; GPT-4; Med-PaLM / Med-PaLM-2 · strategy: Accuracy on four medical benchmarks with chain-of-thought and self-consistency inference; MEDITRON variants compared against open baselines and closed models (GPT-3.5, GPT-4, Med-PaLM/2) · best: MEDITRON-70B (among open models)
- **Summary:** Releases MEDITRON-7B/70B, open medical LLMs continued-pretrained on a curated medical corpus (PubMed, guidelines). On MedQA, MedMCQA, PubMedQA, and MMLU-clinical, MEDITRON-70B narrows the gap to GPT-3.5/Med-PaLM and beats prior open models, with careful reporting of chain-of-thought and self-consistency inference. A widely used open baseline for reproducible medical LLM accuracy comparisons.

### A Framework to Assess Clinical Safety and Hallucination Rates of LLMs for Medical Text Summarisation (2025)

- **Authors:** See publication (medRxiv / npj Digital Medicine)
- **Venue:** npj Digital Medicine (Springer Nature); preprint medRxiv 2024 · `10.1038/s41746-025-01670-7`
- **Citations:** 335 citations · 22 influential
- **URL:** https://www.nature.com/articles/s41746-025-01670-7 · [S2](https://www.semanticscholar.org/paper/0e3a5ac3b892d520ebcfebd08c0768980943117a)
- **Task types:** medical text summarization; clinical safety evaluation; hallucination detection
- **Methods / metrics:** hallucination/omission taxonomy; clinician harm rating; error categorization; human evaluation protocol
- **Summary:** Proposes a clinician-in-the-loop framework for evaluating clinical safety and hallucination rates when LLMs summarize medical text (e.g., patient records), categorizing errors by type and potential clinical harm. Provides a structured, reproducible evaluation protocol for open-ended clinical generation where reference-based metrics fail, quantifying how often and how severely models fabricate or omit clinically salient content.

### Med-HALT: Medical Domain Hallucination Test for Large Language Models (2023)

- **Authors:** Ankit Pal, Logesh Kumar Umapathi, Malaikannan Sankarasubbu
- **Venue:** CoNLL 2023 (EMNLP) · `arXiv:2307.15343`
- **Citations:** 276 citations · 16 influential
- **URL:** https://arxiv.org/abs/2307.15343 · [S2](https://www.semanticscholar.org/paper/3b0792f6d7f6aa6aadd316e73943116afef2979b)
- **Task types:** medical QA; hallucination detection
- **Methods / metrics:** accuracy; pointwise scoring with penalty; hallucination rate
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: Text-Davinci (GPT-3); GPT-3.5; LLaMa-2; MPT; Falcon · strategy: Reasoning and memory hallucination test suites with a pointwise scoring scheme, comparing five LLMs on medical exam-derived questions. · best: GPT-3.5 (strongest of the five; not dominant)
- **Summary:** Introduces Med-HALT, reasoning- and memory-based hallucination tests built from medical exams across multiple countries, and evaluates five LLMs: Text-Davinci, GPT-3.5, LLaMa-2, MPT and Falcon. Reports significant performance differences across models in problem-solving and information-retrieval reliability, quantifying hallucination-prone behavior.

### Use of GPT-4 to Diagnose Complex Clinical Cases (2023)

- **Authors:** Alexander V. Eriksen et al.
- **Venue:** NEJM AI (Massachusetts Medical Society) · `10.1056/AIp2300031`
- **Citations:** 179 citations · 12 influential
- **URL:** https://ai.nejm.org/doi/full/10.1056/AIp2300031 · [S2](https://www.semanticscholar.org/paper/4032c638728e155bb2d5d5b676ce7c99ccbf7db9)
- **Task types:** diagnostic reasoning; complex clinical case diagnosis; differential diagnosis
- **Methods / metrics:** top-diagnosis accuracy; comparison vs simulated human reader distribution; percentile ranking
- **Summary:** Evaluates GPT-4 on 38 complex NEJM clinical case challenges, finding it correctly diagnoses 57% of cases and outperforms 99.98% of simulated human readers derived from online answer distributions. Provides a rigorous real-world diagnostic-accuracy comparison against a human reader baseline, illustrating both diagnostic promise and the methodological care needed when benchmarking LLMs against clinicians on open-ended cases.

### CMB: A Comprehensive Medical Benchmark in Chinese (2023)

- **Authors:** Xidong Wang, Guiming Hardy Chen, Dingjie Song, Zhiyi Zhang, Zhihong Chen, Qingying Xiao, Feng Jiang, Jianquan Li, Xiang Wan, Benyou Wang, Haizhou Li
- **Venue:** NAACL 2024 (Main Conference) · `arXiv:2308.08833`
- **Citations:** 168 citations · 11 influential
- **URL:** https://arxiv.org/abs/2308.08833 · [S2](https://www.semanticscholar.org/paper/5df24ed6fdf10d1e92885687abce7bd5e56f3f85)
- **Task types:** medical QA; clinical case reasoning; Chinese-language
- **Methods / metrics:** accuracy; expert evaluation; LLM-as-judge scoring
- **⚑ Empirical multi-LLM comparison** — 8 models · compared: GPT-4; ChatGPT; Baichuan; ChatGLM; HuatuoGPT; Chinese medical LLMs; general Chinese LLMs · strategy: Multiple-choice accuracy on CMB-Exam plus expert and automatic (LLM-judge) scoring on clinical cases, comparing general, Chinese, and medical LLMs. · best: GPT-4
- **Summary:** Builds a localized Chinese medical benchmark (CMB-Exam and CMB-Clin, including traditional Chinese medicine) and evaluates several prominent LLMs including ChatGPT, GPT-4, dedicated Chinese general LLMs, and Chinese medical LLMs. Reports accuracy on exam questions and expert/LLM-judged clinical case scores, with GPT-4 leading among the compared models.

### Benchmarking Large Language Models on CMExam -- A Comprehensive Chinese Medical Exam Dataset (2023)

- **Authors:** Junling Liu, Peilin Zhou, Yining Hua, Dading Chong, Zhongyu Tian, Andrew Liu, Helin Wang, Chenyu You, Zhenhua Guo, Lei Zhu, Michael Lingzhi Li
- **Venue:** NeurIPS 2023 (Datasets and Benchmarks Track) · `arXiv:2306.03030`
- **Citations:** 144 citations · 10 influential
- **URL:** https://arxiv.org/abs/2306.03030 · [S2](https://www.semanticscholar.org/paper/4b4ee637ef5107299212479c37a6594db5a72227)
- **Task types:** medical QA; explanation generation; Chinese-language
- **Methods / metrics:** accuracy; weighted F1; human expert evaluation of explanations
- **⚑ Empirical multi-LLM comparison** — 7 models · compared: GPT-4; ChatGPT (GPT-3.5); LLaMA; Vicuna; Alpaca; Huatuo; ChatGLM · strategy: Multiple-choice accuracy and weighted F1 across representative LLMs on 60K+ exam questions, with medical-professional evaluation of generated explanations and a human accuracy baseline. · best: GPT-4
- **Summary:** Introduces CMExam (60K+ questions from the Chinese National Medical Licensing Examination) and benchmarks representative LLMs on multiple-choice accuracy and explanation generation. GPT-4 achieves the highest accuracy at 61.6% (weighted F1 0.617), still below the 71.6% human baseline, revealing substantial LLM-vs-clinician gaps.

### MedHELM: Holistic Evaluation of Large Language Models for Medical Tasks (2025)

- **Authors:** Suhana Bedi et al.
- **Venue:** arXiv preprint; Nature Medicine (Springer Nature) · `arXiv:2505.23802 / 10.1038/s41591-025-04151-2`
- **Citations:** 70 citations · 6 influential
- **URL:** https://arxiv.org/abs/2505.23802 · [S2](https://www.semanticscholar.org/paper/055f837d7b9cb855708cae3fee9104feb46d0dcb)
- **Task types:** clinical note generation; clinical decision support; patient communication; medical research assistance; administrative workflow
- **Methods / metrics:** MedHELM benchmark; LLM-as-jury scoring; win-rate; cost-normalized comparison; clinician-validated taxonomy
- **⚑ Empirical multi-LLM comparison** — 9 models · compared: DeepSeek R1; o3-mini; Claude 3.5 Sonnet; GPT-4 family frontier models · strategy: 35-benchmark holistic evaluation of 9 frontier LLMs using ground-truth metrics plus a validated LLM-jury; reports win-rates, normalized accuracy per category, and cost-performance trade-offs · best: DeepSeek R1 (66% win-rate)
- **Summary:** A clinician-validated holistic benchmark spanning 5 categories, 22 subcategories, and 121 real-world clinical tasks (many on real EHR data), with 35 evaluations built with 29 clinicians. Evaluates 9 frontier models using both ground-truth metrics and a validated LLM-jury, reporting win-rates and cost trade-offs. Extends the HELM philosophy to medicine, addressing the gap between exam accuracy and practical clinical utility.

### Gemini Goes to Med School: Exploring the Capabilities of Multimodal LLMs on Medical Challenge Problems & Hallucinations (2024)

- **Authors:** Ankit Pal, Malaikannan Sankarasubbu
- **Venue:** arXiv preprint (cs.CL) · `arXiv:2402.07023`
- **Citations:** 63 citations · 0 influential
- **URL:** https://arxiv.org/abs/2402.07023 · [S2](https://www.semanticscholar.org/paper/2f231367b55f30186467158c644a9890c498e4cf)
- **Task types:** medical QA; multimodal medical VQA; hallucination detection
- **Methods / metrics:** accuracy; hallucination susceptibility analysis
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: Gemini Pro; Med-PaLM 2; GPT-4; GPT-4V; open-source medical LLMs · strategy: Accuracy on medical reasoning and visual QA plus hallucination/overconfidence analysis, comparing Gemini against Med-PaLM 2, GPT-4 and GPT-4V. · best: GPT-4 / GPT-4V (Med-PaLM 2 best on reasoning)
- **Summary:** Empirically compares Google Gemini against Med-PaLM 2, GPT-4, GPT-4V and open-source LLMs on medical reasoning, medical visual QA, and hallucination detection. Gemini lags Med-PaLM 2 and GPT-4 on diagnostic reasoning and scores 61.45% on medical VQA versus GPT-4V's 88%, while showing high susceptibility to hallucinations and overconfidence.

### MedBench: A Large-Scale Chinese Benchmark for Evaluating Medical Large Language Models (2023)

- **Authors:** Yan Cai, Linlin Wang, Ye Wang, Gerard de Melo, Ya Zhang, Yanfeng Wang, Liang He
- **Venue:** AAAI 2024 · `arXiv:2312.12806`
- **Citations:** 48 citations · 2 influential
- **URL:** https://arxiv.org/abs/2312.12806 · [S2](https://www.semanticscholar.org/paper/6887f052c78f016fbf9cbb0c4f887e5c14069651)
- **Task types:** medical QA; clinical case reasoning; Chinese-language
- **Methods / metrics:** accuracy
- **⚑ Empirical multi-LLM comparison** — 8 models · compared: GPT-4; ChatGPT; Chinese medical LLMs; general-domain Chinese LLMs (Baichuan, ChatGLM, etc.) · strategy: Accuracy across 40k+ questions from four exam/clinical categories, comparing Chinese medical LLMs against general-domain LLMs. · best: General-domain LLM (e.g. GPT-4; outperformed dedicated Chinese medical LLMs)
- **Summary:** Constructs MedBench, a 40,041-question Chinese medical benchmark spanning licensing, residency, and in-charge qualification exams plus real clinical cases, and evaluates both Chinese medical LLMs and general-domain LLMs. Finds that dedicated Chinese medical LLMs underperform on the benchmark while some general-purpose models show surprisingly strong medical knowledge.

### MedAgentBench: A Realistic Virtual EHR Environment to Benchmark Medical LLM Agents (2025)

- **Authors:** Yixing Jiang et al.
- **Venue:** arXiv preprint (Stanford University) · `arXiv:2501.14654`
- **Citations:** 46 citations · 3 influential
- **URL:** https://arxiv.org/abs/2501.14654 · [S2](https://www.semanticscholar.org/paper/6abbebb1516f705feb2723df5b9d4d37a9220d63)
- **Task types:** medical LLM agents; EHR interaction; multi-step clinical task execution; tool use / FHIR queries
- **Methods / metrics:** task success rate; agentic evaluation; FHIR interactive environment; per-category success breakdown
- **⚑ Empirical multi-LLM comparison** — compared: Claude 3.5 Sonnet v2 · strategy: Task success rate across 300 physician-written tasks in a FHIR interactive environment, with per-category breakdown and cross-model variation reported · best: Claude 3.5 Sonnet v2 (69.67% success)
- **Summary:** Introduces a FHIR-compliant interactive virtual-EHR benchmark with 300 physician-written tasks across 10 categories over 100 realistic patient profiles (700k+ data elements), shifting evaluation from static QA to agentic, tool-using clinical workflows. Best model (Claude 3.5 Sonnet v2) reaches only 69.67% task success, exposing large gaps in multi-step planning and EHR interaction. A key methodology for comparing LLMs on operational clinical tasks.

### MEDIC: Comprehensive Evaluation of Leading Indicators for LLM Safety and Utility in Clinical Applications (2024)

- **Authors:** Praveen K. Kanithi et al.
- **Venue:** arXiv preprint (M42 / Cerebras) · `arXiv:2409.07314`
- **Citations:** 28 citations · 4 influential
- **URL:** https://arxiv.org/abs/2409.07314 · [S2](https://www.semanticscholar.org/paper/38ca73bbaa08295f97ef0b64354ac6a759016cbd)
- **Task types:** clinical safety evaluation; medical reasoning; clinical summarization; bias/ethics assessment; clinical note QA
- **Methods / metrics:** Cross-Examination Framework; hallucination rate; information fidelity; multi-axis scoring; refusal vs error-detection safety
- **⚑ Empirical multi-LLM comparison** — strategy: Multi-axis MEDIC framework scoring across a heterogeneous task suite with a reference-free Cross-Examination Framework quantifying hallucination/information fidelity; public leaderboard comparing multiple LLMs (no single architecture dominates)
- **Summary:** Proposes MEDIC, a multi-dimensional evaluation framework assessing LLMs across medical reasoning, ethics/bias, data & language understanding, in-context learning, and clinical safety. Introduces a reference-free Cross-Examination Framework to quantify information fidelity and hallucination rates, and surfaces a knowledge-execution gap and passive-vs-active safety divergence. Argues that single benchmark accuracy is insufficient for clinical deployment decisions.

### CLIMB: A Benchmark of Clinical Bias in Large Language Models (2024)

- **Authors:** Yubo Zhang et al.
- **Venue:** arXiv preprint · `arXiv:2407.05250`
- **Citations:** 10 citations · 1 influential
- **URL:** https://arxiv.org/abs/2407.05250 · [S2](https://www.semanticscholar.org/paper/b87fb8913486bb7ef2d9c2b5b0dfcb96116d5f10)
- **Task types:** clinical bias evaluation; diagnostic prediction; demographic fairness; clinical NLP
- **Methods / metrics:** intrinsic/extrinsic bias metrics; AssocMAD; counterfactual demographic perturbation; disparity measurement
- **⚑ Empirical multi-LLM comparison** — 5 models · compared: Mistral; LLaMA; medically-adapted Mistral/LLaMA variants · strategy: Intrinsic bias via novel AssocMAD metric measuring disparities across demographic groups; extrinsic bias via counterfactual demographic perturbation on diagnosis prediction; disparity/fairness measurement across models
- **Summary:** Introduces CLIMB, a benchmark for systematically measuring both intrinsic (association-level) and extrinsic (task-level) clinical bias in LLMs across demographic groups in medical contexts. Proposes new bias metrics (e.g., AssocMAD) and evaluates how demographic perturbations shift diagnostic and management outputs. Provides an evaluation methodology focused on fairness/equity rather than raw accuracy, complementary to exam benchmarks.

### Me-LLaMA: Foundation Large Language Models for Medical Applications (2024)

- **Authors:** Qianqian Xie, Qingyu Chen, Aokun Chen, Cheng Peng, Yan Hu, et al.
- **Venue:** arXiv preprint (cs.CL) · `arXiv:2402.12749`
- **Citations:** 4 citations · 0 influential
- **URL:** https://arxiv.org/abs/2402.12749 · [S2](https://www.semanticscholar.org/paper/1f33eb15b64cc0a8b1a3fe319b9d8bf959b4b35e)
- **Task types:** medical QA; clinical NLP tasks; clinical case reasoning
- **Methods / metrics:** accuracy; F1; task-specific metrics
- **⚑ Empirical multi-LLM comparison** — 6 models · compared: Me-LLaMA 13B; Me-LLaMA 70B; LLaMA-2; ChatGPT; GPT-4; PMC-LLaMA / other medical LLMs · strategy: Zero-shot and supervised evaluation across 6 task types / 12 datasets comparing Me-LLaMA variants against LLaMA, ChatGPT, GPT-4 and other medical LLMs. · best: Me-LLaMA (task-dependent; competitive with GPT-4)
- **Summary:** Introduces Me-LLaMA (13B and 70B) medical foundation models and evaluates them against LLaMA, ChatGPT, GPT-4 and other open-source medical LLMs across six medical text tasks over 12 datasets plus complex clinical case diagnosis. With task-specific tuning Me-LLaMA surpasses ChatGPT on 7 of 8 datasets and GPT-4 on 5 of 8, matching them on clinical case reasoning.

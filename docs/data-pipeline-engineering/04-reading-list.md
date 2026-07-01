# 04 — Annotated Reading List

A curated bibliography for designing and building staged batch data pipelines
and statistical-analysis software. Every entry was verified to exist (publisher,
journal, official documentation, or hosting institution) at the time of writing.
Editions and course offerings move — re-verify before citing formally.

**How this list is organized**

- **A. Foundations** — the few resources to read first.
- **B. Books** — data engineering / pipelines, then research-software / stats.
- **C. University courses & open courseware.**
- **D. Online courses / MOOCs.**
- **E. Foundational papers & canonical articles.**
- **F. Architecture patterns & principles.**
- **G. Statistical-method references.**
- **H. Code craftsmanship & maintainability** (SOLID, cohesion/coupling,
  refactoring, technical debt, Python practices) — supports `05`.

Each section opens with a ⭐ **start here** pick.

---

## A. Foundations (read these first)

1. **Designing Data-Intensive Applications** — Martin Kleppmann (O'Reilly; 1st
   2017, 2nd 2025 w/ Chris Riccomini). The canonical text on data-system
   trade-offs, including the definitive treatment of batch vs. stream
   processing and dataflow. Start here for the *why* behind every architectural
   choice. https://www.oreilly.com/library/view/designing-data-intensive-applications/9781098119058/
2. **Fundamentals of Data Engineering** — Joe Reis & Matt Housley (O'Reilly,
   2022). Organizes the field around the data-engineering lifecycle
   (generation → ingestion → transformation → storage → serving) plus
   undercurrents (security, orchestration, governance). Technology-agnostic;
   contrasts batch/stream and ETL/ELT. https://www.oreilly.com/library/view/fundamentals-of-data/9781098108298/
3. **Good Enough Practices in Scientific Computing** — Wilson, Bryan, Cranston,
   Kitzes, Nederbragt & Teal, *PLOS Comp. Biol.* 13(6):e1005510 (2017). The
   pragmatic minimum standard for project organization, data management, and
   reproducible workflow hygiene. https://doi.org/10.1371/journal.pcbi.1005510
4. **Functional Data Engineering** — Maxime Beauchemin (Medium, 2018). The
   canonical articulation of pure, idempotent batch tasks over immutable
   partitions. Short, foundational. https://maximebeauchemin.medium.com/functional-data-engineering-a-modern-paradigm-for-batch-data-processing-2327ec32c42a

---

## B. Books

### B.1 Data engineering, pipelines & ETL/ELT

⭐ Start with Kleppmann and Reis & Housley (§A).

- **97 Things Every Data Engineer Should Know** — ed. Tobias Macey (O'Reilly,
  2021). 97 short practitioner essays on lineage, reliability, "the end of ETL."
  https://www.oreilly.com/library/view/97-things-every/9781492062400/
- **Data Pipelines Pocket Reference** — James Densmore (O'Reilly, 2021).
  Compact, practical primer on building pipelines in the modern stack; batch vs.
  streaming ingestion, build-vs-buy, an end-to-end Python/SQL example.
  https://www.oreilly.com/library/view/data-pipelines-pocket/9781492087823/
- **Data Pipelines with Apache Airflow** — Bas Harenslak & Julian de Ruiter
  (Manning; 1st 2021, 2nd 2025 for Airflow 3). The definitive practical guide to
  DAG-based orchestration: scheduling, dependencies, backfills, productionizing
  batch. https://www.manning.com/books/data-pipelines-with-apache-airflow
- **Analytics Engineering with SQL and dbt** — Rui Pedro Machado & Hélder Russa
  (O'Reilly, 2023). The ELT / transform-in-warehouse paradigm: models,
  materializations, tests, semantic layer.
  https://www.oreilly.com/library/view/analytics-engineering-with/9781098142377/
- **Streaming Systems** — Akidau, Chernyak & Lax (O'Reilly, 2018). Authoritative
  on stream semantics (event vs. processing time, windowing, watermarks,
  triggers, exactly-once) and the unified batch/streaming model. Read when you
  genuinely need streaming. https://www.oreilly.com/library/view/streaming-systems/9781491983867/
- **Spark: The Definitive Guide** — Bill Chambers & Matei Zaharia (O'Reilly,
  2018). The reference for large-scale batch / micro-batch processing.
  https://www.oreilly.com/library/view/spark-the-definitive/9781491912201/
- **Kafka: The Definitive Guide, 2nd ed.** — Shapira, Palino, Sivaram & Petty
  (O'Reilly, 2021). Foundational for event-driven pipelines.
  https://www.oreilly.com/library/view/kafka-the-definitive/9781492043072/
- **The Data Warehouse Toolkit, 3rd ed.** — Ralph Kimball & Margy Ross (Wiley,
  2013). The standard on dimensional modeling (star schemas, fact/dimension
  design, slowly changing dimensions) with chapters on ETL subsystems.
  https://www.wiley.com/en-us/9781118530801
- **Data Management at Scale** — Piethein Strengholt (O'Reilly; 1st 2020, 2nd
  2023). Enterprise architecture blueprints: governance, data mesh/fabric.
  https://www.oreilly.com/library/view/data-management-at/9781098138851/
- **Data Mesh** — Zhamak Dehghani (O'Reilly, 2022). The organizational
  counterpoint to centralized pipelines: decentralized domain ownership,
  data-as-a-product. https://www.thoughtworks.com/en-us/insights/books/data-mesh
- **The Data Engineering Cookbook** — Andreas Kretz (free living document).
  Open compendium of storage, encoding, partitioning, batch vs. stream.
  https://cookbook.learndataengineering.com/

### B.2 Research-software, scientific Python & reproducibility

⭐ Start: **Research Software Engineering with Python** (open access).

- **Research Software Engineering with Python** — Irving, Hertweck, Johnston,
  Ostblom, Wickham & Wilson (CRC Press, 2021; open access). The most directly
  on-target book: the full research-software lifecycle — shell, Git, Make,
  project structure, packaging, testing, provenance, publishing.
  https://third-bit.com/py-rse/
- **The Practice of Reproducible Research** — eds. Kitzes, Turek & Deniz (UC
  Press, 2018; open access). 31 practitioner case studies plus a synthesis and a
  reproducible-project template. http://www.practicereproducibleresearch.org/
- **Software Engineering for Data Scientists** — Catherine Nelson (O'Reilly,
  2024). Bridges data science and SE: OO design, documentation, packaging,
  testing, logging, moving from notebooks to production.
  https://www.oreilly.com/library/view/software-engineering-for/9781098136192/
- **Python for Data Analysis, 3rd ed.** — Wes McKinney (O'Reilly, 2022; open
  access). By pandas' creator; the canonical data-wrangling reference.
  https://wesmckinney.com/book/
- **Effective Pandas: Patterns for Data Manipulation** — Matt Harrison (MetaSnake,
  2021). Idiomatic, readable pandas over ad-hoc scripts.
  https://store.metasnake.com/effective-pandas-book
- **Robust Python** — Patrick Viafore (O'Reilly, 2021). Type hints, user-defined
  types, and testing strategies for safe, maintainable Python.
  https://www.oreilly.com/library/view/robust-python/9781098100650/
- **Effective Computation in Physics** — Scopatz & Huff (O'Reilly, 2015).
  Software-craftsmanship field guide for scientists: Python, shell, version
  control, testing, HDF5, packaging.
  https://www.oreilly.com/library/view/effective-computation-in/9781491901564/
- **High Performance Python, 3rd ed.** — Gorelick & Ozsvald (O'Reilly, 2025).
  Profiling and optimizing numerical/data-heavy Python.
  https://www.oreilly.com/library/view/high-performance-python/9781098165956/
- **A Primer on Scientific Programming with Python, 5th ed.** — Hans Petter
  Langtangen (Springer, 2016). Structuring numerical code; procedural and OO.
  https://link.springer.com/book/10.1007/978-3-662-49887-3
- **Reproducible Research with R and RStudio, 3rd ed.** — Christopher Gandrud
  (CRC Press, 2020). The R-centric reproducible-workflow counterpart.
  https://www.routledge.com/9780367143985
- **Clean Code** — Robert C. Martin (Prentice Hall, 2008). The craftsmanship
  classic; adapt the OO-heavy advice to data idioms.
  https://www.oreilly.com/library/view/clean-code-a/9780136083238/

---

## C. University courses & open courseware

⭐ Start: **UC Berkeley Stat 159/259 — Collaborative and Reproducible Data
Science** (the most on-target for this class of work).

### Reproducible / SE-for-data-science
- **Stat 159/259 — Collaborative and Reproducible Data Science** — UC Berkeley
  (Pérez, Butler, Andrade). Git, shell, testing, automation, code review in the
  Scientific Python/Jupyter ecosystem. https://stat159.berkeley.edu/fall-2025/
- **Principles, Statistical and Computational Tools for Reproducible Data
  Science** — Harvard/HarvardX (Huttenhower, Quackenbush, Trippa, Choirat).
  Provenance, Git, reproducible repositories, dynamic reports.
  https://pll.harvard.edu/course/principles-statistical-and-computational-tools-reproducible-data-science
- **Software Carpentry / Data Carpentry** — The Carpentries (continuously
  maintained). The de-facto research-computing skills curriculum: shell, Git,
  Python, plotting, reproducible analysis. https://software-carpentry.org/lessons/
  · Git: https://swcarpentry.github.io/git-novice/
  · pandas analysis: https://datacarpentry.github.io/python-ecology-lesson/

### Data science lifecycle & engineering
- **Data 100 — Principles and Techniques of Data Science** — UC Berkeley. The
  full lifecycle: cleaning, EDA, inference, prediction, scalable processing.
  https://ds100.org/
- **INFO 258 / DATA 101 — Data Engineering** — UC Berkeley I-School
  (Parameswaran). The most explicitly "data pipelines" course: batch and
  streaming pipelines, scheduling, architecture, governance. https://data101.org/
- **CS109a — Introduction to Data Science** — Harvard SEAS (Protopapas, Rader).
  End-to-end workflow incl. wrangling and reliable data access. http://cs109.org/
- **CME 211 — Software Development for Scientists and Engineers** — Stanford
  (ICME). SE for computational science: complexity, data structures, OO design,
  tooling. http://web.stanford.edu/class/cme211/

### Database & data-intensive systems internals
- **15-445/645 — Intro to Database Systems** — CMU (Andy Pavlo). DBMS internals:
  storage, indexing, transactions, query processing. https://15445.courses.cs.cmu.edu/
- **CS186 — Introduction to Database Systems** — UC Berkeley. Build a relational
  DB; indexing, query processing, concurrency, recovery. https://cs186berkeley.net/
- **6.5830 — Database Systems** — MIT (OCW). Primary-literature course incl.
  streaming and key-value databases. https://ocw.mit.edu/courses/6-5830-database-systems-fall-2023/
- **CS245 — Principles of Data-Intensive Systems** — Stanford (Zaharia, Spark's
  creator; archived). Architecture shared across data-intensive systems.
  https://cs245.stanford.edu/
- **CS246 — Mining Massive Data Sets** — Stanford (Leskovec). MapReduce/Spark for
  parallel algorithms over very large data. https://web.stanford.edu/class/cs246/
- **6.0001 — Introduction to CS and Programming in Python** — MIT (OCW). Beginner
  on-ramp. https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/

---

## D. Online courses / MOOCs

⭐ Free start: **Data Engineering Zoomcamp** (hands-on, end-to-end).

### Data engineering
- **Data Engineering Zoomcamp** — DataTalksClub (free, open-source). 9-week
  hands-on build: Docker/Terraform, orchestration, warehouse, dbt, Spark batch,
  Kafka streaming. https://github.com/DataTalksClub/data-engineering-zoomcamp
- **DeepLearning.AI Data Engineering Professional Certificate** — Coursera (Joe
  Reis & AWS). The lifecycle + undercurrents with AWS labs (Airflow, Spark).
  https://www.coursera.org/professional-certificates/data-engineering
- **IBM Data Engineering Professional Certificate** — Coursera/IBM. 16 courses
  incl. "ETL and Data Pipelines with Shell, Airflow and Kafka."
  https://www.coursera.org/professional-certificates/ibm-data-engineer
- **Google Cloud Cloud Data Engineer** — Coursera/Google. Incl. "Build Streaming
  Data Pipelines" with Dataflow/Pub-Sub/BigQuery.
  https://www.coursera.org/professional-certificates/gcp-data-engineering
- **Data Engineer in Python (Career Track)** — DataCamp. Ingestion, cleaning,
  ETL/ELT, Airflow. https://www.datacamp.com/tracks/data-engineer-in-python
- **Astronomer Academy — Airflow 101** — (free) authoritative orchestrator path.
  https://academy.astronomer.io/path/airflow-101

### Reproducibility, statistics & SE for research
- **Reproducible Research** — Johns Hopkins (Coursera; Peng, Leek, Caffo). The
  canonical MOOC: literate programming, organizing an analysis, checklists.
  https://www.coursera.org/learn/reproducible-research/
- **Statistical Inference** — Johns Hopkins (Coursera). CIs, hypothesis testing,
  p-values, power, multiple testing, resampling.
  https://www.coursera.org/learn/statistical-inference
- **Statistics with Python (Specialization)** — Univ. of Michigan (Coursera).
  EDA, inference, modeling with statsmodels/pandas in notebooks.
  https://www.coursera.org/specializations/statistics-with-python
- **Software Engineering Principles in Python** — DataCamp. Modularity, OO,
  docs, unit testing, packaging. https://www.datacamp.com/courses/software-engineering-principles-in-python
- **Introduction to Testing in Python** — DataCamp. pytest/unittest, validating
  data pipelines. https://www.datacamp.com/courses/introduction-to-testing-in-python

---

## E. Foundational papers & canonical articles

### Batch, streaming & big-data engines
- **MapReduce: Simplified Data Processing on Large Clusters** — Dean & Ghemawat,
  OSDI 2004. The foundational batch abstraction.
  https://research.google/pubs/mapreduce-simplified-data-processing-on-large-clusters/
- **The Dataflow Model** — Akidau, Bradshaw, Chambers et al., PVLDB 2015. The
  unified bounded/unbounded model (windowing, watermarks, triggers) behind Beam.
  https://research.google/pubs/the-dataflow-model/
- **FlumeJava: Easy, Efficient Data-Parallel Pipelines** — Chambers, Raniwala,
  Perry et al., PLDI 2010. Deferred-execution pipeline API over an optimized
  dataflow graph. https://research.google/pubs/flumejava-easy-efficient-data-parallel-pipelines/
- **Apache Beam Programming Guide** — ASF (official). The unified batch+streaming
  model in practice. https://beam.apache.org/documentation/programming-guide/

### Architecture evolution & the discipline
- **How to beat the CAP theorem** (Lambda Architecture) — Nathan Marz (2011).
  https://nathanmarz.com/blog/how-to-beat-the-cap-theorem.html
- **Questioning the Lambda Architecture** (Kappa) — Jay Kreps, O'Reilly Radar
  (2014). https://www.oreilly.com/radar/questioning-the-lambda-architecture/
- **Functional Data Engineering** — Maxime Beauchemin (2018). Idempotency in
  batch. https://maximebeauchemin.medium.com/functional-data-engineering-a-modern-paradigm-for-batch-data-processing-2327ec32c42a
- **The Rise of the Data Engineer** — Maxime Beauchemin (2017). The discipline's
  emergence. https://www.freecodecamp.org/news/the-rise-of-the-data-engineer-91be18f1e603/
- **Airflow: a workflow management platform** — Maxime Beauchemin (2015). The
  original Airflow announcement. https://medium.com/airbnb-engineering/airflow-a-workflow-management-platform-46318b977fd8

### Pipelines as software (anti-patterns & production)
- **Hidden Technical Debt in Machine Learning Systems** — Sculley, Holt, Golovin
  et al., NeurIPS 2015. Names glue-code / pipeline-jungle anti-patterns; the
  seminal motivation for disciplined pipeline architecture.
  https://papers.nips.cc/paper/5656-hidden-technical-debt-in-machine-learning-systems
- **TFX: A TensorFlow-Based Production-Scale ML Platform** — Baylor et al., KDD
  2017. Reference architecture for end-to-end ML pipelines.
  https://www.kdd.org/kdd2017/papers/view/tfx-a-tensorflow-based-production-scale-machine-learning-platform
- **Exactly-Once Semantics Are Possible: Here's How Kafka Does It** — Narkhede &
  Wang, Confluent (2017). Idempotency/exactly-once reference.
  https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/

### Storage & read/write modeling
- **Data Lake** — Martin Fowler (2015). Schema-on-read; the "data swamp" risk.
  https://martinfowler.com/bliki/DataLake.html
- **Event Sourcing** — Martin Fowler (2005). State as an ordered log of immutable
  events; replayability. https://martinfowler.com/eaaDev/EventSourcing.html

---

## F. Architecture patterns & principles

⭐ Start: **POSA1 — "Pipes and Filters"** and **Garlan & Shaw**.

### Pipe-and-filter & architectural styles
- **An Introduction to Software Architecture** — David Garlan & Mary Shaw
  (1993/94; CMU-CS-94-166). Codified architectural *styles*; pipe-and-filter as
  the canonical example. https://userweb.cs.txstate.edu/~rp31/papers/intro_softarch.pdf
- **Pattern-Oriented Software Architecture, Vol. 1 (POSA1)** — Buschmann et al.
  (Wiley, 1996). Documents the "Pipes and Filters" pattern in full.
- **Software Architecture: Perspectives on an Emerging Discipline** — Shaw &
  Garlan (Prentice Hall, 1996). Components, connectors, styles as a design
  language. https://dl.acm.org/doi/book/10.5555/231003
- **Enterprise Integration Patterns — "Pipes and Filters"** — Hohpe & Woolf
  (Addison-Wesley, 2003). https://www.enterpriseintegrationpatterns.com/patterns/messaging/PipesAndFilters.html
- **Pipes and Filters pattern** — Azure Architecture Center (Microsoft Learn).
  Cloud rendering; explicitly mandates *idempotent* filters.
  https://learn.microsoft.com/en-us/azure/architecture/patterns/pipes-and-filters

### Composition, dataflow & the Unix lineage
- **Collection Pipeline** — Martin Fowler. The small-scale embodiment of
  pipe-and-filter (filter/map/reduce). https://martinfowler.com/articles/collection-pipeline/
- **Flow-Based Programming** — J. Paul Morrison (2nd ed., 2010). Networks of
  asynchronous processes exchanging information packets.
  https://www.jpaulmorrison.com/fbp/
- **The Art of Unix Programming** — Eric S. Raymond (Addison-Wesley, 2003; full
  text online). The Unix philosophy and the origin of the pipe.
  http://www.catb.org/esr/writings/taoup/html/

### Separation of concerns, idempotency & operations
- **On the role of scientific thought (EWD447)** — Edsger W. Dijkstra (1974).
  Coined "separation of concerns." https://www.cs.utexas.edu/~EWD/transcriptions/EWD04xx/EWD447.html
- **RFC 9110 — HTTP Semantics (§9.2.2 Idempotent Methods)** — IETF (2022). The
  authoritative definition of idempotency. https://www.rfc-editor.org/info/rfc9110/
- **Idempotent Consumer** — Chris Richardson, microservices.io. Dedupe on
  processed-id to make retries safe. https://microservices.io/patterns/communication-style/idempotent-consumer.html
- **The Twelve-Factor App** — Wiggins et al. (2011/2017). Config-in-environment,
  build/release/run separation, stateless disposable processes. https://12factor.net/

### Reproducibility & data stewardship
- **Ten Simple Rules for Reproducible Computational Research** — Sandve,
  Nekrutenko, Taylor & Hovig, *PLOS Comp. Biol.* 9(10):e1003285 (2013).
  Track provenance, automate, record seeds, archive intermediates.
  https://doi.org/10.1371/journal.pcbi.1003285
- **Best Practices for Scientific Computing** — Wilson et al., *PLOS Biology*
  12(1):e1001745 (2014). Write for people, automate, version-control, test,
  document. https://doi.org/10.1371/journal.pbio.1001745
- **The FAIR Guiding Principles** — Wilkinson et al., *Scientific Data* 3:160018
  (2016). Findable, Accessible, Interoperable, Reusable. https://doi.org/10.1038/sdata.2016.18
- **FAIR Principles for Research Software (FAIR4RS)** — Barker et al.,
  *Scientific Data* 9:622 (2022). FAIR adapted to software.
  https://doi.org/10.1038/s41597-022-01710-x
- **The Turing Way** — The Turing Way Community (Alan Turing Institute; living
  handbook). The broadest single practical reference for reproducible, ethical,
  collaborative data science. https://book.the-turing-way.org/

---

## G. Statistical-method references

⭐ Start: **Hollander, Wolfe & Chicken** (textbook) for methods; **scipy.stats**
docs for implementation.

### Foundational papers
- **Use of Ranks in One-Criterion Variance Analysis** — Kruskal & Wallis, *JASA*
  47(260):583–621 (1952). The Kruskal–Wallis H-test.
  https://doi.org/10.1080/01621459.1952.10483441
- **Multiple Comparisons Using Rank Sums** — O. J. Dunn, *Technometrics*
  6(3):241–252 (1964). The standard non-parametric post-hoc ("Dunn's test").
  https://doi.org/10.1080/00401706.1964.10490181
- **A Simple Sequentially Rejective Multiple Test Procedure** — S. Holm,
  *Scand. J. Statistics* 6(2):65–70 (1979). The Holm correction.
  https://www.jstor.org/stable/4615733
- **A Mathematical Theory of Communication** — C. E. Shannon, *Bell System
  Technical Journal* 27 (1948). Defines Shannon entropy.
  https://doi.org/10.1002/j.1538-7305.1948.tb01338.x

### Canonical textbooks
- **Nonparametric Statistical Methods, 3rd ed.** — Hollander, Wolfe & Chicken
  (Wiley, 2014). The standard graduate reference: rank-based methods incl.
  Kruskal–Wallis and rank-sum post-hocs. https://www.wiley.com/en-us/9780470387375
- **Markov Chains and Mixing Times, 2nd ed.** — Levin, Peres & Wilmer (AMS,
  2017). Ch. 4 is a canonical treatment of total variation distance.
  https://bookstore.ams.org/view?ProductCode=MBK/58

### Official documentation (implementation references)
- **`scipy.stats.kruskal`** — Kruskal–Wallis H-test. https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.kruskal.html
- **`scikit_posthocs.posthoc_dunn`** — Dunn's post-hoc with `p_adjust`
  (Holm/Bonferroni/…). https://scikit-posthocs.readthedocs.io/en/latest/generated/scikit_posthocs.posthoc_dunn.html
- **`statsmodels.stats.multitest.multipletests`** — FWER/FDR p-value corrections
  (bonferroni, holm, BH, …). https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html
- **`scipy.stats.entropy`** — Shannon entropy / KL divergence, configurable base.
  https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.entropy.html
- **`scipy.stats.chisquare`** — chi-squared goodness-of-fit.
  https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chisquare.html
- **`numpy.percentile`** — percentiles with selectable interpolation method.
  https://numpy.org/doc/stable/reference/generated/numpy.percentile.html
- **NumPy random `Generator` / `default_rng`** — deterministic RNG, seeding,
  `SeedSequence` for parallel streams. https://numpy.org/doc/stable/reference/random/generator.html
- **pytest documentation** — fixtures, parametrization, `pytest.approx` for
  float comparison. https://docs.pytest.org/

---

## H. Code craftsmanship & maintainability

⭐ Start: **Ousterhout, *A Philosophy of Software Design*** (complexity), plus
Martin's free **"The Clean Architecture"** post for the dependency rule.

### SOLID & object/module design principles
- **Design Principles and Design Patterns** — Robert C. Martin (2000). The essay
  that assembled the five principles later acronymized as SOLID. (objectmentor
  original is dead; verified mirror:)
  https://staff.cs.utu.fi/~jounsmed/doos_06/material/DesignPrinciplesAndPatterns.pdf
- **The individual SOLID papers** — Robert C. Martin (C++ Report columns, 1996+):
  OCP https://condor.depaul.edu/dmumaugh/OOT/Design-Principles/ocp.pdf ·
  LSP https://condor.depaul.edu/dmumaugh/OOT/Design-Principles/lsp.pdf ·
  ISP https://condor.depaul.edu/dmumaugh/OOT/Design-Principles/isp.pdf ·
  DIP https://condor.depaul.edu/dmumaugh/OOT/Design-Principles/dip.pdf ·
  SRP (1996) https://www.cs.utexas.edu/~downing/papers/SRP-1996.pdf
- **Agile Software Development, Principles, Patterns, and Practices** — Robert C.
  Martin (Prentice Hall, 2002). Book-length consolidation of SOLID and
  package-design principles. ISBN 978-0135974445.
- **Data Abstraction and Hierarchy** — Barbara Liskov, *ACM SIGPLAN Notices*
  23(5), 1988 (OOPSLA '87 keynote). The origin sentence of the LSP.
  https://www.cs.tufts.edu/~nr/cs257/archive/barbara-liskov/data-abstraction-and-hierarchy.pdf
- **A Behavioral Notion of Subtyping** — Liskov & Wing, *ACM TOPLAS* 16(6), 1994.
  The formal definition of behavioral subtyping (DOI 10.1145/197320.197383).
  https://www.cs.cmu.edu/~wing/publications/LiskovWing94.pdf
- **The Clean Architecture** — Robert C. Martin (blog, 2012). The Dependency Rule
  ("source code dependencies point only inward"). https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
- **Clean Architecture** — Robert C. Martin (Prentice Hall, 2017). The book-length
  treatment. ISBN 978-0134494166.

### Cohesion, coupling, modularity
- **Structured Design** — Stevens, Myers & Constantine, *IBM Systems Journal*
  13(2), 1974. **Introduced "coupling" and "cohesion."** DOI 10.1147/sj.132.0115.
  https://dl.acm.org/doi/10.1147/sj.132.0115
- **Structured Design** (book) — Yourdon & Constantine (Prentice-Hall, 1979). The
  seven-level cohesion scale and the coupling spectrum.
  https://archive.org/details/structureddesign00edwa
- **On the Criteria To Be Used in Decomposing Systems into Modules** — David L.
  Parnas, *CACM* 15(12), 1972. The origin of **information hiding**.
  http://sunnyday.mit.edu/16.355/parnas-criteria.html
- **What Every Programmer Should Know About Object-Oriented Design** — Meilir
  Page-Jones (Dorset House, 1995). Introduces **connascence** (ch. 8). Expanded
  taxonomy in *Fundamentals of Object-Oriented Design in UML* (2000). Modern
  reference: https://connascence.io/

### Complexity, simplicity, construction
- **A Complexity Measure** — Thomas J. McCabe, *IEEE TSE* SE-2(4), 1976.
  **Cyclomatic complexity** `V(G)=E−N+2`. https://www.literateprogramming.com/mccabe.pdf
- **A Philosophy of Software Design** — John Ousterhout (1st 2018, 2nd 2021).
  Managing complexity via deep modules and information hiding.
  https://web.stanford.edu/~ouster/cgi-bin/aposd.php
- **Code Complete, 2nd ed.** — Steve McConnell (Microsoft Press, 2004).
  Evidence-based software construction. https://www.microsoftpressstore.com/store/code-complete-9780735619678
- **radon** — Python metrics tool: cyclomatic complexity, Maintainability Index.
  https://radon.readthedocs.io/

### Craft, refactoring, debt, legacy
- **The Pragmatic Programmer** — Hunt & Thomas (1st 1999; 20th-anniv. 2019).
  Origin of **DRY**, orthogonality, tracer bullets. https://pragprog.com/titles/tpp20/the-pragmatic-programmer-20th-anniversary-edition/
- **Clean Code** — Robert C. Martin (Prentice Hall, 2008). Names (ch. 2),
  functions (ch. 3), comments (ch. 4), smells (ch. 17). ISBN 978-0132350884.
- **Refactoring, 2nd ed.** — Martin Fowler (Addison-Wesley, 2018; 1st 1999 w/
  Beck). Named refactorings + "Bad Smells in Code." https://martinfowler.com/books/refactoring.html
  · catalog https://refactoring.com/
- **Yagni** — Martin Fowler (2015). The four costs of speculative features.
  https://martinfowler.com/bliki/Yagni.html
- **Working Effectively with Legacy Code** — Michael Feathers (Prentice Hall,
  2004). "Legacy code is code without tests"; dependency-breaking seams. ISBN
  978-0131177055.
- **The WyCash Portfolio Management System** — Ward Cunningham, OOPSLA '92. The
  **technical-debt metaphor's** origin. https://c2.com/doc/oopsla92.html
- **Technical Debt** / **Technical Debt Quadrant** — Martin Fowler (2019 / 2009).
  https://martinfowler.com/bliki/TechnicalDebt.html ·
  https://martinfowler.com/bliki/TechnicalDebtQuadrant.html

### Python practice: style, typing, tooling, docs
- **PEP 8** (style) https://peps.python.org/pep-0008/ · **PEP 20** (Zen)
  https://peps.python.org/pep-0020/ · **PEP 257** (docstrings)
  https://peps.python.org/pep-0257/ · **PEP 484** (type hints)
  https://peps.python.org/pep-0484/ · **PEP 561** (typed packages)
  https://peps.python.org/pep-0561/
- **Google Python Style Guide** — https://google.github.io/styleguide/pyguide.html
- **Type checkers & linters/formatters:** mypy https://mypy.readthedocs.io/ ·
  Pyright https://microsoft.github.io/pyright/ · Ruff https://docs.astral.sh/ruff/ ·
  flake8 https://flake8.pycqa.org/ · pylint https://pylint.readthedocs.io/ ·
  black https://black.readthedocs.io/
- **Testing:** pytest https://docs.pytest.org/ · Test Pyramid
  https://martinfowler.com/bliki/TestPyramid.html · The Practical Test Pyramid
  https://martinfowler.com/articles/practical-test-pyramid.html · Hypothesis
  (property-based) https://hypothesis.readthedocs.io/
- **Docs & decisions:** Diátaxis https://diataxis.fr/ · Sphinx
  https://www.sphinx-doc.org/ · Architecture Decision Records (Nygard, 2011)
  https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- **Packaging & reproducibility:** PEP 517 https://peps.python.org/pep-0517/ ·
  PEP 518 (pyproject.toml) https://peps.python.org/pep-0518/ · PyPA pyproject
  guide https://packaging.python.org/en/latest/guides/writing-pyproject-toml/ ·
  venv https://docs.python.org/3/library/venv.html
- **Review & versioning:** Google Code Review Developer Guide
  https://google.github.io/eng-practices/review/ · Conventional Commits
  https://www.conventionalcommits.org/en/v1.0.0/ · Semantic Versioning
  https://semver.org/

---

## Verification notes

- Every entry was checked against a live source (publisher, journal/DOI,
  official docs, or hosting institution). A few sites block automated fetchers
  (some `dl.acm.org`, Medium redirects, dbt's blog) but were cross-confirmed via
  canonical landing pages.
- **Editions move:** DDIA, Kafka: The Definitive Guide, Data Pipelines with
  Apache Airflow, Data Management at Scale, High Performance Python, and others
  have multiple editions — match the edition to your target ISBN.
- **Course offerings move:** university course pages reflect the latest verified
  public offering; numbers and instructors change year to year.
- **Author correction carried from research:** *Research Software Engineering
  with Python* is by Irving, Hertweck, Johnston, Ostblom, Wickham & Wilson.

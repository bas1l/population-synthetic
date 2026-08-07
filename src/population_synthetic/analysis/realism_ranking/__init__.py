"""realism_ranking -- cross-combination ranking of the persona-realism judge output.

The cross-unit half of the two-level persona-realism pipeline. ``persona_realism``
judges one combination at a time and writes per-combination artifacts plus a
per-persona tidy CSV; this package reads many of those and makes every claim that
requires more than one unit:

* **Axis A -- validity.** Every competitor's impossibility rate with a bootstrap CI,
  ranked. The real (SCB-sampled) population is an **ordinary ranked competitor** here,
  not the origin: the open question is whether conditional chained sampling -- which
  never cross-references attributes -- produces internally incoherent people, and a
  metric measuring distance *from* the real population could not answer a question
  *about* it. The ranking is computable and correct whether the real population places
  first, last, or in the middle.
* **Axis B -- coverage.** Typicality dispersion, where the real population **is** the
  target: the documented failure mode of an LLM population is mode collapse, so the
  goal is to *match* the real spread, not to maximise it. ``distance_to_scb`` near zero
  is better, and it survives here unchanged.

Getting those two directions backwards would invert the interpretation, so they are
kept explicitly separate throughout.

Dependency direction is one-way: this package reads the on-disk contract
(``analysis/utils/realism_csv.py`` plus each combination's report) and never imports
the judge, the LLM client, or ``persona_realism``'s reduction internals. It performs no
LLM work at all -- re-running it is free.
"""

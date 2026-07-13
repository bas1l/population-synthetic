"""population_synthetic.analysis.method_significance — per-category method/model significance.

Sits after the fidelity/model_ranking stages (entry point:
``scripts/analyze/analyze_method_significance.py``): consumes the per-combo
comparison reports (reused via ``model_ranking``'s ``loader`` — no fidelity
recomputation) and asks, **per country and per demographic attribute, which
factor drives Total-Variation fidelity — the generation *method* (ordered
strategy) or the *model*, and whether the method-trend differs by model**.

The escape from the ``n=1`` per (model, method, category) wall is to use the
demographic categories as the blocking/replication factor, which maps the
problem onto Demšar (2006) "Statistical Comparisons of Classifiers over Multiple
Data Sets" (models = classifiers, categories = datasets). Dataflow:

    load (model_ranking.loader) → build → visualize

``builder`` assembles the per-country analysis — per-attribute ordered method
trend (Page's L + linear/quadratic contrast) and model omnibus (Friedman +
Iman-Davenport + Kendall's W), BH-corrected across attributes; per-(attribute,
model) descriptive trend slopes; and the overall Demšar model comparison
(Friedman → Nemenyi → critical-difference inputs), overall Page's L method trend
and the ``logit(TV) ~ model*method + (1|category)`` mixed-model interaction — all
from the shared ``analysis.utils.stats_tests`` primitives. This package never
recomputes statistics from populations: the comparison reports are its only data
source.
"""

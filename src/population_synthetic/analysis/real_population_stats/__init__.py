"""real_population_stats -- standalone reference-figure/CSV stage for one real population.

Pipe-and-filter leaf stage: reads one mapped real population (``03_Analysis/mapping/
real_{country}.json``) -> aggregates per-category proportions (pure computation,
``stats.py``) -> renders figures (pure sinks, ``charts.py``) + writes CSVs
(``csv_writer.py``), orchestrated by ``artifacts.py``. No synthetic population, no
comparison metric, no GUI/dispatch knowledge -- see the module docstrings for each
file's exact boundary.
"""

from __future__ import annotations

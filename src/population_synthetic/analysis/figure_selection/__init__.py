"""figure_selection -- publish a config-declared roster of figures into ``04_Figures``.

Terminal node of the analysis DAG, and the one process that **computes nothing**. It
draws no figure, imports no chart module and makes no publication decision: it reads a
roster out of ``config/analysis/figure_selection.yaml``, resolves each entry to the
three files the presentation layer already wrote, and copies those bytes into the
figures stage. It sits *downstream* of the presentation boundary, not inside it.

It exists because the selection was previously made by hand into a folder outside the
repository. That cost three things this package restores: the roster was not diffable
or re-runnable; a fresh sweep silently invalidated the staged copies with nothing to
detect the drift; and hand-copying took the PNG, leaving behind the EPS that is the
one format every target venue accepts.

Module boundaries (see each module's docstring for the exact contract):

``config``
    Read, validate and materialise the roster: :class:`FigureSet` /
    :class:`FigureEntry`. Everything decidable without touching the analysis tree
    raises here -- unknown set, unregistered process id, unknown placeholder, a
    ``{slug}`` without its block, a duplicate figure number.
``resolve``
    One entry + a country -> the three concrete source paths, through
    ``figures.OUTPUT_SUFFIXES`` and ``manifest_loader.axis_slug``. Owns the two
    country-dependent gates: colliding destination basenames, and the on-disk
    existence sweep that reports **every** missing file rather than the first.

The roster is validated and fully resolved before a single byte is copied, so a run
that is going to fail leaves the figures stage untouched.
"""

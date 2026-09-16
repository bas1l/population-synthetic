"""resolve.py -- one roster entry + a country -> the three concrete source paths.

This is the whole country-dependent half of the selection contract. A
:class:`~population_synthetic.analysis.figure_selection.config.FigureEntry` carries an
extension-less stem relative to the analysis stage; this module substitutes the two
placeholders into it, routes its first segment through the registry, and appends every
format the presentation layer emits.

Three things are borrowed rather than restated, and that is the point of the module:

* the **format list** is ``figures.OUTPUT_SUFFIXES``. The roster names no format and
  neither does this module, so a figure family cannot be published in fewer formats
  than the layer wrote -- the exact drift ``figures.py`` exists to prevent;
* the **slug** is ``manifest_loader.axis_slug``, the single source of truth for
  ``{country}_{strategy}_{model}``. It is the same call the producing tasks made when
  they named those folders, so a roster entry cannot format a slug they never wrote;
* the **process folder** is the registry's ``analysis_output_dir(..., for_read=True)``.
  No stage-folder or process-folder literal appears here, and a stem citing a process
  whose folder was renamed still resolves through the legacy-read fallback.

It also owns the two validation rows that need a resolved path rather than a template:
:func:`check_basename_collisions` (two entries that would overwrite each other under
``as_generated/``) and :func:`check_sources_exist` (a stem with nothing behind it, or a
partial format set). Both sweep the whole set and report **every** offender, not the
first -- a roster is curated in batches and fixing one fault at a time per run is the
behaviour that makes a validation gate hated rather than used.

Nothing here reads or writes a figure: it produces paths and checks them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from population_synthetic.analysis.figure_selection.config import (
    COUNTRY_PLACEHOLDER,
    SLUG_PLACEHOLDER,
    FigureEntry,
    FigureSet,
)
from population_synthetic.analysis.utils.figures import OUTPUT_SUFFIXES, RASTER_SUFFIX
from population_synthetic.analysis.utils.registry import analysis_output_dir
from population_synthetic.generators.synthetic.manifest_loader import axis_slug

__all__ = [
    "ResolvedFigure",
    "check_basename_collisions",
    "check_sources_exist",
    "resolve_entry",
    "resolve_set",
]


@dataclass(frozen=True)
class ResolvedFigure:
    """One roster entry bound to a country, and the files behind it."""

    entry: FigureEntry
    country: str
    #: The entry's ``source`` with both placeholders substituted -- what the roster
    #: means, spelled out, and what an error message quotes back.
    stem: str
    #: ``{suffix: path}`` over every format in ``figures.OUTPUT_SUFFIXES``.
    paths: Mapping[str, Path]

    @property
    def basename(self) -> str:
        """The stem's last segment -- the filename ``as_generated/`` publishes under."""
        return self.stem.rsplit("/", 1)[-1]

    @property
    def numbered_basename(self) -> str:
        """The filename ``numbered/`` publishes under: ``F07_model_x_method_heatmap``."""
        return f"F{self.entry.n:02d}_{self.entry.name}"


def resolve_entry(entry: FigureEntry, *, country: str, output_base: str | Path) -> ResolvedFigure:
    """Bind one entry to *country* and return its stem plus one path per format.

    Does not touch the filesystem beyond the registry's legacy-folder probe: the
    returned paths may not exist, which is what :func:`check_sources_exist` reports.
    """
    if not country or not str(country).strip():
        raise ValueError(f"resolve_entry requires a non-empty country (got {country!r}).")

    substitutions = {COUNTRY_PLACEHOLDER: country}
    if entry.slug is not None:
        # Composed, never formatted: the same call the producing task made.
        substitutions[SLUG_PLACEHOLDER] = axis_slug(entry.slug.model, entry.slug.strategy, country)
    stem = entry.source.format(**substitutions)

    process_id, _, remainder = stem.partition("/")
    process_dir = analysis_output_dir(process_id, output_base, for_read=True)
    base_path = process_dir.joinpath(*remainder.split("/"))

    return ResolvedFigure(
        entry=entry,
        country=country,
        stem=stem,
        paths={suffix: base_path.with_name(base_path.name + suffix) for suffix in OUTPUT_SUFFIXES},
    )


def resolve_set(figure_set: FigureSet, *, country: str, output_base: str | Path) -> tuple[ResolvedFigure, ...]:
    """Resolve a whole set for one country and run the country-dependent gates.

    Returns the resolved figures in the set's order (figure number), having raised on
    any destination collision. Existence is checked separately by
    :func:`check_sources_exist` so a caller can resolve without a tree on disk.
    """
    resolved = tuple(
        resolve_entry(entry, country=country, output_base=output_base) for entry in figure_set.entries
    )
    check_basename_collisions(resolved, set_name=figure_set.name)
    return resolved


def check_basename_collisions(resolved: Sequence[ResolvedFigure], *, set_name: str) -> None:
    """Raise when two entries would publish under the same ``as_generated`` filename.

    The analysis stage disambiguates some figures by directory rather than by
    filename, so two perfectly distinct stems can share a basename; flattening them
    into one folder would silently publish one and drop the other.
    """
    seen: dict[str, ResolvedFigure] = {}
    for figure in resolved:
        first = seen.get(figure.basename)
        if first is not None:
            raise ValueError(
                f"Figure set {set_name!r} resolves two entries to the same as_generated basename "
                f"{figure.basename!r} for country {figure.country!r}: "
                f"{first.entry.source!r} and {figure.entry.source!r}. Drop one or publish the set "
                f"under a country whose paths differ."
            )
        seen[figure.basename] = figure


def check_sources_exist(resolved: Iterable[ResolvedFigure], *, set_name: str) -> None:
    """Raise unless every resolved figure exists in **every** published format.

    Two faults, one sweep, and the whole roster reported rather than the first
    offender: a stem with no raster behind it (the figure was never drawn, or the
    process that draws it was never run), and a raster whose vector siblings are
    absent (a figure drawn before the presentation layer emitted them). A partial
    format set is never published -- taking the PNG alone is precisely the loss this
    process was built to stop.
    """
    absent: list[str] = []
    partial: list[str] = []
    for figure in resolved:
        missing = [suffix for suffix, path in sorted(figure.paths.items()) if not path.is_file()]
        if not missing:
            continue
        location = f"F{figure.entry.n:02d} {figure.entry.name!r} ({figure.stem})"
        if RASTER_SUFFIX in missing:
            absent.append(f"{location}: no {RASTER_SUFFIX} at {figure.paths[RASTER_SUFFIX]}")
        else:
            partial.append(f"{location}: missing {missing} beside {figure.paths[RASTER_SUFFIX]}")

    if not absent and not partial:
        return

    report = []
    if absent:
        report.append(f"{len(absent)} figure(s) not found in the analysis stage:\n  " + "\n  ".join(absent))
    if partial:
        report.append(
            f"{len(partial)} figure(s) present but incomplete -- every figure publishes in "
            f"{list(OUTPUT_SUFFIXES)}, and a partial format set is never copied:\n  " + "\n  ".join(partial)
        )
    raise FileNotFoundError(
        f"Figure set {set_name!r} cannot be published; nothing was copied.\n" + "\n".join(report)
    )

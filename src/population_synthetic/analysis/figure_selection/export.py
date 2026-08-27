"""export.py -- copy a validated figure set into the figures stage, and record what it copied.

The end of the process, and the only module in it that writes anything. It receives a
:class:`~population_synthetic.analysis.figure_selection.config.FigureSet` and a country,
runs the two country-dependent gates in
:mod:`~population_synthetic.analysis.figure_selection.resolve`, and -- only if the whole
set passed -- copies every format of every entry into both namings, then writes the
provenance manifest.

**It copies bytes and decides nothing.** No chart module is imported, no figure is
redrawn, nothing is re-encoded or resized. The formats are whatever the presentation
layer wrote; this module moves them.

Three properties are the contract:

*Resolve-all, validate-all, then copy.* Every path is resolved and every gate run
before the destination is so much as created, so a run that is going to fail leaves
the figures stage exactly as it found it -- the one behaviour that makes the stage
trustworthy, since a half-published set is indistinguishable from a complete one by
looking at it.

*Nothing published is ever partial.* Each file lands through
``atomic_io.atomic_copy_file`` (temp file, fsync, ``os.replace``), so a killed run
leaves whole files behind rather than truncated ones, and the manifest is written
**last** -- its presence is the completion marker for the set.

*The manifest is the provenance record.* Given a staged image and nothing else,
``_index.json`` answers which ``output_base``, which country, which set and which run
produced it, and carries each source's size, mtime and SHA-256 so drift against a
re-run analysis stage is detectable without re-reading the analysis tree.

Re-runs overwrite what they publish. A destination file the current roster does not
claim is reported at WARNING and left alone -- it is usually a previous, larger set --
unless ``force`` clears the two naming folders first, which is how a shrinking roster
leaves nothing stale behind.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from population_synthetic.analysis.figure_selection.config import FigureSet
from population_synthetic.analysis.figure_selection.resolve import (
    ResolvedFigure,
    check_sources_exist,
    resolve_set,
)
from population_synthetic.analysis.utils.figures import OUTPUT_SUFFIXES
from population_synthetic.analysis.utils.registry import (
    ANALYSIS_STAGE_DIR,
    FIGURES_STAGE_DIR,
    figures_output_dir,
)
from population_synthetic.utils.atomic_io import atomic_copy_file, atomic_write_json

logger = logging.getLogger(__name__)

__all__ = [
    "INDEX_FILENAME",
    "NAMINGS",
    "NAMING_AS_GENERATED",
    "NAMING_NUMBERED",
    "CopiedFigure",
    "CopiedFormat",
    "ExportResult",
    "export_figure_set",
]

#: The source filename, verbatim: ``swedish_02_model_method_heatmap.png``. Traceable
#: back to the analysis stage by name alone, which is why it is emitted at all.
NAMING_AS_GENERATED = "as_generated"

#: The manuscript's own name for the figure: ``F07_model_x_method_heatmap.png``. The
#: number is the roster's ``n``, so a citation resolves to a file.
NAMING_NUMBERED = "numbered"

#: Both namings, in the order they are copied and reported. Every set is emitted in
#: **both** -- they are two views of one selection, not two options.
NAMINGS = (NAMING_AS_GENERATED, NAMING_NUMBERED)

#: The provenance manifest, one per emitted set, beside its two naming folders.
INDEX_FILENAME = "_index.json"

#: Read size for the source digest. A figure is a few MB at most; this only keeps a
#: pathological one off the heap.
_HASH_CHUNK_BYTES = 1 << 20


@dataclass(frozen=True)
class CopiedFormat:
    """One published format of one figure: where it came from, and what it was."""

    suffix: str
    source: Path
    size_bytes: int
    #: The source's modification time as a POSIX timestamp -- serialised as UTC ISO
    #: 8601, and carried across onto the copy by ``atomic_copy_file``.
    mtime: float
    sha256: str
    #: ``{naming: destination path}`` over :data:`NAMINGS`.
    destinations: Mapping[str, Path]


@dataclass(frozen=True)
class CopiedFigure:
    """One roster entry, published: the resolved source and one record per format."""

    figure: ResolvedFigure
    formats: tuple[CopiedFormat, ...]


@dataclass(frozen=True)
class ExportResult:
    """What one ``(country, set)`` export published, and what it found beside it."""

    country: str
    set_name: str
    output_base: Path
    set_dir: Path
    index_path: Path
    #: When the export ran, UTC ISO 8601 -- the top-level timestamp in the manifest.
    generated_at: str
    figures: tuple[CopiedFigure, ...]
    #: Destination files this run did not write and did not remove: present in a
    #: naming folder, absent from the manifest. Reported, never deleted (that is
    #: what ``force`` is for).
    unclaimed: tuple[Path, ...]

    @property
    def n_files(self) -> int:
        """How many files were copied: entries x formats x namings."""
        return sum(len(figure.formats) for figure in self.figures) * len(NAMINGS)


def _sha256(path: Path) -> str:
    """Digest a file's bytes, chunked."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_iso(timestamp: float) -> str:
    """A POSIX timestamp as a UTC ISO-8601 string (the manifest's time format)."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _stage_paths(output_base: Path, *, country: str, set_name: str) -> tuple[Path, dict[str, Path]]:
    """Return ``(set_dir, {naming: dir})`` for one country and set, geometry checked.

    The registry composes the paths; this asserts they have the shape the rest of the
    module assumes -- both namings siblings under one set directory, each named for
    its naming. It is not a formality: ``force`` deletes those directories whole, and
    the guarantee that the deletion cannot reach outside ``{country}/{set}/`` is this
    check rather than a trusted string.
    """
    naming_dirs = {
        naming: figures_output_dir(output_base, country=country, set_name=set_name, naming=naming)
        for naming in NAMINGS
    }
    parents = {directory.parent for directory in naming_dirs.values()}
    misnamed = sorted(naming for naming, directory in naming_dirs.items() if directory.name != naming)
    if len(parents) != 1 or misnamed:
        raise ValueError(
            f"Figures stage layout for country {country!r}, set {set_name!r} is not "
            f"{{country}}/{{set}}/{{naming}}: naming dirs {sorted(str(d) for d in naming_dirs.values())} "
            f"(misnamed {misnamed}, {len(parents)} distinct parent(s))."
        )
    return parents.pop(), naming_dirs


def _clear_naming_dirs(naming_dirs: Mapping[str, Path]) -> None:
    """Remove both naming folders whole, so a shrunk roster leaves nothing stale.

    Bounded by :func:`_stage_paths`, which has already established that each of these
    is ``{figures stage}/{country}/{set}/{naming}``. The manifest is deliberately not
    removed: it is rewritten in place at the end of the same run.
    """
    for naming, directory in naming_dirs.items():
        if not directory.exists():
            continue
        logger.info("Clearing %s figures folder %s (--force).", naming, directory)
        shutil.rmtree(directory)


def _copy_figure(figure: ResolvedFigure, naming_dirs: Mapping[str, Path]) -> CopiedFigure:
    """Copy every format of one figure into both namings and record what was copied.

    The two destination basenames are the resolved figure's own (``basename`` for the
    source filename, ``numbered_basename`` for the citation one); this only appends
    the format's suffix, so no filename convention is invented here.
    """
    basenames = {
        NAMING_AS_GENERATED: figure.basename,
        NAMING_NUMBERED: figure.numbered_basename,
    }
    formats: list[CopiedFormat] = []
    for suffix in OUTPUT_SUFFIXES:
        source = figure.paths[suffix]
        stat = source.stat()
        destinations = {
            naming: naming_dirs[naming] / f"{basenames[naming]}{suffix}" for naming in NAMINGS
        }
        for destination in destinations.values():
            atomic_copy_file(source, destination)
        formats.append(
            CopiedFormat(
                suffix=suffix,
                source=source,
                size_bytes=stat.st_size,
                mtime=stat.st_mtime,
                sha256=_sha256(source),
                destinations=destinations,
            )
        )
    return CopiedFigure(figure=figure, formats=tuple(formats))


def _unclaimed_files(naming_dirs: Mapping[str, Path], copied: Sequence[CopiedFigure]) -> tuple[Path, ...]:
    """Return the destination entries this run did not write, both namings swept.

    Membership is by name against what was just copied -- not by mtime and not by
    extension -- so a figure dropped from the roster is caught however it was written
    and whenever it was written.
    """
    claimed: dict[str, set[str]] = {naming: set() for naming in naming_dirs}
    for figure in copied:
        for published in figure.formats:
            for naming, destination in published.destinations.items():
                claimed[naming].add(destination.name)

    unclaimed: list[Path] = []
    for naming, directory in naming_dirs.items():
        if not directory.is_dir():
            continue
        unclaimed.extend(
            sorted(entry for entry in directory.iterdir() if entry.name not in claimed[naming])
        )
    return tuple(unclaimed)


def _manifest(result: ExportResult) -> dict[str, Any]:
    """Serialise an :class:`ExportResult` into the ``_index.json`` payload.

    Self-contained by design: the run's identity at the top level, and per entry
    everything needed to decide whether a staged file is still the one the analysis
    stage holds -- without opening either tree.
    """
    return {
        "output_base": str(result.output_base),
        "country": result.country,
        "set": result.set_name,
        "generated_at": result.generated_at,
        "analysis_stage_dir": ANALYSIS_STAGE_DIR,
        "figures_stage_dir": FIGURES_STAGE_DIR,
        "namings": list(NAMINGS),
        "formats": list(OUTPUT_SUFFIXES),
        "n_figures": len(result.figures),
        "n_files": result.n_files,
        "figures": [
            {
                "n": figure.figure.entry.n,
                "name": figure.figure.entry.name,
                "source": figure.figure.entry.source,
                "source_stem": figure.figure.stem,
                "formats": {
                    published.suffix: {
                        "source_path": str(published.source),
                        "size_bytes": published.size_bytes,
                        "mtime": _utc_iso(published.mtime),
                        "sha256": published.sha256,
                        **{
                            naming: destination.name
                            for naming, destination in published.destinations.items()
                        },
                    }
                    for published in figure.formats
                },
            }
            for figure in result.figures
        ],
    }


def export_figure_set(
    figure_set: FigureSet,
    *,
    country: str,
    output_base: str | Path,
    force: bool = False,
) -> ExportResult:
    """Publish one figure set for one country into the figures stage.

    Args:
        figure_set: The validated roster, as loaded by ``config.load_figure_set``.
        country: The country id the run was invoked for; substituted into every stem.
        output_base: The run's output base -- parent of both stage folders.
        force: Clear the set's two naming folders before copying, so a roster that
            shrank leaves nothing stale behind. Bounded to ``{country}/{set}/``:
            no other country, set or stage is touched.

    Returns:
        The :class:`ExportResult`, carrying what was published and any destination
        file the roster no longer claims.

    Raises:
        ValueError: If two entries collide on an ``as_generated`` filename.
        FileNotFoundError: If any entry is missing from the analysis stage, or is
            present in fewer than every published format. Nothing is copied.
    """
    output_base = Path(output_base)
    # Both gates before any destination work: this is what leaves the figures stage
    # untouched when the set does not fully resolve.
    resolved = resolve_set(figure_set, country=country, output_base=output_base)
    check_sources_exist(resolved, set_name=figure_set.name)

    set_dir, naming_dirs = _stage_paths(output_base, country=country, set_name=figure_set.name)
    if force:
        _clear_naming_dirs(naming_dirs)
    for directory in naming_dirs.values():
        directory.mkdir(parents=True, exist_ok=True)

    copied = tuple(_copy_figure(figure, naming_dirs) for figure in resolved)
    unclaimed = _unclaimed_files(naming_dirs, copied)
    if unclaimed:
        logger.warning(
            "Figure set %r (%s): %d file(s) in %s were not written by this run and were left "
            "in place -- usually a previous, larger roster. Re-run with --force to clear them:\n  %s",
            figure_set.name,
            country,
            len(unclaimed),
            set_dir,
            "\n  ".join(str(path) for path in unclaimed),
        )

    result = ExportResult(
        country=country,
        set_name=figure_set.name,
        output_base=output_base,
        set_dir=set_dir,
        index_path=set_dir / INDEX_FILENAME,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        figures=copied,
        unclaimed=unclaimed,
    )
    # Written last, so its presence marks a set that copied completely.
    atomic_write_json(result.index_path, _manifest(result))
    logger.info(
        "Figure set %r (%s): published %d figure(s) x %d format(s) into %s and wrote %s.",
        figure_set.name,
        country,
        len(copied),
        len(OUTPUT_SUFFIXES),
        set_dir,
        INDEX_FILENAME,
    )
    return result

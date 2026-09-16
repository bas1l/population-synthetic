"""config.py -- the figure-selection roster DTO (``config/analysis/figure_selection.yaml``).

Config is the single source of truth (project invariant): which figures a manuscript or
a deck publishes is a research decision, and it is recorded in that YAML and nowhere
else. This module reads it, validates it and materialises it as :class:`FigureSet` /
:class:`FigureEntry`. There is no in-code roster, no default set and no fallback entry.

**Everything decidable without a country and without touching the analysis tree raises
here**, which is what lets the caller reject a bad roster before it has looked at a
single file:

* ``--set`` names a set the file does not declare -- raises, listing the known sets;
* the ``source`` stem's first segment is not a registry process id -- raises, naming it;
* the stem uses a placeholder that is not one of the two declared ones -- raises;
* the stem uses ``{slug}`` without a ``slug:`` block, or declares one without using the
  placeholder -- raises either way, because both mean the entry does not say what it
  looks like it says;
* two entries in a set share a figure number, or repeat the same ``source`` -- raises,
  naming both.

The two remaining rows of the validation contract -- colliding destination basenames
and a stem with no file behind it -- depend on the country the run resolved, so they
live in :mod:`~population_synthetic.analysis.figure_selection.resolve` beside the
substitution that produces them.

Nothing here knows about matplotlib, file formats, the figures stage or the copy: it
reads YAML and types strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.utils.registry import load_registry

__all__ = [
    "COUNTRY_PLACEHOLDER",
    "SELECTION_PATH",
    "SLUG_PLACEHOLDER",
    "FigureEntry",
    "FigureSet",
    "SlugSpec",
    "known_set_names",
    "load_figure_set",
]

#: The roster's canonical location. Overridable per call (tests, an alternative
#: roster) but never defaulted away: an absent file raises.
SELECTION_PATH = PROJECT_ROOT / "config" / "analysis" / "figure_selection.yaml"

#: The run's country id, substituted into the stem. A placeholder rather than a fixed
#: position because the analysis stage carries the country in a filename for some
#: processes (``model_ranking/{country}_models_table``) and in a directory for others
#: (``realism_ranking/{country}/impossibility_heatmap``).
COUNTRY_PLACEHOLDER = "country"

#: The canonical axis slug, composed through ``manifest_loader.axis_slug`` from the
#: entry's ``slug:`` block plus the run's country -- never string-formatted locally,
#: so a roster entry cannot disagree with the folder the producing task wrote.
SLUG_PLACEHOLDER = "slug"

#: Every placeholder a ``source`` stem may use. An unknown one raises rather than
#: surviving into a path as a literal ``{...}`` segment that would then simply not
#: exist on disk, reporting the fault one layer too late and far less clearly.
_KNOWN_PLACEHOLDERS = (COUNTRY_PLACEHOLDER, SLUG_PLACEHOLDER)

#: The keys a ``slug:`` block declares -- exactly these, no more and no fewer. The
#: country is the run's, not the entry's, so it is deliberately absent.
_SLUG_KEYS = ("model", "strategy")

#: The keys an entry declares. ``slug`` is the only optional one.
_REQUIRED_ENTRY_KEYS = ("n", "name", "source")
_OPTIONAL_ENTRY_KEYS = ("slug",)

#: Matches a ``{token}`` in a source stem.
_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")


@dataclass(frozen=True)
class SlugSpec:
    """The axis coordinates an entry pins, for a stem that uses ``{slug}``.

    Only the model and the strategy: the country comes from the run, which is what
    keeps a combination-specific entry portable across countries.
    """

    model: str
    strategy: str


@dataclass(frozen=True)
class FigureEntry:
    """One roster line: a figure number, a published name and a source stem.

    ``source`` is extension-less and relative to the analysis stage folder; the
    formats are the presentation layer's, not the roster's, so no entry names one.
    """

    n: int
    name: str
    source: str
    slug: SlugSpec | None = None


@dataclass(frozen=True)
class FigureSet:
    """One named roster (``manuscript``, ``deck``, ...), in citation order."""

    name: str
    entries: tuple[FigureEntry, ...]


def _load_raw(selection_path: Path) -> dict[str, Any]:
    """Read and minimally validate the roster YAML (fail-fast)."""
    if not selection_path.exists():
        raise FileNotFoundError(f"Figure selection config not found: {selection_path}")

    with open(selection_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(
            f"Figure selection config must be a mapping, got {type(raw).__name__}: {selection_path}"
        )

    sets = raw.get("sets")
    if not isinstance(sets, dict) or not sets:
        raise ValueError(f"Figure selection config missing non-empty 'sets' mapping: {selection_path}")

    return raw


def _placeholders(source: str, set_name: str, position: int, selection_path: Path) -> set[str]:
    """Return the placeholder names used in *source*, raising on an unknown one."""
    used = {match.group(1) for match in _PLACEHOLDER_RE.finditer(source)}
    unknown = sorted(name for name in used if name not in _KNOWN_PLACEHOLDERS)
    if unknown:
        raise ValueError(
            f"Figure set {set_name!r} entry {position} ({source!r}) uses unknown placeholder(s) "
            f"{unknown}: the only placeholders a source stem may use are "
            f"{[f'{{{p}}}' for p in _KNOWN_PLACEHOLDERS]}: {selection_path}"
        )
    return used


def _build_slug(entry: Any, set_name: str, position: int, selection_path: Path) -> SlugSpec:
    """Validate one ``slug:`` block and materialize it as a :class:`SlugSpec`."""
    if not isinstance(entry, dict):
        raise ValueError(
            f"Figure set {set_name!r} entry {position}: 'slug' must be a mapping of "
            f"{list(_SLUG_KEYS)}, got {type(entry).__name__}: {selection_path}"
        )
    missing = [key for key in _SLUG_KEYS if not entry.get(key)]
    unexpected = sorted(key for key in entry if key not in _SLUG_KEYS)
    if missing or unexpected:
        raise ValueError(
            f"Figure set {set_name!r} entry {position}: 'slug' must declare exactly "
            f"{list(_SLUG_KEYS)} (missing {missing}, unexpected {unexpected}); the country is the "
            f"run's, not the entry's: {selection_path}"
        )
    return SlugSpec(model=str(entry["model"]), strategy=str(entry["strategy"]))


def _build_entry(
    entry: Any,
    set_name: str,
    position: int,
    process_ids: frozenset[str],
    selection_path: Path,
) -> FigureEntry:
    """Validate one roster line and materialize it as a :class:`FigureEntry`."""
    if not isinstance(entry, dict):
        raise ValueError(
            f"Figure set {set_name!r} entry {position} must be a mapping, got "
            f"{type(entry).__name__}: {selection_path}"
        )
    missing = [key for key in _REQUIRED_ENTRY_KEYS if entry.get(key) in (None, "")]
    if missing:
        raise ValueError(
            f"Figure set {set_name!r} entry {position} missing required key(s) {missing}: {selection_path}"
        )
    unexpected = sorted(key for key in entry if key not in (*_REQUIRED_ENTRY_KEYS, *_OPTIONAL_ENTRY_KEYS))
    if unexpected:
        raise ValueError(
            f"Figure set {set_name!r} entry {position} declares unknown key(s) {unexpected}: known keys "
            f"are {list((*_REQUIRED_ENTRY_KEYS, *_OPTIONAL_ENTRY_KEYS))}: {selection_path}"
        )

    number = entry["n"]
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ValueError(
            f"Figure set {set_name!r} entry {position}: 'n' must be a positive integer figure "
            f"number, got {number!r}: {selection_path}"
        )

    source = str(entry["source"]).strip()
    segments = source.split("/")
    # A stem is read relative to a process folder and may never climb out of it: the
    # first segment is what the registry validates, so a `..` would publish a figure
    # attributed to a process that did not draw it. Checked before the shape below, so
    # a backslash-separated stem is diagnosed as a separator fault rather than as a
    # stem that merely looks like a single segment.
    if ".." in segments or "\\" in source:
        raise ValueError(
            f"Figure set {set_name!r} entry {position}: 'source' must stay inside its process folder "
            f"and use '/' separators, got {source!r}: {selection_path}"
        )
    if len(segments) < 2 or not all(segment.strip() for segment in segments):
        raise ValueError(
            f"Figure set {set_name!r} entry {position}: 'source' must be a process id followed by an "
            f"extension-less stem below it (e.g. 'model_ranking/{{country}}_models_table'), got "
            f"{source!r}: {selection_path}"
        )
    process_id = segments[0]
    if process_id not in process_ids:
        raise ValueError(
            f"Figure set {set_name!r} entry {position} ({source!r}): first segment {process_id!r} is "
            f"not a registered analysis process id; known ids are {sorted(process_ids)}: {selection_path}"
        )

    used = _placeholders(source, set_name, position, selection_path)
    slug_block = entry.get("slug")
    uses_slug = SLUG_PLACEHOLDER in used
    if uses_slug and slug_block is None:
        raise ValueError(
            f"Figure set {set_name!r} entry {position} ({source!r}) uses {{{SLUG_PLACEHOLDER}}} but "
            f"declares no 'slug' block: the combination it names cannot be resolved: {selection_path}"
        )
    if slug_block is not None and not uses_slug:
        raise ValueError(
            f"Figure set {set_name!r} entry {position} ({source!r}) declares a 'slug' block but never "
            f"uses {{{SLUG_PLACEHOLDER}}}: the pinned combination would be silently ignored: {selection_path}"
        )

    return FigureEntry(
        n=number,
        name=str(entry["name"]).strip(),
        source=source,
        slug=_build_slug(slug_block, set_name, position, selection_path) if slug_block is not None else None,
    )


def _check_unique(entries: tuple[FigureEntry, ...], set_name: str, selection_path: Path) -> None:
    """Raise on a repeated figure number or a repeated source stem, naming both."""
    for label, key in (("figure number 'n'", lambda e: e.n), ("source stem", lambda e: e.source)):
        seen: dict[Any, FigureEntry] = {}
        for entry in entries:
            value = key(entry)
            first = seen.get(value)
            if first is not None:
                raise ValueError(
                    f"Figure set {set_name!r} repeats {label} {value!r}: "
                    f"F{first.n:02d} {first.name!r} ({first.source}) and "
                    f"F{entry.n:02d} {entry.name!r} ({entry.source}): {selection_path}"
                )
            seen[value] = entry


def known_set_names(selection_path: str | Path = SELECTION_PATH) -> tuple[str, ...]:
    """Return the set names the roster declares, sorted."""
    return tuple(sorted(_load_raw(Path(selection_path))["sets"]))


def load_figure_set(set_name: str, selection_path: str | Path = SELECTION_PATH) -> FigureSet:
    """Load and validate one named set from the roster (fail-fast).

    Entries are returned in figure-number order, which is the order ``numbered/`` is
    emitted in; ``as_generated/`` is order-insensitive.
    """
    selection_path = Path(selection_path)
    raw = _load_raw(selection_path)
    sets = raw["sets"]
    if set_name not in sets:
        raise KeyError(
            f"Unknown figure set {set_name!r}: known sets are {sorted(sets)}: {selection_path}"
        )

    declared = sets[set_name]
    if not isinstance(declared, list) or not declared:
        raise ValueError(
            f"Figure set {set_name!r} must be a non-empty list of entries, got "
            f"{type(declared).__name__}: {selection_path}"
        )

    process_ids = frozenset(load_registry())
    entries = tuple(
        _build_entry(entry, set_name, position, process_ids, selection_path)
        for position, entry in enumerate(declared, start=1)
    )
    _check_unique(entries, set_name, selection_path)
    return FigureSet(name=set_name, entries=tuple(sorted(entries, key=lambda e: e.n)))

"""labels.py -- The one place that decides what a config id is *called* on a figure.

Before this module the analysis layer had no display-name layer at all. Every figure
printed the raw config id -- ``openrouter_kimi_k3``, ``all_generate_evaluate_random_pick_v2``,
``housing_tenure`` -- even though the model and strategy axis YAMLs have carried a
``label:`` field all along, read only by the Qt GUI and by the run-namer. All six
analysis callers of ``discover_axis_values()`` did ``sorted(d["id"] for d in ...)`` and
threw the label away, and the single id transformation anywhere in the codebase was a
``strategy.replace("_", "\\n")`` that stacked one strategy id as five lowercase lines.

**What it owns.** Resolving a config id to the string a reader sees, and the method
letters. A display string is *read from config*, never derived by string manipulation
of the id and never the id itself.

**What it knows nothing about.** matplotlib, figures, colour and statistics. Nothing
here imports a plotting library, names a hue, receives an array or computes a number;
the strings it returns are equally correct in a CSV, a caption or a LaTeX table. It is
therefore usable by -- and dependent on -- no chart module.

**Config is the only table.** There is no id-to-string dictionary in this file. The
model name comes from that model's own ``display.name``, the strategy phrase from its
``label:``, the method letter from the *rank* of its family in ``_families.yaml``, the
attribute phrase from ``config/analysis/attribute_labels.yaml``, the reference source
from each country's ``display.reference_source``, and the manuscript-controlled words
("individuals", "Strategies") from ``config/analysis/figure_terms.yaml``. A hand-maintained
Python map, or a second YAML restating what the axis files already say, would be a
copy free to drift from the thing it copies.

**Every miss raises.** :class:`UnknownAxisValue` names the offending id and the files
searched. There is deliberately no ``.get(id, id)`` anywhere in this module: falling
back to the raw id is the ``attr or DEFAULT`` pattern ``design-principles.md`` bans,
and its failure mode here is a published figure with ``openrouter_kimi_k3`` on an axis,
caught -- if at all -- at proofing rather than at run time.

The axis YAMLs are read **directly**, as in
:mod:`population_synthetic.analysis.utils.axes` and for the same reason: the obvious
route, ``generators.synthetic.manifest_loader``, imports from ``analysis.utils`` itself,
so routing through it would be circular. Nothing is read at import time and no parsed
config is cached in a module global -- every call resolves the ids it was actually
given, so a test can point any resolver at a temporary config tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.utils.axes import (
    FAMILIES_FILENAME,
    STRATEGIES_DIR,
    decompose_slug,
    load_family_order,
    strategy_complexity_order,
    strategy_families,
    strategy_versions,
)

# ------------------------------------------------------------------
# Where the display strings live
# ------------------------------------------------------------------

#: The axis-YAML root. ``STRATEGIES_DIR`` is imported from :mod:`.axes` rather than
#: recomputed, so the two modules can never disagree about where the strategy axis is.
AXES_DIR = PROJECT_ROOT / "config" / "synthetic" / "axes"
MODELS_DIR = AXES_DIR / "models"
COUNTRIES_DIR = AXES_DIR / "countries"

#: The canonical-attribute display labels. Attributes are the one axis with no display
#: field of their own -- the names are mapped-schema keys shared by every mapping tier
#: -- so this file supplies it once, country-agnostically. See the file's own header.
ATTRIBUTE_LABELS_PATH = PROJECT_ROOT / "config" / "analysis" / "attribute_labels.yaml"

#: The manuscript-controlled words a figure prints (``individuals``, the strategy-key
#: heading, the name of the real population). See the file's own header for why a word
#: is config rather than a literal in a chart module.
FIGURE_TERMS_PATH = PROJECT_ROOT / "config" / "analysis" / "figure_terms.yaml"

#: The Ollama endpoint registry, read for the provenance table only. Read directly for
#: the same circular-import reason as the axis files.
OLLAMA_HOSTS_PATH = PROJECT_ROOT / "config" / "synthetic" / "ollama_hosts.yaml"


# ------------------------------------------------------------------
# The method letters
# ------------------------------------------------------------------

#: The letter alphabet the generation methods are labelled from. The letter is the
#: family's **rank** in ``_families.yaml`` indexed into this string -- it is derived at
#: call time and never stored, so reordering that file reorders the letters and no
#: Python constant has to be edited to follow. Ranks beyond ``Z`` raise.
METHOD_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

#: What separates a letter from its phrase in the in-figure key. An em dash (U+2014),
#: which the house font covers.
METHOD_KEY_SEPARATOR = " — "


class UnknownAxisValue(ValueError):
    """Raised when an id has no display string in config.

    Carries the axis *kind*, the offending *value*, and the config files searched, so
    the message alone says what to add and where. A :class:`ValueError` subclass
    because that is what :mod:`.axes` already raises for the sibling condition (an id
    with no axis file), so a caller catching the general case still catches this one.
    """

    def __init__(self, kind: str, value: str, searched: Iterable[str | Path]) -> None:
        self.kind = kind
        self.value = value
        self.searched: tuple[Path, ...] = tuple(Path(p) for p in searched)
        listed = ", ".join(str(p) for p in self.searched) or "(no files searched)"
        super().__init__(
            f"Unknown {kind} id {value!r}: no display string in config. Searched: {listed}. "
            f"Add the id there -- the label layer never falls back to the raw id, because a "
            f"raw id on a published figure is a defect that is only caught at proofing."
        )


# ------------------------------------------------------------------
# Config reading
# ------------------------------------------------------------------


def _load_mapping(path: Path, what: str) -> dict[str, Any]:
    """Parse *path* as a YAML mapping (fail-fast on absent or malformed)."""
    if not path.is_file():
        raise FileNotFoundError(f"{what} not found: {path}.")
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"{what} must be a YAML mapping, got {type(raw).__name__}: {path}")
    return raw


def _axis_document(kind: str, value: str, directory: Path) -> tuple[dict[str, Any], Path]:
    """Return one axis YAML's parsed body and its path, or raise :class:`UnknownAxisValue`."""
    path = directory / f"{value}.yaml"
    if not path.is_file():
        raise UnknownAxisValue(kind, value, [path])
    return _load_mapping(path, f"{kind.capitalize()} axis file"), path


def _display_string(raw: Any, *, field: str, value: str, path: Path) -> str:
    """Validate one config value as a display string, or raise.

    Three conditions, each a defect that would otherwise reach the canvas: a missing or
    non-string value (nothing to print), an empty one (a blank tick label, which reads
    as a rendering bug rather than as a config omission), and one containing an
    underscore (the code-identifier convention no journal guideline sanctions -- see the
    labelling conventions in the presentation-layer plan).
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            f"{path}: {value!r} must declare a non-empty string '{field}', got {raw!r}. "
            f"A display string is required, not optional -- rendering blank is not an option."
        )
    text = raw.strip()
    if "_" in text:
        raise ValueError(
            f"{path}: '{field}' for {value!r} is {text!r}, which contains an underscore. "
            f"Display strings are prose, not identifiers; spell it with spaces."
        )
    return text


# ------------------------------------------------------------------
# The axis resolvers
# ------------------------------------------------------------------


def model_label(model_id: str, *, models_dir: str | Path | None = None) -> str:
    """Return the display name of *model_id*, without its serving provider.

    Read from that model axis YAML's ``display.name`` -- an explicit field, **not** the
    ``label:`` with a provider token split off it. String-splitting on ``openrouter_``
    would encode the provider list in code, break on the next provider, and quietly
    mangle any model whose own name begins with its provider's word.

    The ``display.name`` is also required to be a suffix of ``label:``: the two fields
    describe the same model and differ only by the dropped provider, so a rename of one
    that is not carried to the other is a drift this catches at the first resolve.
    """
    directory = Path(models_dir) if models_dir is not None else MODELS_DIR
    data, path = _axis_document("model", model_id, directory)

    display = data.get("display")
    if not isinstance(display, dict):
        raise ValueError(
            f"{path}: model {model_id!r} must declare a 'display' mapping with a 'name', "
            f"got {display!r}. It carries the provider-free figure name; the serving "
            f"provider is preserved in the generated provenance table instead."
        )
    name = _display_string(display.get("name"), field="display.name", value=model_id, path=path)

    label = data.get("label")
    if isinstance(label, str) and label.strip() and not label.strip().endswith(name):
        raise ValueError(
            f"{path}: model {model_id!r} has label {label.strip()!r} and display.name {name!r}, "
            f"which do not agree -- display.name must be the label with only the serving "
            f"provider dropped. Update both together."
        )
    return name


def model_labels(model_ids: Sequence[str], *, models_dir: str | Path | None = None) -> dict[str, str]:
    """Resolve several model ids at once, preserving the given order."""
    return {model_id: model_label(model_id, models_dir=models_dir) for model_id in dict.fromkeys(model_ids)}


def strategy_label(strategy_id: str, *, strategies_dir: str | Path | None = None) -> str:
    """Return the display phrase of *strategy_id*, from its axis YAML ``label:``.

    Strategies need no ``display:`` block: unlike a model id, a strategy label names no
    serving provider, so there is nothing to drop and the existing field is the whole
    answer. On a figure the method axis is normally rendered as a letter
    (:func:`method_letters`) with this phrase carried in the key.
    """
    directory = Path(strategies_dir) if strategies_dir is not None else STRATEGIES_DIR
    data, path = _axis_document("strategy", strategy_id, directory)
    return _display_string(data.get("label"), field="label", value=strategy_id, path=path)


def strategy_labels(
    strategy_ids: Sequence[str],
    *,
    strategies_dir: str | Path | None = None,
) -> dict[str, str]:
    """Resolve several strategy ids at once, preserving the given order."""
    return {
        strategy_id: strategy_label(strategy_id, strategies_dir=strategies_dir)
        for strategy_id in dict.fromkeys(strategy_ids)
    }


def country_label(country_id: str, *, countries_dir: str | Path | None = None) -> str:
    """Return the display name of *country_id*, from its axis YAML ``label:``.

    Country ids reach the canvas today in titles and filenames (``swedish_02``), so they
    resolve here like any other axis value.
    """
    directory = Path(countries_dir) if countries_dir is not None else COUNTRIES_DIR
    data, path = _axis_document("country", country_id, directory)
    return _display_string(data.get("label"), field="label", value=country_id, path=path)


def attribute_label(attribute: str, *, labels_path: str | Path | None = None) -> str:
    """Return the display phrase of a canonical attribute (``housing_tenure`` -> ``Housing tenure``).

    Read from ``config/analysis/attribute_labels.yaml``, the one place an attribute's
    name is spelled for a reader. Not title-cased or de-underscored on the fly: a
    mechanical transformation gets ``Birth Country Detail`` and ``Age Group`` wrong
    against the sentence-case convention and can never produce a phrase that differs
    from the key at all.
    """
    path = Path(labels_path) if labels_path is not None else ATTRIBUTE_LABELS_PATH
    raw = _load_mapping(path, "Attribute label config")
    labels = raw.get("labels")
    if not isinstance(labels, dict) or not labels:
        raise ValueError(f"{path} must declare a non-empty 'labels' mapping, got {labels!r}.")
    if attribute not in labels:
        raise UnknownAxisValue("attribute", attribute, [path])
    return _display_string(labels[attribute], field=f"labels.{attribute}", value=attribute, path=path)


# ------------------------------------------------------------------
# The manuscript-controlled words and the reference name
# ------------------------------------------------------------------


def figure_term(key: str, *, terms_path: str | Path | None = None) -> str:
    """Return the manuscript-controlled word stored under *key* (``individuals`` -> ``individuals``).

    Read from the ``terms:`` mapping of ``config/analysis/figure_terms.yaml``. These are
    the words the manuscript's terminology rules decide for published artwork
    ("individual", not persona; "strategy", not method), so a chart module never types
    one: a literal would carry the repository's dialect onto the canvas.

    Raises:
        FileNotFoundError: If the terms file is absent.
        UnknownAxisValue: If *key* is not declared.
        ValueError: If the file has no non-empty ``terms`` mapping, or the value is not a
            non-empty display string (or contains an underscore).
    """
    path = Path(terms_path) if terms_path is not None else FIGURE_TERMS_PATH
    raw = _load_mapping(path, "Figure terms config")
    terms = raw.get("terms")
    if not isinstance(terms, dict) or not terms:
        raise ValueError(f"{path} must declare a non-empty 'terms' mapping, got {terms!r}.")
    if key not in terms:
        raise UnknownAxisValue("figure term", key, [path])
    return _display_string(terms[key], field=f"terms.{key}", value=key, path=path)


def reference_source(country_id: str, *, countries_dir: str | Path | None = None) -> str:
    """Return the short name of *country_id*'s reference source (``swedish_02`` -> ``SCB``).

    Read from that country axis YAML's ``display.reference_source``: the statistical
    agency the real population is drawn from. It is **provenance**, not a figure term:
    manuscript-facing artwork calls the real population ``figure_term("reference")``,
    never by its agency. Held per country because a literal ``"SCB"`` would be wrong
    for Italy.

    Raises:
        UnknownAxisValue: If no axis file declares *country_id*.
        ValueError: If the file has no ``display`` mapping, or ``display.reference_source``
            is not a non-empty display string. There is no fallback to the country label.
    """
    directory = Path(countries_dir) if countries_dir is not None else COUNTRIES_DIR
    data, path = _axis_document("country", country_id, directory)
    display = data.get("display")
    if not isinstance(display, dict):
        raise ValueError(
            f"{path}: country {country_id!r} must declare a 'display' mapping with a "
            f"'reference_source', got {display!r}. It names the source of the real population "
            f"on a figure (e.g. 'SCB')."
        )
    return _display_string(
        display.get("reference_source"),
        field="display.reference_source",
        value=country_id,
        path=path,
    )


# ------------------------------------------------------------------
# The scanned-population ids
# ------------------------------------------------------------------

#: What a real-population id is prefixed with. The consistency scan and the realism
#: judge both enumerate the API-sourced population beside the synthetic ones and both
#: name it this way; the prefix is the whole difference between the two id shapes, so
#: it is named once here rather than spelled at each comparison.
REAL_POPULATION_PREFIX = "real_"

#: How a synthetic combination is spelled when a figure has room for the whole thing --
#: the model's provider-free name, then the phrase its method is called. Used where the
#: axis is *populations* rather than models crossed with methods, which is the one case
#: a method letter cannot be read against a row and a column.
COMBINATION_SEPARATOR = " / "


def discover_strategy_ids(strategies_dir: str | Path | None = None) -> list[str]:
    """List the strategy axis ids, sorted. ``_``-prefixed files are index, not values."""
    directory = Path(strategies_dir) if strategies_dir is not None else STRATEGIES_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"Strategy axis directory not found: {directory}.")
    return sorted(p.stem for p in directory.glob("*.yaml") if not p.name.startswith("_"))


def discover_country_ids(countries_dir: str | Path | None = None) -> list[str]:
    """List the country axis ids, sorted. ``_``-prefixed files are index, not values."""
    directory = Path(countries_dir) if countries_dir is not None else COUNTRIES_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"Country axis directory not found: {directory}.")
    return sorted(p.stem for p in directory.glob("*.yaml") if not p.name.startswith("_"))


def population_label(
    population_id: str,
    *,
    models_dir: str | Path | None = None,
    strategies_dir: str | Path | None = None,
    countries_dir: str | Path | None = None,
) -> str:
    """Return what a *scanned population* is called on a figure.

    Two id shapes reach a legend here and nowhere else in the layer: the API-sourced
    reference, spelled ``real_{country}``, and one synthetic run, spelled
    ``{country}_{strategy}_{model}``. Both are resolved through the ordinary axis
    resolvers -- the run slug is decomposed against the *declared* axis ids by
    :func:`~population_synthetic.analysis.utils.axes.decompose_slug`, never by splitting
    on ``_``, because both strategy and model ids contain underscores of their own and a
    naive split silently produces a plausible wrong pair.

    Raises:
        UnknownAxisValue: If *population_id* is neither shape, or names an axis value no
            config declares. As everywhere in this module there is no fallback to the raw
            id: a legend reading ``swedish_02_all_pick_v2_claude_haiku`` is exactly the
            defect this layer exists to make impossible.
    """
    countries = Path(countries_dir) if countries_dir is not None else COUNTRIES_DIR
    strategies = Path(strategies_dir) if strategies_dir is not None else STRATEGIES_DIR
    models = Path(models_dir) if models_dir is not None else MODELS_DIR

    if population_id.startswith(REAL_POPULATION_PREFIX):
        country = population_id[len(REAL_POPULATION_PREFIX):]
        return f"{country_label(country, countries_dir=countries)} real population"

    decomposed = decompose_slug(
        population_id,
        discover_country_ids(countries),
        discover_strategy_ids(strategies),
        discover_model_ids(models),
    )
    if decomposed is None:
        raise UnknownAxisValue("population", population_id, [countries, strategies, models])
    _country, strategy, model = decomposed
    return (
        f"{model_label(model, models_dir=models)}"
        f"{COMBINATION_SEPARATOR}"
        f"{strategy_label(strategy, strategies_dir=strategies)}"
    )


# ------------------------------------------------------------------
# The method letters
# ------------------------------------------------------------------


@dataclass(frozen=True)
class _MethodAssignment:
    """One strategy id's letter and the config facts it was derived from."""

    strategy_id: str
    letter: str
    family: str
    version: int
    versioned: bool


def _family_labels(directory: Path) -> dict[str, str]:
    """Map each declared family id to its display label (fail-fast).

    ``load_family_order`` is called first so the index's *structure* is validated in
    exactly one place -- this function only adds the label of each already-validated
    entry, which :mod:`.axes` has no use for.
    """
    order = load_family_order(directory)
    path = directory / FAMILIES_FILENAME
    raw = _load_mapping(path, "Strategy family index")
    labels: dict[str, str] = {}
    for entry in raw["families"]:
        family_id = entry["id"]
        labels[family_id] = _display_string(entry.get("label"), field="label", value=family_id, path=path)
    return {family_id: labels[family_id] for family_id in order}


def _method_assignments(
    strategy_ids: Sequence[str],
    directory: Path,
) -> list[_MethodAssignment]:
    """Assign a letter to each id, simplest family first.

    The letter is the family's position in ``_families.yaml`` indexed into
    :data:`METHOD_LETTERS`, so it is a property of the *family*, not of the id set: a
    figure showing only families 1 and 3 shows A and C, never A and B, which is what
    lets two figures with different arms be read against each other.

    The version marker is the opposite -- a property of the *set*. v1 and v2 are
    distinct analysis levels the pipeline never pools, so a set containing both
    versions of a family must distinguish them, and a set containing one version has
    nothing to distinguish and takes the bare letter.
    """
    ordered = strategy_complexity_order(list(strategy_ids), strategies_dir=directory)
    families = strategy_families(ordered, strategies_dir=directory)
    versions = strategy_versions(ordered, strategies_dir=directory)
    rank = {family: index for index, family in enumerate(load_family_order(directory))}

    versions_per_family: dict[str, set[int]] = {}
    for strategy_id in ordered:
        versions_per_family.setdefault(families[strategy_id], set()).add(versions[strategy_id])

    assignments: list[_MethodAssignment] = []
    for strategy_id in ordered:
        family = families[strategy_id]
        index = rank[family]
        if index >= len(METHOD_LETTERS):
            raise ValueError(
                f"Family {family!r} has rank {index} in {directory / FAMILIES_FILENAME}, beyond the "
                f"{len(METHOD_LETTERS)} letters available. A method axis this wide needs a labelling "
                f"scheme decided deliberately, not a wrapped or repeated letter."
            )
        versioned = len(versions_per_family[family]) > 1
        version = versions[strategy_id]
        letter = f"{METHOD_LETTERS[index]}{version}" if versioned else METHOD_LETTERS[index]
        assignments.append(
            _MethodAssignment(
                strategy_id=strategy_id,
                letter=letter,
                family=family,
                version=version,
                versioned=versioned,
            )
        )
    return assignments


def method_letters(
    strategy_ids: Sequence[str],
    *,
    strategies_dir: str | Path | None = None,
) -> dict[str, str]:
    """Map each strategy id to its method letter, in simplest-first order.

    ``{"all_pick": "A", "all_pick_dag": "B", ...}`` for a single-version set;
    ``{"all_pick_dag": "B1", "all_pick_dag_v2": "B2", ...}`` where the set holds both
    versions of a family. Insertion order is
    :func:`~population_synthetic.analysis.utils.axes.strategy_complexity_order`, so the
    result doubles as the axis order and no caller has to sort it again.

    The version marker is set as a plain digit rather than a Unicode subscript: the
    house font has no U+2080-2089 glyphs, so a true subscript would render as a
    missing-glyph box or silently pull a second typeface in through matplotlib's
    per-glyph fallback. Mathtext (``$B_1$``) would render, but is matplotlib syntax and
    this module must not know that a renderer exists.

    Raises whatever ``strategy_complexity_order`` raises -- an unknown id, missing or
    malformed ``family``/``version``, or a family absent from the family index.
    """
    directory = Path(strategies_dir) if strategies_dir is not None else STRATEGIES_DIR
    return {a.strategy_id: a.letter for a in _method_assignments(strategy_ids, directory)}


def method_key_lines(
    strategy_ids: Sequence[str],
    *,
    strategies_dir: str | Path | None = None,
) -> list[str]:
    """Return the in-figure key: one line per method letter, simplest first.

    ``["A -- All Pick", "B1 -- All Pick DAG (v1)", ...]`` (with an em dash). The phrase
    is the **family** label from ``_families.yaml``, not the strategy label, because the
    letter names the family; a versioned letter appends its version so the two lines of
    a split family are not two identical phrases.

    The key travels with the graphic rather than being deferred to the caption, which
    is what PLOS and Springer require of a figure key; captions repeat it.
    """
    directory = Path(strategies_dir) if strategies_dir is not None else STRATEGIES_DIR
    assignments = _method_assignments(strategy_ids, directory)
    family_labels = _family_labels(directory)
    lines: list[str] = []
    for assignment in assignments:
        phrase = family_labels[assignment.family]
        if assignment.versioned:
            phrase = f"{phrase} (v{assignment.version})"
        lines.append(f"{assignment.letter}{METHOD_KEY_SEPARATOR}{phrase}")
    return lines


# ------------------------------------------------------------------
# The provenance table
# ------------------------------------------------------------------

#: The provenance table's columns, in order. This is where the provenance dropped from
#: the figure axes is kept: the serving provider, the exact model string that provider
#: was asked for, the endpoint, and -- for the locally served models -- which machine
#: answered. HELM-style papers put it in a table for the same reason.
PROVENANCE_COLUMNS = (
    "model_id",
    "model",
    "provider",
    "api_model",
    "endpoint",
    "host",
    "host_label",
    "discarded",
)

#: What separates the entries of a multi-valued provenance cell (a model served by more
#: than one Ollama host).
PROVENANCE_JOIN = "; "


def discover_model_ids(models_dir: str | Path | None = None) -> list[str]:
    """List the model axis ids, sorted.

    ``_``-prefixed files are skipped, matching ``discover_axis_values``: the underscore
    is what marks a file in an axis directory as index or scratch rather than as a
    selectable axis value.
    """
    directory = Path(models_dir) if models_dir is not None else MODELS_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"Model axis directory not found: {directory}.")
    return sorted(p.stem for p in directory.glob("*.yaml") if not p.name.startswith("_"))


def _require_bool(raw: Any, *, field: str, value: str, path: Path, default: bool) -> bool:
    """Read an optional boolean flag; absent means *default*, anything non-boolean raises."""
    if raw is None:
        return default
    if not isinstance(raw, bool):
        raise ValueError(f"{path}: '{field}' for {value!r} must be a boolean, got {raw!r}.")
    return raw


def _ollama_serving(
    model_id: str,
    data: dict[str, Any],
    path: Path,
    hosts: dict[str, Any],
    hosts_path: Path,
) -> tuple[list[str], list[str], list[str]]:
    """Return the (host ids, endpoints, host labels) serving one Ollama model.

    The per-host worker map in the axis file is the declaration of *which* hosts serve
    the model (an absent host does not serve it); the endpoint and the machine's
    description come from the host registry. A host named in the axis file but absent
    from the registry raises -- it is an endpoint nothing can resolve.
    """
    parallel = (data.get("parameters") or {}).get("parallel") or {}
    workers = parallel.get("workers")
    if not isinstance(workers, dict) or not workers:
        raise ValueError(
            f"{path}: ollama model {model_id!r} must declare 'parameters.parallel.workers' as a "
            f"per-host mapping, got {workers!r}. The map's keys are the hosts that serve it."
        )
    declared = [host_id for host_id in hosts if host_id in workers]
    unknown = sorted(set(workers) - set(hosts))
    if unknown:
        raise ValueError(
            f"{path}: ollama model {model_id!r} names host(s) {unknown} that {hosts_path} does not "
            f"declare (known: {sorted(hosts)}). The host registry is the only source of endpoints."
        )
    endpoints: list[str] = []
    labels: list[str] = []
    for host_id in declared:
        entry = hosts[host_id]
        if not isinstance(entry, dict):
            raise ValueError(f"{hosts_path}: host {host_id!r} must be a mapping, got {entry!r}.")
        for field in ("base_url", "label"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"{hosts_path}: host {host_id!r} must declare a non-empty '{field}'.")
        endpoints.append(entry["base_url"].strip())
        labels.append(entry["label"].strip())
    return declared, endpoints, labels


def model_provenance_rows(
    *,
    models_dir: str | Path | None = None,
    hosts_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """One provenance record per model axis, keyed by :data:`PROVENANCE_COLUMNS`.

    ``model`` is the figure display name, so a reader can carry a name off a chart and
    find the row that says how it was served. ``api_model`` is the exact string the
    provider was asked for -- the OpenRouter arms are routed by it and a re-quantized
    route is invisible without it. ``host``/``host_label``/``endpoint`` are filled for
    the locally served models, whose two machines are different GPUs.

    An **empty** ``endpoint``, ``host`` or ``host_label`` is an explicit absent marker,
    not a default: a remote provider is reached at its SDK's own endpoint, which the
    axis config deliberately does not pin, and it runs on no machine of ours. Every
    other cell is required and raises when absent.
    """
    directory = Path(models_dir) if models_dir is not None else MODELS_DIR
    registry_path = Path(hosts_path) if hosts_path is not None else OLLAMA_HOSTS_PATH

    hosts_doc = _load_mapping(registry_path, "Ollama host registry")
    hosts = hosts_doc.get("hosts")
    if not isinstance(hosts, dict) or not hosts:
        raise ValueError(f"{registry_path} must declare a non-empty 'hosts' mapping, got {hosts!r}.")

    rows: list[dict[str, Any]] = []
    for model_id in discover_model_ids(directory):
        data, path = _axis_document("model", model_id, directory)
        model_config = data.get("model_config")
        if not isinstance(model_config, dict):
            raise ValueError(f"{path}: model {model_id!r} must declare a 'model_config' mapping.")
        for field in ("provider", "model"):
            if not isinstance(model_config.get(field), str) or not model_config[field].strip():
                raise ValueError(f"{path}: model {model_id!r} must declare a non-empty 'model_config.{field}'.")

        provider = model_config["provider"].strip()
        if provider == "ollama":
            host_ids, endpoints, host_labels = _ollama_serving(model_id, data, path, hosts, registry_path)
        else:
            declared_url = model_config.get("base_url")
            host_ids, host_labels = [], []
            endpoints = [declared_url.strip()] if isinstance(declared_url, str) and declared_url.strip() else []

        rows.append(
            {
                "model_id": model_id,
                "model": model_label(model_id, models_dir=directory),
                "provider": provider,
                "api_model": model_config["model"].strip(),
                "endpoint": PROVENANCE_JOIN.join(endpoints),
                "host": PROVENANCE_JOIN.join(host_ids),
                "host_label": PROVENANCE_JOIN.join(host_labels),
                "discarded": _require_bool(
                    data.get("discarded"), field="discarded", value=model_id, path=path, default=False
                ),
            }
        )
    return rows

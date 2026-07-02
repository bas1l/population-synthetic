"""Per-country comparison scheme: the in-scope attributes and DB-exact category
sets that drive population comparison.

The scheme is the single source of truth for *what the comparison scores*: which
demographic properties are compared for a country and, per property, the exact
category set the country's real-population database emits. It is curated empirically --
each category list is the distinct non-None values the real mapper produces
over that country's real population -- so the comparison axis has no
empty buckets, no DB-absent properties, and no mapper-synthesized categories.

The scheme is sourced from two config trees. The mapping side --
``config/mapping/{scb,istat}`` -- supplies the scored axis: the ``_index.json`` master
lists the in-scope attributes (ordered) and each per-attribute file's ``values`` list
*is* that attribute's comparison category set. Because both mappers now emit only
declared ``values``, the scored axis equals the ``values`` and no separate filter is
needed. The cross-attribute statistics -- ``joint_pairs``, ``coherence_attributes`` and
``coherence_threshold`` -- come from a separate comparison-analysis config,
``config/analysis/comparison/{country}.json``, which is pure evaluator tuning and has
nothing to do with mapping. A directory still carrying the legacy ``_scheme.json``
(pre-migration) is read through the unchanged legacy path, which bundles all four.

``age_group`` appears as a comparison dimension even though populations store only
the raw integer ``age``; the evaluator derives the age bin on the fly (see
``evaluator.attr_value``). Its categories are the age-bin labels declared as
``values`` in ``age.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.mapping.real_mapper.factory import _mapper_class
from population_synthetic.analysis.mapping.real_mapper.mappings import index_path, load_index

_MAPPINGS_ROOT = PROJECT_ROOT / "config" / "mapping"
_ANALYSIS_ROOT = PROJECT_ROOT / "config" / "analysis" / "comparison"
_SCHEME_FILENAME = "_scheme.json"
_DEFAULT_COHERENCE_THRESHOLD = 0.001


@dataclass(frozen=True)
class GroundedJointPair:
    """One attribute pair with its API-grounding verdict for joint-fidelity scoring.

    ``grounded`` is ``True`` when the real population's joint over ``pair`` comes from a
    real API conditional cross-tabulation (so validating a synthetic joint against it is
    meaningful) and ``False`` when the reference joint is itself a marginal product or a
    forced-independence copy (validating against it would over-claim fidelity). ``basis``
    records the audit finding that justifies the verdict (see
    ``docs/scb_population_distribution_analysis.md``).
    """

    pair: tuple[str, str]
    grounded: bool
    basis: str = ""


@dataclass(frozen=True)
class CombinationCheck:
    """One configurable k-way combination-plausibility check.

    Generalises the legacy age x education x employment coherence triple to an arbitrary
    ``attributes`` tuple; ``k`` is the tuple arity and ``threshold`` the rare-support
    cut-off (a combination with real support below ``threshold`` is flagged rare; zero
    support is impossible).
    """

    attributes: tuple[str, ...]
    k: int
    threshold: float


@dataclass(frozen=True)
class C2STConfig:
    """Classifier-two-sample-test tuning (cross-validation folds, backend, seed)."""

    folds: int
    method: str
    seed: int


@dataclass(frozen=True)
class ComparisonScheme:
    """In-scope attributes and DB-exact category sets for one country.

    ``attributes``/``categories`` describe the scored marginal axis (sourced from the
    mapping config); ``joint_pairs``/``coherence_attributes``/``coherence_threshold``
    are the cross-attribute evaluator tuning (sourced from the analysis config).

    ``grounded_joint_pairs``/``combination_checks``/``c2st_config`` are the multivariate
    evaluator tuning, also sourced from the analysis config. They are additive and
    backward compatible: when a key is genuinely absent from the config,
    ``grounded_joint_pairs`` and ``combination_checks`` default to empty tuples and
    ``c2st_config`` to ``None``. A key that is *present but malformed* fails loudly.
    """

    attributes: list[str]
    categories: dict[str, list[str]]
    joint_pairs: list[tuple[str, str]]
    coherence_attributes: tuple[str, ...]
    coherence_threshold: float
    grounded_joint_pairs: tuple[GroundedJointPair, ...] = ()
    combination_checks: tuple[CombinationCheck, ...] = ()
    c2st_config: C2STConfig | None = None


def _scheme_dir(country: str, mappings_path: Path | None) -> Path:
    if mappings_path is not None:
        return mappings_path
    # Reuse the real-mapper country dispatch (raises for unknown country).
    subdir = _mapper_class(country).MAPPINGS_SUBDIR
    return _MAPPINGS_ROOT / subdir


def _analysis_path(country: str, analysis_path: Path | None) -> Path:
    if analysis_path is not None:
        return analysis_path
    # Filename stem == the mapper's MAPPINGS_SUBDIR (scb.json / istat.json).
    subdir = _mapper_class(country).MAPPINGS_SUBDIR
    return _ANALYSIS_ROOT / f"{subdir}.json"


def _parse_grounded_joint_pairs(raw: dict, source: Path) -> tuple[GroundedJointPair, ...]:
    """Parse the optional ``grounded_joint_pairs`` block.

    Absent key -> empty tuple (backward compatible). Present-but-malformed -> raise.
    Each entry is an object ``{"pair": [attr_x, attr_y], "grounded": bool, "basis": str}``
    where ``basis`` is optional documentation.
    """
    if "grounded_joint_pairs" not in raw:
        return ()
    entries = raw["grounded_joint_pairs"]
    if not isinstance(entries, list):
        raise ValueError(f"Comparison-analysis config {source}: 'grounded_joint_pairs' must be a list")

    parsed: list[GroundedJointPair] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Comparison-analysis config {source}: 'grounded_joint_pairs' entries must be objects")
        for key in ("pair", "grounded"):
            if key not in entry:
                raise KeyError(f"Comparison-analysis config {source}: 'grounded_joint_pairs' entry missing key {key!r}")
        pair = entry["pair"]
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"Comparison-analysis config {source}: 'grounded_joint_pairs' pair must be a [x, y] list")
        if not isinstance(entry["grounded"], bool):
            raise ValueError(f"Comparison-analysis config {source}: 'grounded_joint_pairs' 'grounded' must be bool")
        parsed.append(
            GroundedJointPair(
                pair=(str(pair[0]), str(pair[1])),
                grounded=entry["grounded"],
                basis=str(entry.get("basis", "")),
            )
        )
    return tuple(parsed)


def _parse_combination_checks(raw: dict, source: Path) -> tuple[CombinationCheck, ...]:
    """Parse the optional ``combination_checks`` block.

    Absent key -> empty tuple. Present-but-malformed -> raise. Each entry is
    ``{"attributes": [...], "k": int, "threshold": float}``.
    """
    if "combination_checks" not in raw:
        return ()
    entries = raw["combination_checks"]
    if not isinstance(entries, list):
        raise ValueError(f"Comparison-analysis config {source}: 'combination_checks' must be a list")

    parsed: list[CombinationCheck] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Comparison-analysis config {source}: each 'combination_checks' entry must be an object")
        for key in ("attributes", "k", "threshold"):
            if key not in entry:
                raise KeyError(f"Comparison-analysis config {source}: 'combination_checks' entry missing key {key!r}")
        attributes = entry["attributes"]
        if not isinstance(attributes, list) or not attributes:
            raise ValueError(f"Config {source}: 'combination_checks' 'attributes' must be a non-empty list")
        if not isinstance(entry["k"], int) or isinstance(entry["k"], bool):
            raise ValueError(f"Comparison-analysis config {source}: 'combination_checks' 'k' must be an integer")
        if not isinstance(entry["threshold"], (int, float)) or isinstance(entry["threshold"], bool):
            raise ValueError(f"Comparison-analysis config {source}: 'combination_checks' 'threshold' must be a number")
        parsed.append(
            CombinationCheck(
                attributes=tuple(str(a) for a in attributes),
                k=entry["k"],
                threshold=float(entry["threshold"]),
            )
        )
    return tuple(parsed)


def _parse_c2st(raw: dict, source: Path) -> C2STConfig | None:
    """Parse the optional ``c2st`` block.

    Absent key -> ``None``. Present-but-malformed -> raise. Shape:
    ``{"folds": int, "method": str, "seed": int}``.
    """
    if "c2st" not in raw:
        return None
    cfg = raw["c2st"]
    if not isinstance(cfg, dict):
        raise ValueError(f"Comparison-analysis config {source}: 'c2st' must be an object")
    for key in ("folds", "method", "seed"):
        if key not in cfg:
            raise KeyError(f"Comparison-analysis config {source}: 'c2st' missing key {key!r}")
    if not isinstance(cfg["folds"], int) or isinstance(cfg["folds"], bool):
        raise ValueError(f"Comparison-analysis config {source}: 'c2st' 'folds' must be an integer")
    if not isinstance(cfg["method"], str):
        raise ValueError(f"Comparison-analysis config {source}: 'c2st' 'method' must be a string")
    if not isinstance(cfg["seed"], int) or isinstance(cfg["seed"], bool):
        raise ValueError(f"Comparison-analysis config {source}: 'c2st' 'seed' must be an integer")
    return C2STConfig(folds=cfg["folds"], method=cfg["method"], seed=cfg["seed"])


def _load_analysis_config(
    path: Path,
) -> tuple[
    list[tuple[str, str]],
    tuple[str, ...],
    float,
    tuple[GroundedJointPair, ...],
    tuple[CombinationCheck, ...],
    C2STConfig | None,
]:
    """Read the comparison-analysis config for one country.

    Returns ``(joint_pairs, coherence_attributes, coherence_threshold,
    grounded_joint_pairs, combination_checks, c2st_config)``. Fails loudly on a missing
    file or a missing ``joint_pairs``/``coherence_attributes`` key; ``coherence_threshold``
    defaults to :data:`_DEFAULT_COHERENCE_THRESHOLD` when absent. The three multivariate
    keys are optional (default empty/None when absent) but fail loudly when malformed.
    """
    if not path.is_file():
        raise FileNotFoundError(f"No comparison-analysis config found: {path} not found")

    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    for key in ("joint_pairs", "coherence_attributes"):
        if key not in raw:
            raise KeyError(f"Comparison-analysis config {path} is missing required key {key!r}")

    joint_pairs = [tuple(pair) for pair in raw["joint_pairs"]]
    coherence_attributes = tuple(raw["coherence_attributes"])
    coherence_threshold = float(raw.get("coherence_threshold", _DEFAULT_COHERENCE_THRESHOLD))
    grounded_joint_pairs = _parse_grounded_joint_pairs(raw, path)
    combination_checks = _parse_combination_checks(raw, path)
    c2st_config = _parse_c2st(raw, path)
    return (
        joint_pairs,
        coherence_attributes,
        coherence_threshold,
        grounded_joint_pairs,
        combination_checks,
        c2st_config,
    )


def load_scheme(
    country: str = "swedish",
    mappings_path: Path | None = None,
    analysis_path: Path | None = None,
) -> ComparisonScheme:
    """Load the comparison scheme for *country* (``"swedish"`` or ``"italian"``).

    The scored marginal axis is sourced from the mapping config: the ``_index.json``
    master supplies the in-scope attributes (ordered) and each per-attribute file's
    ``values`` list supplies that attribute's DB-grounded category set (``age_group``'s
    categories are the age-bin labels declared as ``values`` in ``age.json``). The
    cross-attribute statistics (``joint_pairs``/``coherence_attributes``/
    ``coherence_threshold``) are sourced from the comparison-analysis config
    ``config/analysis/comparison/{country}.json``.

    A country directory that still ships the legacy ``_scheme.json`` (and no
    ``_index.json``) is read through the pre-migration path unchanged -- there the
    cross-attribute statistics come from that same file. Fails loudly on a missing
    master/legacy/analysis file, a missing required key, or a per-attribute file that
    omits ``values``. *analysis_path* overrides the analysis-config location (for tests).
    """
    directory = _scheme_dir(country, mappings_path)

    if index_path(directory).is_file():
        return _scheme_from_index(directory, _analysis_path(country, analysis_path))

    return _scheme_from_legacy(country, directory)


def _scheme_from_index(directory: Path, analysis_path: Path) -> ComparisonScheme:
    """Build a :class:`ComparisonScheme` from ``_index.json`` + per-file ``values``
    (marginal axis) and the comparison-analysis config (cross-attribute statistics)."""
    index = load_index(directory)

    attributes: list[str] = list(index["attributes"].keys())  # key order = axis order
    categories: dict[str, list[str]] = {}
    for attr, filename in index["attributes"].items():
        attr_path = directory / filename
        if not attr_path.is_file():
            raise FileNotFoundError(
                f"Comparison scheme for attribute {attr!r} references missing file {attr_path}"
            )
        with open(attr_path, "r", encoding="utf-8") as fh:
            block = json.load(fh)
        if "values" not in block:
            raise KeyError(f"Mapping file {attr_path} is missing required key 'values'")
        categories[attr] = list(block["values"])

    (
        joint_pairs,
        coherence_attributes,
        coherence_threshold,
        grounded_joint_pairs,
        combination_checks,
        c2st_config,
    ) = _load_analysis_config(analysis_path)

    return ComparisonScheme(
        attributes=attributes,
        categories=categories,
        joint_pairs=joint_pairs,
        coherence_attributes=coherence_attributes,
        coherence_threshold=coherence_threshold,
        grounded_joint_pairs=grounded_joint_pairs,
        combination_checks=combination_checks,
        c2st_config=c2st_config,
    )


def _scheme_from_legacy(country: str, directory: Path) -> ComparisonScheme:
    """Build a :class:`ComparisonScheme` from a pre-migration ``_scheme.json`` file."""
    scheme_path = directory / _SCHEME_FILENAME
    if not scheme_path.is_file():
        raise FileNotFoundError(f"No comparison scheme for country {country!r}: {scheme_path} not found")

    with open(scheme_path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    for key in ("attributes", "categories", "joint_pairs", "coherence_attributes"):
        if key not in raw:
            raise KeyError(f"Comparison scheme {scheme_path} is missing required key {key!r}")

    attributes = list(raw["attributes"])
    categories = {attr: list(vals) for attr, vals in raw["categories"].items()}

    missing = [attr for attr in attributes if attr not in categories]
    if missing:
        raise KeyError(f"Comparison scheme {scheme_path} declares attributes without categories: {missing}")

    joint_pairs = [tuple(pair) for pair in raw["joint_pairs"]]
    coherence_attributes = tuple(raw["coherence_attributes"])
    coherence_threshold = float(raw.get("coherence_threshold", _DEFAULT_COHERENCE_THRESHOLD))
    grounded_joint_pairs = _parse_grounded_joint_pairs(raw, scheme_path)
    combination_checks = _parse_combination_checks(raw, scheme_path)
    c2st_config = _parse_c2st(raw, scheme_path)

    return ComparisonScheme(
        attributes=attributes,
        categories=categories,
        joint_pairs=joint_pairs,
        coherence_attributes=coherence_attributes,
        coherence_threshold=coherence_threshold,
        grounded_joint_pairs=grounded_joint_pairs,
        combination_checks=combination_checks,
        c2st_config=c2st_config,
    )

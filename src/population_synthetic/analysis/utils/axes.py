"""axes.py -- Axis-vocabulary helpers shared across analysis processes.

Slug decomposition against the axis-ID registries (``decompose_slug`` /
``diagnose_slug``) and the presentation ordering of the strategy axis
(:func:`strategy_complexity_order`). Both are consumed by the fidelity,
generation-metadata, model-ranking, method-significance, and
multivariate-fidelity processes, so they live in the cross-process
``analysis/utils`` layer rather than in any one pipeline.

Strategy ordering is **config-derived**, not a Python list: the family order comes
from ``config/synthetic/axes/strategies/_families.yaml`` and each strategy's
``family``/``version`` from its own axis YAML. It is exposed as a *function*, not a
module constant, so nothing is read at import time and there is no mutable global
config singleton -- every caller resolves the order for the ids it actually has.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from population_synthetic._paths import PROJECT_ROOT

# The strategy axis directory: both the per-strategy YAMLs and the family index.
# Read directly (not via ``generators.synthetic.manifest_loader``) because that
# module imports from ``analysis.utils`` -- routing through it would be circular.
STRATEGIES_DIR = PROJECT_ROOT / "config" / "synthetic" / "axes" / "strategies"

# The family-ordering index inside :data:`STRATEGIES_DIR`. The ``_`` prefix is what
# keeps ``discover_axis_values("strategies")`` from loading it as a strategy.
FAMILIES_FILENAME = "_families.yaml"


def load_family_order(strategies_dir: str | Path | None = None) -> list[str]:
    """Return the declared family ids, simplest first (fail-fast on a bad index).

    The list position **is** the family rank. Raises :class:`FileNotFoundError`
    when the index is absent and :class:`ValueError` when it is malformed, empty,
    or declares a duplicate id -- a silently defaulted family order would move the
    manuscript's global-best-strategy tie-break without any signal.
    """
    directory = Path(strategies_dir) if strategies_dir is not None else STRATEGIES_DIR
    path = directory / FAMILIES_FILENAME
    if not path.is_file():
        raise FileNotFoundError(
            f"Strategy family index not found: {path}. It declares the total "
            "simplest-first family order the analysis axis is sorted by."
        )
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"Strategy family index must be a YAML mapping, got {type(raw).__name__}: {path}")

    families = raw.get("families")
    if not isinstance(families, list) or not families:
        raise ValueError(
            f"Strategy family index {path} must have a non-empty 'families' list, got {families!r}."
        )

    order: list[str] = []
    for entry in families:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
            raise ValueError(
                f"Strategy family index {path} entries must be mappings with a non-empty "
                f"string 'id', got {entry!r}."
            )
        if entry["id"] in order:
            raise ValueError(
                f"Strategy family index {path} declares family {entry['id']!r} twice; "
                "the family order must be a strict sequence."
            )
        order.append(entry["id"])
    return order


def _strategy_family_version(strategy_id: str, strategies_dir: Path) -> tuple[str, int]:
    """Read one strategy YAML's ``(family, version)`` pair (fail-fast).

    Mirrors the ``_scheme_from_index`` fail-loud idiom: an absent file, an absent
    key, or a malformed value raises rather than defaulting -- an ordering that
    silently guessed a family would reorder published results.
    """
    path = strategies_dir / f"{strategy_id}.yaml"
    if not path.is_file():
        raise ValueError(
            f"Unknown strategy id {strategy_id!r}: no axis file at {path}. The strategy "
            "axis YAMLs are the single source of truth for family/version."
        )
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Strategy axis file must be a YAML mapping, got {type(data).__name__}: {path}")

    family = data.get("family")
    if not isinstance(family, str) or not family:
        raise ValueError(
            f"Strategy {strategy_id!r} ({path}) must declare a non-empty string 'family', "
            f"got {family!r}."
        )
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError(
            f"Strategy {strategy_id!r} ({path}) must declare an integer 'version' >= 1, "
            f"got {version!r}."
        )
    return family, version


def strategy_versions(
    strategy_ids: list[str],
    *,
    strategies_dir: str | Path | None = None,
) -> dict[str, int]:
    """Map each id in *strategy_ids* to its declared integer ``version`` (fail-fast).

    The version is read from the strategy's own axis YAML, never inferred from an id
    suffix. It exists for **ordering and presentation** -- it is the second component
    of :func:`strategy_complexity_order`'s sort key, which is what keeps each v2 next
    to its v1 sibling. No analysis process branches on it: a versioned id is simply
    its own strategy. Raises on the same conditions as
    :func:`strategy_complexity_order` (unknown id, missing/malformed metadata).
    """
    directory = Path(strategies_dir) if strategies_dir is not None else STRATEGIES_DIR
    return {
        strategy_id: _strategy_family_version(strategy_id, directory)[1]
        for strategy_id in dict.fromkeys(strategy_ids)
    }


def strategy_complexity_order(
    strategy_ids: list[str],
    *,
    strategies_dir: str | Path | None = None,
) -> list[str]:
    """Order *strategy_ids* simplest-first by ``(family_rank, version, id)``.

    The result is a **total** order over the given ids: family rank comes from
    ``_families.yaml`` (declaration position), then ascending ``version`` within a
    family, then the id itself so no two entries can ever compare equal. Totality is
    load-bearing -- the manuscript's global-best-strategy rule breaks ties by
    preferring the *earlier* (simpler) strategy, so an unstable or partial order
    would silently move a published result.

    Duplicate ids are collapsed (each id appears once). Raises :class:`ValueError`
    when an id has no axis file, when its ``family``/``version`` is missing or
    malformed, or when its family is not declared in the family index -- never
    "sorts unknown last", which hides an axis-naming drift behind a plausible chart.
    """
    directory = Path(strategies_dir) if strategies_dir is not None else STRATEGIES_DIR
    family_rank = {family: rank for rank, family in enumerate(load_family_order(directory))}

    unique = list(dict.fromkeys(strategy_ids))
    keys: dict[str, tuple[int, int, str]] = {}
    for strategy_id in unique:
        family, version = _strategy_family_version(strategy_id, directory)
        if family not in family_rank:
            raise ValueError(
                f"Strategy {strategy_id!r} declares family {family!r}, which is not in the "
                f"family index {directory / FAMILIES_FILENAME} "
                f"(declared: {list(family_rank)}). Add the family there to give it a rank."
            )
        keys[strategy_id] = (family_rank[family], version, strategy_id)

    return sorted(unique, key=lambda s: keys[s])


def decompose_slug(
    slug: str,
    country_ids: list[str],
    strategy_ids: list[str],
    model_ids: list[str],
) -> tuple[str, str, str] | None:
    """Decompose ``{country}_{strategy}_{model}`` using the known ID registries.

    Slugs are not parseable by naive ``_`` split because both strategy and model
    IDs contain underscores.  We match a country prefix, then the longest model
    suffix that leaves a valid strategy in the middle.  Returns ``None`` when the
    slug does not correspond to a known axis combination (e.g. legacy ``seed_*``).
    """
    strategy_set = set(strategy_ids)
    for country in country_ids:
        if slug != country and not slug.startswith(country + "_"):
            continue
        rest = slug[len(country):].lstrip("_")
        for model in sorted(model_ids, key=len, reverse=True):
            if rest == model or rest.endswith("_" + model):
                strategy = rest[: len(rest) - len(model)].rstrip("_")
                if strategy in strategy_set:
                    return country, strategy, model
    return None


def diagnose_slug(
    slug: str,
    country_ids: list[str],
    strategy_ids: list[str],
    model_ids: list[str],
) -> str:
    """Explain *why* :func:`decompose_slug` returned ``None`` for *slug*.

    Mirrors the decomposition steps to report which axis (country / model /
    strategy) failed to match, so axis-naming drift is diagnosable rather than a
    silent skip.  Assumes the slug is undecomposable (caller checks first).
    """
    matched_country = next(
        (c for c in country_ids if slug == c or slug.startswith(c + "_")), None
    )
    if matched_country is None:
        return (
            "slug not decomposable: no known country prefix "
            f"(known: {', '.join(sorted(country_ids))})"
        )
    rest = slug[len(matched_country):].lstrip("_")
    matched_model = next(
        (m for m in sorted(model_ids, key=len, reverse=True)
         if rest == m or rest.endswith("_" + m)),
        None,
    )
    if matched_model is None:
        return (
            f"slug not decomposable: country '{matched_country}' ok, but no known "
            f"model suffix (known: {', '.join(sorted(model_ids))})"
        )
    middle = rest[: len(rest) - len(matched_model)].rstrip("_")
    return (
        f"slug not decomposable: country '{matched_country}' + model "
        f"'{matched_model}' ok, but middle '{middle}' is not a known strategy "
        f"(known: {', '.join(sorted(strategy_ids))})"
    )

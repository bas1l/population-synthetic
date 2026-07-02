"""axes.py -- Axis-vocabulary helpers shared across analysis processes.

Slug decomposition against the axis-ID registries (``decompose_slug`` /
``diagnose_slug``) and the presentation ordering of the strategy axis
(:data:`STRATEGY_COMPLEXITY_ORDER`). Both are consumed by the comparison,
llm_metrics cross-run, and performance processes, so they live in the
cross-process ``analysis/utils`` layer rather than in any one pipeline.
"""

from __future__ import annotations

# Strategy axis ordered by pipeline complexity (simplest first); used to order
# strategy columns/groups consistently across charts.
STRATEGY_COMPLEXITY_ORDER = [
    "all_pick",
    "all_pick_dag",
    "all_generate_pick",
    "all_generate_evaluate_pick",
    "all_generate_evaluate_random_pick",
]


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

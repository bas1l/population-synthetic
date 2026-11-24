"""grid_variants.py -- The two publications every annotated grid in the layer emits.

A grid figure is published **twice from one renderer**: once with the count each cell
rests on printed beneath the number, and once with the number alone. The two are the same
figure in every other respect -- same rows, same columns, same extent, same colour scale,
same markings -- because the only thing that varies between them is the annotation policy
handed to :func:`~population_synthetic.analysis.utils.grids.render_grid`. Holding that
difference in a record rather than in a second draw function is what keeps the property
true: a change to the grid is made once and both variants inherit it.

**The canonical, unsuffixed filename is the clean figure.** That is the camera-ready
artifact, and a manuscript figure that prints ``n=267`` in every cell of a grid whose
denominator is constant down the column is printing noise: the count is already in the
CSV the grid was drawn from, and in the marginals of the grids that carry them. The
counted form keeps every one of those numbers and is written beside it as
``..._with_counts``, so dropping the line from the canonical figure costs ink rather than
evidence -- and no re-run is needed to get it back.

The rule is **uniform across every grid family that publishes variants**, and the suffix
is derived here rather than at each driver, so five call sites cannot end up with five
naming schemes. A family declares its two variants and its driver enumerates them through
:func:`variant_suffixes`; adding a third variant publishes it without touching any driver.

**What this module knows nothing about.** Colour, extent, layout, matplotlib (it imports
none of it), which quantity is drawn, its units, or which figure family a variant belongs
to. It holds a naming rule and a record; the wording inside that record is authored by the
chart that owns the figure, because the caption sentence *describes* that figure's cells.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from population_synthetic.analysis.utils.grid_annotations import CellAnnotationPolicy

__all__ = [
    "CANONICAL_VARIANT",
    "COUNTED_VARIANT",
    "GridVariant",
    "variant_map",
    "variant_suffixes",
]

#: The variant published under the bare, unsuffixed filename -- the camera-ready figure,
#: whose cells print the value alone. Named once here so no driver decides it locally.
CANONICAL_VARIANT = "clean"

#: The sibling that keeps the count beneath every value. Suffixed ``_with_counts``, which
#: is what the reader of a filename needs to know about it.
COUNTED_VARIANT = "with_counts"


@dataclass(frozen=True)
class GridVariant:
    """One publication of a grid: an annotation policy, its wording and its type size.

    The three fields travel together because they describe one another. A clean figure
    captioned "printed with the two counts it is the quotient of" would be a figure
    disagreeing with itself, and the size is decided by how many lines the policy sets --
    so splitting them across three arguments would let one move without the others.

    Attributes:
        name: The variant's key in its family's map, and the segment its filename suffix
            is built from (:func:`variant_suffixes`).
        policy: The annotation policy handed to the shared renderer. Decides cell text
            and nothing else.
        cell_clause: The caption sentence describing what a cell prints, authored by the
            chart that owns the figure. Rendered wherever that figure carries a caption.
        fontsize: The in-cell annotation size, from the house scale. Never below
            :data:`~population_synthetic.analysis.utils.style.FONT_FLOOR_PT`.
        linespacing: In-cell line spacing, or ``None`` for the matplotlib default. Only a
            variant that sets two lines has anything to space.
    """

    name: str
    policy: CellAnnotationPolicy
    cell_clause: str
    fontsize: float
    linespacing: float | None


def variant_map(*variants: GridVariant) -> dict[str, GridVariant]:
    """The publishable variants of one grid, keyed by name.

    Args:
        *variants: The family's variants. The canonical one must be among them.

    Returns:
        ``{name: variant}`` in the order given, so a driver enumerating the map publishes
        them in the order the family declared.

    Raises:
        ValueError: If two variants share a name, or if the canonical variant is absent.
            Both are raised rather than tolerated: a duplicate name silently drops a
            publication, and a family with no canonical variant would leave the
            unsuffixed filename -- the one the manuscript references -- unwritten.
    """
    by_name: dict[str, GridVariant] = {}
    for variant in variants:
        if variant.name in by_name:
            raise ValueError(
                f"two grid variants share the name {variant.name!r}; each name is a "
                "filename suffix, so the second would overwrite the first."
            )
        by_name[variant.name] = variant
    if CANONICAL_VARIANT not in by_name:
        raise ValueError(
            f"no {CANONICAL_VARIANT!r} variant among {sorted(by_name)}: the unsuffixed "
            "filename is the camera-ready figure and is named after it, so a family "
            "without one publishes nothing at the name its readers reference."
        )
    return by_name


def variant_suffixes(variants: Mapping[str, GridVariant]) -> list[tuple[str, GridVariant]]:
    """``(filename_suffix, variant)`` for every variant in *variants*.

    The canonical variant takes the empty suffix -- it *is* the figure -- and every other
    is written beside it as ``_{name}``. The rule lives here so the five grid families
    that publish variants cannot drift into five naming schemes.

    Args:
        variants: A family's variant map, as returned by :func:`variant_map`.

    Returns:
        One pair per variant, in the map's own order.

    Raises:
        ValueError: If the map carries no canonical variant, rather than silently
            promoting an arbitrary one into the unsuffixed filename.
    """
    if CANONICAL_VARIANT not in variants:
        raise ValueError(
            f"this grid no longer publishes a {CANONICAL_VARIANT!r} variant; known "
            f"variants are {sorted(variants)}. The unsuffixed filename is named after "
            "it, and promoting another variant into that name would silently change "
            "what every downstream reference resolves to."
        )
    return [
        ("" if name == CANONICAL_VARIANT else f"_{name}", variant)
        for name, variant in variants.items()
    ]

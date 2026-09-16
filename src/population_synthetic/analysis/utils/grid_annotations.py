"""grid_annotations.py -- What text, if any, a heatmap cell prints.

One decision, isolated: given a cell's already-computed record, produce the string the
cell shows. A policy decides **text only**. It never decides a colour, an extent, which
cells are drawn, where the annotation sits, or how large it is -- those belong to
:mod:`population_synthetic.analysis.utils.grids`, which is the only module that draws.
Splitting them is what lets one grid be published twice -- clean at the canonical
filename, with its counts beside it -- from a single draw loop rather than from two
functions that diverge on the next edit.

**Every policy declares the keys it reads.** ``required_keys`` is not documentation: the
renderer validates each cell record against it and raises on a mismatch. The rule exists
because of a recorded near-miss (ADR ``2026-08-12-self-contained-typicality-axis.md``): a
renderer that read ``cell["rate"]`` by literal key, handed a block whose value key was
``value``, painted every cell grey and labelled it unavailable **without raising** -- a
silent-wrong-output path producing a plausible figure. Nothing here guesses a key, falls
back to a second key, or reads with ``.get(key, default)``. A caller whose records use
different names *declares* them (``value_key=``, ``denominator_key=``, ...) and
``required_keys`` follows the declaration, so a typo still raises.

**What this module knows nothing about.** Colour, extent, layout, figure size, fonts,
matplotlib (it imports none of it), any other cell, which quantity is being drawn, its
units, its direction, or the caveats that travel with it. Caveat wording -- a
``reference_note``, a ``direction_reason``, a ``counting_unit`` -- is read from the data
block by the chart that owns the figure and is never authored here or in a renderer.

**Numbers are formatted, never computed.** ``scale`` rescales a stored fraction into the
unit the figure prints (100 for a percentage, 1 for a raw value) and ``number_format`` is
a Python format spec. Neither derives a statistic: a quantity a policy could not format
without deriving it -- the signed distance to a reference, for instance -- is computed by
the chart that owns the reference and arrives as a pre-formatted ``qualifier``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Protocol

__all__ = [
    "COMPACT_NUMBER_FORMAT",
    "CellAnnotationPolicy",
    "MissingCellValue",
    "NoAnnotationPolicy",
    "RateOnlyPolicy",
    "RateWithCountsPolicy",
    "SignedValuePolicy",
    "SignedValueWithStarsPolicy",
]


class MissingCellValue(ValueError):
    """A record's value key holds ``None`` and the policy declares no wording for it.

    Raised rather than silently printing an empty cell: a record was supplied, so the
    caller believes there is something to say about that cell, and a policy that quietly
    drew nothing would turn a contract mismatch into a blank the reader reads as
    "not measured". A caller that genuinely wants wording for a value-less record
    declares it (``absent_text=``); a caller with nothing to say passes ``None`` in place
    of the record and the renderer draws no text at all.

    Also raised for the mirror case: a record that supplies its value but withholds a
    field the policy prints *beside* it. That record contradicts itself, and formatting
    it leniently would set the word ``None`` in a published cell.
    """


class CellAnnotationPolicy(Protocol):
    """The annotation contract: declare the keys read, return the text.

    ``required_keys`` is the exact set of keys a cell record must carry. The renderer
    validates every record against it before drawing anything, so a record shaped for a
    different policy fails loudly instead of rendering as an unmeasured cell.

    ``text`` returns the string the cell prints, or ``None`` for "print nothing here"
    -- a deliberate silence, distinct from the renderer's own "no record for this cell".
    """

    required_keys: frozenset[str]

    def text(self, cell: Mapping[str, Any]) -> str | None:
        """The annotation for *cell*, or ``None`` to print nothing."""


#: A named alternative to a Python format spec, for a grid whose cells span several
#: orders of magnitude -- token counts in the thousands beside costs in thousandths. Two
#: decimals through the range a reader reads as a decimal number, three significant
#: figures outside it, where two decimals would be either noise or an unreadable run of
#: zeroes. It is a *formatting* rule and nothing else: the value it is handed is already
#: final, and which spec applies is decided by that value's magnitude alone.
COMPACT_NUMBER_FORMAT = "compact"

#: The magnitude at or above which :data:`COMPACT_NUMBER_FORMAT` switches to significant
#: figures, and the one below which it does the same for small values.
_COMPACT_UPPER = 1000.0
_COMPACT_LOWER = 0.01


def _format_value(value: Any, *, scale: float, number_format: str) -> str:
    """*value* rescaled and formatted -- a formatting step, never a derivation."""
    scaled = float(value) * scale
    if number_format == COMPACT_NUMBER_FORMAT:
        if abs(scaled) >= _COMPACT_UPPER or (scaled and abs(scaled) < _COMPACT_LOWER):
            return format(scaled, ".3g")
        return format(scaled, ".2f")
    return format(scaled, number_format)


def _head(
    cell: Mapping[str, Any],
    *,
    value_key: str,
    scale: float,
    number_format: str,
    absent_text: str | None,
    policy_name: str,
) -> str:
    """The leading number of an annotation, or the declared wording when it is absent."""
    value = cell[value_key]
    if value is not None:
        return _format_value(value, scale=scale, number_format=number_format)
    if absent_text is None:
        raise MissingCellValue(
            f"{policy_name}: cell record carries {value_key!r} = None and the policy "
            "declares no 'absent_text' for a value-less record. Either declare the "
            "wording this figure uses for a record whose value could not be measured, "
            "or pass None in place of the record so no annotation is drawn."
        )
    return absent_text


@dataclass(frozen=True)
class RateWithCountsPolicy:
    """The value, and beneath it the counts it rests on -- the ``_with_counts`` variant.

    The second line names the base, in one of two forms decided by what the caller
    declares. With a *numerator* the value is a quotient and both counts are printed
    (``110/267``), so the rate never travels without the denominator it was taken over.
    Without one the value is not a quotient and the single count it rests on is printed
    (``n=267``).

    ``qualifier_key`` names an already-formatted string appended to the number -- the
    parenthesised signed distance to a reference, for example. It is read, never derived:
    a policy that computed a distance would need the reference, which is a fact about
    another unit and belongs to the chart that owns the figure.

    Attributes:
        value_key: Record key holding the value. ``None`` there needs *absent_text*.
        denominator_key: Record key holding the base count.
        numerator_key: Record key holding the numerator, or ``None`` when the value is
            not a quotient (the base is then printed as ``n=``).
        scale: Multiplier applied before formatting -- 100 prints a stored fraction as a
            percentage, 1 prints the stored value.
        number_format: Python format spec for the scaled value.
        qualifier_key: Record key holding a pre-formatted suffix, or ``None``.
        absent_text: Wording printed in place of the number when the value is ``None``.
            ``None`` (the default) makes a value-less record an error.
    """

    value_key: str = "rate"
    denominator_key: str = "denominator"
    numerator_key: str | None = "numerator"
    scale: float = 100.0
    number_format: str = ".1f"
    qualifier_key: str | None = None
    absent_text: str | None = None

    @property
    def required_keys(self) -> frozenset[str]:
        keys = {self.value_key, self.denominator_key}
        if self.numerator_key is not None:
            keys.add(self.numerator_key)
        if self.qualifier_key is not None:
            keys.add(self.qualifier_key)
        return frozenset(keys)

    def text(self, cell: Mapping[str, Any]) -> str:
        head = _head(
            cell,
            value_key=self.value_key,
            scale=self.scale,
            number_format=self.number_format,
            absent_text=self.absent_text,
            policy_name=type(self).__name__,
        )
        if self.qualifier_key is not None and cell[self.value_key] is not None:
            head = f"{head}{cell[self.qualifier_key]}"
        denominator = cell[self.denominator_key]
        if self.numerator_key is None:
            return f"{head}\nn={denominator}"
        return f"{head}\n{cell[self.numerator_key]}/{denominator}"


@dataclass(frozen=True)
class RateOnlyPolicy:
    """The value alone -- the clean variant of a grid whose sibling prints the counts.

    Identical to :class:`RateWithCountsPolicy` in everything but the second line, which
    is why the two are substitutable over one draw loop: the same matrix, extent and
    colour scale, differing only in cell text. The counts the counted sibling prints
    stay available in that figure and in the CSV the grid is drawn from, so dropping them
    here loses ink rather than evidence.

    ``qualifier_key`` is the one thing this policy does **not** drop: it names an
    already-formatted suffix -- the typicality grid's parenthesised signed distance to the
    real population -- which on a sequential ramp is the only place the *side* of the
    reference is readable at all (ADR ``2026-08-12``). A clean variant that dropped it
    would not be a tidier figure, it would be a figure missing half its content. Read,
    never derived, exactly as in :class:`RateWithCountsPolicy`.

    Attributes:
        value_key: Record key holding the value.
        scale: Multiplier applied before formatting.
        number_format: Python format spec for the scaled value.
        qualifier_key: Record key holding a pre-formatted suffix, or ``None``.
        absent_text: Wording printed when the value is ``None``; ``None`` makes a
            value-less record an error.
    """

    value_key: str = "rate"
    scale: float = 100.0
    number_format: str = ".1f"
    qualifier_key: str | None = None
    absent_text: str | None = None

    @property
    def required_keys(self) -> frozenset[str]:
        keys = {self.value_key}
        if self.qualifier_key is not None:
            keys.add(self.qualifier_key)
        return frozenset(keys)

    def text(self, cell: Mapping[str, Any]) -> str:
        head = _head(
            cell,
            value_key=self.value_key,
            scale=self.scale,
            number_format=self.number_format,
            absent_text=self.absent_text,
            policy_name=type(self).__name__,
        )
        if self.qualifier_key is not None and cell[self.value_key] is not None:
            head = f"{head}{cell[self.qualifier_key]}"
        return head


@dataclass(frozen=True)
class SignedValuePolicy:
    """The value with its sign always printed -- ``+0.031`` / ``-0.014``.

    For a **two-sided** quantity drawn on the house sequential ramp. That ramp orders
    cells by magnitude alone, so two values equally far above and below the reference are
    drawn differently and neither drawing says which side it was on. The sign is
    therefore load-bearing rather than decoration: it is the only place on such a figure
    where the side is readable. This is the mechanism the 2026-08-12 ADR chose over a
    diverging colormap, and it is why the sign flag is not optional here.

    Attributes:
        value_key: Record key holding the value.
        scale: Multiplier applied before formatting.
        number_format: Python format spec **without** the sign flag, which is prepended.
        absent_text: Wording printed when the value is ``None``; ``None`` makes a
            value-less record an error.
    """

    value_key: str = "value"
    scale: float = 1.0
    number_format: str = ".3f"
    absent_text: str | None = None

    @property
    def required_keys(self) -> frozenset[str]:
        return frozenset({self.value_key})

    def text(self, cell: Mapping[str, Any]) -> str:
        return _head(
            cell,
            value_key=self.value_key,
            scale=self.scale,
            number_format=f"+{self.number_format}",
            absent_text=self.absent_text,
            policy_name=type(self).__name__,
        )


@dataclass(frozen=True)
class SignedValueWithStarsPolicy:
    """A signed value, the symbol qualifying it, and optionally the count behind it.

    For a grid whose **fill and text carry different channels**: the fill encodes a tier
    the cell was binned into and the text encodes the magnitude and direction that tier
    was assigned to. A pairwise-comparison square is the case it is written for -- the
    tier is symmetric across the diagonal while the difference is not, so the square can
    only be read at all if the direction travels in the annotation.

    The sign is therefore load-bearing for the same reason it is in
    :class:`SignedValuePolicy`, and is prepended rather than left to the caller's format
    spec so that no figure can be published having quietly dropped it.

    The symbol is **read, never derived**: mapping a p-value onto a star ladder needs the
    thresholds, which are a fact about that analysis's config and belong to the chart
    that owns the figure. This policy is handed the resolved symbol and prints it.

    A record whose value is ``None`` -- a comparison that was never made -- prints
    *absent_text* alone, on one line, with neither the symbol nor the count beneath it.
    That is the point of the default: a cell that was not tested must not print the
    palest tier's symbol, because "not tested" and "tested, not significant" are
    different findings and a reader cannot recover the difference from the fill, which is
    the colormap's unpainted colour in both the untested and the diagonal case.

    It declares no ``scale``, unlike its rate-shaped siblings: a difference is already in
    the unit its figure prints, and an attribute no caller sets is a decision with no
    owner.

    Attributes:
        value_key: Record key holding the signed value. ``None`` there prints
            *absent_text*.
        stars_key: Record key holding the already-resolved significance symbol.
        count_key: Record key holding the count the comparison rests on, or ``None`` to
            print no count line -- the difference between the ``_with_counts`` variant
            and its clean sibling.
        number_format: Python format spec **without** the sign flag, which is prepended.
        absent_text: Wording printed for a record whose value is ``None``. Defaults to an
            em dash, so an untested cell is marked rather than blank; ``None`` restores
            the sibling policies' behaviour of treating a value-less record as an error.
    """

    value_key: str = "value"
    stars_key: str = "stars"
    count_key: str | None = None
    number_format: str = ".3f"
    absent_text: str | None = "—"

    @property
    def required_keys(self) -> frozenset[str]:
        keys = {self.value_key, self.stars_key}
        if self.count_key is not None:
            keys.add(self.count_key)
        return frozenset(keys)

    def _companion(self, cell: Mapping[str, Any], key: str) -> Any:
        """A field printed beside a value that *was* measured, which must not be absent.

        Raised on rather than printed, because ``None`` here means the record disagrees
        with itself: it claims a measured value while withholding something the figure
        prints next to it. Formatting that as text would put the word ``None`` in a
        published cell.
        """
        companion = cell[key]
        if companion is None:
            raise MissingCellValue(
                f"{type(self).__name__}: cell record carries {self.value_key!r} = "
                f"{cell[self.value_key]!r} but {key!r} = None. A cell with a value must "
                "carry every field printed beside it; a cell that was never measured "
                "sets its value to None as well, which 'absent_text' then covers."
            )
        return companion

    def text(self, cell: Mapping[str, Any]) -> str:
        head = _head(
            cell,
            value_key=self.value_key,
            scale=1.0,
            number_format=f"+{self.number_format}",
            absent_text=self.absent_text,
            policy_name=type(self).__name__,
        )
        if cell[self.value_key] is None:
            return head
        lines = [head, str(self._companion(cell, self.stars_key))]
        if self.count_key is not None:
            lines.append(f"n={self._companion(cell, self.count_key)}")
        return "\n".join(lines)


@dataclass(frozen=True)
class NoAnnotationPolicy:
    """No text in any cell -- the fill and the colourbar carry the whole reading.

    Declares no required key, so it accepts any record shape: it reads none of them. Use
    it for a grid dense enough that per-cell numbers would be unreadable at print size,
    where the cells are still records the caller may draw its own furniture from.
    """

    required_keys: ClassVar[frozenset[str]] = frozenset()

    def text(self, cell: Mapping[str, Any]) -> None:
        return None

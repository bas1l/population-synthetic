"""cap_index.py -- The validation gate's own record of the cap each combination was drawn against.

``population_cap`` writes one ``CapSummary`` per combination into the stage-level
``population_cap/_index.json`` (see
:class:`population_synthetic.analysis.population_cap.cap.CapSummary`), and that record
carries the ``requested_n`` the gate was asked for. Until now nothing read it: it was
write-only telemetry. This module is its reader.

**The rule it exists to define, once.** A combination's cell is

* **full-n** iff ``n >= requested_n`` for *that combination's own slug*, and
* **thin** iff ``n < requested_n``.

``n == requested_n`` is full-n, not thin. The threshold is always the slug's own
``requested_n`` -- never a literal persona count, never ``max(n)`` inferred across the
grid, never a default. The cap is a per-run config value; a hardcoded or inferred copy
would silently disagree with the gate that produced the data, and would be invisibly
wrong precisely in the run where every cell fell short.

The rule is shared rather than per-figure on purpose: every consumer that asks *did this
combination survive the cap* must give the same answer, and three independent definitions
of that question is exactly the drift the repository's config invariant exists to prevent.

The module knows nothing about matplotlib, figures, layout, colours, which metric is
plotted, which country is analysed, or which process is asking. It resolves the stage
directory, reads the index, and answers two questions about integers.

Failure policy: fail-fast at the read boundary. A missing stage directory, a missing or
malformed ``_index.json``, or a lookup for a slug the index does not carry all raise with
the offending path named. There is no default cap and no inferred one -- a figure that
silently degraded to "nothing is thin" would look complete while having dropped the whole
point of the marking.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path

from population_synthetic.analysis.utils.capped_source import resolve_stage_source

#: Filename of the stage-level cap index inside the ``population_cap`` output folder.
INDEX_FILENAME = "_index.json"

#: The two ``CapSummary`` keys this module reads. The record carries more (seed, selected
#: ids, the two gate counts); none of it is this module's concern.
SLUG_KEY = "slug"
REQUESTED_N_KEY = "requested_n"


class CapIndex(Mapping[str, int]):
    """Per-slug ``requested_n``, plus the full-n / thin predicate over it.

    A read-only ``Mapping[str, int]`` from combination slug to the cap that
    combination was drawn against, so a caller that only wants the number can treat
    it as the plain map it is. It additionally carries the *path it was read from*,
    which is what lets a failed lookup name the offending file rather than raising a
    bare ``KeyError`` on a slug string.
    """

    def __init__(self, requested_n: Mapping[str, int], *, source: Path) -> None:
        self._requested_n: dict[str, int] = dict(requested_n)
        self._source = Path(source)

    @property
    def source(self) -> Path:
        """The ``_index.json`` this index was read from (named in every error)."""
        return self._source

    def __getitem__(self, slug: str) -> int:
        try:
            return self._requested_n[slug]
        except KeyError:
            raise KeyError(
                f"Combination {slug!r} has no entry in the population-cap index {self._source}. "
                f"The cap it was drawn against is unknown, and is never defaulted or inferred: "
                f"re-run the population_cap task for this combo. "
                f"Indexed slugs: {sorted(self._requested_n)}"
            ) from None

    def __iter__(self) -> Iterator[str]:
        return iter(self._requested_n)

    def __len__(self) -> int:
        return len(self._requested_n)

    def __repr__(self) -> str:
        return f"CapIndex({len(self._requested_n)} slug(s) from {self._source})"

    def is_full_n(self, slug: str, n: int) -> bool:
        """``True`` iff *n* personas meets or exceeds *slug*'s own requested cap.

        The boundary is inclusive: ``n == requested_n`` is full-n. Raises when *slug*
        has no entry -- an unknown cap is not a licence to assume the cell is fine.
        """
        return n >= self[slug]

    def is_thin(self, slug: str, n: int) -> bool:
        """``True`` iff *slug* holds fewer personas than it requested (``n < requested_n``)."""
        return not self.is_full_n(slug, n)


def load_cap_index(output_base: str | Path) -> CapIndex:
    """Read ``population_cap/_index.json`` under *output_base* into a :class:`CapIndex`.

    Args:
        output_base: The run's output base (the parent of ``03_Analysis/``).

    Returns:
        The per-slug ``requested_n`` map, carrying the path it was read from.

    Raises:
        FileNotFoundError: If the ``population_cap`` stage directory or its
            ``_index.json`` is absent -- the gate has not run for this output base.
        ValueError: If the index is not a JSON list of records, or a record lacks a
            non-empty string slug or a positive integer ``requested_n``, or two records
            claim the same slug.
    """
    index_path = resolve_stage_source(output_base) / INDEX_FILENAME
    if not index_path.is_file():
        raise FileNotFoundError(
            f"Population-cap index not found: {index_path}. It is the gate's own record of "
            f"the cap each combination was drawn against; run the population_cap task "
            f"before any consumer that marks under-sampled combinations."
        )

    with open(index_path, "r", encoding="utf-8") as fh:
        entries = json.load(fh)
    if not isinstance(entries, list):
        raise ValueError(
            f"Population-cap index must be a JSON list of per-combo records, got "
            f"{type(entries).__name__}: {index_path}"
        )

    requested_n: dict[str, int] = {}
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"Population-cap index record {position} must be a JSON object, got "
                f"{type(entry).__name__}: {index_path}"
            )
        slug = entry.get(SLUG_KEY)
        if not isinstance(slug, str) or not slug:
            raise ValueError(
                f"Population-cap index record {position} must carry a non-empty string "
                f"{SLUG_KEY!r}, got {slug!r}: {index_path}"
            )
        value = entry.get(REQUESTED_N_KEY)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(
                f"Population-cap index record for {slug!r} must carry an integer "
                f"{REQUESTED_N_KEY!r} >= 1, got {value!r}: {index_path}"
            )
        if slug in requested_n:
            raise ValueError(
                f"Population-cap index carries slug {slug!r} twice: {index_path}. "
                f"The per-combo records are upserted by slug, so a duplicate means the "
                f"index is corrupt and the cap for that combo is ambiguous."
            )
        requested_n[slug] = value

    return CapIndex(requested_n, source=index_path)

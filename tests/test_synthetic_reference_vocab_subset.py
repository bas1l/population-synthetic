"""Static drift guard: synthetic emittable vocabulary subseteq reference vocabulary.

For every demographic attribute that is scored by the ``StatisticalEvaluator`` --
i.e. one whose mapping block declares *both* a ``pipeline_handler`` (synthetic
side) and a ``reference_handler`` (reference side) -- this test asserts that every
canonical label the synthetic mapper can emit is also a label the reference mapper
can produce.  If the two drift apart, a synthetic-only label becomes a category the
reference distribution can never fill (or vice versa), silently biasing that
attribute's TV-distance / chi-squared in every comparison.

This is the structural counterpart of the ``birth_location`` "Nordic Country"
defect that motivated the config-driven refactor: there the *reference* held a
bucket the synthetic side could never emit; here we lock down the opposite
direction (synthetic emits a label the reference can never score) and any future
config edit that re-introduces drift fails loudly with the offending labels named.

Vocabularies are read purely from the role-based config sub-keys (no mapper run),
so the test is a fast static check over ``config/mapping/{scb,istat}/*.json``.

synthetic emittable vocab (per attr): union of ``output_categories``, the VALUES
of ``pipeline_label_mappings``, the ``label`` of every ``pipeline_keyword_rules``
entry, the values/labels of ``pipeline_refine_buckets`` + ``pipeline_refine_default``,
and the ``numeric_bucket`` label set (``pipeline_numeric_buckets`` values +
``pipeline_bucket_overflow.label``) + a literal ``pipeline_on_miss`` default --
EXCLUDING the ``"Non-standard label"`` sentinel and EXCLUDING raw / passthrough
emissions (``pipeline_on_miss`` in {``non_standard``, ``passthrough``,
``passthrough_or_nonstandard``}, ``pipeline_passthrough_on_separator``), which are
arbitrary free-text and not an enumerable vocabulary.

reference vocab (per attr): union of reference ``output_categories``, the VALUES of
``reference_label_mappings`` / ``reference_composite_mappings`` /
``reference_decile_mappings``, every ``mappings[*].schema_label``, and
``reference_none_default``.

Skipped attributes:
- ``id`` and ``age`` -- non-categorical (passthrough id, numeric gate); no vocabulary.
- attributes present on the synthetic side but with no ``reference_handler``
  (istat ``ethnicity`` / ``urbanization`` / ``income_source``) are skipped
  automatically by the "both handlers" gate -- they are pipeline-only blocks.
- ``birth_country_detail`` is checked, but only over its mapped labels: its
  ``pipeline_on_miss: "passthrough_or_nonstandard"`` lets it emit arbitrary raw
  country names verbatim, which are excluded from the synthetic vocab by the
  raw-passthrough rule above.
"""

from __future__ import annotations

import pytest

from population_synth.comparison.synthetic_mapper.factory import get_synthetic_mapper

#: Sentinel emitted on an unmapped value; never a real category.
_NON_STANDARD = "Non-standard label"

#: ``pipeline_on_miss`` policies that emit raw / arbitrary text rather than a fixed
#: label -- their output is not an enumerable vocabulary, so it is excluded.
_RAW_ON_MISS = {"non_standard", "passthrough", "passthrough_or_nonstandard"}

#: Non-categorical attributes (no label vocabulary to compare).
_SKIP_ATTRS = {"id", "age"}

#: Reviewed, intentional exceptions: (country, attr) -> {labels the synthetic side
#: can emit that the reference side cannot score}.  Each entry is a KNOWN drift kept
#: out of the assertion so genuinely-new drift still fails the test.
#:
#: - ("swedish", "parental_structure"): the Swedish ``parental_structure`` keyword
#:   rules reuse the shared (Italian-derived) cascade, which carries an
#:   ``"Extended Family"`` rule (tokens "famiglia estesa" / "extended" /
#:   "multigenerational").  The Swedish reference (SCB ``Familjetyp``) has no
#:   Extended-Family bucket -- its ``output_categories`` are the 4 SE labels -- so a
#:   Swedish persona whose free text says "extended" maps to a label the SE
#:   reference can never fill.  Italian keeps "Extended Family" as a real 5th
#:   category, so only Sweden is affected.  Flagged for review (prune the rule from
#:   the SE config, or treat as a non-scored residue); not changed here because it
#:   is a behaviour edit outside this phase's scope.
_KNOWN_DRIFT: dict[tuple[str, str], set[str]] = {
    ("swedish", "parental_structure"): {"Extended Family"},
}

_COUNTRIES = ["swedish", "italian"]


def _synthetic_vocab(block: dict) -> set[str]:
    """Labels the synthetic ``pipeline_*`` config can emit for *block* (excl. raw / sentinel)."""
    vocab: set[str] = set()
    vocab.update(block.get("output_categories", []) or [])
    vocab.update((block.get("pipeline_label_mappings", {}) or {}).values())
    for rule in block.get("pipeline_keyword_rules", []) or []:
        vocab.add(rule["label"])
    # ``pipeline_refine_buckets`` is dict (exact lookup) or list (keyword rules).
    refine = block.get("pipeline_refine_buckets")
    if isinstance(refine, dict):
        vocab.update(refine.values())
    elif isinstance(refine, list):
        for rule in refine:
            vocab.add(rule["label"])
    if block.get("pipeline_refine_default") is not None:
        vocab.add(block["pipeline_refine_default"])
    # numeric_bucket labels.
    vocab.update((block.get("pipeline_numeric_buckets", {}) or {}).values())
    overflow = block.get("pipeline_bucket_overflow")
    if isinstance(overflow, dict) and overflow.get("label"):
        vocab.add(overflow["label"])
    # A literal ``pipeline_on_miss`` default (e.g. "Wage / Business", "Other") is a
    # fixed emittable label; the raw / sentinel policies are not.
    on_miss = block.get("pipeline_on_miss")
    if on_miss and on_miss not in _RAW_ON_MISS:
        vocab.add(on_miss)
    vocab.discard(_NON_STANDARD)
    return vocab


def _reference_vocab(block: dict) -> set[str]:
    """Labels the reference ``reference_*`` config can produce for *block*."""
    vocab: set[str] = set()
    vocab.update(block.get("output_categories", []) or [])
    vocab.update((block.get("reference_label_mappings", {}) or {}).values())
    vocab.update((block.get("reference_composite_mappings", {}) or {}).values())
    vocab.update((block.get("reference_decile_mappings", {}) or {}).values())
    for entry in (block.get("mappings", {}) or {}).values():
        if isinstance(entry, dict) and entry.get("schema_label"):
            vocab.add(entry["schema_label"])
    if block.get("reference_none_default") is not None:
        vocab.add(block["reference_none_default"])
    return vocab


@pytest.mark.parametrize("country", _COUNTRIES)
def test_synthetic_vocab_is_subset_of_reference_vocab(country: str) -> None:
    """Every synthetic-emittable label is also a reference-producible label."""
    mapper = get_synthetic_mapper(country)
    mappings = mapper.mappings

    checked: list[str] = []
    offenders: dict[str, list[str]] = {}
    for stem, block in sorted(mappings.items()):
        if not isinstance(block, dict):
            continue
        if "pipeline_handler" not in block or "reference_handler" not in block:
            continue
        attr = block.get("pipeline_attr", stem)
        if attr in _SKIP_ATTRS:
            continue

        syn = _synthetic_vocab(block)
        ref = _reference_vocab(block)
        allowed = _KNOWN_DRIFT.get((country, attr), set())
        missing = sorted((syn - ref) - allowed)
        checked.append(attr)
        if missing:
            offenders[attr] = missing

    assert checked, f"no dual-handler attributes discovered for {country!r}"
    assert not offenders, (
        f"[{country}] synthetic mapper can emit labels the reference mapper cannot "
        f"score (synthetic_vocab NOT subseteq reference_vocab):\n"
        + "\n".join(f"  {attr}: {labels}" for attr, labels in sorted(offenders.items()))
    )

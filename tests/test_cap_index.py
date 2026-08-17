"""Tests for the shared population-cap index reader and its full-n / thin predicate.

The predicate is the one definition of *did this combination survive the cap*, shared
by every figure that marks under-sampled combinations, so the tests pin both halves:
the fail-fast read boundary (missing stage dir, missing index, malformed record,
unknown slug) and the boundary behaviour of ``n >= requested_n``.

The fixture cap is deliberately **not** 100 -- the production runs happen to request
100, so a threshold hardcoded anywhere in the implementation would pass a 100-based
test by coincidence. Every assertion here is stated against the fixture's own
``requested_n``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from population_synthetic.analysis.utils.cap_index import (
    INDEX_FILENAME,
    CapIndex,
    load_cap_index,
)
from population_synthetic.analysis.utils.registry import analysis_output_dir

# A cap other than the production 100, so a literal threshold cannot pass by coincidence.
REQUESTED_N = 40

SLUG_A = "swedish_all_pick_claude_haiku"
SLUG_B = "swedish_all_generate_pick_gemini_flash"


def _stage_dir(output_base: Path) -> Path:
    stage = analysis_output_dir("population_cap", output_base)
    stage.mkdir(parents=True, exist_ok=True)
    return stage


def _write_index(output_base: Path, entries) -> Path:
    path = _stage_dir(output_base) / INDEX_FILENAME
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def _entry(slug: str, requested_n: int = REQUESTED_N) -> dict:
    """A cap-index record shaped like the ``CapSummary`` the gate writes."""
    return {
        "slug": slug,
        "country": "swedish",
        "requested_n": requested_n,
        "raw_passed": requested_n,
        "mapped_passed": requested_n,
        "clean_available": requested_n,
        "selected": requested_n,
        "seed": 7,
        "selected_ids": [],
        "truncated": False,
        "synthetic_file": f"{slug}.json",
        "real_file": "real_swedish.json",
        "mapped_n": requested_n,
    }


# ------------------------------------------------------------------
# Reading
# ------------------------------------------------------------------

def test_load_reads_requested_n_per_slug(tmp_path):
    _write_index(tmp_path, [_entry(SLUG_A), _entry(SLUG_B, REQUESTED_N + 5)])

    index = load_cap_index(tmp_path)

    assert dict(index) == {SLUG_A: REQUESTED_N, SLUG_B: REQUESTED_N + 5}
    assert len(index) == 2
    assert SLUG_A in index
    assert sorted(index) == sorted([SLUG_A, SLUG_B])


def test_load_records_the_source_path(tmp_path):
    path = _write_index(tmp_path, [_entry(SLUG_A)])

    assert load_cap_index(tmp_path).source == path


def test_missing_index_file_raises_naming_the_path(tmp_path):
    stage = _stage_dir(tmp_path)  # the stage exists; only the index is absent

    with pytest.raises(FileNotFoundError) as exc:
        load_cap_index(tmp_path)

    assert str(stage / INDEX_FILENAME) in str(exc.value)


def test_missing_stage_dir_raises_naming_the_path(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        load_cap_index(tmp_path)

    assert str(analysis_output_dir("population_cap", tmp_path)) in str(exc.value)


def test_unknown_slug_raises_naming_the_index_path(tmp_path):
    path = _write_index(tmp_path, [_entry(SLUG_A)])
    index = load_cap_index(tmp_path)

    with pytest.raises(KeyError) as exc:
        index[SLUG_B]

    # ``str(KeyError)`` is the repr of its argument, which escapes Windows separators;
    # the message itself is the readable form.
    message = exc.value.args[0]
    assert SLUG_B in message
    assert str(path) in message


def test_unknown_slug_raises_from_the_predicate_too(tmp_path):
    """An unknown cap is never a licence to assume the cell met it."""
    _write_index(tmp_path, [_entry(SLUG_A)])
    index = load_cap_index(tmp_path)

    with pytest.raises(KeyError):
        index.is_full_n(SLUG_B, REQUESTED_N)


# ------------------------------------------------------------------
# Malformed input -- fail loudly, never default
# ------------------------------------------------------------------

@pytest.mark.parametrize(
    "entries",
    [
        pytest.param({"slug": SLUG_A}, id="not-a-list"),
        pytest.param(["not-an-object"], id="record-not-an-object"),
        pytest.param([{"requested_n": REQUESTED_N}], id="no-slug"),
        pytest.param([{"slug": "", "requested_n": REQUESTED_N}], id="empty-slug"),
        pytest.param([{"slug": SLUG_A}], id="no-requested-n"),
        pytest.param([{"slug": SLUG_A, "requested_n": None}], id="null-requested-n"),
        pytest.param([{"slug": SLUG_A, "requested_n": "40"}], id="string-requested-n"),
        pytest.param([{"slug": SLUG_A, "requested_n": 40.0}], id="float-requested-n"),
        pytest.param([{"slug": SLUG_A, "requested_n": True}], id="bool-requested-n"),
        pytest.param([{"slug": SLUG_A, "requested_n": 0}], id="zero-requested-n"),
        pytest.param([_entry(SLUG_A), _entry(SLUG_A)], id="duplicate-slug"),
    ],
)
def test_malformed_index_raises(tmp_path, entries):
    path = _write_index(tmp_path, entries)

    with pytest.raises(ValueError) as exc:
        load_cap_index(tmp_path)

    assert str(path) in str(exc.value)


# ------------------------------------------------------------------
# The full-n / thin predicate
# ------------------------------------------------------------------

def test_boundary_is_inclusive(tmp_path):
    """``n == requested_n`` is full-n; one persona fewer is thin."""
    _write_index(tmp_path, [_entry(SLUG_A)])
    index = load_cap_index(tmp_path)
    requested = index[SLUG_A]

    assert index.is_full_n(SLUG_A, requested) is True
    assert index.is_thin(SLUG_A, requested) is False
    assert index.is_full_n(SLUG_A, requested - 1) is False
    assert index.is_thin(SLUG_A, requested - 1) is True


def test_predicate_is_monotone_around_the_slugs_own_cap(tmp_path):
    _write_index(tmp_path, [_entry(SLUG_A), _entry(SLUG_B, REQUESTED_N * 2)])
    index = load_cap_index(tmp_path)

    for slug in (SLUG_A, SLUG_B):
        requested = index[slug]
        below = [n for n in range(0, requested)]
        assert not any(index.is_full_n(slug, n) for n in below)
        assert all(index.is_full_n(slug, n) for n in (requested, requested + 1, requested * 3))

    # The caps differ, so the same n is full-n for one slug and thin for the other.
    assert index.is_full_n(SLUG_A, REQUESTED_N)
    assert index.is_thin(SLUG_B, REQUESTED_N)


def test_cap_index_is_constructible_without_a_filesystem():
    """The predicate is usable on an in-memory map (the figure tests rely on this)."""
    index = CapIndex({SLUG_A: REQUESTED_N}, source=Path("fixture") / INDEX_FILENAME)

    assert index[SLUG_A] == REQUESTED_N
    assert index.is_full_n(SLUG_A, REQUESTED_N)
    assert not index.is_full_n(SLUG_A, REQUESTED_N - 1)

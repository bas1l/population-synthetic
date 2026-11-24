"""Unit tests for the ``validation_attrition`` loader: the three-file completeness gate.

The loader's job is to refuse the inputs that would otherwise produce plausible but
wrong attrition numbers -- a combination the gate's two halves saw differently, and an
index written before ``raw_total`` existed -- so most of these tests are about what it
*rejects*.

Fixtures fabricate a minimal output base on ``tmp_path``: the three files the gate
persists, each written at the path ``analysis_output_dir`` resolves for its process, so
no test carries a ``03_Analysis`` literal or a folder name. The axis registries are
injected, so nothing here depends on the repository's live axis config.

The regression this file exists to pin, from the Phase 1 measurement: the drift
predicate is ``raw_total == n_personas``, **not** ``raw_total == raw_passed``. Five
combinations of the live ``swedish_02`` grid legitimately have ``raw_total >
raw_passed`` (549 vs 488 at worst) because their personas genuinely failed the raw
gate. A loader asserting the second predicate would raise on healthy data.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pytest

from population_synthetic.analysis.utils.cap_index import INDEX_FILENAME
from population_synthetic.analysis.utils.registry import analysis_output_dir
from population_synthetic.analysis.validation_attrition.loader import (
    MAPPED_SUMMARY_PROCESS_ID,
    RAW_SUMMARY_PROCESS_ID,
    SUMMARY_FILENAME,
    load_attrition_records,
    resolve_sources,
)

_COUNTRY = "swedish"
_AXIS_IDS = (
    [_COUNTRY],
    ["all_pick", "all_generate_pick"],
    ["claude_haiku", "gemini_flash"],
)
_HEALTHY = f"{_COUNTRY}_all_pick_claude_haiku"
_WITHDRAWN = f"{_COUNTRY}_all_generate_pick_gemini_flash"

# Header prefixes of the two validator roll-ups, as their producers declare them in
# ``validate_{raw,mapped}/validate.py::SUMMARY_HEADER``. The loader reads a subset of
# each (slug / n_personas / passed), so the trailing columns are present here purely to
# prove the subset check tolerates them.
_RAW_HEADER = (
    "slug", "has_issues", "n_personas", "passed", "failed",
    "missing_identity", "n_expected_keys", "pass_rate_pct",
)
_MAPPED_HEADER = ("slug", "has_issues", "n_personas", "passed", "failed", "pass_rate_pct")


def _cap_entry(
    slug: str,
    *,
    requested_n: int = 100,
    raw_total: int = 150,
    raw_passed: int = 150,
    mapped_passed: int = 120,
    clean_available: int | None = None,
    selected: int = 100,
    truncated: bool = True,
    excluded: bool = False,
    exclusion_reason: str | None = None,
    drop_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """One ``CapSummary`` record, shaped exactly as ``population_cap`` persists it.

    ``clean_available`` defaults to ``mapped_passed`` because the clean pool is the
    intersection of the two gates and the mapped gate is the tighter one on every
    combination of the live grid; pass it explicitly to break that.
    """
    entry: dict[str, Any] = {
        "slug": slug,
        "country": _COUNTRY,
        "requested_n": requested_n,
        "raw_total": raw_total,
        "raw_passed": raw_passed,
        "mapped_passed": mapped_passed,
        "clean_available": mapped_passed if clean_available is None else clean_available,
        "selected": selected,
        "seed": 0,
        "selected_ids": [f"persona_{i:05d}" for i in range(selected)],
        "truncated": truncated,
        "synthetic_file": None if excluded else f"{slug}.json",
        "real_file": None if excluded else f"real_{_COUNTRY}.json",
        "mapped_n": selected,
        "excluded": excluded,
        "exclusion_reason": exclusion_reason,
    }
    for key in drop_keys:
        entry.pop(key)
    return entry


def _withdrawn_entry(slug: str = _WITHDRAWN) -> dict[str, Any]:
    """The degenerate case the artifact exists for: 150 generated, 9 clean, 0 selected."""
    return _cap_entry(
        slug,
        raw_total=150,
        raw_passed=150,
        mapped_passed=9,
        selected=0,
        truncated=False,
        excluded=True,
        exclusion_reason=(
            "only 9 clean persona(s) pass both validity gates (raw_passed=150, "
            "mapped_passed=9), fewer than the requested n=100"
        ),
    )


def _write_summary(path: Path, header: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))


def _build_workspace(
    tmp_path: Path,
    entries: Sequence[Mapping[str, Any]],
    *,
    raw_counts: Mapping[str, tuple[int, int]] | None = None,
    mapped_counts: Mapping[str, tuple[int, int]] | None = None,
    omit_raw: Sequence[str] = (),
    omit_mapped: Sequence[str] = (),
    duplicate_raw: str | None = None,
) -> Path:
    """Materialise the gate's three files under *tmp_path*; return the output base.

    Both roll-ups are derived from *entries* by default -- ``validate_raw`` sees the
    whole pool (``raw_total`` personas, ``raw_passed`` of them passing) and
    ``validate_mapped`` sees what mapping produced from the raw-valid ones. Pass
    ``raw_counts`` / ``mapped_counts`` (``{slug: (n_personas, passed)}``) to force a
    disagreement, or ``omit_*`` to leave a combination out of a roll-up entirely.
    """
    cap_dir = analysis_output_dir("population_cap", tmp_path)
    cap_dir.mkdir(parents=True, exist_ok=True)
    (cap_dir / INDEX_FILENAME).write_text(json.dumps(list(entries), indent=2), encoding="utf-8")

    raw_rows = []
    mapped_rows = []
    for entry in entries:
        slug = entry["slug"]
        raw_n, raw_passed = (raw_counts or {}).get(
            slug, (entry.get("raw_total", 0), entry["raw_passed"])
        )
        mapped_n, mapped_passed = (mapped_counts or {}).get(
            slug, (entry["raw_passed"], entry["mapped_passed"])
        )
        if slug not in omit_raw:
            raw_rows.append([slug, raw_passed < raw_n, raw_n, raw_passed, raw_n - raw_passed, 0, 14, 0.0])
        if slug not in omit_mapped:
            mapped_rows.append(
                [slug, mapped_passed < mapped_n, mapped_n, mapped_passed, mapped_n - mapped_passed, 0.0]
            )
    if duplicate_raw is not None:
        raw_rows.append(list(next(row for row in raw_rows if row[0] == duplicate_raw)))

    _write_summary(
        analysis_output_dir(RAW_SUMMARY_PROCESS_ID, tmp_path) / SUMMARY_FILENAME,
        _RAW_HEADER, raw_rows,
    )
    _write_summary(
        analysis_output_dir(MAPPED_SUMMARY_PROCESS_ID, tmp_path) / SUMMARY_FILENAME,
        _MAPPED_HEADER, mapped_rows,
    )
    return tmp_path


def _load(tmp_path: Path, **kwargs: Any):
    return load_attrition_records(tmp_path, axis_ids=_AXIS_IDS, **kwargs)


# --------------------------------------------------------------------------- #
# the happy path                                                                #
# --------------------------------------------------------------------------- #


def test_loads_every_combination_including_the_withdrawn_one(tmp_path: Path) -> None:
    """The row grain is the cap index, withdrawals included -- they are the point."""
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY), _withdrawn_entry()])

    records, skipped = _load(tmp_path)

    assert skipped == []
    assert [r.slug for r in records] == [_HEALTHY, _WITHDRAWN]
    withdrawn = records[1]
    assert withdrawn.excluded is True
    assert withdrawn.selected == 0
    assert withdrawn.generated == 150
    assert withdrawn.clean == 9
    assert "fewer than the requested n=100" in withdrawn.exclusion_reason


def test_axis_identity_is_decomposed_from_the_slug(tmp_path: Path) -> None:
    """Model and strategy travel as columns so no consumer re-parses the slug."""
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY)])

    (record,), _ = _load(tmp_path)

    assert (record.country, record.strategy, record.model) == (_COUNTRY, "all_pick", "claude_haiku")


def test_truncated_is_renamed_to_had_surplus(tmp_path: Path) -> None:
    """The false friend is renamed once, at the boundary, and keeps its meaning."""
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY, truncated=True), _withdrawn_entry()])

    records, _ = _load(tmp_path)

    assert records[0].had_surplus is True  # clean > n: a surplus was cut down
    assert records[1].had_surplus is False  # a withdrawal is never a surplus


def test_absent_exclusion_reason_reads_as_empty_string(tmp_path: Path) -> None:
    """``excluded`` is the flag; the reason is text, and null becomes ''."""
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY, exclusion_reason=None)])

    (record,), _ = _load(tmp_path)

    assert record.excluded is False
    assert record.exclusion_reason == ""


def test_raw_total_above_raw_passed_is_healthy_not_drift(tmp_path: Path) -> None:
    """A genuine raw-gate failure must not be read as gate drift.

    The worst live case: 549 personas generated, 488 passing the raw gate. Asserting
    ``raw_total == raw_passed`` would raise here; the predicate is
    ``raw_total == validate_raw.n_personas``, which holds.
    """
    entry = _cap_entry(_HEALTHY, raw_total=549, raw_passed=488, mapped_passed=132)
    _build_workspace(tmp_path, [entry])

    (record,), skipped = _load(tmp_path)

    assert skipped == []
    assert (record.generated, record.raw_valid, record.mapped_valid) == (549, 488, 132)


def test_resolve_sources_names_the_three_gate_files(tmp_path: Path) -> None:
    """Paths come from the registry, never from a literal."""
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY)])

    sources = resolve_sources(tmp_path)

    assert sources.cap_index == analysis_output_dir("population_cap", tmp_path) / INDEX_FILENAME
    assert sources.validate_raw_summary.parent == analysis_output_dir(RAW_SUMMARY_PROCESS_ID, tmp_path)
    assert sources.validate_mapped_summary.parent == analysis_output_dir(MAPPED_SUMMARY_PROCESS_ID, tmp_path)


# --------------------------------------------------------------------------- #
# the completeness gate                                                         #
# --------------------------------------------------------------------------- #


def test_missing_raw_total_raises_naming_the_rerun_command(tmp_path: Path) -> None:
    """An index predating ``raw_total`` is never silently backfilled from the validator."""
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY, drop_keys=("raw_total",))])

    with pytest.raises(ValueError) as excinfo:
        _load(tmp_path)

    message = str(excinfo.value)
    assert "raw_total" in message
    assert "scripts/analyze/cap_populations.py --force" in message


def test_raw_pool_drift_raises_naming_both_files(tmp_path: Path) -> None:
    """``raw_total`` disagreeing with ``validate_raw``'s ``n_personas`` is the drift signal."""
    _build_workspace(
        tmp_path,
        [_cap_entry(_HEALTHY, raw_total=150)],
        raw_counts={_HEALTHY: (140, 150)},
    )

    with pytest.raises(ValueError) as excinfo:
        _load(tmp_path)

    message = str(excinfo.value)
    assert str(analysis_output_dir("population_cap", tmp_path) / INDEX_FILENAME) in message
    assert str(analysis_output_dir(RAW_SUMMARY_PROCESS_ID, tmp_path) / SUMMARY_FILENAME) in message
    assert "raw_total=150" in message and "n_personas=140" in message
    assert "cap_populations.py --force" in message


def test_mapped_pass_count_drift_raises_naming_both_files(tmp_path: Path) -> None:
    """The same guard on the mapped half, against the mapped roll-up."""
    _build_workspace(
        tmp_path,
        [_cap_entry(_HEALTHY, mapped_passed=120)],
        mapped_counts={_HEALTHY: (150, 99)},
    )

    with pytest.raises(ValueError) as excinfo:
        _load(tmp_path)

    message = str(excinfo.value)
    assert str(analysis_output_dir(MAPPED_SUMMARY_PROCESS_ID, tmp_path) / SUMMARY_FILENAME) in message
    assert "mapped_passed=120" in message and "passed=99" in message


def test_missing_validator_row_is_a_skip_with_a_reason(tmp_path: Path) -> None:
    """A half-run gate is pipeline progress, not corruption: skip, do not raise."""
    _build_workspace(
        tmp_path,
        [_cap_entry(_HEALTHY), _withdrawn_entry()],
        omit_mapped=[_WITHDRAWN],
    )

    records, skipped = _load(tmp_path)

    assert [r.slug for r in records] == [_HEALTHY]
    assert len(skipped) == 1
    slug, reason = skipped[0]
    assert slug == _WITHDRAWN
    assert str(analysis_output_dir(MAPPED_SUMMARY_PROCESS_ID, tmp_path) / SUMMARY_FILENAME) in reason


def test_strict_turns_a_missing_validator_row_into_an_error(tmp_path: Path) -> None:
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY)], omit_raw=[_HEALTHY])

    with pytest.raises(ValueError, match="no row in"):
        _load(tmp_path, strict=True)


def test_undecomposable_slug_is_skipped_with_a_diagnosis(tmp_path: Path) -> None:
    """Axis-naming drift is diagnosable rather than a silent disappearance."""
    _build_workspace(tmp_path, [_cap_entry("legacy_seed_0001")])

    records, skipped = _load(tmp_path)

    assert records == []
    assert len(skipped) == 1
    assert "not decomposable" in skipped[0][1]


def test_duplicate_slug_in_a_validator_summary_raises(tmp_path: Path) -> None:
    """The roll-up is upserted by slug; a duplicate makes the counts ambiguous."""
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY)], duplicate_raw=_HEALTHY)

    with pytest.raises(ValueError, match="appears twice"):
        _load(tmp_path)


def test_absent_validator_summary_raises_naming_its_script(tmp_path: Path) -> None:
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY)])
    (analysis_output_dir(RAW_SUMMARY_PROCESS_ID, tmp_path) / SUMMARY_FILENAME).unlink()

    with pytest.raises(FileNotFoundError) as excinfo:
        _load(tmp_path)

    assert "scripts/analyze/validate_raw_personas.py" in str(excinfo.value)


def test_absent_cap_index_raises_naming_the_gate_script(tmp_path: Path) -> None:
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY)])
    (analysis_output_dir("population_cap", tmp_path) / INDEX_FILENAME).unlink()

    with pytest.raises(FileNotFoundError) as excinfo:
        _load(tmp_path)

    assert "scripts/analyze/cap_populations.py" in str(excinfo.value)


def test_malformed_count_in_the_index_raises(tmp_path: Path) -> None:
    entry = _cap_entry(_HEALTHY)
    entry["clean_available"] = "120"
    _build_workspace(tmp_path, [entry])

    with pytest.raises(ValueError, match="clean_available"):
        _load(tmp_path)


def test_non_boolean_excluded_flag_raises(tmp_path: Path) -> None:
    """A verdict that is not a boolean cannot be reported as one."""
    entry = _cap_entry(_HEALTHY)
    entry["excluded"] = "false"
    _build_workspace(tmp_path, [entry])

    with pytest.raises(ValueError, match="boolean 'excluded'"):
        _load(tmp_path)


# --------------------------------------------------------------------------- #
# selection filters                                                             #
# --------------------------------------------------------------------------- #


def test_filters_select_without_reporting_a_skip(tmp_path: Path) -> None:
    """Filtering is selection, not a verdict: a filtered-out combo is not a skip."""
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY), _withdrawn_entry()])

    records, skipped = _load(tmp_path, models=["claude_haiku"])

    assert [r.slug for r in records] == [_HEALTHY]
    assert skipped == []


def test_slug_filter_selects_the_named_combination(tmp_path: Path) -> None:
    _build_workspace(tmp_path, [_cap_entry(_HEALTHY), _withdrawn_entry()])

    records, skipped = _load(tmp_path, slugs=[_WITHDRAWN])

    assert [r.slug for r in records] == [_WITHDRAWN]
    assert skipped == []

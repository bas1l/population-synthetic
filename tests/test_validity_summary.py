"""Tests for the folder-level validity ``_summary.csv`` roll-up (upsert + row building)."""

from __future__ import annotations

import csv
from pathlib import Path

from population_synthetic.analysis.utils.validity_csv import upsert_summary_row
from population_synthetic.analysis.validate_mapped import SUMMARY_HEADER as MAPPED_HEADER
from population_synthetic.analysis.validate_mapped import ValidateMappedSummary
from population_synthetic.analysis.validate_mapped import summary_row as mapped_summary_row
from population_synthetic.analysis.validate_raw import SUMMARY_HEADER as RAW_HEADER
from population_synthetic.analysis.validate_raw import ValidateRawSummary
from population_synthetic.analysis.validate_raw import summary_row as raw_summary_row


def _read(path: Path) -> list[list[str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def test_upsert_creates_replaces_and_sorts(tmp_path: Path):
    p = tmp_path / "_summary.csv"
    header = ("slug", "has_issues", "n_personas")
    upsert_summary_row(p, header, ("b_slug", True, 5))
    upsert_summary_row(p, header, ("a_slug", False, 3))
    upsert_summary_row(p, header, ("b_slug", False, 9))  # replace, not append

    rows = _read(p)
    assert rows[0] == list(header)
    # sorted by slug; b_slug replaced (one row) with its new values
    assert [r[0] for r in rows[1:]] == ["a_slug", "b_slug"]
    assert rows[2] == ["b_slug", "False", "9"]


def test_raw_summary_row_flags_issues_and_rate():
    summary = ValidateRawSummary(
        slug="swedish_all_pick_claude_haiku",
        n=100,
        passed=80,
        failed=20,
        missing_identity=5,
        n_expected_keys=14,
        csv_path="x",
    )
    row = raw_summary_row(summary)
    assert row == ("swedish_all_pick_claude_haiku", True, 100, 80, 20, 5, 14, 80.0)
    assert RAW_HEADER == (
        "slug",
        "has_issues",
        "n_personas",
        "passed",
        "failed",
        "missing_identity",
        "n_expected_keys",
        "pass_rate_pct",
    )


def test_raw_summary_row_carries_denominator_next_to_rate():
    """A pass rate over 14 required keys is not the same quantity as one over 15.

    The summary mixes countries (and index revisions) in one file, so ``n_expected_keys``
    must sit alongside the rate rather than being inferred from the slug.
    """
    sweden = raw_summary_row(
        ValidateRawSummary(
            slug="swedish_x", n=10, passed=10, failed=0, missing_identity=0,
            n_expected_keys=14, csv_path="x",
        )
    )
    italy = raw_summary_row(
        ValidateRawSummary(
            slug="italian_x", n=10, passed=10, failed=0, missing_identity=0,
            n_expected_keys=15, csv_path="x",
        )
    )
    rate_idx = RAW_HEADER.index("pass_rate_pct")
    n_idx = RAW_HEADER.index("n_expected_keys")
    assert sweden[rate_idx] == italy[rate_idx] == 100.0  # identical rates ...
    assert (sweden[n_idx], italy[n_idx]) == (14, 15)  # ... over different requirements


def test_raw_summary_row_clean_combo_has_no_issues():
    row = raw_summary_row(
        ValidateRawSummary(
            slug="s", n=50, passed=50, failed=0, missing_identity=0, n_expected_keys=14,
            csv_path="x",
        )
    )
    assert row[1] is False
    assert row[RAW_HEADER.index("pass_rate_pct")] == 100.0


def test_raw_summary_row_empty_combo_is_flagged():
    row = raw_summary_row(
        ValidateRawSummary(
            slug="s", n=0, passed=0, failed=0, missing_identity=0, n_expected_keys=14,
            csv_path="x",
        )
    )
    assert row[1] is True  # n == 0 counts as an issue (nothing generated)
    assert row[RAW_HEADER.index("pass_rate_pct")] == 0.0


def test_mapped_summary_row():
    row = mapped_summary_row(
        ValidateMappedSummary(slug="s", n=40, passed=30, failed=10, csv_path="x")
    )
    assert row == ("s", True, 40, 30, 10, 75.0)
    assert MAPPED_HEADER == ("slug", "has_issues", "n_personas", "passed", "failed", "pass_rate_pct")

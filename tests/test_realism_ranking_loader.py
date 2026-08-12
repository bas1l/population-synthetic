"""Unit tests for the ``realism_ranking`` loader: discovery + the two consumption gates.

The loader's job is to refuse the two inputs that would silently produce plausible but
wrong numbers -- a combination that is only half-written, and a consumption set judged
by more than one judge -- so most of these tests are about what it *rejects*.

Fixtures fabricate a minimal output base on ``tmp_path``: the capped mapped index the
discovery walk reads, plus per-combination judge artifacts under the registry-resolved
``persona_realism`` folder. No LLM, no real output base.
"""

from __future__ import annotations

import json

import pytest

from population_synthetic.analysis.realism_ranking.loader import load_competitors
from population_synthetic.analysis.utils.capped_source import MAPPED_SUBDIR
from population_synthetic.analysis.utils.realism_csv import (
    RealismPersonaRow,
    write_realism_personas_csv,
)
from population_synthetic.analysis.utils.registry import analysis_output_dir

_COUNTRY = "swedish"
_AXIS_IDS = (
    [_COUNTRY],
    ["all_pick", "all_pick_dag"],
    ["claude_haiku", "claude_sonnet"],
)
_PROVENANCE = {
    "judge_model": "claude-sonnet-5",
    "prompt_template_sha256": "abc123",
    "n_rounds": 2,
}


def _persona_row(pid: str, slug: str, *, impossible: bool, typicality: float | None,
                 model: str = "claude_haiku", strategy: str = "all_pick",
                 is_real: bool = False) -> RealismPersonaRow:
    return RealismPersonaRow(
        persona_id=pid,
        slug=slug,
        country=_COUNTRY,
        model=model,
        strategy=strategy,
        is_real_reference=is_real,
        n_rounds_attempted=2,
        n_rounds_successful=2,
        can_exist_true_votes=0 if impossible else 2,
        can_exist_majority=not impossible,
        typicality_mean=typicality,
        typicality_sd=None,
        typicality_rounds=() if typicality is None else (int(typicality), int(typicality)),
        max_severity="S3" if impossible else "",
        clash_count=1 if impossible else 0,
    )


def _write_combo(
    base, slug, *, n_impossible=1, n_possible=3, model="claude_haiku", strategy="all_pick",
    is_real=False, provenance=None, report=True, personas_csv=True, n_personas_override=None,
):
    """Write one combination's judge artifacts under the registry-resolved folder."""
    combo_dir = analysis_output_dir("persona_realism", base) / _COUNTRY / slug
    combo_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        _persona_row(f"persona_{i:05d}", slug, impossible=True, typicality=None,
                     model=model, strategy=strategy, is_real=is_real)
        for i in range(n_impossible)
    ] + [
        _persona_row(f"persona_{n_impossible + i:05d}", slug, impossible=False,
                     typicality=float(4 + i), model=model, strategy=strategy, is_real=is_real)
        for i in range(n_possible)
    ]
    if personas_csv:
        write_realism_personas_csv(rows, combo_dir / f"{slug}_personas.csv")
    if report:
        payload = {
            "process": "persona_realism",
            "combo_label": slug,
            "n_personas": n_personas_override if n_personas_override is not None else len(rows),
            "n_failed": 0,
            "impossibility": {"rate": n_impossible / len(rows), "lo": 0.0, "hi": 1.0},
            "dispersion": {"n": n_possible, "variance": 1.0, "entropy": 1.5,
                           "tail_coverage": 0.0, "tail_threshold": 3.0},
            "reliability": {},
            "provenance": dict(provenance or _PROVENANCE),
        }
        (combo_dir / f"{slug}.json").write_text(json.dumps(payload), encoding="utf-8")
    return combo_dir


def _write_index(base, slugs):
    mapped = analysis_output_dir("population_cap", base) / MAPPED_SUBDIR
    mapped.mkdir(parents=True, exist_ok=True)
    entries = [{"slug": slug, "synthetic_file": f"{slug}.json"} for slug in slugs]
    (mapped / "_index.json").write_text(json.dumps(entries), encoding="utf-8")


def _base(tmp_path, slugs):
    _write_index(tmp_path, slugs)
    return tmp_path


_SLUG_A = "swedish_all_pick_claude_haiku"
_SLUG_B = "swedish_all_pick_dag_claude_sonnet"
_REAL = f"real_{_COUNTRY}"


# --------------------------------------------------------------------------- #
# discovery                                                                    #
# --------------------------------------------------------------------------- #


def test_loads_synthetic_combinations_and_the_real_competitor(tmp_path):
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_combo(base, _SLUG_A)
    _write_combo(base, _SLUG_B, model="claude_sonnet", strategy="all_pick_dag")
    _write_combo(base, _REAL, is_real=True, model="", strategy="")

    records, skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    assert skipped == []
    assert {r.slug for r in records} == {_SLUG_A, _SLUG_B, _REAL}
    real = next(r for r in records if r.is_real_reference)
    assert real.model == "" and real.strategy == ""
    # The bootstrap's sampling unit is rebuilt from the tidy rows, not read from the report.
    record = next(r for r in records if r.slug == _SLUG_A)
    assert record.impossible_indicators == (1, 0, 0, 0)
    assert record.typicality_means == (4.0, 5.0, 6.0)


def test_missing_real_competitor_is_a_skip_not_a_failure(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A)
    records, skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    assert [r.slug for r in records] == [_SLUG_A]
    assert any(slug == _REAL for slug, _ in skipped)


# --------------------------------------------------------------------------- #
# gate 1: completeness                                                         #
# --------------------------------------------------------------------------- #


def test_partial_directory_without_report_is_skipped_with_reason(tmp_path):
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_combo(base, _SLUG_A)
    _write_combo(base, _SLUG_B, report=False)  # verdict caches but no report
    records, skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    assert [r.slug for r in records] == [_SLUG_A]
    reason = dict(skipped)[_SLUG_B]
    assert "no combination report" in reason


def test_partial_directory_raises_under_strict(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A, report=False)
    with pytest.raises(RuntimeError, match="not consumable"):
        load_competitors(base, axis_ids=_AXIS_IDS, strict=True)


def test_missing_personas_csv_is_skipped_with_an_actionable_reason(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A, personas_csv=False)
    _records, skipped = load_competitors(base, axis_ids=_AXIS_IDS)
    assert "--rewrite-artifacts" in dict(skipped)[_SLUG_A]


def test_row_count_disagreement_raises(tmp_path):
    """A CSV and a report describing different persona sets is corruption, not progress."""
    base = _base(tmp_path, [_SLUG_A])
    _write_combo(base, _SLUG_A, n_personas_override=99)
    with pytest.raises(ValueError, match="n_personas=99"):
        load_competitors(base, axis_ids=_AXIS_IDS)


def test_malformed_report_raises_naming_the_upstream_script(tmp_path):
    base = _base(tmp_path, [_SLUG_A])
    combo_dir = _write_combo(base, _SLUG_A)
    (combo_dir / f"{_SLUG_A}.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="analyze_persona_realism.py"):
        load_competitors(base, axis_ids=_AXIS_IDS)


# --------------------------------------------------------------------------- #
# gate 2: homogeneity                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "key, value",
    [("judge_model", "claude-haiku-4-5"), ("prompt_template_sha256", "deadbeef"), ("n_rounds", 5)],
)
def test_heterogeneous_judge_raises_naming_the_offender(tmp_path, key, value):
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_combo(base, _SLUG_A)
    _write_combo(base, _SLUG_B, model="claude_sonnet", strategy="all_pick_dag",
                 provenance={**_PROVENANCE, key: value})
    with pytest.raises(ValueError, match=_SLUG_B):
        load_competitors(base, axis_ids=_AXIS_IDS)


def test_homogeneous_set_passes_the_guard(tmp_path):
    base = _base(tmp_path, [_SLUG_A, _SLUG_B])
    _write_combo(base, _SLUG_A)
    _write_combo(base, _SLUG_B, model="claude_sonnet", strategy="all_pick_dag")
    records, _ = load_competitors(base, axis_ids=_AXIS_IDS)
    assert len(records) == 2

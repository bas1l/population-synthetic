"""Tests for the cross-factor significance path of generation_metadata (Phase 3).

Covers the previously-untested in-memory comparison logic in
``generation_metadata.comparison``:

- ``build_summary_comparison``     -- factor pooling (model pools across methods,
                                      method across models); token gating.
- ``significance_from_comparison`` -- known-answer Kruskal-Wallis (H, df) passthrough,
                                      the ``n<2`` and ``<2 groups`` skip guards, and
                                      the ``--metrics`` subset.
- ``_compact_letter_display``      -- CLD letters from a Dunn/Holm matrix: separated
                                      groups differ, overlapping groups share, a
                                      straddling middle group carries both letters.
- ``group_label``                  -- combo -> letter lookup used by the CSV writer.

Plus one integration assertion over a >=2 model x >=2 method ``01_Raw`` fixture that
the CSV group columns and the JSON ``significance`` block are emitted.

Statistics are compared with ``pytest.approx`` (never exact float equality), and the
CLD algorithm is exercised directly on hand-built Dunn matrices so it is pinned
independent of the upstream rank test.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from population_synthetic.analysis.generation_metadata import summarize
from population_synthetic.analysis.generation_metadata.combo_aggregator import METRIC_NAMES, ComboSummary
from population_synthetic.analysis.generation_metadata.comparison import (
    SUMMARY_METRIC_SPECS,
    _compact_letter_display,
    build_summary_comparison,
    group_label,
    significance_from_comparison,
)
from population_synthetic.analysis.population_cap import cap_combo
from population_synthetic.analysis.utils.registry import analysis_output_dir


def _combo(
    model: str,
    strategy: str,
    samples: dict[str, list[float]],
    *,
    country: str = "swedish",
    has_token_data: bool = True,
) -> ComboSummary:
    """A minimal ComboSummary carrying only the fields the comparison path reads."""
    return ComboSummary(
        country=country,
        model=model,
        strategy=strategy,
        n_personas=max((len(v) for v in samples.values()), default=0),
        has_token_data=has_token_data,
        metrics={},
        skipped=[],
        samples=samples,
    )


# --------------------------------------------------------------------------- #
# spec table consistency
# --------------------------------------------------------------------------- #


def test_summary_specs_cover_metric_names_in_order():
    assert tuple(s.key for s in SUMMARY_METRIC_SPECS) == tuple(METRIC_NAMES)


# --------------------------------------------------------------------------- #
# build_summary_comparison -- factor pooling
# --------------------------------------------------------------------------- #


def test_factor_pooling_concatenates_across_the_other_factor():
    # 2 models x 2 methods; "calls" is not token-gated so all four combos count.
    combos = [
        _combo("m1", "all_pick", {"calls": [1.0, 2.0]}),
        _combo("m1", "all_generate_pick", {"calls": [3.0]}),
        _combo("m2", "all_pick", {"calls": [4.0, 5.0]}),
        _combo("m2", "all_generate_pick", {"calls": [6.0, 7.0]}),
    ]
    result = build_summary_comparison(combos)
    calls = result["metrics"]["calls"]

    # model factor: m1 pools its two methods (2+1=3), m2 pools its two (2+2=4).
    by_model = calls["by_model"]["groups"]
    assert sorted(by_model["m1"]) == [1.0, 2.0, 3.0]
    assert sorted(by_model["m2"]) == [4.0, 5.0, 6.0, 7.0]

    # method factor: each method pools across both models.
    by_method = calls["by_method"]["groups"]
    assert sorted(by_method["all_pick"]) == [1.0, 2.0, 4.0, 5.0]
    assert sorted(by_method["all_generate_pick"]) == [3.0, 6.0, 7.0]

    # model x method matrix carries per-cell aggregates for every populated cell.
    matrix = calls["matrix"]
    assert matrix["models"] == ["m1", "m2"]
    assert matrix["methods"] == ["all_generate_pick", "all_pick"]


def test_token_gated_metric_skipped_without_telemetry():
    combos = [
        _combo("m1", "all_pick", {"calls": [1.0, 2.0]}, has_token_data=False),
        _combo("m2", "all_pick", {"calls": [3.0, 4.0]}, has_token_data=False),
    ]
    result = build_summary_comparison(combos)
    # non-token metric still built; token metric (cost) skipped for lack of tokens.
    assert result["metrics"]["calls"]["by_model"] is not None
    assert result["metrics"]["cost"]["skipped"]
    sig = significance_from_comparison(result)
    assert "token" in sig["metrics"]["cost"]["by_model"]["skipped"].lower()


# --------------------------------------------------------------------------- #
# significance_from_comparison -- known-answer KW + guards
# --------------------------------------------------------------------------- #


def test_significance_kruskal_known_answer_and_df():
    # Three models, one method: by_model has 3 groups A/B/C = [1,2,3]/[4,5,6]/[7,8,9].
    # No ties -> hand-computed Kruskal-Wallis H = 7.2, df = k-1 = 2.
    combos = [
        _combo("mA", "all_pick", {"calls": [1.0, 2.0, 3.0]}),
        _combo("mB", "all_pick", {"calls": [4.0, 5.0, 6.0]}),
        _combo("mC", "all_pick", {"calls": [7.0, 8.0, 9.0]}),
    ]
    sig = significance_from_comparison(build_summary_comparison(combos))
    model_block = sig["metrics"]["calls"]["by_model"]
    assert model_block["kruskal"]["H"] == pytest.approx(7.2, rel=1e-6)
    assert model_block["kruskal"]["df"] == 2
    # groups ordered by ascending median, each carrying a CLD letter.
    names = [g["name"] for g in model_block["groups"]]
    assert names == ["mA", "mB", "mC"]
    medians = [g["median"] for g in model_block["groups"]]
    assert medians == pytest.approx([2.0, 5.0, 8.0])
    # the single-method factor collapses to one group -> skipped.
    assert "skipped" in sig["metrics"]["calls"]["by_method"]


def test_significance_skips_fewer_than_two_groups():
    combos = [_combo("only", "all_pick", {"calls": [1.0, 2.0, 3.0]})]
    sig = significance_from_comparison(build_summary_comparison(combos))
    assert "need >=2 groups" in sig["metrics"]["calls"]["by_model"]["skipped"]


def test_significance_skips_group_with_n_lt_2():
    # m2 pools to a single value -> dispersion undefined -> whole factor skipped.
    combos = [
        _combo("m1", "all_pick", {"calls": [1.0, 2.0, 3.0]}),
        _combo("m2", "all_pick", {"calls": [9.0]}),
    ]
    sig = significance_from_comparison(build_summary_comparison(combos))
    skip = sig["metrics"]["calls"]["by_model"]["skipped"]
    assert "n<2" in skip
    assert "m2" in skip


def test_significance_metric_subset_restricts_metrics():
    combos = [
        _combo("mA", "all_pick", {"calls": [1.0, 2.0], "time": [1.0, 2.0]}),
        _combo("mB", "all_pick", {"calls": [3.0, 4.0], "time": [3.0, 4.0]}),
    ]
    result = build_summary_comparison(combos, metric_keys=["calls"])
    assert set(result["metrics"]) == {"calls"}
    sig = significance_from_comparison(result)
    assert list(sig["metadata"]["metrics"]) == ["calls"]


# --------------------------------------------------------------------------- #
# compact-letter display (pinned directly on hand-built Dunn matrices)
# --------------------------------------------------------------------------- #


def test_cld_separated_groups_get_distinct_letters():
    dunn = [{"a": "x", "b": "y", "p_holm": 0.001}]
    letters = _compact_letter_display(["x", "y"], dunn, alpha=0.05)
    assert letters["x"] != letters["y"]
    assert {letters["x"], letters["y"]} == {"a", "b"}


def test_cld_overlapping_groups_share_a_letter():
    dunn = [{"a": "x", "b": "y", "p_holm": 0.9}]
    letters = _compact_letter_display(["x", "y"], dunn, alpha=0.05)
    assert letters["x"] == letters["y"] == "a"


def test_cld_straddling_middle_group_carries_both_letters():
    # A differs from C, but B differs from neither -> B straddles both cliques.
    order = ["A", "B", "C"]
    dunn = [
        {"a": "A", "b": "B", "p_holm": 0.40},  # ns
        {"a": "B", "b": "C", "p_holm": 0.40},  # ns
        {"a": "A", "b": "C", "p_holm": 0.001},  # sig
    ]
    letters = _compact_letter_display(order, dunn, alpha=0.05)
    assert letters["A"] == "a"
    assert letters["C"] == "b"
    assert letters["B"] == "ab"
    # validity: groups sharing a letter are never a significant pair; A and C,
    # which are significant, share none.
    assert set(letters["A"]) & set(letters["C"]) == set()


def test_group_label_lookup_and_empty_on_skip():
    combos = [
        _combo("mA", "all_pick", {"calls": [1.0, 2.0, 3.0]}),
        _combo("mB", "all_pick", {"calls": [7.0, 8.0, 9.0]}),
    ]
    sig = significance_from_comparison(build_summary_comparison(combos))
    la = group_label(sig, "calls", "by_model", "mA")
    lb = group_label(sig, "calls", "by_model", "mB")
    assert la and lb
    # method factor skipped -> label is empty; unknown metric -> empty; no sig -> empty.
    assert group_label(sig, "calls", "by_method", "all_pick") == ""
    assert group_label(sig, "nonexistent", "by_model", "mA") == ""
    assert group_label(None, "calls", "by_model", "mA") == ""


# --------------------------------------------------------------------------- #
# integration: >=2 models x >=2 methods 01_Raw fixture -> CSV cols + JSON block
# --------------------------------------------------------------------------- #

_MODELS = ("claude_haiku", "claude_opus")
_METHODS = ("all_pick", "all_generate_pick")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def _entries(base_prompt: int) -> list[dict]:
    # Two calls with distinct per-model token magnitudes so the factors separate.
    return [
        {
            "request_sent_at": "2026-07-23T10:00:00",
            "response_received_at": "2026-07-23T10:00:05",
            "prompt_tokens": base_prompt,
            "completion_tokens": base_prompt // 2,
            "total_tokens": base_prompt + base_prompt // 2,
            "attempt": 1,
            "error": None,
        },
        {
            "request_sent_at": "2026-07-23T10:00:05",
            "response_received_at": "2026-07-23T10:00:12",
            "prompt_tokens": base_prompt + 10,
            "completion_tokens": (base_prompt + 10) // 2,
            "total_tokens": (base_prompt + 10) + (base_prompt + 10) // 2,
            "attempt": 1,
            "error": None,
        },
    ]


def _build_2x2_fixture(output_base: Path) -> None:
    raw = output_base / "01_Raw"
    magnitudes = {"claude_haiku": 100, "claude_opus": 400}
    for model in _MODELS:
        for method in _METHODS:
            slug = f"swedish_{method}_{model}"
            # Three personas per combo so pooled model/method groups have n>=2.
            for i in range(1, 4):
                _write_jsonl(
                    raw / slug / f"persona_{i:04d}" / "llm_interactions.jsonl",
                    _entries(magnitudes[model] + i),
                )
    # generation_metadata reads the capped mirror, not 01_Raw: run the real cap first
    # (n larger than any combo's persona count keeps every fixture persona).
    cap_stage = analysis_output_dir("population_cap", output_base)
    for slug_dir in sorted(p for p in raw.iterdir() if p.is_dir()):
        cap_combo(slug_dir, 100, 0, cap_stage / slug_dir.name)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_summarize_emits_group_columns_and_significance_block(tmp_path: Path):
    _build_2x2_fixture(tmp_path)
    written = summarize(output_base=tmp_path, countries=["swedish"], charts=False)
    assert "swedish" in written

    rows = _read_csv(written["swedish"]["csv"])
    header = set(rows[0].keys())
    # Group columns present for every comparison metric and both factors.
    for metric in METRIC_NAMES:
        assert f"{metric}_model_group" in header
        assert f"{metric}_method_group" in header

    # Group columns come after the scalar tail (success_rate is the last scalar).
    ordered_cols = list(rows[0].keys())
    assert ordered_cols.index("success_rate") < ordered_cols.index("calls_model_group")

    # A non-token metric with 4 combos across 2 models -> model factor computed;
    # every row carries a non-empty model-group letter for it.
    assert all(r["total_tokens_model_group"] for r in rows)

    payload = json.loads(written["swedish"]["json"].read_text(encoding="utf-8"))
    assert "significance" in payload
    sig = payload["significance"]
    assert sig["metadata"]["alpha"] == pytest.approx(0.05)
    assert set(sig["metadata"]["models"]) == set(_MODELS)
    assert set(sig["metadata"]["methods"]) == set(_METHODS)
    # KW result present for a computed metric+factor.
    model_block = sig["metrics"]["total_tokens"]["by_model"]
    assert "groups" in model_block and model_block["kruskal"]["df"] == 1
    assert "labels" in model_block["dunn"] and "p_holm" in model_block["dunn"]

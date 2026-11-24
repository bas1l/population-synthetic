"""Tests for the shared analysis statistics: Holm adjustment, Dunn post-hoc, slug decomposition.

The Holm and Dunn tests pin the hand-rolled non-parametric machinery in
``analysis.utils.stats_tests``; the ``decompose_slug`` tests pin the greedy
axis-ID parsing (and its ``None`` failure mode) in ``analysis.utils.axes``.
"""

from __future__ import annotations

import pytest

from population_synthetic.analysis.utils.axes import decompose_slug, diagnose_slug
from population_synthetic.analysis.utils.stats_tests import _holm, dunn_posthoc, summarize

COUNTRIES = ["swedish", "italian"]
STRATEGIES = ["all_pick", "all_generate_pick"]
MODELS = ["claude_sonnet", "claude_haiku", "ollama_lucie_7b"]


# --- Holm step-down ---------------------------------------------------------

def test_holm_step_down():
    # order asc: 0.01 (*3), 0.03 (*2), 0.04 (*1) with running max -> [0.03, 0.06, 0.06]
    adj = _holm([0.01, 0.04, 0.03])
    assert adj[0] == pytest.approx(0.03)
    assert adj[1] == pytest.approx(0.06)
    assert adj[2] == pytest.approx(0.06)


def test_holm_clamped_to_one():
    assert all(p <= 1.0 for p in _holm([0.9, 0.95, 0.99]))


# --- Dunn post-hoc ----------------------------------------------------------

def test_dunn_pair_count_and_holm_monotonic():
    groups = {"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]}
    res = dunn_posthoc(groups)
    assert len(res) == 3  # C(3, 2)
    for row in res:
        assert set(row) == {"a", "b", "z", "p_raw", "p_holm"}
        assert row["p_holm"] >= row["p_raw"] - 1e-12  # Holm never reduces p
        assert 0.0 <= row["p_raw"] <= 1.0
        assert 0.0 <= row["p_holm"] <= 1.0


def test_dunn_z_sign_follows_rank_difference():
    # Group "low" is entirely below "high"; mean-rank(low) < mean-rank(high) -> z < 0.
    res = dunn_posthoc({"low": [1, 2, 3, 4], "high": [10, 11, 12, 13]})
    assert len(res) == 1
    row = res[0]
    assert (row["a"], row["b"]) == ("low", "high")
    assert row["z"] < 0


def test_dunn_identical_values_degenerate():
    res = dunn_posthoc({"a": [5, 5, 5], "b": [5, 5, 5]})
    assert len(res) == 1
    assert res[0]["z"] == 0.0
    assert res[0]["p_raw"] == 1.0


def test_dunn_fewer_than_two_groups():
    assert dunn_posthoc({"only": [1, 2, 3]}) == []
    assert dunn_posthoc({}) == []


# --- summarize (phase-stable fields; q1/q3 convention asserted in Phase 2) ---

def test_summarize_basic():
    s = summarize([1, 2, 3, 4])
    assert s["n"] == 4
    assert s["median"] == pytest.approx(2.5)
    assert s["mean"] == pytest.approx(2.5)
    assert s["min"] == 1
    assert s["max"] == 4
    # q1/q3 use the project-wide nearest-rank convention (not numpy linear).
    # idx(25%) = ceil(.25*4)-1 = 0 -> 1 ; idx(75%) = ceil(.75*4)-1 = 2 -> 3
    assert s["q1"] == pytest.approx(1.0)
    assert s["q3"] == pytest.approx(3.0)


def test_summarize_empty():
    s = summarize([])
    assert s["n"] == 0
    assert s["median"] is None


# --- decompose_slug ---------------------------------------------------------

def test_decompose_slug_basic():
    assert decompose_slug("swedish_all_pick_claude_sonnet", COUNTRIES, STRATEGIES, MODELS) == (
        "swedish", "all_pick", "claude_sonnet",
    )
    assert decompose_slug(
        "italian_all_generate_pick_ollama_lucie_7b", COUNTRIES, STRATEGIES, MODELS
    ) == ("italian", "all_generate_pick", "ollama_lucie_7b")


def test_decompose_slug_greedy_longest_model():
    # "claude_sonnet" must win over a shorter "sonnet" suffix.
    models = ["sonnet", "claude_sonnet"]
    assert decompose_slug("swedish_all_pick_claude_sonnet", COUNTRIES, STRATEGIES, models) == (
        "swedish", "all_pick", "claude_sonnet",
    )


def test_decompose_slug_undecomposable_returns_none():
    assert decompose_slug("seed_legacy_run_42", COUNTRIES, STRATEGIES, MODELS) is None
    # Valid country + model but the middle is not a known strategy.
    assert decompose_slug("swedish_bogus_claude_sonnet", COUNTRIES, STRATEGIES, MODELS) is None


def test_diagnose_slug_pinpoints_failing_axis():
    no_country = diagnose_slug("seed_legacy_run_42", COUNTRIES, STRATEGIES, MODELS)
    assert "no known country prefix" in no_country

    no_model = diagnose_slug("swedish_foo_bar", COUNTRIES, STRATEGIES, MODELS)
    assert "country 'swedish' ok" in no_model
    assert "no known model suffix" in no_model

    bad_strategy = diagnose_slug("swedish_bogus_claude_sonnet", COUNTRIES, STRATEGIES, MODELS)
    assert "not a known strategy" in bad_strategy
    assert "bogus" in bad_strategy

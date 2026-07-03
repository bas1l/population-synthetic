"""Unit tests for the standalone joint_fidelity process (builder + driver).

Covers the envelope shape returned by ``build_joint_fidelity`` (the four multivariate
sub-blocks + identity fields), the per-combo roll-up produced by
``aggregate_joint_fidelity``, and an end-to-end driver smoke test that seeds a minimal
mapped output tree and asserts the joint_fidelity/ folder + files appear. Metric
correctness itself is covered in tests/test_multivariate.py and is not duplicated here.
"""

import json

import pytest

from population_synthetic.analysis.comparison.scheme import (
    ComparisonScheme,
    GroundedJointPair,
)
from population_synthetic.analysis.joint_fidelity.builder import (
    aggregate_joint_fidelity,
    build_joint_fidelity,
)

_AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-85"]


def _pop(individuals, source="test", n=None):
    return {
        "metadata": {"source": source, "n": len(individuals) if n is None else n},
        "individuals": individuals,
    }


def _person(i, **attrs):
    base = {"id": i}
    base.update(attrs)
    return base


def _scheme():
    return ComparisonScheme(
        attributes=["age_group", "employment_status"],
        categories={
            "age_group": _AGE_GROUPS,
            "employment_status": ["Employed", "Unemployed"],
        },
        joint_pairs=[("age_group", "employment_status")],
        coherence_attributes=("age_group", "employment_status"),
        coherence_threshold=0.001,
        grounded_joint_pairs=(
            GroundedJointPair(pair=("age_group", "employment_status"), grounded=True, basis="test"),
        ),
    )


def _real_and_synth():
    real = _pop([
        _person(i, age=30, employment_status="Employed") for i in range(8)
    ] + [
        _person(8 + i, age=70, employment_status="Unemployed") for i in range(4)
    ])
    synth = _pop([
        _person(i, age=30, employment_status="Employed") for i in range(6)
    ] + [
        _person(6 + i, age=70, employment_status="Unemployed") for i in range(6)
    ])
    return real, synth


# --- build_joint_fidelity ------------------------------------------------


def test_build_joint_fidelity_returns_well_formed_envelope():
    real, synth = _real_and_synth()
    envelope = build_joint_fidelity(
        real, synth, _scheme(), slug="swedish_all_pick_claude_sonnet", country="swedish"
    )
    assert envelope["slug"] == "swedish_all_pick_claude_sonnet"
    assert envelope["country"] == "swedish"
    assert envelope["n_synthetic"] == 12
    # The four multivariate sub-blocks are present.
    multivariate = envelope["multivariate"]
    assert set(multivariate) == {
        "c2st", "association", "joint_fidelity", "combination_plausibility",
    }
    # The grounded joint pair flows through with its flag.
    pairs = multivariate["joint_fidelity"]["pairs"]
    assert len(pairs) == 1
    assert pairs[0]["grounded"] is True


# --- aggregate_joint_fidelity --------------------------------------------


def test_aggregate_joint_fidelity_one_row_per_combo():
    real, synth = _real_and_synth()
    scheme = _scheme()
    envelopes = [
        build_joint_fidelity(real, synth, scheme, slug=slug, country="swedish")
        for slug in ("swedish_all_pick_claude_sonnet", "swedish_all_pick_claude_haiku")
    ]
    rows = aggregate_joint_fidelity(envelopes)
    assert len(rows) == 2
    expected_cols = {
        "slug", "strategy", "model", "c2st_auc",
        "mean_abs_delta_v", "frobenius_norm", "mean_grounded_joint_tv",
    }
    for row in rows:
        assert set(row) == expected_cols
    # Slugs decompose against the real axis registry.
    by_slug = {r["slug"]: r for r in rows}
    assert by_slug["swedish_all_pick_claude_sonnet"]["strategy"] == "all_pick"
    assert by_slug["swedish_all_pick_claude_sonnet"]["model"] == "claude_sonnet"


# --- driver smoke test ---------------------------------------------------


def _load_driver():
    """Load the driver script by file path (scripts/ is not an importable package)."""
    import importlib.util

    from population_synthetic._paths import PROJECT_ROOT

    path = PROJECT_ROOT / "scripts" / "analyze" / "analyze_joint_fidelity.py"
    spec = importlib.util.spec_from_file_location("analyze_joint_fidelity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_driver_writes_joint_fidelity_tree(tmp_path, monkeypatch):
    driver = _load_driver()

    mapped_dir = tmp_path / "03_Analysis" / "mapped"
    mapped_dir.mkdir(parents=True)

    real, synth = _real_and_synth()
    (mapped_dir / "real_swedish.json").write_text(json.dumps(real), encoding="utf-8")
    (mapped_dir / "swedish_all_pick_claude_sonnet.json").write_text(
        json.dumps(synth), encoding="utf-8"
    )
    index = [
        {
            "slug": "swedish_all_pick_claude_sonnet",
            "country": "swedish",
            "synthetic_file": "swedish_all_pick_claude_sonnet.json",
            "real_file": "real_swedish.json",
            "n": 12,
            "skipped": 0,
        }
    ]
    (mapped_dir / "_index.json").write_text(json.dumps(index), encoding="utf-8")

    monkeypatch.setattr(
        driver.sys,
        "argv",
        [
            "analyze_joint_fidelity.py",
            "--output-base", str(tmp_path),
            "--slug", "swedish_all_pick_claude_sonnet",
            "--no-charts",
        ],
    )
    driver.main()

    joint_dir = tmp_path / "03_Analysis" / "joint_fidelity"
    assert (joint_dir / "swedish_all_pick_claude_sonnet" / "swedish_all_pick_claude_sonnet.json").is_file()
    assert (
        joint_dir / "swedish_all_pick_claude_sonnet" / "swedish_all_pick_claude_sonnet_association.csv"
    ).is_file()
    assert (joint_dir / "swedish_joint_fidelity.json").is_file()
    assert (joint_dir / "swedish_joint_fidelity.csv").is_file()

    # Non-regression: the driver must not write under comparison/ or performance/.
    assert not (tmp_path / "03_Analysis" / "comparison").exists()
    assert not (tmp_path / "03_Analysis" / "performance").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])

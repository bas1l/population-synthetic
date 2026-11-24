"""End-to-end test for the shared ``write_comparison_artifacts`` orchestrator.

Guards against the driver drift the module was created to kill: one call must lay
down the JSON report, every CSV table, and every figure. Uses a numpy-only
(``method="mmd"``) C2ST config so no sklearn backend is required.
"""

from __future__ import annotations

from population_synthetic.analysis.fidelity.artifacts import write_comparison_artifacts
from population_synthetic.analysis.fidelity.evaluator import StatisticalEvaluator
from population_synthetic.analysis.fidelity.scheme import (
    C2STConfig,
    CombinationCheck,
    ComparisonScheme,
    GroundedJointPair,
)

_AGE_GROUPS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-85"]


def _scheme():
    return ComparisonScheme(
        attributes=["age_group", "biological_sex", "education_level", "employment_status"],
        categories={
            "age_group": _AGE_GROUPS,
            "biological_sex": ["Male", "Female"],
            "education_level": ["University Degree", "High School"],
            "employment_status": ["Employed", "Unemployed"],
        },
        joint_pairs=[("age_group", "education_level")],
        coherence_attributes=("age_group", "education_level", "employment_status"),
        coherence_threshold=0.001,
        grounded_joint_pairs=(
            GroundedJointPair(pair=("age_group", "biological_sex"), grounded=True, basis="audit"),
            GroundedJointPair(pair=("age_group", "education_level"), grounded=False, basis="reference"),
        ),
        combination_checks=(
            CombinationCheck(
                attributes=("age_group", "education_level", "employment_status"),
                k=3, threshold=0.001,
            ),
        ),
        c2st_config=C2STConfig(folds=2, method="mmd", seed=0),
    )


def _pop(n, source):
    people = [
        {"id": i, "age": 30, "biological_sex": ("Male", "Female")[i % 2],
         "education_level": "University Degree", "employment_status": "Employed"}
        for i in range(n)
    ]
    return {"metadata": {"source": source, "n": n}, "individuals": people}


def test_write_comparison_artifacts_emits_full_set(tmp_path):
    scheme = _scheme()
    real_pop = _pop(20, "real")
    synthetic_pop = _pop(10, "pipeline")
    report = StatisticalEvaluator(real_pop, synthetic_pop, scheme=scheme).generate_report()

    output_path = tmp_path / "swedish_all_pick_x" / "swedish_all_pick_x.json"
    write_comparison_artifacts(
        report, real_pop, synthetic_pop, output_path, scheme,
        slug="swedish_all_pick_x", real_label="real_swedish",
    )

    base = output_path.parent
    stem = output_path.stem
    # JSON report
    assert output_path.is_file()
    # CSV tables (marginals + association + 3 multivariate + 2 legacy)
    for suffix in ["", "_association", "_c2st", "_joint_fidelity",
                   "_combination_plausibility", "_joint_chi_sq", "_coherence"]:
        assert (base / f"{stem}{suffix}.csv").is_file(), suffix

    # Figures land in the charts dir (base / stem)
    charts_dir = base / stem
    for name in ["c2st", "joint_fidelity", "combination_plausibility", "joint_chi_sq"]:
        assert (charts_dir / f"{stem}_{name}.png").is_file(), name
    # coherence: no flagged individuals here, but the two-panel figure still renders
    assert (charts_dir / f"{stem}_coherence.png").is_file()


def test_write_comparison_artifacts_no_charts_skips_figures(tmp_path):
    scheme = _scheme()
    real_pop = _pop(20, "real")
    synthetic_pop = _pop(10, "pipeline")
    report = StatisticalEvaluator(real_pop, synthetic_pop, scheme=scheme).generate_report()

    output_path = tmp_path / "slug" / "slug.json"
    write_comparison_artifacts(
        report, real_pop, synthetic_pop, output_path, scheme,
        slug="slug", real_label="real", no_charts=True,
    )
    assert output_path.is_file()
    assert (output_path.parent / "slug_c2st.csv").is_file()
    # No charts dir created when no_charts=True.
    assert not (output_path.parent / "slug").exists()


def test_write_comparison_artifacts_exclude_legacy(tmp_path):
    scheme = _scheme()
    real_pop = _pop(20, "real")
    synthetic_pop = _pop(10, "pipeline")
    report = StatisticalEvaluator(real_pop, synthetic_pop, scheme=scheme).generate_report()

    output_path = tmp_path / "slug" / "slug.json"
    write_comparison_artifacts(
        report, real_pop, synthetic_pop, output_path, scheme,
        slug="slug", real_label="real", no_charts=True, include_legacy=False,
    )
    assert (output_path.parent / "slug_c2st.csv").is_file()
    assert not (output_path.parent / "slug_joint_chi_sq.csv").exists()
    assert not (output_path.parent / "slug_coherence.csv").exists()

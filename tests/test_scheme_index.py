"""Unit tests for the ``_index.json`` reader and the index-sourced comparison scheme.

Production config is still on the legacy ``_scheme.json`` (migrated in a later
phase), so these tests build a small ``_index.json`` + per-attribute ``values``
files (plus a comparison-analysis config) under ``tmp_path`` and point
``load_scheme`` / ``load_index`` at them via the ``mappings_path`` / ``analysis_path``
arguments.
"""

import json

import pytest

from population_synthetic.analysis.mapping.real_mapper.mappings import load_index
from population_synthetic.analysis.fidelity.scheme import ComparisonScheme, load_scheme

_ANALYSIS_FILENAME = "_analysis.json"


def _write_country(
    directory, attributes, *, joint_pairs, coherence, threshold=0.001, omit=(), extra_analysis=None, deprecated=()
):
    """Write a fixture country dir: ``_index.json`` (attributes) + per-attribute files
    + an ``_analysis.json`` comparison-analysis config (cross-attribute statistics).

    ``extra_analysis`` merges extra keys (e.g. ``grounded_joint_pairs``,
    ``combination_checks``, ``c2st``) into the analysis config verbatim. ``deprecated``
    (when non-empty) is written to the index's ``deprecated_attributes`` key."""
    directory.mkdir(parents=True, exist_ok=True)
    index = {
        "description": "fixture",
        "attributes": {attr: f"{attr}.json" for attr in attributes},
    }
    if deprecated:
        index["deprecated_attributes"] = list(deprecated)
    (directory / "_index.json").write_text(json.dumps(index), encoding="utf-8")
    analysis = {
        "joint_pairs": joint_pairs,
        "coherence_attributes": coherence,
        "coherence_threshold": threshold,
    }
    if extra_analysis:
        analysis.update(extra_analysis)
    (directory / _ANALYSIS_FILENAME).write_text(json.dumps(analysis), encoding="utf-8")
    for attr, values in attributes.items():
        if attr in omit:
            continue
        (directory / f"{attr}.json").write_text(
            json.dumps({"values": values, "real": {}, "synthetic": {}}), encoding="utf-8"
        )


def _load(directory, country="swedish"):
    """Load a scheme from a fixture dir, pointing at its ``_analysis.json``."""
    return load_scheme(country, mappings_path=directory, analysis_path=directory / _ANALYSIS_FILENAME)


_AGE_BINS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-85"]


# --- _index.json reader ----------------------------------------------------

def test_load_index_returns_ordered_attributes(tmp_path):
    _write_country(
        tmp_path,
        {"age_group": _AGE_BINS, "biological_sex": ["Male", "Female"]},
        joint_pairs=[["age_group", "biological_sex"]],
        coherence=["age_group"],
    )
    index = load_index(tmp_path)
    assert list(index["attributes"]) == ["age_group", "biological_sex"]


def test_load_index_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_index(tmp_path)


def test_load_index_missing_attributes_raises(tmp_path):
    # ``attributes`` is now the only required key; joint_pairs/coherence moved out.
    (tmp_path / "_index.json").write_text(json.dumps({"description": "x"}), encoding="utf-8")
    with pytest.raises(KeyError, match="attributes"):
        load_index(tmp_path)


def test_load_index_no_longer_requires_analysis_keys(tmp_path):
    # An attributes-only index is valid: joint_pairs/coherence_attributes are not index keys.
    (tmp_path / "_index.json").write_text(
        json.dumps({"attributes": {"a": "a.json"}}), encoding="utf-8"
    )
    index = load_index(tmp_path)
    assert list(index["attributes"]) == ["a"]


def test_load_index_empty_attributes_raises(tmp_path):
    (tmp_path / "_index.json").write_text(json.dumps({"attributes": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        load_index(tmp_path)


# --- scheme built from master + per-file values + analysis config ----------

def test_scheme_built_from_index_and_values(tmp_path):
    _write_country(
        tmp_path,
        {
            "age_group": _AGE_BINS,
            "biological_sex": ["Male", "Female"],
            "employment_status": ["Employed", "Unemployed"],
        },
        joint_pairs=[["age_group", "employment_status"]],
        coherence=["age_group", "employment_status"],
    )
    scheme = _load(tmp_path)
    assert isinstance(scheme, ComparisonScheme)
    # Attribute order follows the _index.json key order.
    assert scheme.attributes == ["age_group", "biological_sex", "employment_status"]
    # age_group categories are the 7 bin labels from age.json's values.
    assert scheme.categories["age_group"] == _AGE_BINS
    assert scheme.categories["employment_status"] == ["Employed", "Unemployed"]
    # joint_pairs are tuples; coherence a tuple; threshold a float -- all from the analysis config.
    assert scheme.joint_pairs == [("age_group", "employment_status")]
    assert scheme.coherence_attributes == ("age_group", "employment_status")
    assert scheme.coherence_threshold == 0.001


def test_scheme_sources_cross_attribute_stats_from_analysis_config(tmp_path):
    # A distinctive threshold proves the value is read from the analysis config, not defaulted.
    _write_country(
        tmp_path,
        {"age_group": _AGE_BINS, "employment_status": ["Employed", "Unemployed"]},
        joint_pairs=[["age_group", "employment_status"]],
        coherence=["age_group", "employment_status"],
        threshold=0.05,
    )
    scheme = _load(tmp_path)
    assert scheme.coherence_threshold == 0.05


def test_scheme_missing_analysis_key_raises(tmp_path):
    _write_country(
        tmp_path, {"biological_sex": ["Male", "Female"]}, joint_pairs=[], coherence=[],
    )
    # Corrupt the analysis config: drop coherence_attributes.
    (tmp_path / _ANALYSIS_FILENAME).write_text(json.dumps({"joint_pairs": []}), encoding="utf-8")
    with pytest.raises(KeyError, match="coherence_attributes"):
        _load(tmp_path)


def test_scheme_missing_analysis_file_raises(tmp_path):
    _write_country(
        tmp_path, {"biological_sex": ["Male", "Female"]}, joint_pairs=[], coherence=[],
    )
    (tmp_path / _ANALYSIS_FILENAME).unlink()
    with pytest.raises(FileNotFoundError):
        _load(tmp_path)


def test_scheme_is_country_driven_by_index_contents(tmp_path):
    # Italy-like fixture: no income_source attribute in the index at all.
    sv_dir = tmp_path / "scb"
    it_dir = tmp_path / "istat"
    _write_country(
        sv_dir,
        {"age_group": _AGE_BINS, "income_source": ["Wage / Business", "Pension"]},
        joint_pairs=[], coherence=[],
    )
    _write_country(
        it_dir,
        {"age_group": _AGE_BINS, "employment_status": ["Employed", "Not Employed"]},
        joint_pairs=[], coherence=[],
    )
    sv = _load(sv_dir)
    it = _load(it_dir, "italian")
    assert "income_source" in sv.attributes
    assert "income_source" not in it.attributes


def test_scheme_missing_values_key_raises(tmp_path):
    _write_country(
        tmp_path, {"biological_sex": ["Male", "Female"]}, joint_pairs=[], coherence=[],
    )
    # Corrupt the attribute file: drop its 'values'.
    (tmp_path / "biological_sex.json").write_text(json.dumps({"real": {}}), encoding="utf-8")
    with pytest.raises(KeyError, match="values"):
        _load(tmp_path)


def test_scheme_missing_referenced_file_raises(tmp_path):
    _write_country(
        tmp_path, {"biological_sex": ["Male", "Female"]}, joint_pairs=[], coherence=[],
        omit=("biological_sex",),
    )
    with pytest.raises(FileNotFoundError):
        _load(tmp_path)


def test_legacy_scheme_json_still_read_when_no_index(tmp_path):
    # A directory with only the legacy _scheme.json is read through the old path, which
    # bundles the cross-attribute statistics inline (threshold defaults when absent).
    legacy = {
        "attributes": ["biological_sex"],
        "categories": {"biological_sex": ["Male", "Female"]},
        "joint_pairs": [],
        "coherence_attributes": [],
    }
    (tmp_path / "_scheme.json").write_text(json.dumps(legacy), encoding="utf-8")
    scheme = load_scheme("swedish", mappings_path=tmp_path)
    assert scheme.attributes == ["biological_sex"]
    assert scheme.categories["biological_sex"] == ["Male", "Female"]
    assert scheme.coherence_threshold == 0.001


# --- deprecated_attributes (analysis-axis deprecation) ---------------------

def test_deprecated_attribute_excluded_from_scheme(tmp_path):
    # A name in deprecated_attributes stays out of both .attributes and .categories,
    # while the per-attribute file is still present on disk (mapper retains it).
    _write_country(
        tmp_path,
        {
            "age_group": _AGE_BINS,
            "biological_sex": ["Male", "Female"],
            "birth_location": ["Sweden", "Outside Europe"],
        },
        joint_pairs=[["age_group", "biological_sex"]],
        coherence=["age_group"],
        deprecated=["birth_location"],
    )
    scheme = _load(tmp_path)
    assert scheme.attributes == ["age_group", "biological_sex"]
    assert "birth_location" not in scheme.attributes
    assert "birth_location" not in scheme.categories
    # The non-deprecated axes keep their category sets intact.
    assert scheme.categories["biological_sex"] == ["Male", "Female"]


def test_deprecated_unknown_attribute_raises(tmp_path):
    # A deprecated name absent from ``attributes`` is a config error -> fail loudly.
    _write_country(
        tmp_path,
        {"age_group": _AGE_BINS, "biological_sex": ["Male", "Female"]},
        joint_pairs=[], coherence=[],
        deprecated=["not_an_attribute"],
    )
    with pytest.raises(ValueError, match="deprecated_attributes"):
        _load(tmp_path)


def test_deprecated_emptying_axis_raises(tmp_path):
    # Deprecating every attribute leaves no analysis axis -> fail loudly.
    _write_country(
        tmp_path,
        {"age_group": _AGE_BINS, "biological_sex": ["Male", "Female"]},
        joint_pairs=[], coherence=[],
        deprecated=["age_group", "biological_sex"],
    )
    with pytest.raises(ValueError, match="no non-deprecated attributes"):
        _load(tmp_path)


def test_absent_deprecated_key_unchanged_behavior(tmp_path):
    # Regression guard: no deprecated_attributes key -> the full axis is retained.
    attrs = {
        "age_group": _AGE_BINS,
        "biological_sex": ["Male", "Female"],
        "birth_location": ["Sweden", "Outside Europe"],
    }
    _write_country(tmp_path, attrs, joint_pairs=[], coherence=[])
    scheme = _load(tmp_path)
    assert scheme.attributes == ["age_group", "biological_sex", "birth_location"]
    assert "birth_location" in scheme.categories


@pytest.mark.parametrize(
    "deprecated",
    [
        "birth_location",          # a bare string, not a list
        ["birth_location", 1],     # a list with a non-string entry
        {"birth_location": True},  # an object, not a list
    ],
)
def test_load_index_deprecated_attributes_must_be_list_of_strings(tmp_path, deprecated):
    (tmp_path / "_index.json").write_text(
        json.dumps({"attributes": {"a": "a.json"}, "deprecated_attributes": deprecated}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="deprecated_attributes"):
        load_index(tmp_path)


# --- multivariate config keys (grounded_joint_pairs / combination_checks / c2st) ----

def _minimal_country(directory, **extra_analysis):
    _write_country(
        directory,
        {"age_group": _AGE_BINS, "biological_sex": ["Male", "Female"]},
        joint_pairs=[["age_group", "biological_sex"]],
        coherence=["age_group"],
        extra_analysis=extra_analysis or None,
    )


def test_multivariate_keys_absent_default_cleanly(tmp_path):
    # No grounded_joint_pairs / combination_checks / c2st in the config -> empty/None defaults.
    _minimal_country(tmp_path)
    scheme = _load(tmp_path)
    assert scheme.grounded_joint_pairs == ()
    assert scheme.combination_checks == ()
    assert scheme.c2st_config is None


def test_grounded_joint_pairs_parsed(tmp_path):
    _minimal_country(
        tmp_path,
        grounded_joint_pairs=[
            {"pair": ["age_group", "biological_sex"], "grounded": True, "basis": "age_sex"},
            {"pair": ["age_group", "education_level"], "grounded": False},
        ],
    )
    scheme = _load(tmp_path)
    assert len(scheme.grounded_joint_pairs) == 2
    first = scheme.grounded_joint_pairs[0]
    assert first.pair == ("age_group", "biological_sex")
    assert first.grounded is True
    assert first.basis == "age_sex"
    second = scheme.grounded_joint_pairs[1]
    assert second.grounded is False
    assert second.basis == ""  # optional basis defaults to empty string


def test_combination_checks_parsed(tmp_path):
    _minimal_country(
        tmp_path,
        combination_checks=[
            {"attributes": ["age_group", "education_level", "employment_status"], "k": 3, "threshold": 0.002},
        ],
    )
    scheme = _load(tmp_path)
    assert len(scheme.combination_checks) == 1
    check = scheme.combination_checks[0]
    assert check.attributes == ("age_group", "education_level", "employment_status")
    assert check.k == 3
    assert check.threshold == 0.002


def test_c2st_parsed(tmp_path):
    _minimal_country(tmp_path, c2st={"folds": 5, "method": "sklearn", "seed": 42})
    scheme = _load(tmp_path)
    assert scheme.c2st_config is not None
    assert scheme.c2st_config.folds == 5
    assert scheme.c2st_config.method == "sklearn"
    assert scheme.c2st_config.seed == 42


@pytest.mark.parametrize(
    "grounded, exc",
    [
        ({"grounded_joint_pairs": {"pair": ["a", "b"], "grounded": True}}, ValueError),  # not a list
        ({"grounded_joint_pairs": [{"grounded": True}]}, KeyError),  # missing 'pair'
        ({"grounded_joint_pairs": [{"pair": ["a", "b"]}]}, KeyError),  # missing 'grounded'
        ({"grounded_joint_pairs": [{"pair": ["a", "b", "c"], "grounded": True}]}, ValueError),  # pair not length 2
        ({"grounded_joint_pairs": [{"pair": ["a", "b"], "grounded": "yes"}]}, ValueError),  # grounded not bool
    ],
)
def test_grounded_joint_pairs_malformed_raises(tmp_path, grounded, exc):
    _minimal_country(tmp_path, **grounded)
    with pytest.raises(exc):
        _load(tmp_path)


@pytest.mark.parametrize(
    "combos, exc",
    [
        ({"combination_checks": {"attributes": ["a"], "k": 1, "threshold": 0.1}}, ValueError),  # not a list
        ({"combination_checks": [{"k": 3, "threshold": 0.1}]}, KeyError),  # missing 'attributes'
        ({"combination_checks": [{"attributes": [], "k": 0, "threshold": 0.1}]}, ValueError),  # empty attributes
        ({"combination_checks": [{"attributes": ["a"], "k": "3", "threshold": 0.1}]}, ValueError),  # k not int
        ({"combination_checks": [{"attributes": ["a"], "k": 1, "threshold": "x"}]}, ValueError),  # threshold not num
    ],
)
def test_combination_checks_malformed_raises(tmp_path, combos, exc):
    _minimal_country(tmp_path, **combos)
    with pytest.raises(exc):
        _load(tmp_path)


@pytest.mark.parametrize(
    "c2st, exc",
    [
        ({"c2st": [1, 2, 3]}, ValueError),  # not an object
        ({"c2st": {"method": "sklearn", "seed": 42}}, KeyError),  # missing 'folds'
        ({"c2st": {"folds": "5", "method": "sklearn", "seed": 42}}, ValueError),  # folds not int
        ({"c2st": {"folds": 5, "method": 1, "seed": 42}}, ValueError),  # method not str
        ({"c2st": {"folds": 5, "method": "sklearn", "seed": 4.2}}, ValueError),  # seed not int
    ],
)
def test_c2st_malformed_raises(tmp_path, c2st, exc):
    _minimal_country(tmp_path, **c2st)
    with pytest.raises(exc):
        _load(tmp_path)


def test_production_scb_config_grounded_pairs_load(tmp_path):
    # The real SCB analysis config should parse and expose the grounded flag per pair.
    from population_synthetic.analysis.fidelity.scheme import _load_analysis_config
    from population_synthetic._paths import PROJECT_ROOT

    path = PROJECT_ROOT / "config" / "analysis" / "fidelity" / "scb.json"
    (_, _, _, grounded_pairs, combination_checks, c2st_config) = _load_analysis_config(path)
    assert any(gp.grounded for gp in grounded_pairs)
    assert any(not gp.grounded for gp in grounded_pairs)
    # education x employment is the documented forced-independence (non-grounded) pair.
    by_pair = {gp.pair: gp.grounded for gp in grounded_pairs}
    assert by_pair[("education_level", "employment_status")] is False
    assert by_pair[("age_group", "biological_sex")] is True
    assert combination_checks and combination_checks[0].k == 3
    assert c2st_config is not None and c2st_config.folds == 5

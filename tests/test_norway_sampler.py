"""Tests for the Norwegian SSB conditional sampler.

Pins two properties: deterministic reproducibility under a seeded RNG, and the
no-synthetic-distributions contract that ``income_source`` is dropped (the key
is omitted, matching Italy) when no API-derived distribution is available.
"""

import numpy as np

from population_synthetic.generators.real.data import PopulationDistributions
from population_synthetic.generators.real.norway.sample_service import SSBSampleService


def _make_distributions(income_source=None) -> PopulationDistributions:
    """Minimal single-outcome distributions so sampling is deterministic.

    Every marginal has one category, so the only randomness is the RNG draw
    over degenerate distributions — the output is fixed except where a real
    multi-category distribution would branch.
    """
    return PopulationDistributions(
        age_sex={(30, "Male"): 1.0},
        education_by_age={("25-34", "Male"): {"University Degree": 1.0}},
        employment_by_sex_education={
            "Male": {"University Degree": {"Employed": 1.0}}
        },
        birth_location={"Norway": 1.0},
        region={"Oslo": 1.0},
        socioeconomic={("25-34", "Male"): {"Middle Class": 1.0}},
        parental_structure={"Nuclear Family": 1.0},
        civil_status_by_age_sex={("25-34", "Male"): {"Unmarried": 1.0}},
        industry_sector={"Health and social work": 1.0},
        employment_type_by_age={("25-34", "Male"): {"Permanent|Full-time": 1.0}},
        housing_tenure={"Owned": 1.0},
        household_size={"2": 1.0},
        income_source_by_employment_age=income_source if income_source else {},
        birth_country_detail={},
        ethnicity_map={},
        tables_used=(),
    )


def test_income_source_dropped_when_no_distribution():
    # No SSB table provides income source -> the key must be absent (not None,
    # not invented), exactly as the Italian generator drops it.
    dist = _make_distributions(income_source={})
    rng = np.random.default_rng(0)
    record = SSBSampleService.sample_one(dist, rng, 0)
    assert "income_source" not in record


def test_income_source_present_when_distribution_supplied():
    dist = _make_distributions(
        income_source={("Employed", "25-34"): {"Employment income": 1.0}}
    )
    rng = np.random.default_rng(0)
    record = SSBSampleService.sample_one(dist, rng, 0)
    assert record["income_source"] == {"label": "Employment income"}


def test_seeded_sampling_is_reproducible():
    dist = _make_distributions()
    a = SSBSampleService.sample_population(dist, np.random.default_rng(42), 20)
    b = SSBSampleService.sample_population(dist, np.random.default_rng(42), 20)
    assert a == b


def test_sampled_record_has_expected_core_fields():
    dist = _make_distributions()
    record = SSBSampleService.sample_one(dist, np.random.default_rng(1), 7)
    assert record["id"] == 7
    assert record["age"] == 30
    assert record["biological_sex"]["label"] == "Male"
    assert record["education_level"] == {"label": "University Degree"}
    assert record["employment_status"] == {"label": "Employed"}
    # Employed individuals get industry + employment_type populated.
    assert record["industry_sector"] == {"label": "Health and social work"}
    assert record["employment_type"]["attachment"]["label"] == "Permanent"
    assert record["employment_type"]["hours"]["label"] == "Full-time"

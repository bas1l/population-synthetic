"""Tests for the Swedish (SCB) conditional sampler.

Pins two properties of ``SampleService.sample_one``:

- **fail-fast lookups** -- every conditional table raises ``ValueError`` on a
  missing (age_group, sex) cell instead of silently borrowing the other sex's or
  another age group's distribution;
- **hash-seed independence** -- the same RNG seed gives byte-identical output in
  two interpreters started with different ``PYTHONHASHSEED`` values (the
  published reference once depended on set iteration order).
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from population_synthetic.generators.real.data import PopulationDistributions
from population_synthetic.generators.real.helpers import VALID_AGE_GROUPS
from population_synthetic.generators.real.sweden.sample_service import SampleService

_SEXES = ("men", "women")


def _cells(dist: dict[str, float]) -> dict[tuple[str, str], dict[str, float]]:
    return {(ag, s): dict(dist) for ag in VALID_AGE_GROUPS for s in _SEXES}


def make_distributions() -> PopulationDistributions:
    """Every (age_group, sex) cell populated with a multi-category distribution."""
    age_sex = {(age, s): 1.0 for age in range(18, 86) for s in _SEXES}
    status_ages = {"20-29", "30-49", "50-64", "65-79", "80-"}
    income = {
        (emp, age): {"wage and business income": 0.7, "pensions": 0.2, "capital income": 0.1}
        for emp in ("gainfully employed", "unemployed", "students", "retired", "non gainfully employed")
        for age in sorted(status_ages)
    }
    return PopulationDistributions(
        age_sex=age_sex,
        education_by_age=_cells({"primary": 0.2, "upper secondary": 0.5, "tertiary": 0.3}),
        employment_by_sex_education=_cells({"Employed": 0.6, "Unemployed": 0.1, "Student": 0.1,
                                            "Retired": 0.1, "Sick Leave": 0.05, "Other": 0.05}),
        birth_location=_cells({"Sweden": 0.8, "EU": 0.1, "Outside EU": 0.1}),
        region={"Stockholm county": 0.5, "Skåne county": 0.5},
        region_by_age_sex=_cells({"Stockholm county": 0.5, "Skåne county": 0.5}),
        socioeconomic=_cells({"Poverty": 0.2, "Working Class": 0.3, "Middle Class": 0.4, "Wealthy": 0.1}),
        parental_structure={"Both parents": 0.7, "Single mother": 0.3},
        civil_status_by_age_sex=_cells({"single": 0.5, "married": 0.4, "divorced": 0.1}),
        industry_sector=_cells({"Healthcare": 0.5, "Manufacturing": 0.5}),
        employment_type_by_age=_cells({"permanent|35+ hours": 0.6, "temporary|1-19 hours": 0.4}),
        housing_tenure=_cells({"Rental apartment": 0.5, "Owner-occupied (villa/house)": 0.5}),
        household_size={"1 person": 0.4, "2 persons": 0.6},
        income_source_by_employment_age=income,
        birth_country_detail=_cells({"Finland": 0.5, "Iraq": 0.5}),
        ethnicity_map={},
        tables_used=(),
        employment_status_by_edu=None,
    )


def test_valid_age_groups_is_an_ordered_tuple():
    # A set iterates in PYTHONHASHSEED order; the tuple fixes youngest-to-oldest.
    assert isinstance(VALID_AGE_GROUPS, tuple)
    assert VALID_AGE_GROUPS == ("18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-85")


def test_complete_distributions_sample_cleanly():
    pop = SampleService.sample_population(make_distributions(), np.random.default_rng(1), 300)
    assert len(pop) == 300


_SEX_CONDITIONED_TABLES = (
    "education_by_age",
    "employment_by_sex_education",
    "birth_location",
    "socioeconomic",
    "civil_status_by_age_sex",
    "industry_sector",
    "employment_type_by_age",
    "housing_tenure",
    "birth_country_detail",
    "region_by_age_sex",
)


@pytest.mark.parametrize("table", _SEX_CONDITIONED_TABLES)
@pytest.mark.parametrize("empty", [False, True], ids=["absent", "empty"])
def test_missing_cell_raises_instead_of_falling_back(table: str, empty: bool):
    # Remove one cell (men, 35-44) and force every person into it; the other sex's
    # and the other age groups' cells stay populated, which is exactly what the
    # old fallbacks would have borrowed.
    base = make_distributions()
    cells = dict(getattr(base, table))
    if empty:
        cells[("35-44", "men")] = {}
    else:
        del cells[("35-44", "men")]
    overrides = {
        table: cells,
        "age_sex": {(40, "men"): 1.0},
        # Make every gated step run: employed (industry/employment_type) and
        # foreign-born (birth_country_detail).
        "employment_by_sex_education": (
            cells if table == "employment_by_sex_education" else _cells({"Employed": 1.0})
        ),
        "birth_location": cells if table == "birth_location" else _cells({"Finland": 1.0}),
    }
    dist = dataclasses.replace(base, **overrides)
    with pytest.raises(ValueError, match=r"\('35-44', 'men'\)"):
        SampleService.sample_one(dist, np.random.default_rng(0), 0)


def test_missing_income_source_age_cell_raises():
    base = make_distributions()
    income = {k: v for k, v in base.income_source_by_employment_age.items() if k[1] != "30-49"}
    dist = dataclasses.replace(base, income_source_by_employment_age=income, age_sex={(40, "men"): 1.0})
    with pytest.raises(ValueError, match="age_group='35-44'"):
        SampleService.sample_one(dist, np.random.default_rng(0), 0)


def test_missing_income_source_status_raises():
    base = make_distributions()
    income = {k: v for k, v in base.income_source_by_employment_age.items() if k[0] != "gainfully employed"}
    dist = dataclasses.replace(
        base,
        income_source_by_employment_age=income,
        employment_by_sex_education=_cells({"Employed": 1.0}),
    )
    with pytest.raises(ValueError, match="gainfully employed"):
        SampleService.sample_one(dist, np.random.default_rng(0), 0)


_SUBPROCESS_SAMPLER = """
import json, sys
import numpy as np
sys.path.insert(0, {tests_dir!r})
from test_sweden_sampler import make_distributions
from population_synthetic.generators.real.sweden.sample_service import SampleService
pop = SampleService.sample_population(make_distributions(), np.random.default_rng(42), 2000)
sys.stdout.write(json.dumps(pop, sort_keys=True, default=str))
"""


def _sample_under_hashseed(seed: str) -> str:
    env = dict(os.environ, PYTHONHASHSEED=seed)
    code = _SUBPROCESS_SAMPLER.format(tests_dir=os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    return out.stdout


def test_sampling_is_identical_across_hash_seeds():
    a = _sample_under_hashseed("0")
    b = _sample_under_hashseed("1")
    assert json.loads(a), "subprocess produced no population"
    assert a == b


def test_region_is_drawn_from_the_individuals_own_age_sex_cell():
    # Region used to be one national marginal; it now follows (age_group, sex) like the
    # other conditioned attributes. Give two cells disjoint county sets and check that
    # every individual in the cell draws only from that cell's counties.
    base = make_distributions()
    cells = dict(base.region_by_age_sex)
    cells[("35-44", "men")] = {"Stockholm county": 1.0}
    cells[("65-74", "women")] = {"Skåne county": 1.0}
    dist = dataclasses.replace(base, region_by_age_sex=cells)
    for age, sex, expected in ((40, "men", "Stockholm county"), (70, "women", "Skåne county")):
        one = dataclasses.replace(dist, age_sex={(age, sex): 1.0})
        regions = {
            SampleService.sample_one(one, np.random.default_rng(seed), 0)["region"]["label"]
            for seed in range(30)
        }
        assert regions == {expected}


def test_region_by_age_sex_is_required():
    dist = dataclasses.replace(make_distributions(), region_by_age_sex=None)
    with pytest.raises(ValueError, match="region"):
        SampleService.sample_one(dist, np.random.default_rng(0), 0)


# --- income_source fallback for students aged 65 and over (declared nearest-lower-band rule) ---

def _students_only(missing_age_keys: set[str]) -> PopulationDistributions:
    """Everyone is a student; the students' 55-64 mix is distinctive, listed bands removed."""
    base = make_distributions()
    income = {k: dict(v) for k, v in base.income_source_by_employment_age.items()}
    income[("students", "50-64")] = {"general allowance": 1.0}
    income = {k: v for k, v in income.items() if not (k[0] == "students" and k[1] in missing_age_keys)}
    return dataclasses.replace(
        base,
        income_source_by_employment_age=income,
        employment_by_sex_education=_cells({"Student": 1.0}),
    )


@pytest.mark.parametrize("age", [65, 70, 74, 75, 80, 85])
def test_students_aged_65_plus_use_the_55_64_student_income_mix(age):
    dist = dataclasses.replace(_students_only({"65-79", "80-"}), age_sex={(age, "men"): 1.0})
    for seed in range(20):
        ind = SampleService.sample_one(dist, np.random.default_rng(seed), 0)
        assert ind["employment_status"]["label"] == "Student"
        assert ind["income_source"]["label"] == "general allowance"


def test_student_income_fallback_does_not_override_a_delivered_cell():
    # If the table does deliver the 65-79 student cell, that cell is used, not the 55-64 mix.
    dist = _students_only({"80-"})
    income = dict(dist.income_source_by_employment_age)
    income[("students", "65-79")] = {"pensions": 1.0}
    dist = dataclasses.replace(dist, income_source_by_employment_age=income, age_sex={(70, "men"): 1.0})
    ind = SampleService.sample_one(dist, np.random.default_rng(0), 0)
    assert ind["income_source"]["label"] == "pensions"


def test_income_fallback_is_limited_to_the_declared_pairs():
    # A student aged 40 with no 30-49 cell still raises: the rule covers students 65+ only.
    dist = dataclasses.replace(_students_only({"30-49"}), age_sex={(40, "men"): 1.0})
    with pytest.raises(ValueError, match="age_group='35-44'"):
        SampleService.sample_one(dist, np.random.default_rng(0), 0)
    # Another status aged 70 with no 65-79 cell still raises.
    base = make_distributions()
    income = {k: v for k, v in base.income_source_by_employment_age.items()
              if not (k[0] == "retired" and k[1] == "65-79")}
    dist = dataclasses.replace(
        base,
        income_source_by_employment_age=income,
        employment_by_sex_education=_cells({"Retired": 1.0}),
        age_sex={(70, "men"): 1.0},
    )
    with pytest.raises(ValueError, match="age_group='65-74'"):
        SampleService.sample_one(dist, np.random.default_rng(0), 0)


def test_student_income_fallback_raises_when_the_55_64_source_cell_is_missing():
    dist = dataclasses.replace(_students_only({"50-64", "65-79", "80-"}), age_sex={(70, "men"): 1.0})
    with pytest.raises(ValueError, match="age_group='65-74'"):
        SampleService.sample_one(dist, np.random.default_rng(0), 0)

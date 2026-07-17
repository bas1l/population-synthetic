"""Unit tests for the rewritten Swedish (SCB) source parsers.

Phase 5.2 of the SCB source-improvements plan. Each of the six attributes whose
source was switched or enriched gets a parser test driven by a **recorded
json-stat2 fixture** (captured once from the live SCB PxWeb API and saved under
``tests/data/sweden_parsers/`` -- the tests never hit the network). The fixtures
use reduced age selections to stay small while preserving the real dimension
layout, category codes, and labels.

The tests assert:

- the emitted dict shape / keys (``(age_group, sex) -> {label: probability}``),
- per-subgroup probability normalisation,
- that the in-parser collapses (NACE SNI2007 -> 12 sectors, Boendeform -> 3
  tenures, status ContentsCode -> 6 statuses) **sum real cells correctly** --
  verified against an independent re-indexing of the same fixture,
- the 75+ handling (register bands capped at 74 are folded onto the 75-85 group),
- the explicit ``OKANT`` (unknown birth) drop,

and finally that the concrete :class:`SwedishRealMapper` (loaded from the on-disk
``config/mapping/scb_native`` config) **resolves every raw label** the parsers now
emit -- guarding the same resolution surface as ``test_mapping_engine`` /
``test_real_mapper_base`` for the switched attributes.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.mapping.real_mapper.mappings import load_mappings
from population_synthetic.analysis.mapping.real_mapper.sweden import SwedishRealMapper
from population_synthetic.generators.real.sweden import parsers as P

_FIXTURE_DIR = Path(__file__).parent / "data" / "sweden_parsers"


def _load(name: str) -> dict:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


# --- independent json-stat2 cell indexer (mirror-free correctness oracle) ---


def _cell(raw: dict, selection: dict[str, str]) -> float:
    """Return the value at the *selection* (dim_id -> category code) of a
    json-stat2 dataset, computing the flat index independently of the parsers.

    Row-major (last dimension varies fastest), the json-stat2 contract.
    """
    dataset = raw.get("dataset", raw)
    dim_ids = dataset["id"]
    sizes = dataset["size"]
    values = dataset["value"]

    strides: dict[str, int] = {}
    acc = 1
    for key, size in zip(reversed(dim_ids), reversed(sizes)):
        strides[key] = acc
        acc *= size

    idx = 0
    for dim, code in selection.items():
        ordinal = list(dataset["dimension"][dim]["category"]["index"]).index(code)
        idx += ordinal * strides[dim]
    v = values[idx]
    return float(v or 0)


def _sums_to_one(dist: dict[str, float]) -> bool:
    return math.isclose(sum(dist.values()), 1.0, abs_tol=1e-9)


# --- education_level (UtbBefRegionR, 16-95+) --------------------------------


def test_education_parser_shape_and_75plus_coverage():
    result = P.parse_education_by_age(_load("education.json"), {})
    # Keyed by (age_group, sex); every inner dist normalised.
    assert all(isinstance(k, tuple) and len(k) == 2 for k in result)
    for dist in result.values():
        assert _sums_to_one(dist)
    # The fixture captured age 80 -> the 75-85 group is now populated (the switch
    # from the old 16-74 table closes the 75+ attainment gap).
    assert ("75-85", "men") in result
    assert ("75-85", "women") in result
    # All 8 ISCED97 levels present for a populated subgroup.
    assert len(result[("25-34", "men")]) == 8


# --- socioeconomic_class (SamForvInk1a, single-year) ------------------------


def test_socioeconomic_parser_single_year_folds_to_groups():
    result = P.parse_socioeconomic(_load("socioeconomic.json"))
    # Single-year ages folded into canonical groups; 4 income classes each.
    for key, dist in result.items():
        assert set(dist) == {"Poverty", "Working Class", "Middle Class", "Wealthy"}
        assert _sums_to_one(dist)
    assert ("18-24", "men") in result
    assert ("65-74", "women") in result


def test_socioeconomic_parser_tolerates_confidentiality_nulls():
    # Age 18 x high brackets are legitimately suppressed (null). The parser must
    # skip them without crashing and still produce a valid class distribution.
    raw = _load("socioeconomic.json")
    values = raw.get("dataset", raw)["value"]
    assert any(v is None for v in values), "fixture should carry suppressed cells"
    result = P.parse_socioeconomic(raw)
    assert result  # parsed despite nulls


# --- birth_location (FolkmFodlandHVD, age x sex) ----------------------------


def test_birth_location_parser_conditional_and_drops_okant():
    result = P.parse_birth_location(_load("birth_location.json"), {})
    assert ("18-24", "men") in result and ("65-74", "women") in result
    for dist in result.values():
        assert _sums_to_one(dist)
        # OKANT (unknown country of birth) has no canonical target and is dropped.
        assert not any("unknown" in lbl.lower() or "okant" in lbl.lower() for lbl in dist)
    # The three known birth-region buckets survive.
    assert len(result[("18-24", "men")]) == 3


# --- industry_sector (ArRegSNI2007Riket, NACE -> 12 sectors) ----------------


def test_industry_parser_collapses_to_12_sectors_and_sums_correctly():
    raw = _load("industry_sector.json")
    result = P.parse_industry_sector(raw)
    # At most the 12 canonical sectors, all from the canonical label set.
    canonical = set(P._SNI2007_TO_SECTOR.values())
    for dist in result.values():
        assert set(dist).issubset(canonical)
        assert _sums_to_one(dist)
    # Independent oracle: aggregate the raw SNI cells for (18-24, men) by the
    # collapse map and confirm the parser's normalised sector split matches.
    men_code = list(_load("industry_sector.json")["dimension"]["Kon"]["category"]["index"])[0]
    expected: dict[str, float] = {}
    for sni_code, sector in P._SNI2007_TO_SECTOR.items():
        v = _cell(raw, {"SNI2007": sni_code, "Kon": men_code, "Alder": "20-24"})
        expected[sector] = expected.get(sector, 0.0) + v
    total = sum(expected.values())
    expected_norm = {k: v / total for k, v in expected.items()}
    got = result[("18-24", "men")]
    for sector, p in expected_norm.items():
        assert got.get(sector, 0.0) == pytest.approx(p)


def test_industry_parser_expands_65_74_band_onto_75_85():
    # The register caps employment at 74; the 65-74 band's mix is reused for the
    # 75-85 group so 75+ is modelled from real cells, not an invented split.
    result = P.parse_industry_sector(_load("industry_sector.json"))
    assert result[("65-74", "men")] == result[("75-85", "men")]


# --- housing_tenure (HushallT31, Boendeform -> 3 tenures) -------------------


def test_housing_parser_collapses_to_3_tenures_and_sums_correctly():
    raw = _load("housing_tenure.json")
    result = P.parse_housing_tenure(raw, {})
    tenures = {P._HT_OWNER, P._HT_TENANT, P._HT_RENTAL}
    for dist in result.values():
        assert set(dist).issubset(tenures)
        assert _sums_to_one(dist)
    # Independent oracle for (18-24, women): SMBO + FBBO both fold into
    # tenant-owned, so the collapse must sum the two source codes.
    women_code = list(raw["dimension"]["Kon"]["category"]["index"])[1]
    expected: dict[str, float] = {}
    for code, tenure in P._BOENDEFORM_TO_TENURE.items():
        v = _cell(raw, {"Boendeform": code, "Kon": women_code, "Alder": "18"})
        expected[tenure] = expected.get(tenure, 0.0) + v
    total = sum(expected.values())
    got = result[("18-24", "women")]
    for tenure, count in expected.items():
        assert got.get(tenure, 0.0) == pytest.approx(count / total)


# --- employment_status (ArRegArbStatus, 6-cat register) ---------------------


def test_employment_status_parser_6cat_and_sums_correctly():
    raw = _load("employment_status.json")
    result = P.parse_employment_by_sex_education(raw)
    six = {"Employed", "Unemployed", "Student", "Retired", "Sick Leave", "Other"}
    for dist in result.values():
        assert set(dist).issubset(six)
        assert _sums_to_one(dist)
    # Independent oracle for (55-64, men): each status ContentsCode -> its label,
    # over the 060-64 band that folds into the 55-64 group.
    men_code = list(raw["dimension"]["Kon"]["category"]["index"])[0]
    expected: dict[str, float] = {}
    for code, status in P._EMPLOYMENT_STATUS_CODE_TO_LABEL.items():
        v = _cell(raw, {"ContentsCode": code, "Kon": men_code, "Alder": "060-64"})
        expected[status] = expected.get(status, 0.0) + v
    total = sum(expected.values())
    got = result[("55-64", "men")]
    for status, count in expected.items():
        assert got.get(status, 0.0) == pytest.approx(count / total)


def test_employment_status_parser_models_75plus_from_70_74_band():
    # 75-85 is derived from the 70-74 band only; the register's oldest cells are
    # retiree-dominated, so 75+ comes out predominantly Retired.
    result = P.parse_employment_by_sex_education(_load("employment_status.json"))
    assert ("75-85", "men") in result
    dist = result[("75-85", "men")]
    assert dist["Retired"] == max(dist.values())


# --- mapping resolution: every emitted raw label resolves --------------------


@pytest.fixture(scope="module")
def sweden_mapper() -> SwedishRealMapper:
    mappings = load_mappings(PROJECT_ROOT / "config" / "mapping" / "scb_native")
    return SwedishRealMapper(mappings)


def _emitted_labels(result: dict) -> set[str]:
    labels: set[str] = set()
    for dist in result.values():
        labels.update(dist)
    return labels


@pytest.mark.parametrize(
    "attr, fixture, parse",
    [
        ("education_level", "education.json", lambda r: P.parse_education_by_age(r, {})),
        ("birth_location", "birth_location.json", lambda r: P.parse_birth_location(r, {})),
        ("socioeconomic_class", "socioeconomic.json", P.parse_socioeconomic),
        ("industry_sector", "industry_sector.json", P.parse_industry_sector),
        ("housing_tenure", "housing_tenure.json", P.parse_housing_tenure),
        ("employment_status", "employment_status.json", P.parse_employment_by_sex_education),
    ],
)
def test_scb_native_mapping_resolves_every_new_raw_label(sweden_mapper, attr, fixture, parse):
    raw = _load(fixture)
    # housing/birth take an age_group_map; the rest don't. Dispatch on arity.
    try:
        result = parse(raw, {})  # type: ignore[call-arg]
    except TypeError:
        result = parse(raw)
    for label in _emitted_labels(result):
        out = sweden_mapper.normalize_individual({"id": "t", attr: {"label": label}})
        assert out[attr] is not None, f"{attr}: raw label {label!r} did not resolve"


# --- Phase 6: employment_status two-table MERGE (opt-in, all-register) --------
#
# The merge is the ONE place the generator combines tables rather than reading
# one, so its derivation is tested directly: the closed-form
# ``w(k) = P(k|A,s)*P(k|E,s)/P(k|s)`` combine, the NILF re-expansion, and the
# full parser end-to-end against hand-computed margins (no network / fixtures on
# disk -- the two json-stat2 payloads are constructed in-test).


def test_combine_status_3cat_matches_hand_computed_odds_multiplication():
    # Known margins: P(S|A,s), P(S|E,s), baseline P(S|s) over emp/unemp/nilf.
    p_age3 = {"employed": 0.6, "unemployed": 0.1, "nilf": 0.3}
    p_edu3 = {"employed": 0.8, "unemployed": 0.05, "nilf": 0.15}
    p_base3 = {"employed": 0.7, "unemployed": 0.08, "nilf": 0.22}
    got = P._combine_status_3cat(p_age3, p_edu3, p_base3)
    # w = [0.6*0.8/0.7, 0.1*0.05/0.08, 0.3*0.15/0.22] = [0.6857143, 0.0625, 0.2045455]
    # normalised by sum 0.9527597:
    assert got["employed"] == pytest.approx(0.7197137, abs=1e-6)
    assert got["unemployed"] == pytest.approx(0.0655989, abs=1e-6)
    assert got["nilf"] == pytest.approx(0.2146873, abs=1e-6)
    assert sum(got.values()) == pytest.approx(1.0)


def test_combine_status_3cat_null_edu_falls_back_to_age_only():
    # A suppressed edu leg (empty) => the combine reduces to the age-only vector.
    p_age3 = {"employed": 0.55, "unemployed": 0.12, "nilf": 0.33}
    p_base3 = {"employed": 0.7, "unemployed": 0.08, "nilf": 0.22}
    got = P._combine_status_3cat(p_age3, {}, p_base3)
    assert got == pytest.approx(p_age3)
    # A single missing status also falls back for that status only (factor 1).
    partial = P._combine_status_3cat(
        p_age3, {"employed": 0.8, "nilf": 0.2}, p_base3  # 'unemployed' absent
    )
    assert sum(partial.values()) == pytest.approx(1.0)


def test_expand_nilf_splits_by_age_only_proportions():
    combined3 = {"employed": 0.72, "unemployed": 0.06, "nilf": 0.22}
    # Age-only 6-cat NILF sub-structure (employed/unemployed values irrelevant here).
    p_age6 = {
        "Employed": 0.6, "Unemployed": 0.1,
        "Student": 0.18, "Retired": 0.03, "Sick Leave": 0.03, "Other": 0.06,
    }
    out = P._expand_nilf(combined3, p_age6)
    assert set(out) == {"Employed", "Unemployed", "Student", "Retired", "Sick Leave", "Other"}
    assert out["Employed"] == pytest.approx(0.72)
    assert out["Unemployed"] == pytest.approx(0.06)
    # NILF sub-shares: Student 0.18/0.30=0.6 of the 0.22 NILF mass, etc.
    assert out["Student"] == pytest.approx(0.22 * 0.6)
    assert out["Other"] == pytest.approx(0.22 * 0.2)
    assert sum(out.values()) == pytest.approx(1.0)


def _jsonstat(id_order: list[str], cats: dict[str, list[tuple[str, str]]], cell) -> dict:
    """Build a minimal row-major json-stat2 dataset for the merge parser tests."""
    import itertools

    size = [len(cats[d]) for d in id_order]
    strides: dict[str, int] = {}
    acc = 1
    for d, s in zip(reversed(id_order), reversed(size)):
        strides[d] = acc
        acc *= s
    ordinals = {d: {c: i for i, (c, _) in enumerate(cats[d])} for d in id_order}
    values: list[float] = [0.0] * acc
    for combo in itertools.product(*[[c for c, _ in cats[d]] for d in id_order]):
        sel = dict(zip(id_order, combo))
        idx = sum(strides[d] * ordinals[d][sel[d]] for d in id_order)
        values[idx] = cell(sel)
    dimension = {
        d: {
            "category": {
                "index": {c: i for i, (c, _) in enumerate(cats[d])},
                "label": {c: lbl for c, lbl in cats[d]},
            }
        }
        for d in id_order
    }
    return {"id": id_order, "size": size, "dimension": dimension, "value": values}


def _merge_fixtures() -> tuple[dict, dict]:
    # Register status leg: 6-cat counts for one 5-year band (20-24 -> group 18-24)
    # plus the 15-74 baseline, both sexes (women mirror men).
    status_cc = [
        ("000002NT", "number of employed"),
        ("000002NM", "number of unemployed"),
        ("000002NR", "number of students"),
        ("000002NP", "number of retirees"),
        ("000002NQ", "number of sick"),
        ("000002NO", "number of others"),
    ]
    band = {"000002NT": 600, "000002NM": 100, "000002NR": 200,
            "000002NP": 10, "000002NQ": 40, "000002NO": 50}
    base = {"000002NT": 700, "000002NM": 80, "000002NR": 100,
            "000002NP": 100, "000002NQ": 10, "000002NO": 10}

    def status_cell(sel: dict) -> float:
        table = band if sel["Alder"] == "20-24" else base
        return float(table[sel["ContentsCode"]])

    raw_status = _jsonstat(
        ["Kon", "Alder", "ContentsCode"],
        {
            "Kon": [("1", "men"), ("2", "women")],
            "Alder": [("20-24", "20-24 years"), ("15-74", "15-74 years")],
            "ContentsCode": status_cc,
        },
        status_cell,
    )

    # Education leg: 3-cat status x edu (codes 21 & 61) x sex; women mirror men.
    edu_cc = [
        ("0000088H", "number of employed"),
        ("0000088A", "number of unemployed"),
        ("0000088C", "number of people not in the labour force"),
    ]
    edu_counts = {
        "61": {"0000088H": 800, "0000088A": 50, "0000088C": 150},
        "21": {"0000088H": 400, "0000088A": 150, "0000088C": 450},
    }

    def edu_cell(sel: dict) -> float:
        return float(edu_counts[sel["UtbildningsNiva"]][sel["ContentsCode"]])

    raw_edu = _jsonstat(
        ["Kon", "UtbildningsNiva", "ContentsCode"],
        {
            "Kon": [("1", "men"), ("2", "women")],
            "UtbildningsNiva": [("21", "primary and lower secondary education"),
                                ("61", "post-secondary 3+ incl postgraduate")],
            "ContentsCode": edu_cc,
        },
        edu_cell,
    )
    return raw_status, raw_edu


def test_parse_employment_status_combined_derivation_end_to_end():
    raw_status, raw_edu = _merge_fixtures()
    result = P.parse_employment_status_combined(raw_status, raw_edu, {})

    six = {"Employed", "Unemployed", "Student", "Retired", "Sick Leave", "Other"}
    for dist in result.values():
        assert set(dist) == six
        assert _sums_to_one(dist)

    # Keyed by (age_group, casefolded generator edu label, sex).
    pg = ("18-24", "post-graduate education (isced97 6)", "men")  # -> edu code 61
    assert pg in result
    got = result[pg]
    # Hand-computed: combine [0.6,0.1,0.3] x edu[0.8,0.05,0.15]/base[0.7,0.08,0.22]
    # => 3-cat [0.7197137, 0.0655989, 0.2146873]; NILF re-expanded by age sub-split
    # (student 200/300, retired 10/300, sick 40/300, other 50/300).
    assert got["Employed"] == pytest.approx(0.7197137, abs=1e-6)
    assert got["Unemployed"] == pytest.approx(0.0655989, abs=1e-6)
    assert got["Student"] == pytest.approx(0.2146873 * (200 / 300), abs=1e-6)
    assert got["Retired"] == pytest.approx(0.2146873 * (10 / 300), abs=1e-6)

    # Education MODULATES: a low-education persona (code 21) gets a much lower
    # Employed probability from the same age band.
    lo = result[("18-24", "primary and secondary education less than 9 years (isced97 1)", "men")]
    assert lo["Employed"] == pytest.approx(0.2997061, abs=1e-5)
    assert lo["Employed"] < got["Employed"]

    # An education whose edu leg is absent (code 4 not in the fixture) falls back
    # to the age-only conditional (== the single-table 6-cat split).
    fb = result[("18-24", "upper secondary education 3 years (isced97 3a)", "men")]
    assert fb["Employed"] == pytest.approx(0.6, abs=1e-6)  # 600/1000 age-only
    assert fb["Student"] == pytest.approx(0.2, abs=1e-6)   # 200/1000

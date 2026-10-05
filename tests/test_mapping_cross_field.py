"""The ``cross_field`` directive: engine semantics, config validation, and the production
``scb_native`` employment rules it carries.

Engine cases drive :func:`mapping_engine.resolve_traced` with small in-test blocks. The
production cases map whole raw identities through :class:`SwedishSyntheticMapper` (the path
``map_populations.py`` takes), so a rule only passes when the mapper wires the record's raw
fields and resolved siblings exactly as production does. Every production example is a raw
LLM value from the ``swedish_02`` pool (``01_Raw``), cited by combination and persona.
"""

from __future__ import annotations

import copy

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.mapping import mapping_engine
from population_synthetic.analysis.mapping.mapping_engine import MappingConfigError, resolve_traced, validate_mappings
from population_synthetic.analysis.mapping.real_mapper.mappings import load_mappings
from population_synthetic.analysis.mapping.synthetic_mapper.sweden import SwedishSyntheticMapper
from population_synthetic.analysis.utils.mapping_sentinel import UNMAPPED

from ._mapping_fixtures import SUBSTRING_MATCHING, with_matching

# ---------------------------------------------------------------------------
# Engine semantics
# ---------------------------------------------------------------------------

_VALUES = ["Employed", "Unemployed", "Retired"]


def _block(rules):
    return {
        "Employed": {"contains": ["working"]},
        "Unemployed": {"contains": ["jobless"]},
        "Retired": {"contains": ["retired"]},
        "cross_field": rules,
    }


_JOB_RULE = {"from": ["Unemployed"], "to": "Employed",
             "when": [{"field": "job", "raw": {"contains": ["part-time"], "none_of": ["former"]}}]}


def _r(raw, rules, field_raw, field_resolved=None):
    return resolve_traced(raw, _block(rules), _VALUES, matching=SUBSTRING_MATCHING, priority=_VALUES,
                          field_raw=field_raw, field_resolved=field_resolved or {})


def test_raw_condition_overrides_the_walked_value():
    res = _r("jobless", [_JOB_RULE], {"job": "part-time cashier"})
    assert res.value == "Employed"
    assert res.cross_field_rule == 0
    assert res.pre_cross_value == "Unemployed"
    assert res.walked_value == "Unemployed"


def test_condition_veto_and_absent_sibling_do_not_fire():
    assert _r("jobless", [_JOB_RULE], {"job": "former part-time cashier"}).value == "Unemployed"
    assert _r("jobless", [_JOB_RULE], {"job": None}).value == "Unemployed"
    assert _r("jobless", [_JOB_RULE], {}).value == "Unemployed"


def test_rule_only_applies_to_its_from_values():
    assert _r("retired", [_JOB_RULE], {"job": "part-time"}).value == "Retired"


def test_first_firing_rule_wins_and_only_one_fires():
    rules = [
        {"from": ["Unemployed"], "to": "Retired", "when": [{"field": "job", "raw": {"contains": ["pension"]}}]},
        {"from": ["Unemployed", "Retired"], "to": "Employed",
         "when": [{"field": "job", "raw": {"contains": ["part"]}}]},
    ]
    res = _r("jobless", rules, {"job": "pension, part-time"})
    assert res.value == "Retired"
    assert res.cross_field_rule == 0


def test_every_condition_must_hold():
    rule = {"from": ["Unemployed"], "to": "Employed",
            "when": [{"field": "job", "raw": {"contains": ["part-time"]}},
                     {"field": "age_band", "resolved": ["young"]}]}
    assert _r("jobless", [rule], {"job": "part-time"}, {"age_band": "old"}).value == "Unemployed"
    assert _r("jobless", [rule], {"job": "part-time"}, {"age_band": "young"}).value == "Employed"


def test_a_miss_is_never_overridden():
    rule = {"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "raw": {"contains": ["part"]}}]}
    res = _r("something else", [rule], {"job": "part-time"})
    assert res.value == UNMAPPED
    assert res.missed


def test_missing_context_raises():
    with pytest.raises(ValueError, match="no field_raw"):
        resolve_traced("jobless", _block([_JOB_RULE]), _VALUES, matching=SUBSTRING_MATCHING, priority=_VALUES)


def test_unresolved_sibling_raises():
    rule = {"from": ["Unemployed"], "to": "Employed", "when": [{"field": "status2", "resolved": ["x"]}]}
    with pytest.raises(ValueError, match="did not resolve first"):
        _r("jobless", [rule], {}, {})


@pytest.mark.parametrize("bounds, age, want", [
    ({"lt": 66}, 65, "Employed"),
    ({"lt": 66}, 66, "Unemployed"),
    ({"gte": 19, "lt": 66}, 18, "Unemployed"),
    ({"gte": 19, "lt": 66}, 19, "Employed"),
    ({"gte": 66}, 66, "Employed"),
])
def test_resolved_range_is_half_open(bounds, age, want):
    rule = {"from": ["Unemployed"], "to": "Employed", "when": [{"field": "age", "resolved_range": bounds}]}
    assert _r("jobless", [rule], {}, {"age": age}).value == want


@pytest.mark.parametrize("value", ["45-54", None, True])
def test_resolved_range_on_a_non_number_raises(value):
    rule = {"from": ["Unemployed"], "to": "Employed", "when": [{"field": "age", "resolved_range": {"lt": 66}}]}
    with pytest.raises(ValueError, match="not a number"):
        _r("jobless", [rule], {}, {"age": value})


def test_negation_applies_inside_a_raw_condition():
    prefix = {"token_mode": "prefix", "negation": {"cues": ["ingen"], "window": 2, "clause_breaks": [","]},
              "tie_break": ["priority"]}
    rule = {"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "raw": {"contains": ["anställning"]}}]}
    block = _block([rule])
    for raw_job, want in (("ingen anställning", "Unemployed"), ("deltidsanställning", "Unemployed"),
                          ("anställning, deltid", "Employed")):
        res = resolve_traced("jobless", block, _VALUES, matching=prefix, priority=_VALUES,
                             field_raw={"job": raw_job}, field_resolved={})
        assert res.value == want, raw_job


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def _dir(status_rules=None, job_rules=None, real_rules=None):
    status = {"values": ["Employed", "Unemployed"], "real": {"Employed": {"equals": ["1"]}},
              "synthetic": {"Employed": {"contains": ["working"]}, "Unemployed": {"contains": ["jobless"]}}}
    job = {"values": ["Perm", "NA"], "synthetic": {"Perm": {"contains": ["fast"]}, "NA": {"contains": ["ingen"]}}}
    if status_rules is not None:
        status["synthetic"]["cross_field"] = status_rules
    if job_rules is not None:
        job["synthetic"]["cross_field"] = job_rules
    if real_rules is not None:
        status["real"]["cross_field"] = real_rules
    return with_matching({"_index": {"attributes": {"status": "status.json", "job": "job.json"}},
                          "status": status, "job": job})


_OK = [{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "raw": {"contains": ["fast"]}}]}]


def test_valid_cross_field_passes():
    validate_mappings(_dir(status_rules=_OK))


@pytest.mark.parametrize("rules, match", [
    ([], "non-empty list of rules"),
    ([{"from": ["Unemployed"], "to": "Employed"}], "must declare exactly"),
    ([{"from": ["Jobless"], "to": "Employed", "when": _OK[0]["when"]}], "'from' value 'Jobless'"),
    ([{"from": ["Unemployed"], "to": "Hired", "when": _OK[0]["when"]}], "'to' value 'Hired'"),
    ([{"from": ["Unemployed", "Employed"], "to": "Employed", "when": _OK[0]["when"]}], "also in 'from'"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": []}], "non-empty list of conditions"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "regex": "x"}]}], "unknown condition kind"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "raw": {"contain": ["x"]}}]}],
     "unknown matcher key"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "resolved": []}]}], "non-empty list"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "nope", "raw": {"contains": ["x"]}}]}],
     "not an attribute"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "resolved": ["Temp"]}]}],
     "not one of job's values"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "status", "resolved": ["Employed"]}]}],
     "own value"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "status", "resolved_range": {"lt": 1}}]}],
     "own value"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "resolved_range": {}}]}],
     "one or both of"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "resolved_range": {"lte": 5}}]}],
     "one or both of"),
    ([{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "resolved_range": {"lt": "66"}}]}],
     "must be a number"),
    ([{"from": ["Unemployed"], "to": "Employed",
       "when": [{"field": "job", "resolved_range": {"gte": 66, "lt": 66}}]}], "empty range"),
])
def test_malformed_cross_field_raises(rules, match):
    with pytest.raises(MappingConfigError, match=match):
        validate_mappings(_dir(status_rules=rules))


def test_resolved_range_counts_as_a_dependency():
    status_rules = [{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "resolved_range": {"lt": 1}}]}]
    job_rules = [{"from": ["Perm"], "to": "NA", "when": [{"field": "status", "resolved": ["Unemployed"]}]}]
    assert mapping_engine.cross_field_dependencies({"cross_field": status_rules}) == ("job",)
    with pytest.raises(MappingConfigError, match="dependency cycle"):
        validate_mappings(_dir(status_rules=status_rules, job_rules=job_rules))


def test_dependency_cycle_raises():
    status_rules = [{"from": ["Unemployed"], "to": "Employed", "when": [{"field": "job", "resolved": ["Perm"]}]}]
    job_rules = [{"from": ["Perm"], "to": "NA", "when": [{"field": "status", "resolved": ["Unemployed"]}]}]
    with pytest.raises(MappingConfigError, match="dependency cycle"):
        validate_mappings(_dir(status_rules=status_rules, job_rules=job_rules))


def test_real_side_cross_field_is_rejected():
    with pytest.raises(MappingConfigError, match="only supported on the synthetic side"):
        validate_mappings(_dir(real_rules=_OK))


# ---------------------------------------------------------------------------
# Production rules (config/mapping/scb_native) through the synthetic mapper
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mapper():
    return SwedishSyntheticMapper(load_mappings(PROJECT_ROOT / "config" / "mapping" / "scb_native"))


def _map(mapper, status, job, income=None, age=45):
    identity = {"age": age, "employment_status": status, "employment_type": job}
    if income is not None:
        identity["income_source"] = income
    out = mapper.map_individual(copy.deepcopy(identity), "persona_test")
    return out["employment_status"], out["employment_type"]


# Job seeker / self-labelled unemployed who holds a current paid job -> Employed (AKU / ILO).
JOB_SEEKER_WITH_JOB = [
    # (status, employment_type, expected status, expected type) -- method E (all_generate_evaluate_random_pick_v2)
    ("Arbetssökande (registrerad på Arbetsförmedlingen)", "Deltidsanställning (20 tim/vecka)",
     "Employed", "Permanent Part-time"),  # gpt_oss_120b persona_00083
    ("Deltar i arbetsmarknadsåtgärd", "Lönebidragsanställning, deltid 20 timmar/vecka",
     "Employed", "Permanent Part-time"),  # kimi_k3 persona_00028
    ("arbetssökande", "Deltidsanställning (50%, 20h/vecka)", "Employed", "Permanent Part-time"),  # mistral_medium 00038
    ("Arbetssökande, inskriven på Arbetsförmedlingen", "Extratjänst med lönebidrag via Arbetsförmedlingen, deltid",
     "Employed", "Temporary Part-time"),  # opus_5 persona_00055 (extratjänst is fixed-term by design)
    ("Arbetslös, inskriven hos Arbetsförmedlingen",
     "Anställning med lönebidrag/anställningsstöd via Arbetsförmedlingen, deltid",
     "Employed", "Permanent Part-time"),  # opus_5 persona_00139 (permanence unstated: unchanged rule)
    ("A-kassemottagare", "Omsorgsjobb (deltid) (18 veckotimmar)", "Employed", "Permanent Part-time"),  # qwen 00264
    ("Participant in labour market program (arbetsmarknadsåtgärd)",
     "Lönebidragsanställning, tillsvidare, deltid (ca 20 timmar/vecka)",
     "Employed", "Permanent Part-time"),  # kimi_k3 persona_00054
    ("Arbetssökande", "Visstidsanställning – deltid, 20 timmar/vecka",
     "Employed", "Temporary Part-time"),  # gpt56_sol persona_00103
]
# Status stays as stated: no current paid job in the type text.
JOB_SEEKER_WITHOUT_JOB = [
    ("Arbetssökande", "Fast anställning kombinerad med partiell sjukskrivning, avslutad",
     "Unemployed", "Not Applicable"),  # opus_5 persona_00079: the job has ended
    ("Arbetssökande", "Saknar anställning", "Unemployed", None),  # glm_52 persona_00186
    ("Deltar i etableringsprogrammet hos Arbetsförmedlingen",
     "Ingen anställning – deltar i etableringsprogrammet på heltid", "Unemployed", None),  # opus_5 persona_00099
    ("Arbetsmarknadsåtgärd/praktik via Arbetsförmedlingen",
     "Arbetsmarknadspolitiskt program (arbetspraktik) på heltid, cirka 38 timmar/vecka, tidsbegränsat 6 månader",
     "Unemployed", None),  # opus_5 persona_00045: an unpaid programme is not a job
    ("Arbetssökande, inskriven hos Arbetsförmedlingen",
     "Tidigare allmän visstidsanställning på heltid, avslutad vid kontraktstidens slut",
     "Unemployed", "Not Applicable"),  # opus_5 persona_00073
    ("Arbetssökande", "Arbetssökande, deltid", "Unemployed", None),  # llama31_8b: the type text is a job search
    ("Sökande jobb", "Frivillig tjänst med ersättning", "Unemployed", None),  # gemma4_e4b persona_00051
]
# Pensioner doing current paid work -> Employed; a bare contract label or a former job is not evidence.
PENSIONER = [
    ("Pensionär", "Deltidsanställning (max 20 timmar/vecka)", "Employed", "Permanent Part-time"),  # gpt_oss 00066
    ("Retired (pensionär)", "Occasional hourly employment (timanställning), under 5 hours per week",
     "Employed", None),  # kimi_k3 persona_00085
    ("pensioner with part-time work", "part-time permanent contract (15-20 hours/week)",
     "Employed", None),  # mistral_medium persona_00339
    ("Semi-retired with reduced hours", "Tillsvidareanställning, deltid, 16 timmar/vecka",
     "Employed", "Permanent Short Part-time"),  # kimi_k3 persona_00141
    ("Aktiv pensionär med sidoinkomst", "Egen företagare (självständig)", "Employed", None),  # gpt_oss 00242
    ("Tidigare lärare (pension)", "Uppdragstagaravtal (självständig)", "Employed", None),  # gpt_oss 00226
    ("pensionär", "konsultuppdrag (deltid)", "Employed", None),  # mistral_medium persona_00126
    ("Retired", "Occasional substitute work", "Employed", None),  # mistral_medium persona_00113
    ("Semi-retired", "Fixed-term contract", "Employed", "Temporary Full-time"),  # deepseek: status says works
    ("Retired", "Full-time", "Retired", "Permanent Full-time"),  # mistral_nemo: bare label, unchanged
    ("Retired", "Self-employed", "Retired", "Self-Employed Full-time"),  # mistral_nemo persona_00123
    ("retired", "former permanent full-time employment", "Retired", "Not Applicable"),  # claude_sonnet 00040
    ("Retired", "Full-time before retirement", "Retired", "Not Applicable"),  # mistral_nemo persona_00071
    ("Retired (old-age pension)", "Permanent full-time employment (before retirement)",
     "Retired", "Not Applicable"),  # opus_5 persona_00007
    ("pensionär", "pensionär (eget företag, avvecklat)", "Retired", "Not Applicable"),  # mistral_medium 00082
    ("Pensionär", "Fast anställning (heltid) – ej sannolikt", "Retired", "Permanent Full-time"),  # gpt_oss 00320
    ("retired", "pensionär (delvis, 15 timmar/vecka)", "Retired", "Not Applicable"),  # pension wording -> NA type
]
# Early-retirement / disability pension -> Sick Leave (sjuk- och aktivitetsersättning).
DISABILITY = [
    ("Pensionär", "Hel sjukpension", None, "Sick Leave"),  # glm_52 persona_00178
    ("Early retirement", "Not employed / No active contract", "Disability pension", "Sick Leave"),  # haiku 00113
    ("retired", "none", "disability pension", "Sick Leave"),  # claude_haiku persona_00162
    ("early_retired", "not_applicable", "early_retirement_pension", "Sick Leave"),  # claude_haiku persona_00013
    ("Retired early", "Early retirement pension", "Tjänstepension (Occupational pension)",
     "Retired"),  # mistral_medium persona_00086: an occupational early pension is not förtidspension
    ("Retired", "Pension (Voluntary early retirement, Frivillig förtidspension)",
     "Occupational pension (Tjänstepension)", "Retired"),  # mistral_medium persona_00131
    ("Ålderspensionär med engagemang i föreningsliv/volontärarbete", "Oavlönat frivilligarbete i förening",
     "Allmän pension kompletterad med sjukersättning omvandlad till pension", "Retired"),  # opus_5 persona_00096
]
# Fixed-term by design / stated fixed term -> Temporary, keeping the hours band.
FIXED_TERM = [
    ("Employed part-time", "Seasonal employment, part-time", "Temporary Part-time"),  # claude_sonnet 00057
    ("Unemployed, seeking work", "Summer job, full-time (35-40 hours/week)",
     "Temporary Full-time"),  # mistral_medium persona_00072
    ("Anställd", "Provtidsanställning med 6 månadersperiod", "Temporary Full-time"),  # qwen35_flash 00207
    ("employed", "anstellning med tidsbegränsning", "Temporary Full-time"),  # deepseek persona_00145
    ("Heltidsanställd", "Heltid, tillsvidare (provtid klar)", "Permanent Full-time"),  # qwen35_flash: stated permanent
    ("Anställd", "Heltidstjänst utan tidsbegränsning", "Permanent Full-time"),  # negated cue
]


@pytest.mark.parametrize("status, job, want_status, want_type",
                         JOB_SEEKER_WITH_JOB + JOB_SEEKER_WITHOUT_JOB + PENSIONER)
def test_employment_status_cross_field(mapper, status, job, want_status, want_type):
    got_status, got_type = _map(mapper, status, job)
    assert got_status == want_status
    if want_type is not None:
        assert got_type == want_type


@pytest.mark.parametrize("status, job, income, want_status", DISABILITY)
def test_disability_pension_is_sick_leave(mapper, status, job, income, want_status):
    assert _map(mapper, status, job, income)[0] == want_status


# Sickness / activity compensation is paid at most to the month before 66 (2023-2025 rule;
# from 2026 the month before 67): from 66 the person draws an old-age pension, so the
# disability-pension wording no longer moves a pensioner to Sick Leave.
DISABILITY_BY_AGE = [
    ("Pensionär", "Sjukpensionär, 0 timmar/vecka", "Premiepension", 78, "Retired"),  # glm_52 persona_00017 (E)
    ("Pensionär", "Sjukpensionär, 0 timmar/vecka", "Premiepension", 65, "Sick Leave"),
    ("Pensionär", "Sjukpensionär, 0 timmar/vecka", "Premiepension", 66, "Retired"),
    ("Pensionär", "Förtidspensionär", "Pension", 77, "Retired"),  # mistral_nemo persona_00101 (E, v1 pool)
    ("Retired", "Disability insurance", "Pension", 88, "Retired"),  # llama31_8b persona_00082
    ("early_retired", "not_applicable", "early_retirement_pension", 60, "Sick Leave"),  # haiku 00013 text, age 60
]


@pytest.mark.parametrize("status, job, income, age, want_status", DISABILITY_BY_AGE)
def test_disability_pension_is_sick_leave_only_below_66(mapper, status, job, income, age, want_status):
    assert _map(mapper, status, job, income, age=age)[0] == want_status


@pytest.mark.parametrize("status, job, want_type", FIXED_TERM)
def test_fixed_term_is_temporary(mapper, status, job, want_type):
    assert _map(mapper, status, job)[1] == want_type


def test_employed_former_job_wording_keeps_its_contract(mapper):
    # mistral_nemo writes "Tidigare anställd" for a current job; with an Employed status the
    # ended-job rule does not fire (it reads the final employment_status).
    assert _map(mapper, "Employed", "Tidigare anställd (permanent), 35 timmar/vecka")[1] == "Permanent Full-time"


def test_cross_field_never_changes_an_unmapped_type(mapper):
    # an unmapped employment_type stays unmapped whatever the status rules do
    status, job = _map(mapper, "Arbetssökande", "Tidigareanställd")
    assert job == UNMAPPED
    assert status == "Unemployed"


def test_production_config_validates():
    mappings = load_mappings(PROJECT_ROOT / "config" / "mapping" / "scb_native")
    mapping_engine.validate_mappings(mappings)

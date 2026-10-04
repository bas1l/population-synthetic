"""Regression cases for the SCB-checked audit's rule changes on the ``scb_native`` synthetic side.

Covers ``civil_status``, ``education_level``, ``employment_status``, ``employment_type``,
``housing_tenure`` and ``income_source`` (Phase 2A of
``docs/development/plans/pending/mapping-fixes-scb-audit.md``). Every case is a raw LLM value from
the audit's curated row list with the category the SCB definition gives it:

- ``*_FIXED`` -- rows that were mapped wrongly (or left unmapped) and must now resolve as the
  verdict says;
- ``*_FALSE_ALARMS`` -- first-pass flags the review overturned: the mapping was already right and
  must not move;
- ``*_DECISIONS`` -- rows settled by a recorded decision or an open question's default rather than
  by a verdict (each named in a comment).

The cases resolve through the production config and the real engine, so a token edit that moves
any of them fails here.
"""

from __future__ import annotations

import pytest

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.analysis.mapping import mapping_engine
from population_synthetic.analysis.mapping.real_mapper.mappings import load_mappings
from population_synthetic.analysis.utils.mapping_sentinel import UNMAPPED

_TIER = PROJECT_ROOT / "config" / "mapping" / "scb_native"


@pytest.fixture(scope="module")
def resolve():
    mappings = load_mappings(_TIER)
    index = mappings["_index"]
    matching = mapping_engine.compile_matching(index["matching"]["synthetic"])

    def _resolve(attr: str, raw: str) -> str:
        block = mappings[index["attributes"][attr][:-5]]
        return mapping_engine.resolve(raw, block["synthetic"], block["values"], matching=matching,
                                      priority=block["priority"])
    return _resolve


def _cases(attr, *groups):
    return [pytest.param(attr, raw, want, id=f"{attr}:{raw[:40]}") for group in groups for raw, want in group]


# ---------------------------------------------------------------------------
# civil_status -- legal register status (SCB: a sambo is not married; no legal separation)
# ---------------------------------------------------------------------------

_SG, _MA, _DI, _WI = "Single/Never Married", "Married", "Divorced", "Widowed"

CIVIL_FIXED = [
    ("Sambo", _SG),  # decision: sambo / cohabiting -> Single
    ("cohabiting", _SG),
    ("Ej gift", _SG),  # negated 'gift' is discarded; the positive Single token places it
    ("icke gift", _SG),
    ("Separated", _MA),  # decision: a separated spouse stays G
    ("Separerad", _MA),
    ("Enskild", _SG),  # prefix mode: 'skild' no longer fires inside 'enskild'
    ("싱글", _SG),
    ("Skild, ensamstående", _DI),  # a stated prior status beats 'ensamstående'
    ("Divorced and cohabiting", _DI),
    ("Skild och sambo", _DI),
    ("Ensamstående efter skilsmässa", _DI),
    ("Widowed and cohabiting", _WI),
    ("Dödsfall i äktenskap", _WI),
    ("Ehe", _MA),
    ("In a same-sex marriage", _MA),
    ("Skiljd", _DI),
    ("Vigd", _MA),
    ("Separerad från sambo", _SG),
    ("Utan sambo", _SG),
    ("änka, ogift sedan dess", _WI),
]
CIVIL_FALSE_ALARMS = [
    ("Äktig", UNMAPPED),
    ("Ej äktig", UNMAPPED),
    ("Ingen", UNMAPPED),
]
CIVIL_DECISIONS = [
    ("Registrerad partner", _MA),  # SCB: registered partners count as married
    ("Gift (sambo)", _MA),
    ("previously married", _DI),  # open question 4 default: prior marriage, status unstated -> Divorced
    ("tidigare gift", _DI),
]

# ---------------------------------------------------------------------------
# education_level -- SUN 2000 highest completed level
# ---------------------------------------------------------------------------

_E1 = "Pre-Secondary < 9 yrs (ISCED 1)"
_E2 = "Pre-Secondary 9-10 yrs (ISCED 2)"
_E3C = "Upper Secondary ≤ 2 yrs (ISCED 3C)"
_E3A = "Upper Secondary 3 yrs (ISCED 3A)"
_E5B = "Post-Secondary < 3 yrs (ISCED 4+5B)"
_E5A = "Post-Secondary 3+ yrs (ISCED 5A)"
_E6 = "Post-Graduate (ISCED 6)"

EDUCATION_FIXED = [
    ("Gymnasieskola (2 år)", _E3C),  # 3C only with a stated <= 2-year length
    ("Associate Degree", _E5B),
    ("Högskolebehörighet", _E3A),  # entrance qualification is upper secondary
    ("Degree Programme Entrance Qualification", _E3A),
    ("Förgymnasial utbildning, kortare än 9 år", _E1),
    ("Post-secondary non-tertiary", _E5B),
    ("Pågående gymnasieutbildning", _E2),  # incomplete gymnasium: highest completed is ISCED 2
    ("SFI och grundläggande vuxenutbildning", _E2),
    ("Samhällsvetenskapsprogrammet", _E3A),
    ("Doktorandutbildning (pågående)", _E5A),  # ongoing doctorate: highest completed is 5A
    ("Ej fullgjord grundskola", _E1),
    ("Folkskola (7-årig)", _E1),  # folkskola is SUN code 1
    ("Folkskoleutbildning", _E1),
    ("Primary and lower secondary education", _E2),
    ("Högskoleförberedande examen", _E3A),
    ("Post-secondary education, less than 2 years", _E5B),
]
EDUCATION_FALSE_ALARMS = [
    ("Masterexamen", _E5A),
    ("Master's degree", _E5A),
    ("Magisterexamen", _E5A),
    ("Postgraduate diploma (Magisterexamen)", _E5A),  # lost in Phase 1 (longest), restored here
]
EDUCATION_DECISIONS = [
    ("Högskoleexamen", _E5B),  # bare högskoleexamen -> 4+5B
    ("Högskoleexamen, 3 år", _E5A),
    ("Upper secondary", _E3A),  # upper secondary, length unstated -> 3A
    ("Folkhögskola", UNMAPPED),  # no general SUN level
    ("Post-secondary education", UNMAPPED),  # open question 6 default: no length -> unmapped
    ("Eftergymnasial utbildning, 3 år eller längre", _E5A),
]

# ---------------------------------------------------------------------------
# employment_status -- AKU/BAS hierarchy Employed > Unemployed > Student > Retired > Sick > Other
# ---------------------------------------------------------------------------

EMPLOYMENT_FIXED = [
    ("Homemaker", "Other"),
    ("Hushållsansvarig", "Other"),
    ("Sjukpensionär", "Sick Leave"),  # förtidspension / sjukersättning is not Retired
    ("Förtidspensionär", "Sick Leave"),
    ("Disability Pensioner", "Sick Leave"),
    ("Job seeker", "Unemployed"),
    ("Seeking employment", "Unemployed"),
    ("Deltar i etableringsprogrammet hos Arbetsförmedlingen", "Unemployed"),
    ("Studerande på heltid", "Student"),
    ("student_full_time", "Student"),
    ("Elev", "Student"),
    ("Lärare", "Employed"),
    ("Chefsposition", "Employed"),
    ("Permitterad", "Employed"),
    ("överläkare", "Employed"),
    ("Unemployed (not seeking work)", "Other"),
]
EMPLOYMENT_FALSE_ALARMS = [  # a working student / pensioner is Employed
    ("Deltidspensionär", "Employed"),
    ("Ålderspensionär med deltidsarbete", "Employed"),
    ("Student med deltidsjobb", "Employed"),
    ("Studerande med extrajobb", "Employed"),
    ("Föräldraledig (deltid)", "Employed"),
]

# ---------------------------------------------------------------------------
# employment_type -- AKU attachment x agreed hours
# ---------------------------------------------------------------------------

EMPLOYMENT_TYPE_FIXED = [
    ("Not applicable (not employed)", "Not Applicable"),
    ("Saknar anställning", "Not Applicable"),
    ("Ingen anställning (0 timmar/vecka)", "Not Applicable"),  # zero stated hours
    ("Ingen anställning (heltidsstuderande, 0 timmar/vecka)", "Not Applicable"),
    ("FIXED_TERM_FULL_TIME", "Temporary Full-time"),
    ("Full-time with probationary period", "Temporary Full-time"),
    ("Doktorandanställning (4 år, 100%)", "Temporary Full-time"),
    ("Egen firma med F‑skatt (heltid)", "Self-Employed Full-time"),
    ("Eget företag (deltid, 15h/vecka)", "Self-Employed Short Part-time"),
    ("Enskild näringsidkare, heltid, 40 timmar/vecka", "Self-Employed Full-time"),
    ("Fast tjänst, 40 timmar/vecka", "Permanent Full-time"),
    ("Fastanställd, 80%", "Permanent Part-time"),
]
EMPLOYMENT_TYPE_FALSE_ALARMS = [
    ("Tillsvidareanställning, 36 timmar/vecka", "Permanent Full-time"),
    ("Fast anställning (35 timmar/vecka)", "Permanent Full-time"),
    ("Part-time student", "Not Applicable"),
]
EMPLOYMENT_TYPE_DECISIONS = [
    ("Tillsvidareanställning, 40 timmar i veckan", "Permanent Full-time"),  # '0 timmar' must not hit '40 timmar'
]

# ---------------------------------------------------------------------------
# housing_tenure -- tenure of the building (SMAG / BRF / rental); ägarlägenhet (OB) not fetched
# ---------------------------------------------------------------------------

_OW = "Owner-occupied (villa/house)"
_TO = "Tenant-owned apartment (bostadsrätt)"
_RE = "Rental apartment"

HOUSING_FIXED = [
    ("Ägarlägenhet", UNMAPPED),
    ("Bostadsbolag", _RE),  # a landlord, not a BRF
    ("Hyresrätt via kommunalt bostadsbolag", _RE),
    ("Owning an apartment", _TO),  # an owned flat in Sweden is a bostadsrätt
    ("owner_occupied_apartment", _TO),
    ("Egen bostadsrätt", _TO),
    ("äganderätt (lägenhet)", UNMAPPED),
    ("Tomträtt", _OW),
    ("Council flat", _RE),
    ("Allmännytta", _RE),
    ("Andelslägenhet (kooperativt boende)", _TO),
    ("Fastighetsägda lägenhet", _RE),
    ("Hyr mindre lägenhet i centralorten efter försäljning av villan", _RE),
    ("Cooperative ownership (bostadsbolag)", _TO),
]
HOUSING_FALSE_ALARMS = [
    ("Andrahandskontrakt i bostadsrätt", _TO),
    ("Hyrad bostadsrätt", _TO),
    ("Hyreslägenhet i bostadsrättshus", _TO),
    ("Boende i egen näringsfastighet med bostadsdel", UNMAPPED),
]
HOUSING_DECISIONS = [
    ("Eget hus eller lägenhet", UNMAPPED),  # open question 9 default: a disjunction names no tenure
    ("Eget hus/lägenhet", UNMAPPED),
    ("Owner-occupied (house or apartment)", UNMAPPED),
    ("Villa", _OW),
]

# ---------------------------------------------------------------------------
# income_source -- SCB income components; wage first
# ---------------------------------------------------------------------------

_WA, _CA, _PE = "Wage / Business", "Capital", "Pension"
_IN, _SA, _SAC = "Insurance / Allowance", "Social Assistance", "Sickness / Activity Compensation"
_GA, _HA = "General Allowances", "Housing Allowance"

INCOME_FIXED = [
    ("Software Developer", _WA),  # an occupation names wage income
    ("IT Project Manager", _WA),
    ("Senior Software Engineer", _WA),
    ("Dataanalyst", _WA),
    ("Disability pension", _SAC),
    ("Förtidspension", _SAC),
    ("Invalidpension", _SAC),
    ("Sjukersättning från Försäkringskassan", _SAC),
    ("Bostadstillägg (housing supplement) alongside disability pension", _SAC),
    ("Övertidsersättning", _WA),
    ("Semesterersättning", _WA),
    ("Bistånd", _SA),
    ("Kommunalt bidrag", _SA),
    ("Försörjningsstöd (socialbidrag)", _SA),
    ("Fonder", _CA),
    ("Vinstutdelning från eget företag", _CA),
    ("Annuity payments", _PE),
    ("Arbetsmarknadsstöd", _IN),
    ("Parental financial support", UNMAPPED),  # not an SCB income component
    ("Allowance from parents", UNMAPPED),
]
INCOME_FALSE_ALARMS = [
    ("Sjukpenning", _IN),
    ("Sickness benefit (sjukpenning)", _IN),
    ("Unemployment benefits", _IN),
    ("Lönekonto", _WA),
    ("Sjuklön", _WA),
    ("A-kassa (arbetslöshetsersättning)", _IN),
]
INCOME_DECISIONS = [
    ("Lön kompletterad med barnbidrag", _WA),  # wage first
    ("Kombination av deltidslön och ålderspension", _WA),
    ("Studielån från CSN", _GA),  # component 325, studielån included (open question 10)
    ("Barnbidrag", _GA),
    ("Child support from ex-partner", _GA),
    ("Bostadsbidrag", _HA),  # component 330
    ("Bostadstillägg", _HA),
    ("housing allowance for pensioners", _HA),
]

CASES = (
    _cases("civil_status", CIVIL_FIXED, CIVIL_FALSE_ALARMS, CIVIL_DECISIONS)
    + _cases("education_level", EDUCATION_FIXED, EDUCATION_FALSE_ALARMS, EDUCATION_DECISIONS)
    + _cases("employment_status", EMPLOYMENT_FIXED, EMPLOYMENT_FALSE_ALARMS)
    + _cases("employment_type", EMPLOYMENT_TYPE_FIXED, EMPLOYMENT_TYPE_FALSE_ALARMS, EMPLOYMENT_TYPE_DECISIONS)
    + _cases("housing_tenure", HOUSING_FIXED, HOUSING_FALSE_ALARMS, HOUSING_DECISIONS)
    + _cases("income_source", INCOME_FIXED, INCOME_FALSE_ALARMS, INCOME_DECISIONS)
)


@pytest.mark.parametrize(("attr", "raw", "want"), CASES)
def test_scb_native_core_rule(resolve, attr, raw, want):
    assert resolve(attr, raw) == want

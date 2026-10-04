"""Regression cases for the SCB-checked audit's rule changes on the ``scb_native`` synthetic side.

Covers ``industry_sector``, ``parental_structure``, ``socioeconomic_class`` and the small
attributes (``biological_sex``, ``region``, ``birth_country_detail``, ``household_size``,
``birth_location``). Every case is a raw LLM value from the audit's curated row list
(``docs/development/plans/pending/mapping-fixes-scb-audit.md``, Phase 2B) with the category the
SCB definition gives it:

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

    def _resolve(attr: str, raw: str, refine_value: str | None = None) -> str:
        block = mappings[index["attributes"][attr][:-5]]
        return mapping_engine.resolve(raw, block["synthetic"], block["values"], matching=matching,
                                      priority=block["priority"], refine_value=refine_value)
    return _resolve


# ---------------------------------------------------------------------------
# industry_sector -- SNI 2007 classifies by activity, not by owner or wording
# ---------------------------------------------------------------------------

_FB = "Financial & Business Services"
_IC = "Information & Communication"
_MF = "Manufacturing, Mining & Energy"
_HC = "Healthcare & Social Work"

INDUSTRY_FIXED = [
    ("Professional, scientific and technical activities", _FB),  # SNI M 69-75, not "tech" -> J
    ("Professional, Scientific and Technical Services", _FB),
    ("Forskning och utveckling", _FB),  # R&D is SNI 72 (M), not Education
    ("Research and Development (R&D)", _FB),
    ("Juridik, ekonomi, vetenskap och teknik", _FB),
    ("Teknik, vetenskap och ingenjörsvetenskap", _FB),
    ("Teknik och konsulttjänster", _FB),
    ("Ingenjörstjänster", _FB),
    ("Ingenjörsverksamhet", _FB),
    ("Ingenjörs- och teknikkonsult", _FB),
    ("Ekonomi och företagsledning", _FB),
    ("Hushållsnära tjänster", _FB),
    ("Digital marknadsföring", _FB),  # advertising 73 / PR 70.21
    ("Marknadsföring och kommunikation", _FB),
    ("Teknik och Ingenjörer", UNMAPPED),  # engineering words are C 25-30 or M 71: undecidable
    ("Teknik och ingenjörsvetenskap", UNMAPPED),
    ("Serviceindustri", UNMAPPED),  # not manufacturing
    ("Teknik och kemi", _MF),
    ("Läkemedel och bioteknik", _MF),
    ("Livsmedelsproduktion", _MF),
    ("Avfallshantering och återvinning", _MF),
    ("Rehabilitering", _HC),
    ("Kommunal äldreomsorg", _HC),  # activity, not municipal ownership
    ("Byggnadsindustri", "Construction"),
    ("Handel; reparation av motorfordon och motorcyklar", "Trade"),  # SNI G 45
    ("ITkonsulting", _IC),  # SNI J 62.02
    ("Web Development", _IC),
    ("Religious organizations", "Personal & Cultural Services"),
    ("Volontärarbete", "Not Applicable"),
]

INDUSTRY_FALSE_ALARMS = [
    ("IT-konsulting", _IC),
    ("Cleaning services", _FB),
    ("Kundtjänst och callcenter", _FB),
    ("Säkerhetstjänster", _FB),
    ("Tertiary education", "Education"),
    ("Städ- och fastighetsservice", _FB),
    ("Industrivärlden", _MF),
]

INDUSTRY_DECISIONS = [
    # Warehouse work without trade context is SNI H 52 (decision 2026-10-04).
    ("Warehousing", "Transport"),
    ("Lager- och paketeringsarbete", "Transport"),
    ("Lagerarbete på e-handelslager", "Transport"),
    # Labour-market services (Arbetsförmedlingen, staffing) are SNI 78 (decision).
    ("Arbetsförmedlingen", _FB),
    ("Arbetsmarknadsinsatser", _FB),
    # Open question 16 defaults: section undeterminable -> unmapped; Kundtjänst stays N 82.20.
    ("Engineering", UNMAPPED),
    ("Administration", UNMAPPED),
    ("Rådgivning (allmän)", UNMAPPED),
    ("Media och kultur", UNMAPPED),
    ("Kundtjänst", _FB),
    # A pensioner's former job is not a current sector.
    ("Pensionär (tidigare hemtjänst)", "Not Applicable"),
    # prefix mode: "ikt" no longer matches inside "inriktade".
    ("Näringslivets serviceinriktade", UNMAPPED),
]


@pytest.mark.parametrize("raw, expected", INDUSTRY_FIXED + INDUSTRY_FALSE_ALARMS + INDUSTRY_DECISIONS)
def test_industry_sector(resolve, raw, expected):
    assert resolve("industry_sector", raw) == expected


# ---------------------------------------------------------------------------
# parental_structure -- LE0102 familjetyp: legal ("ursprunglig") parents + folkbokföring residence
# ---------------------------------------------------------------------------

_NP = "Natural Parents"
_MS = "Mother and Stepparent"
_SM = "Single Mother"
_SF = "Single Father"

PARENTAL_FIXED = [
    ("Borgerlig familj med föräldrar", _NP),
    ("Sambofamilj", _NP),  # a cohabiting couple's child has two ursprungliga föräldrar
    ("Cohabiting couple without marriage", _NP),
    ("Ett föräldrapar", _NP),
    ("Föräldrar tillsammans", _NP),
    ("parents present", _NP),
    ("mother and father (divorced, lived with mother)", _SM),  # residence decides after divorce
    ("mother and father (divorced, lived with father)", _SF),
    ("mother and father (separated, lived with father)", _SF),
    ("boende med mamma", _SM),
    ("Mamma", _SM),
    ("Father", _SF),
    ("Änkling", _SF),
    ("Both parents deceased", "Other Than Parents"),
    ("Mor och sambo", _MS),  # styvförälder = co-resident adult who is not a legal parent
    ("mother and same-sex partner", _MS),
    ("mother and foster father", _MS),
    ("both parents divorced", UNMAPPED),  # residence not stated
    ("Separated biological parents", UNMAPPED),
    ("two parents (mother and father, one deceased)", UNMAPPED),
]

PARENTAL_FALSE_ALARMS = [
    ("mother and grandmother", _SM),
    ("adoptive parents (mother and father)", _NP),
    ("two mothers", _NP),
    ("Same-sex couple (two fathers)", _NP),
    ("Two fathers (same-sex couple)", _NP),
    ("divorced parents (lived primarily with mother)", _SM),
    ("father and grandfather", _SF),
]

PARENTAL_DECISIONS = [
    # Two-phase texts: the earlier phase wins (decision); `mother remarried` is no longer a token.
    ("Both biological parents until divorce in adolescence, then mother-headed single-parent household", _NP),
    ("Both biological parents until divorce in adolescence, then lived mainly with mother", _NP),
    ("Ensamstående mamma som senare gifte sig", _SM),
    ("Single mother remarried", _SM),
    # Joint custody / alternating residence: undeterminable without the registered parent
    # (open question 14 default).
    ("mother and father (divorced, joint custody)", UNMAPPED),
    ("shared custody (mother and father)", UNMAPPED),
    # Same-sex couple with parenthood unstated keeps the register-modal default (open question 15).
    ("Same-sex couple", _NP),
    ("Two same-sex partners", _NP),
    # Adoptive parents are ursprungliga föräldrar.
    ("Adoptive parents", _NP),
    ("Adoptivföräldrar", _NP),
    ("Single adoptive mother", _SM),
    # prefix mode: "father only" no longer matches inside "grandfather only".
    ("Grandfather only", "Other Than Parents"),
    # Open question 21 defaults: no child relation stated / bare family label.
    ("Ensamstående kvinna", UNMAPPED),
    ("Borgerlig familj", UNMAPPED),
]


@pytest.mark.parametrize("raw, expected", PARENTAL_FIXED + PARENTAL_FALSE_ALARMS + PARENTAL_DECISIONS)
def test_parental_structure(resolve, raw, expected):
    assert resolve("parental_structure", raw) == expected


# ---------------------------------------------------------------------------
# socioeconomic_class -- income band relative to the (age, sex) median: <0.6 / 0.6-1 / 1-2 / >2
# ---------------------------------------------------------------------------

_PO = "Poverty"
_WC = "Working Class"
_MC = "Middle Class"
_WE = "Wealthy"

SOCIO_FIXED = [
    ("Ekonomiskt utsatt", _PO),  # explicit poverty cue
    ("Ekonomiskt utsatt pensionär", _PO),
    ("Ekonomiskt beroende av offentliga stöd", _PO),
    ("Biståndsberoende", _PO),
    ("Economically Disadvantaged", _PO),
    ("High-income professional", _WE),  # the income cue decides, not the occupation word
    ("Affluent professional", _WE),
    ("Pensionär med hög inkomst", _WE),
    ("Klassresenär från arbetarklass till medelklass", _MC),  # class journey: the current class
    ("medelklass (student)", _MC),
    ("Earning above average", _MC),
    ("Borgare (medel)", _MC),
]

SOCIO_FALSE_ALARMS = [
    ("High income bracket", _WE),
    ("Betalda med hög inkomst", _WE),
    ("At-risk-of-poverty", _PO),
    ("Lägre medelklassen", _WC),
    ("Lower middle class (lägre medelklass)", _WC),
    ("Lägre medelklass (Tjänsteman)", _WC),
]

SOCIO_DECISIONS = [
    # Boundary decision (2026-10-04): low income / underklass -> Poverty; modest / moderate -> Working;
    # median / average -> Middle; lower class -> Working.
    ("Låginkomsttagare", _PO),
    ("Lägre inkomst", _PO),
    ("Underklass", _PO),
    ("modest income class", _WC),
    ("moderate income", _WC),
    ("Medianinkomst", _MC),
    ("Average income", _MC),
    ("Lower class", _WC),
    ("Lägre klass", _WC),
    # Open question 12 default: lower / low socioeconomic status and Lågklass read as "lower class".
    ("Lägre socioekonomisk grupp", _WC),
    ("Låg socioekonomisk status", _WC),
    ("Lågklass", _WC),
    # Lower-middle is Working Class everywhere (was split between two classes).
    ("Lägre medelklass", _WC),
    # Open question 13 defaults: generic economy wording.
    ("Begränsad ekonomi", _WC),
    ("Låg pension", _PO),
    ("Ekonomiskt stabil", UNMAPPED),
    # prefix mode: "hög inkomst" no longer matches inside "medelhög inkomst".
    ("Medelhög inkomst", _MC),
    # Status words carry no income band (Phase 4: removed under either option).
    ("Student", UNMAPPED),
    ("Studerande", UNMAPPED),
    ("Pensionär", UNMAPPED),
]


@pytest.mark.parametrize("raw, expected", SOCIO_FIXED + SOCIO_FALSE_ALARMS + SOCIO_DECISIONS)
def test_socioeconomic_class(resolve, raw, expected):
    assert resolve("socioeconomic_class", raw) == expected


# ---------------------------------------------------------------------------
# small attributes
# ---------------------------------------------------------------------------

SMALL_CASES = [
    # biological_sex: legal sex; prefix mode already keeps "male" out of "female".
    ("biological_sex", "Female", "Female"),
    ("biological_sex", "Kvinna", "Female"),
    ("biological_sex", "cis man", "Male"),
    ("biological_sex", "herr", "Male"),
    ("biological_sex", '{"male": 0.5, "female": 0.5}', UNMAPPED),  # both sexes named
    ("biological_sex", "Trans man", UNMAPPED),  # legal sex unknown (open question 21)
    # region: unaccented and province names that sit inside one län.
    ("region", "Ostergotland", "Östergötland"),
    ("region", "Östra Götaland", "Östergötland"),
    ("region", "Västergötland", "Västra Götaland"),
    ("region", "Gästrikland", "Gävleborg"),
    ("region", "Svedala", "Skåne"),
    ("region", "Svedaland", UNMAPPED),  # garbled; equals, not contains
    ("region", "Uppland", UNMAPPED),  # split between two län (open question 21)
    ("region", "Region Väst", UNMAPPED),
    # birth_country_detail: "Sverige (född i utlandet)" is not Sweden-born.
    ("birth_country_detail", "Sverige", "Sweden"),
    ("birth_country_detail", "Sverige (född i utlandet)", UNMAPPED),
    ("birth_country_detail", "Sverige (utanlandsfödd)", UNMAPPED),
    ("birth_country_detail", "Uplandia", "Sweden"),
    ("birth_country_detail", "Serbia", UNMAPPED),  # not in the top-20 reference (open question 21)
    # household_size: "With parents (2)" is the person plus two parents.
    ("household_size", "With parents (2)", "3 persons"),
    ("household_size", "4 personer", "4 persons"),
    ("household_size", "Ensamstående med ett barn", "2 persons"),
]


@pytest.mark.parametrize("attr, raw, expected", SMALL_CASES)
def test_small_attributes(resolve, attr, raw, expected):
    assert resolve(attr, raw) == expected


# ---------------------------------------------------------------------------
# birth_location -- FolkmFodlandHVD: FSV / FEU / FUEU (Sweden / other EU / outside the EU)
# ---------------------------------------------------------------------------

BIRTH_REGION_CASES = [
    ("Stockholm", None, "Sweden"),
    ("Polen", None, "Born in another EU country"),
    ("Åland Islands", None, "Born in another EU country"),  # Finland; "island" is a whole word only
    ("Oslo, Norge", None, "Born outside the EU"),
    ("United Kingdom", None, "Born outside the EU"),
    ("Island", None, "Born outside the EU"),  # Swedish for Iceland
    ("Bagdad, Irak", None, "Born outside the EU"),
    ("Europe", None, UNMAPPED),  # EU or not is undecidable
    ("Nordic country", None, UNMAPPED),
    ("", "Germany", "Born in another EU country"),  # refined from birth_country_detail
    ("", "Bosnia and Herzegovina", "Born outside the EU"),
]


@pytest.mark.parametrize("raw, refine, expected", BIRTH_REGION_CASES)
def test_birth_location(resolve, raw, refine, expected):
    assert resolve("birth_location", raw, refine_value=refine) == expected


def test_birth_location_real_labels():
    block = load_mappings(_TIER)["birth_location"]
    real = mapping_engine.compile_matching(load_mappings(_TIER)["_index"]["matching"]["real"])
    for raw, expected in [("born in Sweden", "Sweden"), ("born in another EU Member State", "Born in another EU country"),
                          ("born outside the EU", "Born outside the EU")]:
        assert mapping_engine.resolve(raw, block["real"], block["values"], matching=real,
                                      priority=block["priority"]) == expected

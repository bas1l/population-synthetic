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

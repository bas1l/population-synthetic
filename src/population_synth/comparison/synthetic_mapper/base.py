"""Abstract and base synthetic-population mappers.

The *synthetic mapper* turns one raw pipeline ``identity.json`` record (free-text
attribute values produced by an LLM) into the canonical 17-key schema dict the
``StatisticalEvaluator`` consumes.  ``AbstractSyntheticMapper`` declares the
per-attribute contract; ``BaseSyntheticMapper`` provides the orchestration plus
the attributes that are identical across countries.  Country specificities live
in the ``SwedishSyntheticMapper`` / ``ItalianSyntheticMapper`` subclasses, so the
two countries are never interleaved in a single function.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from population_synth.comparison.extract.mappings import _repair_utf8_double_encoding
from population_synth.comparison.extract.normalizers_se import (
    _age_to_group,
    _normalize_environment,
    _normalize_ethnicity,
    _normalize_parental_structure,
    _normalize_socioeconomic,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared country-token sets (used by both countries' birth-location logic)
# ---------------------------------------------------------------------------

_EUROPEAN_COUNTRIES = {
    "finland", "finl", "norge", "norway", "danmark", "denmark", "island", "iceland",
    "polen", "poland", "tyskland", "germany", "frankrike", "france", "italien", "italy",
    "spanien", "spain", "rumänien", "romania", "ungern", "hungary", "tjeckien", "czech",
    "greece", "grekland", "portugal", "österrike", "austria", "belgien", "belgium",
    "nederländerna", "netherlands", "holland", "ukraine", "ukraina", "serbien", "serbia",
    "kroatien", "croatia", "bosnien", "bosnia", "albanien", "albania", "bulgarien", "bulgaria",
    "slovakien", "slovakia", "litauen", "lithuania", "lettland", "latvia", "estland", "estonia",
    "kosovo", "nordmakedon", "monteneg", "moldov", "vitryssland", "belarus",
    "united kingdom", "uk", "england", "scotland", "wales", "ireland", "irland",
    "schweiz", "switzerland", "slovenien", "slovenia",
}

_NON_EUROPEAN_COUNTRIES = {
    "irak", "iraq", "syrien", "syria", "somalia", "iran", "afghanistan",
    "bagdad", "damaskus", "teheran", "kabul", "mogadishu", "eritrea",
    "etiopien", "ethiopia", "kina", "china", "indien", "india", "pakistan",
    "turkiet", "turkey", "libanon", "lebanon", "palestina", "palestine",
    "marocko", "morocco", "tunisien", "tunisia", "algeriet", "algeria",
    "nigeria", "kenya", "tanzania", "usa", "united states", "brasil", "brazil",
    "mexiko", "mexico", "chile", "colombia", "argentina", "vietnam", "thailand",
    "filippinerna", "philippines", "japan", "sydkorea", "south korea",
    "middle east", "mellanöstern", "north africa", "nordafrika", "sub-saharan",
    "yemen", "jemen", "libyen", "libya", "egypten", "egypt", "jordanien", "jordan",
}


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def is_flat_identity(identity: dict) -> bool:
    """Return True for the flat / configurable identity.json format."""
    return "age" in identity and not any(k.startswith("level_") for k in identity) and "narrative" not in identity


def match_common_sex(sex_lower: str) -> str | None:
    """Resolve the English/Swedish biological-sex tokens shared by both countries."""
    if any(k in sex_lower for k in ("female", "kvinna", "kvinnlig", "kvinnor", "flicka", "tjej", "hona", "woman")):
        return "Female"
    if sex_lower in ("xx", "hon", "f"):
        return "Female"
    if any(k in sex_lower for k in ("male", "pojke", "kille", "manlig")):
        return "Male"
    if sex_lower in ("man", "xy", "m") or "kön man" in sex_lower or sex_lower == "män":
        return "Male"
    return None


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class AbstractSyntheticMapper(ABC):
    """Per-attribute mapping contract for the synthetic (pipeline) population."""

    #: Attributes whose unmapped values should NOT be reported (country opt-out).
    SILENT_UNMAPPED: set[str] = set()

    @abstractmethod
    def map_biological_sex(self, raw: str, unmapped: list[str]) -> str: ...

    @abstractmethod
    def map_education(self, raw: str, unmapped: list[str]) -> str: ...

    @abstractmethod
    def map_employment_status(self, raw: str, unmapped: list[str]) -> str: ...

    @abstractmethod
    def map_birth_location(self, identity: dict, unmapped: list[str]) -> str: ...

    @abstractmethod
    def map_region(self, identity: dict) -> str: ...

    @abstractmethod
    def map_birth_country_detail(self, raw: str) -> str: ...

    @abstractmethod
    def map_civil_status(self, raw: str, unmapped: list[str]) -> str: ...

    @abstractmethod
    def map_household_size(self, raw: Any) -> str: ...

    @abstractmethod
    def map_housing_tenure(self, raw: str, unmapped: list[str]) -> str: ...

    @abstractmethod
    def map_industry_sector(self, raw: str) -> str: ...

    @abstractmethod
    def map_employment_type(self, raw: str, unmapped: list[str]) -> str: ...

    @abstractmethod
    def map_income_source(self, raw: str) -> str: ...

    @abstractmethod
    def parse_narrative(self, identity: dict, persona_id: str) -> dict[str, Any] | None: ...


# ---------------------------------------------------------------------------
# Base implementation: orchestration + cross-country attributes
# ---------------------------------------------------------------------------

class BaseSyntheticMapper(AbstractSyntheticMapper):
    """Shared orchestration and the attributes identical across countries."""

    # -- orchestrator -------------------------------------------------------

    def map_individual(self, identity: dict, persona_id: str) -> dict[str, Any] | None:
        """Map a single raw identity dict to the canonical 17-key schema dict.

        Auto-detects the identity format (narrative vs flat) and returns ``None``
        for unreadable formats or critically-incomplete personas.
        """
        if "narrative" in identity:
            return self.parse_narrative(identity, persona_id)
        if not is_flat_identity(identity):
            logger.warning("%s: unrecognised identity format (keys: %s) -- skipping", persona_id, list(identity))
            return None
        return self._map_flat(identity, persona_id)

    def _map_flat(self, identity: dict, persona_id: str) -> dict[str, Any] | None:
        identity = {k: _repair_utf8_double_encoding(str(v)) if isinstance(v, str) else v
                    for k, v in identity.items()}
        unmapped: list[str] = []

        # map_age_group is the validity gate (skip personas with missing/non-int age);
        # the canonical schema stores the raw integer age, and the comparison stats
        # derive the age group on the fly -- no synthesized age_group field is stored.
        if self.map_age_group(identity.get("age"), persona_id) is None:
            return None

        result = {
            "age": int(identity["age"]),
            "biological_sex": self.map_biological_sex(str(identity.get("biological_sex") or ""), unmapped),
            "education_level": self.map_education(str(identity.get("education_level") or ""), unmapped),
            "employment_status": self.map_employment_status(str(identity.get("employment_status") or ""), unmapped),
            "birth_location": self.map_birth_location(identity, unmapped),
            "ethnicity": self.map_ethnicity(str(identity.get("ethnicity_broad_global_approx") or ""), unmapped),
            "current_environment_type": self.map_environment(
                str(identity.get("current_environment_type") or ""), unmapped),
            "socioeconomic_class": self.map_socioeconomic(str(identity.get("socioeconomic_class") or ""), unmapped),
            "parental_structure": self.map_parental_structure(str(identity.get("parental_structure") or ""), unmapped),
            "region": self.map_region(identity),
            "birth_country_detail": self.map_birth_country_detail(str(identity.get("birth_country_detail") or "")),
            "civil_status": self.map_civil_status(str(identity.get("civil_status") or ""), unmapped),
            "household_size": self.map_household_size(identity.get("household_size")),
            "housing_tenure": self.map_housing_tenure(str(identity.get("housing_tenure") or ""), unmapped),
            "industry_sector": self.map_industry_sector(str(identity.get("industry_sector") or "")),
            "employment_type": self.map_employment_type(str(identity.get("employment_type") or ""), unmapped),
            "income_source": self.map_income_source(str(identity.get("income_source") or "")),
        }

        if unmapped:
            logger.warning("%s: unmapped flat fields: %s", persona_id, "; ".join(unmapped))
        return result

    # -- shared attributes (identical across countries) ---------------------

    def map_age_group(self, raw_age: Any, persona_id: str) -> str | None:
        if raw_age is None:
            logger.warning("%s: missing age -- skipping persona", persona_id)
            return None
        try:
            return _age_to_group(int(raw_age))
        except (ValueError, TypeError):
            logger.warning("%s: non-integer age %r -- skipping persona", persona_id, raw_age)
            return None

    def map_ethnicity(self, raw: str, unmapped: list[str]) -> str:
        value = _normalize_ethnicity(raw) or "Non-standard label"
        if value == "Non-standard label" and "ethnicity" not in self.SILENT_UNMAPPED:
            unmapped.append(f"ethnicity={raw!r}")
        return value

    def map_environment(self, raw: str, unmapped: list[str]) -> str:
        value = _normalize_environment(raw) or "Non-standard label"
        if value == "Non-standard label" and "current_environment_type" not in self.SILENT_UNMAPPED:
            unmapped.append(f"current_environment_type={raw!r}")
        return value

    def map_socioeconomic(self, raw: str, unmapped: list[str]) -> str:
        value = _normalize_socioeconomic(raw) or "Non-standard label"
        if value == "Non-standard label":
            unmapped.append(f"socioeconomic_class={raw!r}")
        return value

    def map_parental_structure(self, raw: str, unmapped: list[str]) -> str:
        value = _normalize_parental_structure(raw) or "Non-standard label"
        if value == "Non-standard label":
            unmapped.append(f"parental_structure={raw!r}")
        return value

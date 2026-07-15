"""Parsers turning raw SCB PxWeb responses into distributions.

Converts SCB PxWeb JSON table payloads into the normalised probability
dictionaries consumed by the Sweden fetch service. Handles per-dimension
category labelling and income-bracket classification into socioeconomic
classes.
"""
from __future__ import annotations

from population_synthetic.generators.real.helpers import VALID_AGE_GROUPS, resolve_age_group
from population_synthetic.generators.real.income_class import classify_brackets, median_from_brackets

from .constants import SCB_INCOME_BRACKETS


def parse_age_sex(raw: dict) -> dict[tuple[int, str], float]:
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    age_labels = list(dims["Alder"]["category"]["label"].values())
    sexes_raw = list(dims["Kon"]["category"]["label"].values())

    def _year_label_to_int(label: str) -> int | None:
        try:
            year = int(label.split()[0])
        except (ValueError, IndexError):
            return None
        return year if 18 <= year <= 85 else None

    n_sex = len(sexes_raw)
    counts: dict[tuple[int, str], float] = {}
    for i, age_label in enumerate(age_labels):
        age = _year_label_to_int(age_label)
        if age is None:
            continue
        for j, sex in enumerate(sexes_raw):
            idx = i * n_sex + j
            v = float(values[idx] or 0) if idx < len(values) else 0.0
            counts[(age, sex)] = v

    if not counts:
        raise ValueError("No age/sex data parsed from response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def parse_education_by_age(
    raw: dict, age_group_map: dict
) -> dict[tuple[str, str], dict[str, float]]:
    dataset = raw.get("dataset", raw)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    age_key = next((k for k in dims if "lder" in k.lower() or "age" in k.lower()), None)
    edu_key = next(
        (k for k in dims if "sun" in k.lower() or "utbild" in k.lower() or "educ" in k.lower()),
        None,
    )
    sex_key = next((k for k in dims if "kon" in k.lower() or "sex" in k.lower()), None)

    if not age_key or not edu_key:
        raise ValueError("Could not identify age/education dimensions in response")
    if not sex_key:
        raise ValueError("Could not identify sex (Kon) dimension in education response")

    ages_raw = list(dims[age_key]["category"]["label"].values())
    edus_raw = list(dims[edu_key]["category"]["label"].values())
    sex_labels_raw = list(dims[sex_key]["category"]["label"].values())

    id_list = dataset.get("id", list(dims.keys()))
    edu_pos = id_list.index(edu_key) if edu_key in id_list else -1
    age_pos = id_list.index(age_key) if age_key in id_list else -1
    sex_pos = id_list.index(sex_key) if sex_key in id_list else -1

    n_edu = len(edus_raw)
    n_age = len(ages_raw)
    n_sex = len(sex_labels_raw)

    dim_order = sorted([(edu_pos, "edu"), (age_pos, "age"), (sex_pos, "sex")])
    sizes = {"edu": n_edu, "age": n_age, "sex": n_sex}
    strides: dict[str, int] = {}
    stride = 1
    for _, name in reversed(dim_order):
        strides[name] = stride
        stride *= sizes[name]

    result: dict[tuple[str, str], dict[str, float]] = {}
    for edu_i, edu_raw in enumerate(edus_raw):
        for age_i, age_raw in enumerate(ages_raw):
            age_group = resolve_age_group(age_raw, age_group_map)
            for sex_i, sex in enumerate(sex_labels_raw):
                if age_group not in VALID_AGE_GROUPS:
                    continue
                flat_idx = edu_i * strides["edu"] + age_i * strides["age"] + sex_i * strides["sex"]
                raw_val = values[flat_idx] if flat_idx < len(values) else None
                # Confidentiality-suppressed cells arrive as null (or "..").
                # Treat them as an absent (zero-count) contribution to the sum
                # rather than crashing; never impute a value.
                if raw_val is None or raw_val == "..":
                    v = 0.0
                else:
                    v = float(raw_val)
                key = (age_group, sex)
                if key not in result:
                    result[key] = {}
                result[key][edu_raw] = result[key].get(edu_raw, 0.0) + v

    if not result:
        raise ValueError("No education data parsed from response")
    for key, dist in result.items():
        total = sum(dist.values()) or 1.0
        result[key] = {k: v / total for k, v in dist.items()}

    return result


# --- employment_status: register (ArRegArbStatus) labour-market status by
# --- age x sex ---------------------------------------------------------------
# The register encodes each labour-market status as its own ContentsCode measure
# (a count), NOT as categories of one dimension. We request the six count statuses
# and map each ContentsCode to a canonical status label; the "labour force",
# "total", and rate measures (NL/NU/NN/NK/NS) are deliberately excluded. This is a
# structural code->label map (an allowed constant per design-principles.md), NOT a
# probability table: every probability still comes from summing real API cells.
# NOTE: despite the legacy "by_sex_education" naming, this source has no education
# dimension (see constants.py).
_STATUS_EMPLOYED = "Employed"
_STATUS_UNEMPLOYED = "Unemployed"
_STATUS_STUDENT = "Student"
_STATUS_RETIRED = "Retired"
_STATUS_SICK = "Sick Leave"
_STATUS_OTHER = "Other"

_EMPLOYMENT_STATUS_CODE_TO_LABEL: dict[str, str] = {
    "000002NT": _STATUS_EMPLOYED,    # number of employed
    "000002NM": _STATUS_UNEMPLOYED,  # number of unemployed
    "000002NR": _STATUS_STUDENT,     # number of students
    "000002NP": _STATUS_RETIRED,     # number of retirees
    "000002NQ": _STATUS_SICK,        # number of sick
    "000002NO": _STATUS_OTHER,       # number of others
}

# ContentsCode measures to request (the six mutually-exclusive count statuses).
EMPLOYMENT_STATUS_CONTENTS_CODES: tuple[str, ...] = tuple(_EMPLOYMENT_STATUS_CODE_TO_LABEL)

# The register carries only 5-year age bands and caps at 74. Each band is expanded
# to the canonical pipeline group(s) it covers. The 18-24 group is proxied by the
# 20-24 band (there is no 18-19 band free of minors). The oldest band (70-74) is
# also applied to the 75-85 group so ages beyond the register's coverage are
# modelled from real cells -- and because 70-74 is already retiree-dominated, the
# 75-85 group comes out predominantly out-of-labour-force, as intended for 75+.
# Keyed by the API age *code* ("060-64" carries the register's leading-zero code).
EMPLOYMENT_STATUS_AGE_BANDS: tuple[str, ...] = (
    "20-24", "25-29", "30-34", "35-39", "40-44", "45-49",
    "50-54", "55-59", "060-64", "65-69", "70-74",
)
_EMPLOYMENT_STATUS_AGE_BAND_TO_GROUPS: dict[str, tuple[str, ...]] = {
    "20-24": ("18-24",),
    "25-29": ("25-34",),
    "30-34": ("25-34",),
    "35-39": ("35-44",),
    "40-44": ("35-44",),
    "45-49": ("45-54",),
    "50-54": ("45-54",),
    "55-59": ("55-64",),
    "060-64": ("55-64",),
    "65-69": ("65-74",),
    "70-74": ("65-74", "75-85"),
}


def parse_employment_by_sex_education(
    raw: dict,
) -> dict[tuple[str, str], dict[str, float]]:
    """Parse the register labour-status table into an (age_group, sex) conditional.

    NOTE: despite the legacy name, this parses ``ArRegArbStatus``, which has no
    education dimension. Labour-market status is encoded in the ``ContentsCode``
    dimension (one count measure per status); each requested code maps to a
    canonical status label via ``_EMPLOYMENT_STATUS_CODE_TO_LABEL``. Returns
    ``{(age_group, sex_label): {status_label: probability}}`` with each inner dict
    normalized to sum to 1.0.

    Confidentiality-suppressed cells arrive as null (or ``".."``) and are treated
    as an absent (zero-count) contribution to the sum, never imputed. A fully
    suppressed subgroup (all six statuses zero/suppressed for an (age_group, sex))
    fails fast. Raises on any ContentsCode or age band absent from the maps.
    """
    dataset = raw.get("dataset", raw)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    dim_ids = dataset.get("id") or list(dims.keys())
    dim_sizes = dataset.get("size") or [len(dims[k]["category"]["label"]) for k in dim_ids]

    status_key = next((k for k in dim_ids if k.lower() == "contentscode"), None)
    age_key = next((k for k in dim_ids if "lder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dim_ids if "kon" in k.lower() or "sex" in k.lower()), None)
    if not status_key or not age_key or not sex_key:
        raise ValueError(
            f"Could not identify status/age/sex dimensions in employment-status "
            f"response; dims={list(dims.keys())}"
        )

    # Row-major strides (last dimension varies fastest) so the linear index is
    # correct regardless of where each dimension sits in the response order and of
    # the singleton Region/Fodelseregion/Tid dimensions.
    strides: dict[str, int] = {}
    acc = 1
    for key, size in zip(reversed(dim_ids), reversed(dim_sizes)):
        strides[key] = acc
        acc *= size

    status_items = list(dims[status_key]["category"]["label"].items())  # (code, label)
    age_items = list(dims[age_key]["category"]["label"].items())  # (code, label)
    sex_labels = list(dims[sex_key]["category"]["label"].values())

    counts: dict[tuple[str, str], dict[str, float]] = {}
    for st_pos, (st_code, _st_label) in enumerate(status_items):
        status = _EMPLOYMENT_STATUS_CODE_TO_LABEL.get(st_code)
        if status is None:
            raise ValueError(
                f"Unmapped labour-status ContentsCode {st_code!r} — no canonical status"
            )
        for s_pos, sex in enumerate(sex_labels):
            for a_pos, (age_code, _al) in enumerate(age_items):
                groups = _EMPLOYMENT_STATUS_AGE_BAND_TO_GROUPS.get(age_code)
                if groups is None:
                    raise ValueError(
                        f"Unmapped labour-status age band {age_code!r} — no canonical group"
                    )
                idx = (
                    st_pos * strides[status_key]
                    + s_pos * strides[sex_key]
                    + a_pos * strides[age_key]
                )
                raw_val = values[idx] if idx < len(values) else None
                if raw_val is None or raw_val == "..":
                    v = 0.0
                else:
                    v = float(raw_val)
                for group in groups:
                    key = (group, sex)
                    if key not in counts:
                        counts[key] = {}
                    counts[key][status] = counts[key].get(status, 0.0) + v

    if not counts:
        raise ValueError("No employment-status data parsed from response")

    for (age_group, sex), dist in counts.items():
        if sum(dist.values()) == 0.0:
            raise ValueError(
                f"Fully suppressed employment-status subgroup for age_group={age_group!r}, "
                f"sex={sex!r} — all statuses are zero or suppressed"
            )

    for key, dist in counts.items():
        total = sum(dist.values()) or 1.0
        counts[key] = {k: v / total for k, v in dist.items()}
    return counts


# --- employment_status two-table MERGE (opt-in, ALL-REGISTER) ----------------
# Phase 6. Recovers the status<->education link that no single SCB table carries
# by combining two REGISTER margins under an explicit "no status x age x
# education interaction" assumption (the closed-form log-linear [SA][SE] model):
#
#     w(status) = P(status | age, sex) * P(status | edu, sex) / P(status | sex)
#     P(status | age, edu, sex) = w(status) / sum_status w(status)
#
# evaluated per (age_group, education, sex) cell. This is a DERIVATION over real
# register cells -- no external number, no distributional family, no invented
# cell -- and is the ONLY place the generator reasons across tables. It is
# compliant with the no-synthetic-distributions invariant ONLY under the spec's
# guardrails (all-register sources; assumption documented here and at the Step 3
# call site; only real cells combined; nulls tolerated, never imputed). See
# docs/reference/scb-pxweb-catalog/employment-status-merge-derivation.md. When
# the merge flag is OFF the generator uses the single-table age x sex path
# (parse_employment_by_sex_education) unchanged and this code never runs.

# 3-cat common status set the two tables are reduced to before multiplying.
_ST3_EMPLOYED = "employed"
_ST3_UNEMPLOYED = "unemployed"
_ST3_NILF = "nilf"
_STATUS_3CAT: tuple[str, ...] = (_ST3_EMPLOYED, _ST3_UNEMPLOYED, _ST3_NILF)

# The four register 6-cat statuses that make up NILF; re-expanded from the
# age-only leg after the 3-cat merge so the output keeps the Phase-4 taxonomy.
_NILF_STATUSES: tuple[str, ...] = (_STATUS_STUDENT, _STATUS_RETIRED, _STATUS_SICK, _STATUS_OTHER)

# Reduce the ArRegArbStatus 6-cat labels to the common 3-cat set.
_STATUS_6CAT_TO_3CAT: dict[str, str] = {
    _STATUS_EMPLOYED: _ST3_EMPLOYED,
    _STATUS_UNEMPLOYED: _ST3_UNEMPLOYED,
    _STATUS_STUDENT: _ST3_NILF,
    _STATUS_RETIRED: _ST3_NILF,
    _STATUS_SICK: _ST3_NILF,
    _STATUS_OTHER: _ST3_NILF,
}

# ArbStatusUtbM (edu leg) status ContentsCode -> 3-cat. Only these three count
# measures are requested; the labour-force/total/rate measures are excluded.
_ARBSTATUSUTBM_STATUS_CODE_TO_3CAT: dict[str, str] = {
    "0000088H": _ST3_EMPLOYED,    # number of employed
    "0000088A": _ST3_UNEMPLOYED,  # number of unemployed
    "0000088C": _ST3_NILF,        # number of people not in the labour force
}
EMPLOYMENT_STATUS_EDU_STATUS_CODES: tuple[str, ...] = tuple(_ARBSTATUSUTBM_STATUS_CODE_TO_3CAT)

# ArbStatusUtbM level-of-education codes to request (its coarser 6-class scheme).
EMPLOYMENT_STATUS_EDU_CODES: tuple[str, ...] = ("21", "3", "4", "5", "61", "US")

# ArbStatusUtbM's status<->education shape is measured on the working-age 20-64
# total; applying it to 15-19 / 65+ personas is a mild, documented extrapolation.
EMPLOYMENT_STATUS_EDU_AGE: str = "20-64"

# Baseline P(status | sex) comes from ArRegArbStatus's all-ages 15-74 aggregate
# (same table/definition as the age leg). Requested alongside the 5-year bands.
EMPLOYMENT_STATUS_BASELINE_AGE: str = "15-74"

# Structural collapse of the generator's 8 ISCED97 education levels (the labels
# parse_education_by_age emits, from UtbBefRegionR) onto ArbStatusUtbM's coarser
# education codes -- a nesting map (allowed constant per design-principles.md;
# confirmed against the live metadata dump, not guessed). Keyed by the CASEFOLDED
# generator label so the lookup is robust to label casing; the two ISCED levels
# that ArbStatusUtbM does not distinguish (1 & 2 -> primary/lower-secondary;
# 5A & 6 -> post-secondary 3+ incl. postgraduate) share a coarse class.
_GEN_EDU_LABEL_TO_STATUS_EDU_CODE: dict[str, str] = {
    "primary and secondary education less than 9 years (isced97 1)": "21",
    "primary and secondary education 9-10 years (isced97 2)": "21",
    "upper secondary education, 2 years or less (isced97 3c)": "3",
    "upper secondary education 3 years (isced97 3a)": "4",
    "post-secondary education, less than 3 years (isced97 4+5b)": "5",
    "post-secondary education 3 years or more (isced97 5a)": "61",
    "post-graduate education (isced97 6)": "61",
    "no information about level of educational attainment": "US",
}


def _reduce_6cat_to_3cat(dist6: dict[str, float]) -> dict[str, float]:
    """Reduce a 6-cat register status distribution to the common 3-cat set."""
    out: dict[str, float] = dict.fromkeys(_STATUS_3CAT, 0.0)
    for status, p in dist6.items():
        out[_STATUS_6CAT_TO_3CAT[status]] += p
    return out


def _combine_status_3cat(
    p_age3: dict[str, float],
    p_edu3: dict[str, float],
    p_base3: dict[str, float],
) -> dict[str, float]:
    """Odds-multiplication combine, per (age, edu, sex) cell, over the 3-cat set.

    ``w(k) = P(k|age,sex) * P(k|edu,sex) / P(k|sex)`` then normalise. If the
    education leg is unavailable for a status (a suppressed null cell, so ``p_edu3``
    lacks it, or its baseline is zero) the edu factor is 1 -- i.e. that status
    falls back to the age-only conditional, exactly as the spec (§8.2) prescribes.
    """
    w: dict[str, float] = {}
    for k in _STATUS_3CAT:
        pa = p_age3.get(k, 0.0)
        pe = p_edu3.get(k)
        pb = p_base3.get(k, 0.0)
        factor = (pe / pb) if (pe is not None and pb > 0.0) else 1.0
        w[k] = pa * factor
    total = sum(w.values()) or 1.0
    return {k: v / total for k, v in w.items()}


def _expand_nilf(combined3: dict[str, float], p_age6: dict[str, float]) -> dict[str, float]:
    """Re-expand the merged 3-cat vector to the 6-cat taxonomy.

    Employed/unemployed carry through; the NILF mass is split into
    students/retirees/sick/others using the **age-only** proportions from
    ArRegArbStatus (education modulates only the top-level emp/unemp/NILF split).
    """
    out: dict[str, float] = {
        _STATUS_EMPLOYED: combined3[_ST3_EMPLOYED],
        _STATUS_UNEMPLOYED: combined3[_ST3_UNEMPLOYED],
    }
    nilf_sub = {s: p_age6.get(s, 0.0) for s in _NILF_STATUSES}
    nilf_total = sum(nilf_sub.values())
    if nilf_total > 0.0:
        for s in _NILF_STATUSES:
            out[s] = combined3[_ST3_NILF] * nilf_sub[s] / nilf_total
    else:
        # No NILF sub-structure in the age leg (degenerate): keep the mass rather
        # than drop it, folding it onto "Other" so the vector still sums to 1.
        out[_STATUS_OTHER] = combined3[_ST3_NILF]
    total = sum(out.values()) or 1.0
    return {k: v / total for k, v in out.items()}


def _status_counts_by_age_code(raw_status: dict) -> dict[tuple[str, str], dict[str, float]]:
    """Raw 6-cat status COUNTS keyed by (age_code, sex_label) from ArRegArbStatus.

    Unlike ``parse_employment_by_sex_education`` this keeps the source age *code*
    (so the caller can separate the 5-year bands from the ``15-74`` baseline) and
    returns un-normalised counts. Nulls/``".."`` become zero-count (never imputed).
    """
    dataset = raw_status.get("dataset", raw_status)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    dim_ids = dataset.get("id") or list(dims.keys())
    dim_sizes = dataset.get("size") or [len(dims[k]["category"]["label"]) for k in dim_ids]

    status_key = next((k for k in dim_ids if k.lower() == "contentscode"), None)
    age_key = next((k for k in dim_ids if "lder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dim_ids if "kon" in k.lower() or "sex" in k.lower()), None)
    if not status_key or not age_key or not sex_key:
        raise ValueError(
            f"Could not identify status/age/sex dimensions in employment-status "
            f"response; dims={list(dims.keys())}"
        )

    strides: dict[str, int] = {}
    acc = 1
    for key, size in zip(reversed(dim_ids), reversed(dim_sizes)):
        strides[key] = acc
        acc *= size

    status_items = list(dims[status_key]["category"]["label"].items())  # (code, label)
    age_items = list(dims[age_key]["category"]["label"].items())  # (code, label)
    sex_labels = list(dims[sex_key]["category"]["label"].values())

    counts: dict[tuple[str, str], dict[str, float]] = {}
    for st_pos, (st_code, _lbl) in enumerate(status_items):
        status = _EMPLOYMENT_STATUS_CODE_TO_LABEL.get(st_code)
        if status is None:
            raise ValueError(
                f"Unmapped labour-status ContentsCode {st_code!r} — no canonical status"
            )
        for s_pos, sex in enumerate(sex_labels):
            for a_pos, (age_code, _al) in enumerate(age_items):
                idx = (
                    st_pos * strides[status_key]
                    + s_pos * strides[sex_key]
                    + a_pos * strides[age_key]
                )
                raw_val = values[idx] if idx < len(values) else None
                v = 0.0 if (raw_val is None or raw_val == "..") else float(raw_val)
                key = (age_code, sex)
                bucket = counts.setdefault(key, {})
                bucket[status] = bucket.get(status, 0.0) + v
    return counts


def _edu_3cat_by_class_sex(raw_edu: dict) -> dict[tuple[str, str], dict[str, float]]:
    """P(status | edu_class, sex) as a 3-cat distribution from ArbStatusUtbM.

    Returns ``{(edu_code, sex_label): {emp/unemp/nilf: prob}}``. A class/sex whose
    three status cells are not ALL present (any suppressed null, or zero total) is
    OMITTED, so combine falls back to the age-only conditional for it (spec §8.2).
    """
    dataset = raw_edu.get("dataset", raw_edu)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    dim_ids = dataset.get("id") or list(dims.keys())
    dim_sizes = dataset.get("size") or [len(dims[k]["category"]["label"]) for k in dim_ids]

    status_key = next((k for k in dim_ids if k.lower() == "contentscode"), None)
    edu_key = next((k for k in dim_ids if "utbild" in k.lower() or "educ" in k.lower()), None)
    sex_key = next((k for k in dim_ids if "kon" in k.lower() or "sex" in k.lower()), None)
    if not status_key or not edu_key or not sex_key:
        raise ValueError(
            f"Could not identify status/education/sex dimensions in status-education "
            f"response; dims={list(dims.keys())}"
        )

    strides: dict[str, int] = {}
    acc = 1
    for key, size in zip(reversed(dim_ids), reversed(dim_sizes)):
        strides[key] = acc
        acc *= size

    status_items = list(dims[status_key]["category"]["label"].items())  # (code, label)
    edu_items = list(dims[edu_key]["category"]["label"].items())  # (code, label)
    sex_labels = list(dims[sex_key]["category"]["label"].values())

    # (edu_code, sex) -> {3cat_status: count or None-if-suppressed}
    raw_cells: dict[tuple[str, str], dict[str, float | None]] = {}
    for st_pos, (st_code, _lbl) in enumerate(status_items):
        st3 = _ARBSTATUSUTBM_STATUS_CODE_TO_3CAT.get(st_code)
        if st3 is None:
            raise ValueError(
                f"Unmapped status-education ContentsCode {st_code!r} — not one of "
                f"{tuple(_ARBSTATUSUTBM_STATUS_CODE_TO_3CAT)}"
            )
        for e_pos, (edu_code, _el) in enumerate(edu_items):
            for s_pos, sex in enumerate(sex_labels):
                idx = (
                    st_pos * strides[status_key]
                    + e_pos * strides[edu_key]
                    + s_pos * strides[sex_key]
                )
                raw_val = values[idx] if idx < len(values) else None
                val = None if (raw_val is None or raw_val == "..") else float(raw_val)
                raw_cells.setdefault((edu_code, sex), {})[st3] = val

    result: dict[tuple[str, str], dict[str, float]] = {}
    for key, cells in raw_cells.items():
        # Require all three statuses present (non-null) to form a clean edu leg.
        if any(cells.get(k) is None for k in _STATUS_3CAT):
            continue
        total = sum(cells[k] for k in _STATUS_3CAT)  # type: ignore[misc]
        if total <= 0.0:
            continue
        result[key] = {k: cells[k] / total for k in _STATUS_3CAT}  # type: ignore[operator]
    return result


def parse_employment_status_combined(
    raw_status: dict,
    raw_edu: dict,
    age_group_map: dict,
) -> dict[tuple[str, str, str], dict[str, float]]:
    """Merge the two register tables into an (age_group, education, sex) conditional.

    Materialises ``{(age_group, education_label_casefold, sex_label): {status: prob}}``
    over the 6-cat register status taxonomy, by evaluating the odds-multiplication
    ``P(S|A,s)*P(S|E,s)/P(S|s)`` per cell (``_combine_status_3cat``) then
    re-expanding NILF (``_expand_nilf``). ``education_label_casefold`` is the
    casefolded generator ISCED label (as Step 3 looks it up).

    Inputs (ALL REGISTER):
    - ``raw_status``: ArRegArbStatus over the 5-year bands **plus** the ``15-74``
      all-ages aggregate (age leg P(S|A,s) + baseline P(S|s)).
    - ``raw_edu``: ArbStatusUtbM status x education x sex (edu leg P(S|E,s)).

    Assumption: no status x age x education interaction (documented; surfaced at
    the Step 3 call site and in provenance). Never mix the AKU survey table.
    """
    status_counts = _status_counts_by_age_code(raw_status)

    # Age leg: 6-cat P(S|A,s) per canonical group (5-year bands folded via the
    # Phase-4 band map); baseline: 6-cat P(S|s) from the 15-74 aggregate per sex.
    age6_counts: dict[tuple[str, str], dict[str, float]] = {}
    baseline6_counts: dict[str, dict[str, float]] = {}
    for (age_code, sex), dist in status_counts.items():
        if age_code == EMPLOYMENT_STATUS_BASELINE_AGE:
            acc = baseline6_counts.setdefault(sex, {})
            for status, v in dist.items():
                acc[status] = acc.get(status, 0.0) + v
            continue
        groups = _EMPLOYMENT_STATUS_AGE_BAND_TO_GROUPS.get(age_code)
        if groups is None:
            raise ValueError(
                f"Unmapped labour-status age band {age_code!r} — no canonical group"
            )
        for group in groups:
            acc = age6_counts.setdefault((group, sex), {})
            for status, v in dist.items():
                acc[status] = acc.get(status, 0.0) + v

    if not age6_counts:
        raise ValueError("No per-band employment-status data parsed for the merge age leg")
    if not baseline6_counts:
        raise ValueError(
            f"No baseline ({EMPLOYMENT_STATUS_BASELINE_AGE}) employment-status rows found — "
            "the merge requires the all-ages aggregate for P(status|sex)"
        )

    # Normalise the age leg to 6-cat probabilities (and detect fully-suppressed).
    p_age6: dict[tuple[str, str], dict[str, float]] = {}
    for key, dist in age6_counts.items():
        total = sum(dist.values())
        if total == 0.0:
            raise ValueError(
                f"Fully suppressed employment-status subgroup for {key!r} in merge age leg"
            )
        p_age6[key] = {k: v / total for k, v in dist.items()}

    p_base3: dict[str, dict[str, float]] = {}
    for sex, dist in baseline6_counts.items():
        total = sum(dist.values()) or 1.0
        p_base3[sex] = _reduce_6cat_to_3cat({k: v / total for k, v in dist.items()})

    edu3 = _edu_3cat_by_class_sex(raw_edu)

    result: dict[tuple[str, str, str], dict[str, float]] = {}
    for (age_group, sex), age6 in p_age6.items():
        p_age3 = _reduce_6cat_to_3cat(age6)
        base3 = p_base3.get(sex, {})
        for edu_label_cf, edu_code in _GEN_EDU_LABEL_TO_STATUS_EDU_CODE.items():
            p_edu3 = edu3.get((edu_code, sex), {})
            combined3 = _combine_status_3cat(p_age3, p_edu3, base3)
            result[(age_group, edu_label_cf, sex)] = _expand_nilf(combined3, age6)

    if not result:
        raise ValueError("No combined employment-status distribution could be built")
    return result


def parse_birth_location(
    raw: dict, age_group_map: dict
) -> dict[tuple[str, str], dict[str, float]]:
    """Parse the birth-region table into an age x sex conditional.

    Mirrors ``parse_birth_country_detail`` but stays robust to the table's
    dimension ordering (here ``[Fodelseland, HDI, Kon, Alder, ...]`` with a
    singleton HDI wedged between region and sex): the linear value index is
    computed from row-major strides derived from the response's own
    ``id``/``size`` rather than assuming a fixed loop nesting. The ``OKANT``
    (unknown country of birth) bucket has no canonical target and is dropped
    explicitly -- normalising over the three known regions redistributes the
    unknowns proportionally rather than inventing a fourth category.
    """
    dataset = raw.get("dataset", raw)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    dim_ids = dataset.get("id") or list(dims.keys())
    dim_sizes = dataset.get("size") or [len(dims[k]["category"]["label"]) for k in dim_ids]

    region_key = next(
        (k for k in dim_ids if "fodelse" in k.lower() or "birth" in k.lower() or "land" in k.lower()),
        None,
    )
    age_key = next((k for k in dim_ids if "lder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dim_ids if "kon" in k.lower() or "sex" in k.lower()), None)
    if not region_key or not age_key or not sex_key:
        raise ValueError(
            f"Could not identify region/age/sex dimensions in birth-location response; dims={list(dims.keys())}"
        )

    # Row-major strides (last dimension varies fastest) so the linear index is
    # correct regardless of where each dimension sits in the response order.
    strides: dict[str, int] = {}
    acc = 1
    for key, size in zip(reversed(dim_ids), reversed(dim_sizes)):
        strides[key] = acc
        acc *= size

    region_items = list(dims[region_key]["category"]["label"].items())  # (code, label)
    age_items = list(dims[age_key]["category"]["label"].items())  # (code, label)
    sex_labels = list(dims[sex_key]["category"]["label"].values())

    counts: dict[tuple[str, str], dict[str, float]] = {}
    for r_pos, (r_code, r_label) in enumerate(region_items):
        if r_code == "OKANT" or "unknown" in r_label.lower():
            continue
        for s_pos, sex in enumerate(sex_labels):
            for a_pos, (_a_code, a_label) in enumerate(age_items):
                age_group = resolve_age_group(a_label, age_group_map)
                if age_group not in VALID_AGE_GROUPS:
                    continue
                idx = (
                    r_pos * strides[region_key]
                    + s_pos * strides[sex_key]
                    + a_pos * strides[age_key]
                )
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                key = (age_group, sex)
                if key not in counts:
                    counts[key] = {}
                counts[key][r_label] = counts[key].get(r_label, 0.0) + v

    if not counts:
        raise ValueError("No birth_location data parsed from response")
    for key, dist in counts.items():
        total = sum(dist.values()) or 1.0
        counts[key] = {k: v / total for k, v in dist.items()}
    return counts


def parse_region(raw: dict) -> dict[str, float]:
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    region_labels_raw = list(dims["Region"]["category"]["label"].values())
    n_age = len(dims["Alder"]["category"]["label"])
    n_sex = len(dims["Kon"]["category"]["label"])

    counts: dict[str, float] = {}
    for ri, region_raw in enumerate(region_labels_raw):
        total = 0.0
        for ai in range(n_age):
            for si in range(n_sex):
                idx = ri * n_age * n_sex + ai * n_sex + si
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                total += v
        counts[region_raw] = counts.get(region_raw, 0.0) + total

    if not counts:
        raise ValueError("No region data parsed from response")
    grand_total = sum(counts.values()) or 1.0
    return {k: v / grand_total for k, v in counts.items()}


def parse_urbanization_by_county(raw: dict, region_label_map: dict) -> dict[str, float]:
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    region_labels_raw = list(dims["Region"]["category"]["label"].values())
    typ_labels = list(dims["TypOmr"]["category"]["label"].values())
    n_typ = len(typ_labels)

    it_idx = next((i for i, lbl in enumerate(typ_labels) if "within" in lbl.lower() or lbl.upper() == "IT"), None)
    tot_idx = next((i for i, lbl in enumerate(typ_labels) if "total" in lbl.lower() or lbl.upper() == "TOT"), None)

    if it_idx is None or tot_idx is None:
        raise ValueError(
            f"Could not identify IT/TOT dimensions in urbanization response; got: {typ_labels}"
        )

    result: dict[str, float] = {}
    for ri, region_raw in enumerate(region_labels_raw):
        schema_label = region_label_map.get(region_raw)
        if not schema_label:
            raise ValueError(f"No mapping for SCB region label in urbanization data: {region_raw!r}")
        it_val = float(values[ri * n_typ + it_idx] or 0) if ri * n_typ + it_idx < len(values) else 0.0
        tot_val = float(values[ri * n_typ + tot_idx] or 1) if ri * n_typ + tot_idx < len(values) else 1.0
        result[schema_label] = it_val / tot_val if tot_val else 0.0

    return result


def parse_civil_status_by_age_sex(
    raw: dict, age_group_map: dict
) -> dict[tuple[str, str], dict[str, float]]:
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    cs_labels_raw = list(dims["Civilstand"]["category"]["label"].values())
    age_labels_raw = list(dims["Alder"]["category"]["label"].values())
    sex_labels_raw = list(dims["Kon"]["category"]["label"].values())

    counts: dict[tuple[str, str], dict[str, float]] = {}
    idx = 0
    for cs_raw in cs_labels_raw:
        for age_raw in age_labels_raw:
            age_group = resolve_age_group(age_raw, age_group_map)
            for sex in sex_labels_raw:
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                idx += 1
                if age_group not in VALID_AGE_GROUPS:
                    continue
                key = (age_group, sex)
                if key not in counts:
                    counts[key] = {}
                counts[key][cs_raw] = counts[key].get(cs_raw, 0.0) + v

    if not counts:
        raise ValueError("No civil_status data parsed from response")
    for key, dist in counts.items():
        total = sum(dist.values()) or 1.0
        counts[key] = {k: v / total for k, v in dist.items()}
    return counts


# --- industry_sector: register (ArRegSNI2007Riket) NACE Rev. 2 -> 12 canonical
# sectors ---------------------------------------------------------------------
# The register table exposes ~52 fine SNI2007 codes with no API-provided
# section-level aggregate close to the pipeline's 12 canonical sectors, so the
# collapse is done here. This is a *structural* code->label aggregation map (an
# allowed constant per design-principles.md), NOT a probability table: every
# probability still comes from summing real API cells. The 12 targets are exactly
# the canonical English labels in config/mapping/scb_native/industry_sector.json,
# so the mapping config needs no change. The follows SCB's own standard SNI
# aggregation (B-E -> manufacturing/mining/energy/environment; K-N -> financial
# operations & business services; R-U -> personal & cultural services).
_IND_AGRI = "Agriculture, Forestry & Fishing"
_IND_MFG = "Manufacturing, Mining & Energy"
_IND_CONSTR = "Construction"
_IND_TRADE = "Trade"
_IND_TRANSPORT = "Transport"
_IND_ACCOM = "Accommodation & Food Services"
_IND_INFO = "Information & Communication"
_IND_FIN = "Financial & Business Services"
_IND_PUBADMIN = "Public Administration"
_IND_EDU = "Education"
_IND_HEALTH = "Healthcare & Social Work"
_IND_PERSCULT = "Personal & Cultural Services"

_SNI2007_TO_SECTOR: dict[str, str] = {
    "01-03": _IND_AGRI,
    "05-09": _IND_MFG,   # mining and quarrying
    "10-12": _IND_MFG,
    "13-15": _IND_MFG,
    "16": _IND_MFG,
    "17": _IND_MFG,
    "18": _IND_MFG,
    "19": _IND_MFG,
    "20": _IND_MFG,
    "21": _IND_MFG,
    "22": _IND_MFG,
    "23": _IND_MFG,
    "24": _IND_MFG,
    "25": _IND_MFG,
    "26-28": _IND_MFG,
    "29-30": _IND_MFG,
    "31-32": _IND_MFG,
    "33": _IND_MFG,
    "35": _IND_MFG,      # electricity, gas, steam (energy)
    "36-37": _IND_MFG,   # water supply; sewerage (environment)
    "38-39": _IND_MFG,   # waste management (environment)
    "41-43": _IND_CONSTR,
    "45": _IND_TRADE,    # sale/repair of motor vehicles
    "46": _IND_TRADE,    # wholesale
    "47": _IND_TRADE,    # retail
    "49-52": _IND_TRANSPORT,
    "53": _IND_TRANSPORT,  # postal and courier
    "55-56": _IND_ACCOM,
    "58-60": _IND_INFO,
    "61": _IND_INFO,
    "62-63": _IND_INFO,
    "64": _IND_FIN,
    "65": _IND_FIN,
    "66": _IND_FIN,
    "68": _IND_FIN,      # real estate
    "69": _IND_FIN,      # legal and accounting
    "70": _IND_FIN,
    "71": _IND_FIN,
    "72": _IND_FIN,      # scientific R&D
    "73": _IND_FIN,
    "74-75": _IND_FIN,
    "77": _IND_FIN,
    "78": _IND_FIN,
    "79-82": _IND_FIN,
    "84": _IND_PUBADMIN,
    "85": _IND_EDU,
    "86": _IND_HEALTH,
    "87": _IND_HEALTH,
    "88": _IND_HEALTH,
    "90-93": _IND_PERSCULT,
    "94-99": _IND_PERSCULT,
}

# SNI2007 codes to request from the API (every mappable fine code). "TOTAL" and
# "00" (unknown activity, no canonical sector) are deliberately excluded so the
# parser sees only mappable codes.
INDUSTRY_SNI2007_CODES: tuple[str, ...] = tuple(_SNI2007_TO_SECTOR)

# The register table only carries coarse, partly-overlapping age bands. Each
# disjoint source band is expanded to the canonical pipeline age group(s) it
# covers so every group receives a real (age-appropriate) sector distribution.
# The wide 25-54 band is shared across the three canonical groups it spans; the
# 65-74 band's mix is also used for 75-85 (the register's employed population is
# capped at 74). Keyed by the API age *code*.
INDUSTRY_AGE_BANDS: tuple[str, ...] = ("20-24", "25-54", "55-64", "65-74")
_IND_AGE_BAND_TO_GROUPS: dict[str, tuple[str, ...]] = {
    "20-24": ("18-24",),
    "25-54": ("25-34", "35-44", "45-54"),
    "55-64": ("55-64",),
    "65-74": ("65-74", "75-85"),
}


def parse_industry_sector(raw: dict) -> dict[tuple[str, str], dict[str, float]]:
    """Parse the register industry table into an (age_group, sex) conditional.

    Aggregates the fine SNI2007 (NACE Rev. 2) codes into the 12 canonical
    sectors by summing real cell counts, and keys the result by
    ``(age_group, sex_label)``. Raises on any SNI2007 code or age band not in the
    aggregation maps (fail-fast; no silent drop).
    """
    dataset = raw.get("dataset", raw)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    dim_ids = dataset.get("id") or list(dims.keys())
    dim_sizes = dataset.get("size") or [len(dims[k]["category"]["label"]) for k in dim_ids]

    sni_key = next(
        (k for k in dim_ids if "sni" in k.lower() or "nace" in k.lower() or "industrial" in k.lower()),
        None,
    )
    age_key = next((k for k in dim_ids if "lder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dim_ids if "kon" in k.lower() or "sex" in k.lower()), None)
    if not sni_key or not age_key or not sex_key:
        raise ValueError(
            f"Could not identify SNI/age/sex dimensions in industry response; dims={list(dims.keys())}"
        )

    strides: dict[str, int] = {}
    acc = 1
    for key, size in zip(reversed(dim_ids), reversed(dim_sizes)):
        strides[key] = acc
        acc *= size

    sni_items = list(dims[sni_key]["category"]["label"].items())  # (code, label)
    age_items = list(dims[age_key]["category"]["label"].items())  # (code, label)
    sex_labels = list(dims[sex_key]["category"]["label"].values())

    counts: dict[tuple[str, str], dict[str, float]] = {}
    for c_pos, (sni_code, _lbl) in enumerate(sni_items):
        sector = _SNI2007_TO_SECTOR.get(sni_code)
        if sector is None:
            raise ValueError(
                f"Unmapped SNI2007 industry code {sni_code!r} — no canonical sector"
            )
        for s_pos, sex in enumerate(sex_labels):
            for a_pos, (age_code, _al) in enumerate(age_items):
                groups = _IND_AGE_BAND_TO_GROUPS.get(age_code)
                if groups is None:
                    raise ValueError(
                        f"Unmapped industry age band {age_code!r} — no canonical group"
                    )
                idx = (
                    c_pos * strides[sni_key]
                    + s_pos * strides[sex_key]
                    + a_pos * strides[age_key]
                )
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                for group in groups:
                    key = (group, sex)
                    if key not in counts:
                        counts[key] = {}
                    counts[key][sector] = counts[key].get(sector, 0.0) + v

    if not counts:
        raise ValueError("No industry_sector data parsed from response")
    for key, dist in counts.items():
        total = sum(dist.values()) or 1.0
        counts[key] = {k: v / total for k, v in dist.items()}
    return counts


def parse_employment_type_combined(
    raw_attach: dict,
    raw_hours: dict,
    age_group_map: dict,
) -> dict[tuple[str, str], dict[str, float]]:
    # --- Parse attachment by (age_group, sex) ---
    dims_a = raw_attach.get("dimension", {})
    vals_a = raw_attach.get("value", [])

    ank_key = next((k for k in dims_a if "ank" in k.lower()), None)
    age_key_a = next((k for k in dims_a if "lder" in k.lower() or "age" in k.lower()), None)
    sex_key_a = next((k for k in dims_a if "kon" in k.lower() or "sex" in k.lower()), None)
    if not ank_key or not age_key_a:
        raise ValueError(f"Could not identify attachment/age dimensions; dims={list(dims_a.keys())}")
    if not sex_key_a:
        raise ValueError(f"Could not identify sex (Kon) dimension in attachment response; dims={list(dims_a.keys())}")

    ank_labels = list(dims_a[ank_key]["category"]["label"].values())
    age_labels_a = list(dims_a[age_key_a]["category"]["label"].values())
    sex_labels_a = list(dims_a[sex_key_a]["category"]["label"].values())

    id_list_a = raw_attach.get("id", list(dims_a.keys()))
    ank_pos = id_list_a.index(ank_key) if ank_key in id_list_a else -1
    age_pos_a = id_list_a.index(age_key_a) if age_key_a in id_list_a else -1
    sex_pos_a = id_list_a.index(sex_key_a) if sex_key_a in id_list_a else -1

    dim_order_a = sorted([(ank_pos, "ank"), (age_pos_a, "age"), (sex_pos_a, "sex")])
    sizes_a = {"ank": len(ank_labels), "age": len(age_labels_a), "sex": len(sex_labels_a)}
    strides_a: dict[str, int] = {}
    stride = 1
    for _, name in reversed(dim_order_a):
        strides_a[name] = stride
        stride *= sizes_a[name]

    attach_by_age_sex: dict[tuple[str, str], dict[str, float]] = {}
    for ank_i, ank_raw in enumerate(ank_labels):
        for age_i, age_raw in enumerate(age_labels_a):
            age_group = resolve_age_group(age_raw, age_group_map)
            for sex_i, sex in enumerate(sex_labels_a):
                flat_idx = ank_i * strides_a["ank"] + age_i * strides_a["age"] + sex_i * strides_a["sex"]
                v = float(vals_a[flat_idx] or 0) if flat_idx < len(vals_a) else 0.0
                if age_group not in VALID_AGE_GROUPS:
                    continue
                key = (age_group, sex)
                if key not in attach_by_age_sex:
                    attach_by_age_sex[key] = {}
                attach_by_age_sex[key][ank_raw] = attach_by_age_sex[key].get(ank_raw, 0.0) + v

    for key in attach_by_age_sex:
        total = sum(attach_by_age_sex[key].values()) or 1.0
        attach_by_age_sex[key] = {k: v / total for k, v in attach_by_age_sex[key].items()}

    # --- Parse working hours by (age_group, sex) ---
    dims_h = raw_hours.get("dimension", {})
    vals_h = raw_hours.get("value", [])

    hours_key = next(
        (k for k in dims_h if "tid" in k.lower() or "hours" in k.lower() or "vecko" in k.lower()),
        None,
    )
    age_key_h = next((k for k in dims_h if "lder" in k.lower() or "age" in k.lower()), None)
    sex_key_h = next((k for k in dims_h if "kon" in k.lower() or "sex" in k.lower()), None)
    if not hours_key or not age_key_h:
        raise ValueError(f"Could not identify hours/age dimensions; dims={list(dims_h.keys())}")
    if not sex_key_h:
        raise ValueError(f"Could not identify sex (Kon) dimension in hours response; dims={list(dims_h.keys())}")

    hours_labels = list(dims_h[hours_key]["category"]["label"].values())
    age_labels_h = list(dims_h[age_key_h]["category"]["label"].values())
    sex_labels_h = list(dims_h[sex_key_h]["category"]["label"].values())

    id_list_h = raw_hours.get("id", list(dims_h.keys()))
    hours_pos = id_list_h.index(hours_key) if hours_key in id_list_h else -1
    age_pos_h = id_list_h.index(age_key_h) if age_key_h in id_list_h else -1
    sex_pos_h = id_list_h.index(sex_key_h) if sex_key_h in id_list_h else -1

    dim_order_h = sorted([(hours_pos, "hours"), (age_pos_h, "age"), (sex_pos_h, "sex")])
    sizes_h = {"hours": len(hours_labels), "age": len(age_labels_h), "sex": len(sex_labels_h)}
    strides_h: dict[str, int] = {}
    stride = 1
    for _, name in reversed(dim_order_h):
        strides_h[name] = stride
        stride *= sizes_h[name]

    hours_by_age_sex: dict[tuple[str, str], dict[str, float]] = {}
    for hr_i, hr_raw in enumerate(hours_labels):
        for age_i, age_raw in enumerate(age_labels_h):
            age_group = resolve_age_group(age_raw, age_group_map)
            for sex_i, sex in enumerate(sex_labels_h):
                flat_idx = hr_i * strides_h["hours"] + age_i * strides_h["age"] + sex_i * strides_h["sex"]
                v = float(vals_h[flat_idx] or 0) if flat_idx < len(vals_h) else 0.0
                if age_group not in VALID_AGE_GROUPS:
                    continue
                key = (age_group, sex)
                if key not in hours_by_age_sex:
                    hours_by_age_sex[key] = {}
                hours_by_age_sex[key][hr_raw] = hours_by_age_sex[key].get(hr_raw, 0.0) + v

    for key in hours_by_age_sex:
        total = sum(hours_by_age_sex[key].values()) or 1.0
        hours_by_age_sex[key] = {k: v / total for k, v in hours_by_age_sex[key].items()}

    # --- Combine: outer-product of attachment x hours per (age_group, sex) ---
    # Distribution keys are composite strings "{attachment_label}|{hours_label}"
    result: dict[tuple[str, str], dict[str, float]] = {}
    all_keys = set(attach_by_age_sex.keys()) | set(hours_by_age_sex.keys())
    for key in all_keys:
        age_group, sex = key
        if age_group not in VALID_AGE_GROUPS:
            continue
        ank = attach_by_age_sex.get(key, {})
        hrs = hours_by_age_sex.get(key, {})
        if not ank or not hrs:
            continue

        dist: dict[str, float] = {}
        for ank_label, p_ank in ank.items():
            for hr_label, p_hr in hrs.items():
                composite_key = f"{ank_label}|{hr_label}"
                dist[composite_key] = p_ank * p_hr

        total = sum(dist.values()) or 1.0
        result[key] = {k: v / total for k, v in dist.items()}

    if not result:
        raise ValueError("No employment_type distribution could be built from attachment + hours data")
    return result


# --- housing_tenure: person-level register (HushallT31) Boendeform -> 3 canonical
# tenure classes --------------------------------------------------------------
# Structural collapse map (an allowed constant per design-principles.md): the
# building-type x tenure "Boendeform" codes are folded onto the three canonical
# tenure labels already in config/mapping/scb_native/housing_tenure.json by
# summing real cell counts. The targets are the exact canonical English labels so
# the mapping config needs no change.
_HT_OWNER = "Owner-occupied (villa/house)"
_HT_TENANT = "Tenant-owned apartment (bostadsrätt)"
_HT_RENTAL = "Rental apartment"

_BOENDEFORM_TO_TENURE: dict[str, str] = {
    "SMAG": _HT_OWNER,    # one/two-dwelling, owner-occupied
    "SMBO": _HT_TENANT,   # one/two-dwelling, tenant-owned
    "FBBO": _HT_TENANT,   # multi-dwelling, tenant-owned
    "SMHY0": _HT_RENTAL,  # one/two-dwelling, rented
    "FBHY0": _HT_RENTAL,  # multi-dwelling, rented
}
# Boendeform codes to request (only those with a canonical owner/tenant/rent
# target). SPBO (special housing), OB (other housing) and ÖVRIGT (data missing)
# have no canonical tenure and are excluded explicitly, alongside the TOT total.
HOUSING_BOENDEFORM_CODES: tuple[str, ...] = tuple(_BOENDEFORM_TO_TENURE)
_BOENDEFORM_EXCLUDED: frozenset[str] = frozenset({"SPBO", "OB", "ÖVRIGT", "TOT"})


def parse_housing_tenure(
    raw: dict, age_group_map: dict
) -> dict[tuple[str, str], dict[str, float]]:
    """Parse the person-level housing table into an (age_group, sex) conditional.

    Collapses the ``Boendeform`` building-type x tenure codes onto the three
    canonical tenure classes by summing real cell counts, keyed by
    ``(age_group, sex_label)``. ``SPBO``/``OB``/``ÖVRIGT``/``TOT`` are skipped
    explicitly (no canonical target); any other unrecognised code raises.
    """
    dataset = raw.get("dataset", raw)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    dim_ids = dataset.get("id") or list(dims.keys())
    dim_sizes = dataset.get("size") or [len(dims[k]["category"]["label"]) for k in dim_ids]

    boende_key = next(
        (k for k in dim_ids if "boende" in k.lower() or "housing" in k.lower() or "tenure" in k.lower()),
        None,
    )
    age_key = next((k for k in dim_ids if "lder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dim_ids if "kon" in k.lower() or "sex" in k.lower()), None)
    if not boende_key or not age_key or not sex_key:
        raise ValueError(
            f"Could not identify housing/age/sex dimensions in housing response; dims={list(dims.keys())}"
        )

    strides: dict[str, int] = {}
    acc = 1
    for key, size in zip(reversed(dim_ids), reversed(dim_sizes)):
        strides[key] = acc
        acc *= size

    boende_items = list(dims[boende_key]["category"]["label"].items())  # (code, label)
    age_items = list(dims[age_key]["category"]["label"].items())  # (code, label)
    sex_labels = list(dims[sex_key]["category"]["label"].values())

    counts: dict[tuple[str, str], dict[str, float]] = {}
    for b_pos, (b_code, _bl) in enumerate(boende_items):
        if b_code in _BOENDEFORM_EXCLUDED:
            continue
        tenure = _BOENDEFORM_TO_TENURE.get(b_code)
        if tenure is None:
            raise ValueError(
                f"Unmapped Boendeform housing code {b_code!r} — no canonical tenure"
            )
        for s_pos, sex in enumerate(sex_labels):
            for a_pos, (_age_code, age_label) in enumerate(age_items):
                age_group = resolve_age_group(age_label, age_group_map)
                if age_group not in VALID_AGE_GROUPS:
                    continue
                idx = (
                    b_pos * strides[boende_key]
                    + s_pos * strides[sex_key]
                    + a_pos * strides[age_key]
                )
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                key = (age_group, sex)
                if key not in counts:
                    counts[key] = {}
                counts[key][tenure] = counts[key].get(tenure, 0.0) + v

    if not counts:
        raise ValueError("No housing_tenure data parsed from response")
    for key, dist in counts.items():
        total = sum(dist.values()) or 1.0
        counts[key] = {k: v / total for k, v in dist.items()}
    return counts


def parse_household_size(raw: dict) -> dict[str, float]:
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    size_key = next(
        (k for k in dims if "hushall" in k.lower() or "household" in k.lower() or "storlek" in k.lower()),
        None,
    )
    if not size_key:
        raise ValueError(
            f"Could not identify household-size dimension in response; dims={list(dims.keys())}"
        )

    size_labels = list(dims[size_key]["category"]["label"].values())
    counts: dict[str, float] = {}
    for i, label_raw in enumerate(size_labels):
        v = float(values[i] or 0) if i < len(values) else 0.0
        counts[label_raw] = counts.get(label_raw, 0.0) + v

    if not counts:
        raise ValueError("No household_size data parsed from response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def parse_income_source(
    raw: dict,
) -> dict[tuple[str, str], dict[str, float]]:
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    inc_key = next((k for k in dims if "inkomst" in k.lower() or "income" in k.lower()), None)
    age_key = next((k for k in dims if "lder" in k.lower() or "age" in k.lower()), None)
    emp_key = next((k for k in dims if "syssels" in k.lower() or "employ" in k.lower()), None)
    if not inc_key or not age_key or not emp_key:
        raise ValueError(
            f"Could not identify income/age/employment dimensions; dims={list(dims.keys())}"
        )

    inc_labels = list(dims[inc_key]["category"]["label"].values())
    age_labels = list(dims[age_key]["category"]["label"].values())
    emp_labels = list(dims[emp_key]["category"]["label"].values())

    n_age = len(age_labels)
    n_emp = len(emp_labels)

    counts: dict[tuple[str, str], dict[str, float]] = {}
    for inc_i, inc_raw in enumerate(inc_labels):
        for age_i, age_raw in enumerate(age_labels):
            for emp_i, emp_raw in enumerate(emp_labels):
                val_idx = inc_i * n_age * n_emp + age_i * n_emp + emp_i
                v = values[val_idx] if val_idx < len(values) else None
                if v is None:
                    continue
                v = float(v)
                if v <= 0.0:
                    continue
                key = (emp_raw, age_raw)
                if key not in counts:
                    counts[key] = {}
                counts[key][inc_raw] = counts[key].get(inc_raw, 0.0) + v

    if not counts:
        raise ValueError("No income_source data parsed from response")
    for key in counts:
        total = sum(counts[key].values()) or 1.0
        counts[key] = {k: v / total for k, v in counts[key].items()}
    return counts


_SCB_SEX_CODE_TO_LABEL: dict[str, str] = {"1": "men", "2": "women"}

_BRACKET_CODE_TO_EDGES: dict[str, tuple[float, float]] = {
    code: (lo, hi) for code, lo, hi in SCB_INCOME_BRACKETS
}
_BRACKET_CODE_TO_MID: dict[str, float] = {
    code: (lo + hi) / 2.0 for code, lo, hi in SCB_INCOME_BRACKETS
}


def parse_socioeconomic(raw: dict) -> dict[tuple[str, str], dict[str, float]]:
    dataset = raw.get("dataset", raw)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    age_key = next((k for k in dims if "lder" in k.lower() or k.lower() == "alder"), None)
    sex_key = next((k for k in dims if k.lower() == "kon" or "sex" in k.lower()), None)
    bracket_key = next((k for k in dims if "inkomstklass" in k.lower()), None)

    if not age_key:
        raise ValueError(f"Missing age dimension in socioeconomic response; dims={list(dims.keys())}")
    if not sex_key:
        raise ValueError(f"Missing sex dimension in socioeconomic response; dims={list(dims.keys())}")
    if not bracket_key:
        raise ValueError(f"Missing income-bracket dimension in socioeconomic response; dims={list(dims.keys())}")

    age_codes = list(dims[age_key]["category"]["index"].keys())
    age_labels = list(dims[age_key]["category"]["label"].values())
    sex_codes = list(dims[sex_key]["category"]["index"].keys())
    bracket_codes = list(dims[bracket_key]["category"]["index"].keys())

    id_list = dataset.get("id", list(dims.keys()))
    age_pos = id_list.index(age_key) if age_key in id_list else -1
    sex_pos = id_list.index(sex_key) if sex_key in id_list else -1
    brk_pos = id_list.index(bracket_key) if bracket_key in id_list else -1

    n_age = len(age_codes)
    n_sex = len(sex_codes)
    n_brk = len(bracket_codes)

    dim_order = sorted([(age_pos, "age"), (sex_pos, "sex"), (brk_pos, "brk")])
    sizes = {"age": n_age, "sex": n_sex, "brk": n_brk}
    strides: dict[str, int] = {}
    stride = 1
    for _, name in reversed(dim_order):
        strides[name] = stride
        stride *= sizes[name]

    # Accumulate raw counts per (pipeline_age_group, sex_label, bracket_code).
    cell_counts: dict[tuple[str, str], dict[str, float]] = {}

    for age_i, age_label in enumerate(age_labels):
        # SamForvInk1a delivers single-year Alder labels ("18 years", ...);
        # fold each into its canonical pipeline age group. Ages outside the
        # pipeline range (e.g. 16-17, 86+) resolve to None and are skipped.
        pipeline_age = resolve_age_group(age_label, {})
        if pipeline_age is None:
            continue
        for sex_i, sex_code in enumerate(sex_codes):
            sex_label = _SCB_SEX_CODE_TO_LABEL.get(sex_code)
            if sex_label is None:
                continue
            cell_key = (pipeline_age, sex_label)
            if cell_key not in cell_counts:
                cell_counts[cell_key] = {}
            for brk_i, brk_code in enumerate(bracket_codes):
                flat_idx = (
                    age_i * strides["age"]
                    + sex_i * strides["sex"]
                    + brk_i * strides["brk"]
                )
                raw_val = values[flat_idx] if flat_idx < len(values) else None
                if raw_val is None or raw_val == "..":
                    # Confidentiality suppression in a sparse single-year x
                    # bracket cell: the count is unknown, not zero. Skip it so
                    # we neither impute a value nor assert a certain-zero count;
                    # real cells for the same bracket (other ages in the group)
                    # still contribute. Never crashes on the null.
                    continue
                v = float(raw_val)
                cell_counts[cell_key][brk_code] = cell_counts[cell_key].get(brk_code, 0.0) + v

    if not cell_counts:
        raise ValueError("No socioeconomic bracket data parsed from response")

    result: dict[tuple[str, str], dict[str, float]] = {}
    for cell_key, brk_dist in cell_counts.items():
        if sum(brk_dist.values()) == 0:
            raise ValueError(
                f"All bracket counts are zero for cell {cell_key!r} — "
                "cannot compute income class distribution"
            )
        ordered_codes = [c for c in _BRACKET_CODE_TO_EDGES if c in brk_dist]
        midpoints = [_BRACKET_CODE_TO_MID[c] for c in ordered_codes]
        counts_list = [brk_dist[c] for c in ordered_codes]
        edges = [_BRACKET_CODE_TO_EDGES[c] for c in ordered_codes]

        median = median_from_brackets(midpoints, counts_list)
        result[cell_key] = classify_brackets(edges, counts_list, median)

    return result


def parse_parental_structure(raw: dict) -> dict[str, float]:
    dataset = raw.get("dataset", raw)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    family_key = next(
        (k for k in dims if "familj" in k.lower() or "family" in k.lower() or "hush" in k.lower()),
        None,
    )
    if not family_key:
        raise ValueError("Could not identify family dimension in response")

    labels_raw = list(dims[family_key]["category"]["label"].values())

    counts: dict[str, float] = {}
    for i, label_raw in enumerate(labels_raw):
        v = float(values[i] or 0) if i < len(values) else 0.0
        counts[label_raw] = counts.get(label_raw, 0.0) + v

    if not counts:
        raise ValueError("No family structure data parsed from response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def parse_birth_country_detail(
    raw: dict, age_group_map: dict
) -> dict[tuple[str, str], dict[str, float]]:
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    country_key = next(
        (k for k in dims if "fodelse" in k.lower() or "birth" in k.lower() or "land" in k.lower()),
        None,
    )
    age_key = next((k for k in dims if "lder" in k.lower() or "age" in k.lower()), None)
    sex_key = next((k for k in dims if "kon" in k.lower() or "sex" in k.lower()), None)
    if not country_key or not age_key or not sex_key:
        raise ValueError(
            f"Could not identify country/age/sex dimensions in birth-country response; dims={list(dims.keys())}"
        )

    country_labels = list(dims[country_key]["category"]["label"].items())  # (code, label)
    age_labels_raw = list(dims[age_key]["category"]["label"].values())
    sex_labels_raw = list(dims[sex_key]["category"]["label"].values())

    counts: dict[tuple[str, str], dict[str, float]] = {}
    idx = 0
    for _code, label in country_labels:
        for age_raw in age_labels_raw:
            age_group = resolve_age_group(age_raw, age_group_map)
            for sex in sex_labels_raw:
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                idx += 1
                if age_group not in VALID_AGE_GROUPS:
                    continue
                key = (age_group, sex)
                if key not in counts:
                    counts[key] = {}
                counts[key][label] = counts[key].get(label, 0.0) + v

    if not counts:
        raise ValueError("No birth_country_detail data parsed from response")
    for key, dist in counts.items():
        total = sum(dist.values()) or 1.0
        counts[key] = {k: v / total for k, v in dist.items()}
    return counts

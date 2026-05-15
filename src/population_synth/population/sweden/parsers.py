from __future__ import annotations

from population_synth.population.helpers import VALID_AGE_GROUPS, resolve_age_group
from population_synth.population.income_class import classify_brackets, median_from_brackets

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
                flat_idx = edu_i * strides["edu"] + age_i * strides["age"] + sex_i * strides["sex"]
                v = float(values[flat_idx] or 0) if flat_idx < len(values) else 0.0
                if age_group not in VALID_AGE_GROUPS:
                    continue
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


def parse_employment_by_sex_education(
    raw: dict,
) -> dict[str, dict[str, dict[str, float]]]:
    """Parse NAKUBefUtbNivAr: employment status x education level x sex.

    Returns ``{sex_label: {education_label: {status_label: probability}}}``
    with each inner dict normalized to sum to 1.0. All keys are raw API labels.
    """
    dataset = raw.get("dataset", raw)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    emp_key = next(
        (k for k in dims if "arbets" in k.lower() or "labour" in k.lower()),
        None,
    )
    edu_key = next(
        (k for k in dims if "utbild" in k.lower() or "educ" in k.lower()),
        None,
    )
    sex_key = next(
        (k for k in dims if "kon" in k.lower() or "sex" in k.lower()),
        None,
    )

    if not emp_key or not edu_key or not sex_key:
        raise ValueError(
            f"Could not identify employment/education/sex dimensions in response; "
            f"dims={list(dims.keys())}"
        )

    emp_labels_raw = list(dims[emp_key]["category"]["label"].values())
    edu_labels_raw = list(dims[edu_key]["category"]["label"].values())
    sex_labels_raw = list(dims[sex_key]["category"]["label"].values())

    id_list = dataset.get("id", list(dims.keys()))
    emp_pos = id_list.index(emp_key) if emp_key in id_list else -1
    edu_pos = id_list.index(edu_key) if edu_key in id_list else -1
    sex_pos = id_list.index(sex_key) if sex_key in id_list else -1

    n_emp = len(emp_labels_raw)
    n_edu = len(edu_labels_raw)
    n_sex = len(sex_labels_raw)

    dim_order = sorted([(emp_pos, "emp"), (edu_pos, "edu"), (sex_pos, "sex")])
    sizes = {"emp": n_emp, "edu": n_edu, "sex": n_sex}
    strides: dict[str, int] = {}
    stride = 1
    for _, name in reversed(dim_order):
        strides[name] = stride
        stride *= sizes[name]

    counts: dict[str, dict[str, dict[str, float]]] = {}
    suppressed_cells = 0
    total_cells = 0

    for emp_i, emp_raw in enumerate(emp_labels_raw):
        for edu_i, edu_raw in enumerate(edu_labels_raw):
            for sex_i, sex in enumerate(sex_labels_raw):
                flat_idx = (
                    emp_i * strides["emp"]
                    + edu_i * strides["edu"]
                    + sex_i * strides["sex"]
                )
                total_cells += 1
                raw_val = values[flat_idx] if flat_idx < len(values) else None

                if raw_val is None or raw_val == "..":
                    suppressed_cells += 1
                    v = 0.0
                else:
                    v = float(raw_val)

                if sex not in counts:
                    counts[sex] = {}
                if edu_raw not in counts[sex]:
                    counts[sex][edu_raw] = {}
                counts[sex][edu_raw][emp_raw] = counts[sex][edu_raw].get(emp_raw, 0.0) + v

    if not counts:
        raise ValueError("No employment-by-education data parsed from response")

    for sex, edu_dict in counts.items():
        for edu, emp_dict in edu_dict.items():
            if sum(emp_dict.values()) == 0.0:
                raise ValueError(
                    f"Fully suppressed employment subgroup for sex={sex!r}, "
                    f"education={edu!r} — all cells are zero or suppressed"
                )

    for sex in counts:
        for edu in counts[sex]:
            total = sum(counts[sex][edu].values()) or 1.0
            counts[sex][edu] = {k: v / total for k, v in counts[sex][edu].items()}

    return counts


def parse_birth_location(raw: dict) -> dict[str, float]:
    dataset = raw.get("dataset", raw)
    dims = dataset.get("dimension", {})
    values = dataset.get("value", [])

    region_key = next(
        (k for k in dims if "fodelse" in k.lower() or "birth" in k.lower() or "region" in k.lower()),
        None,
    )
    if not region_key:
        raise ValueError("Could not identify birth-region dimension in response")

    regions_raw = list(dims[region_key]["category"]["label"].values())
    counts: dict[str, float] = {}
    for i, region_raw in enumerate(regions_raw):
        v = float(values[i] or 0) if i < len(values) else 0.0
        counts[region_raw] = counts.get(region_raw, 0.0) + v

    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


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


def parse_industry_sector(raw: dict) -> dict[str, float]:
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    sni_key = next(
        (k for k in dims if "sni" in k.lower() or "nace" in k.lower() or "industrial" in k.lower()),
        None,
    )
    if not sni_key:
        raise ValueError(
            f"Could not identify SNI/NACE dimension in industry response; dims={list(dims.keys())}"
        )

    sni_labels_raw = list(dims[sni_key]["category"]["label"].values())

    counts: dict[str, float] = {}
    for i, label_raw in enumerate(sni_labels_raw):
        v = float(values[i] or 0) if i < len(values) else 0.0
        counts[label_raw] = counts.get(label_raw, 0.0) + v

    if not counts:
        raise ValueError("No industry_sector data parsed from response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


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


def parse_housing_tenure(raw: dict) -> dict[str, float]:
    dims = raw.get("dimension", {})
    values = raw.get("value", [])

    hustyp_key = next(
        (k for k in dims if "hustyp" in k.lower() or "building" in k.lower()), None
    )
    tenure_key = next(
        (k for k in dims if "upplatel" in k.lower() or "tenure" in k.lower()), None
    )
    if not hustyp_key or not tenure_key:
        raise ValueError(
            f"Could not identify building-type/tenure dimensions in housing response; dims={list(dims.keys())}"
        )

    hustyp_labels = list(dims[hustyp_key]["category"]["label"].values())
    tenure_labels = list(dims[tenure_key]["category"]["label"].values())

    id_list = raw.get("id", list(dims.keys()))
    hustyp_pos = id_list.index(hustyp_key) if hustyp_key in id_list else -1
    tenure_pos = id_list.index(tenure_key) if tenure_key in id_list else -1
    hustyp_before_tenure = hustyp_pos < tenure_pos

    counts: dict[str, float] = {}
    idx = 0
    if hustyp_before_tenure:
        for _ht_raw in hustyp_labels:
            for te_raw in tenure_labels:
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                idx += 1
                counts[te_raw] = counts.get(te_raw, 0.0) + v
    else:
        for te_raw in tenure_labels:
            for _ht_raw in hustyp_labels:
                v = float(values[idx] or 0) if idx < len(values) else 0.0
                idx += 1
                counts[te_raw] = counts.get(te_raw, 0.0) + v

    if not counts:
        raise ValueError("No housing_tenure data parsed from response")
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


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


_SCB_BAND_TO_AGE_GROUP: dict[str, str] = {
    # 18-19 year-olds fall back to this band -- the table starts at 20.
    "20-24 years": "18-24",
    "25-29 years": "25-34",
    "30-34 years": "25-34",
    "35-39 years": "35-44",
    "40-44 years": "35-44",
    "45-49 years": "45-54",
    "50-54 years": "45-54",
    "55-59 years": "55-64",
    "60-64 years": "55-64",
    "65-69 years": "65-74",
    "70-74 years": "65-74",
    "75-79 years": "75-85",
    "80-84 years": "75-85",
    "85+ years":   "75-85",
}

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
        pipeline_age = _SCB_BAND_TO_AGE_GROUP.get(age_label)
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
                    v = 0.0
                else:
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

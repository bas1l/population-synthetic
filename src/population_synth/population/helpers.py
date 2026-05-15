from __future__ import annotations

import numpy as np

VALID_AGE_GROUPS = {"18-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-85"}
AGE_GROUP_BOUNDS = [
    (18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"),
    (45, 54, "45-54"), (55, 64, "55-64"), (65, 74, "65-74"),
    (75, 85, "75-85"),
]


def age_to_group(age: int) -> str:
    for lo, hi, group in AGE_GROUP_BOUNDS:
        if lo <= age <= hi:
            return group
    raise ValueError(f"Age {age} outside valid range")


def resolve_age_group(label: str, mapping: dict[str, str]) -> str | None:
    mapped = mapping.get(label)
    if mapped:
        return mapped
    try:
        age = int(label.split()[0])
    except (ValueError, IndexError):
        import re
        m = re.match(r"(\d+)", label)
        if not m:
            return None
        age = int(m.group(1))
    for lo, hi, group in AGE_GROUP_BOUNDS:
        if lo <= age <= hi:
            return group
    return None


def normalize(dist: dict) -> dict:
    total = sum(dist.values()) or 1.0
    return {k: v / total for k, v in dist.items()}


def sample_from(rng: np.random.Generator, dist: dict) -> str:
    keys = list(dist.keys())
    probs = np.array([dist[k] for k in keys], dtype=float)
    probs /= probs.sum()
    return rng.choice(keys, p=probs)  # type: ignore[return-value]

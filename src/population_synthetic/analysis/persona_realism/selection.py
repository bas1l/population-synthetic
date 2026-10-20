"""selection.py -- which personas of a combination the judge selects (the roster).

The one selection rule every consumer of a combination's verdict cache shares. The
judge (``runner``) selects personas from the **capped mapped population**
(``population_cap/_mapped``, resolved by the caller through ``resolve_mapped_dir``);
stage 2, the artifact writer and ``realism_ranking``'s round-cap path must read back
exactly that set and nothing else. A combination folder can hold cache files of
personas that are no longer selected -- a re-cap draws a different persona set, and
leftover files are never deleted -- so no consumer may derive its persona set by
globbing the folder: each derives it here, from the same mapped file, and ignores
every file outside it.

Pure: no paths, no IO, no LLM client, so the cross-unit ``realism_ranking`` layer can
import it without learning anything about the judge.
"""

from __future__ import annotations

import random
import re
from collections.abc import Sequence
from typing import Any

from population_synthetic.analysis.persona_realism.config import JudgeConfig

__all__ = ["selected_indices", "selected_persona_ids"]

# The verdict/telemetry filename shape the sibling readers expect: ``artifacts.py``
# on ``persona_*.jsonl`` and ``reduce.py`` on ``persona_[0-9]*.json``. A cache key
# outside this shape is invisible to both, so :func:`_persona_key` enforces it.
_PERSONA_KEY_RE = re.compile(r"persona_\d+")


def _select_indices(n: int, sample_size: int | None, seed: Any) -> list[int]:
    """Choose which population indices to judge (seeded sampling; all if unbounded).

    ``sample_size`` null or >= population size -> all personas (no error). Sampling
    is deterministic in *seed* and returns sorted original indices so the on-disk
    ``persona_XXXXX.json`` cache is stable across resumed runs.
    """
    if sample_size is None or sample_size >= n:
        return list(range(n))
    rng = random.Random(seed)
    return sorted(rng.sample(range(n), sample_size))


def _select_prefix_indices(n: int, sample_size: int | None) -> list[int]:
    """Choose the first *sample_size* population indices (0..N-1); all if unbounded.

    Deterministic FIRST-N prefix, NOT seeded random (contrast :func:`_select_indices`).
    Used only for the real-reference cap (``sample_size_override``): the SCB population
    is already an i.i.d. sample, so a prefix is a valid random subsample, it is
    reproducible across runs, and it reuses any already-cached prefix personas -- so the
    round-count-aware resume/top-up gate selects the same personas on every run.
    ``sample_size`` null or >= population size -> all personas (no error).
    """
    if sample_size is None or sample_size >= n:
        return list(range(n))
    return list(range(sample_size))


def _persona_key(population: Sequence[dict[str, Any]], idx: int, combo_label: str) -> str:
    """Return the verdict-cache key for population index *idx*: the record's OWN id.

    NOT ``f"persona_{idx:05d}"``. The population read by this runner is the **capped**
    mapped file -- a seeded sparse subset of the clean pool -- so list index k and
    persona id k are different personas as soon as ``population_cap`` runs. Keying the
    cache on the index would attribute one persona's rounds to another on any re-draw
    (a new cap, a grown pool, a changed mapping config), silently and undetectably.

    The key is normalised to the ``persona_<5 digits>`` shape the sibling readers glob
    for (``artifacts.py`` on ``persona_*.jsonl``, ``reduce.py`` on
    ``persona_[0-9]*.json``): a synthetic record already carries its raw persona-dir
    name (``persona_00312``) and is used verbatim; the real reference carries an
    integer ``id`` (0, 1, 2, ...) and is formatted to match. Anything else raises --
    a key outside that shape is invisible to the readers, which would look like a
    combo that judged nothing.
    """
    raw = population[idx].get("id")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValueError(
            f"combo {combo_label!r}: mapped individual at index {idx} carries no 'id'; "
            f"the verdict cache is keyed on it."
        )
    if isinstance(raw, bool):  # bool is an int subclass; never a persona id
        raise ValueError(f"combo {combo_label!r}: index {idx} has a boolean 'id' ({raw!r}).")
    if isinstance(raw, int):
        return f"persona_{raw:05d}"
    text = str(raw).strip()
    if text.isdigit():
        return f"persona_{int(text):05d}"
    if _PERSONA_KEY_RE.fullmatch(text):
        return text
    raise ValueError(
        f"combo {combo_label!r}: index {idx} has id {raw!r}, which is neither an integer "
        f"nor of the form 'persona_<digits>'; the verdict readers glob 'persona_[0-9]*' "
        f"and would not see it."
    )


def selected_indices(n: int, cfg: JudgeConfig, *, sample_size_override: int | None = None) -> list[int]:
    """The population indices the judge selects from a mapped population of *n* records.

    The real-reference cap (*sample_size_override*, ``real_sample_size``) takes a
    deterministic first-N prefix; a synthetic combination (``None``) takes the seeded
    ``cfg.sample_size`` draw.
    """
    if sample_size_override is not None:
        return _select_prefix_indices(n, sample_size_override)
    return _select_indices(n, cfg.sample_size, cfg.bootstrap.get("seed"))


def selected_persona_ids(
    population: Sequence[dict[str, Any]],
    combo_label: str,
    cfg: JudgeConfig,
    *,
    sample_size_override: int | None = None,
) -> tuple[str, ...]:
    """The verdict-cache key of every persona the judge selects, sorted (the roster).

    *population* is the combination's capped mapped ``individuals`` list. This is the
    persona set stage 1 judges, so it is the persona set every reader of the cache
    consumes: a cache file whose key is not in it is a leftover and is ignored.
    """
    return tuple(sorted(
        _persona_key(population, idx, combo_label)
        for idx in selected_indices(len(population), cfg, sample_size_override=sample_size_override)
    ))

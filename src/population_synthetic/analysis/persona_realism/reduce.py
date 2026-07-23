"""reduce.py -- pure reduction round -> persona -> combination.

The first pure layer downstream of the judge-call cache (pipe-and-filter, guide
02 sect. 8). It consumes the frozen ``RoundVerdict`` DTOs produced by
:mod:`population_synthetic.analysis.persona_realism.judge` -- read back from the
durable ``raw/persona_XXXXX.json`` cache the runner wrote -- and reduces them in
two nested steps:

    list[RoundVerdict]      -> PersonaVerdict     (per-persona)
    list[PersonaVerdict|None] -> ComboRealism     (per-combination)

Both reductions are total functions of their inputs with no side effects. This
module must NOT know about the CLI, the LLM client, matplotlib, paths, or the
analysis registry. The one disk touch is :func:`load_combo_verdicts`, a thin
pure read of the cache the runner wrote, assigned to this input-boundary layer
(it round-trips Phase 2's ``dataclasses.asdict`` back through the *same*
``judge.parse_round_verdict`` validation boundary, so a corrupted cache fails
loud rather than yielding a malformed verdict).

Statistical-rigor invariants carried through (guide 03):

* **N and the successful count travel on every record.** A per-persona statistic
  carries ``n_rounds`` (the successful rounds actually present -- the honest
  denominator, since fully-failed rounds are absent from the cache); a
  per-combination record carries ``n_personas`` (successful) *and* ``n_failed``
  (personas whose calls all failed / whose cache file is absent), so a rate is
  never silently computed over a shrunken, unreported base.
* **"Judged possible" (a real zero) stays distinct from "call failed / absent"**
  -- a failed persona enters :func:`reduce_combo` as ``None`` and is counted in
  ``n_failed``, never folded into the possibility base.
* **Typicality is treated as ordinal.** Per-persona we retain the raw per-round
  ordinal values (not only a mean) so the stats layer can pick a rank-aware
  reliability metric; the mean/SD are convenience summaries, gated to ``None``
  when undefined (no scored round / a single scored round) rather than ``NaN``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from population_synthetic.analysis.persona_realism.judge import RoundVerdict, parse_round_verdict
from population_synthetic.analysis.utils import _stats

__all__ = [
    "ClashKey",
    "PersonaVerdict",
    "ComboRealism",
    "LoadedPersona",
    "reduce_persona",
    "reduce_combo",
    "load_persona_verdicts",
    "load_combo_verdicts",
]


@dataclass(frozen=True)
class ClashKey:
    """A canonical attribute-pair x severity clash identity (hashable dict key).

    ``pair`` is the two clashing axes as a **sorted** tuple, so the judge naming
    ``(a, b)`` in one round and ``(b, a)`` in another counts as the *same* clash.
    ``severity`` is one of ``S1``/``S2``/``S3``. Used as the key of the per-persona
    :attr:`PersonaVerdict.clash_frequency` and the per-combo
    :attr:`ComboRealism.clash_taxonomy` maps.
    """

    pair: tuple[str, str]
    severity: str


@dataclass(frozen=True)
class PersonaVerdict:
    """One persona reduced across its N judge rounds.

    ``n_rounds`` is the number of *successful* rounds present in the cache (the
    denominator for every field below); a fully-failed persona never reaches this
    reduction (it is absent from the cache and enters :func:`reduce_combo` as
    ``None``). ``p_possible`` is the share of those rounds with ``can_exist=True``
    (the retained per-round fraction ``p_i``); ``possible_majority`` is the
    majority verdict (``p_possible >= 0.5`` -- a tie on an even N resolves to
    *possible*, the conservative direction for an impossibility count).

    ``typicality_mean``/``typicality_sd`` summarise the ordinal typicality over
    the rounds where it is present (i.e. ``can_exist`` rounds); both are ``None``
    when undefined -- ``mean`` when no round scored a typicality, ``sd`` for fewer
    than two scored rounds (a single point has no spread) -- never ``NaN``.

    ``can_exist_rounds`` and ``typicality_rounds`` retain the raw per-round values
    (``typicality_rounds`` holds ``None`` for an impossible round) so the stats
    layer can compute reliability across rounds directly. ``clash_frequency`` maps
    each :class:`ClashKey` to the count of rounds (of ``n_rounds``) in which it
    appeared at least once.
    """

    persona_id: str
    n_rounds: int
    n_possible: int
    p_possible: float
    possible_majority: bool
    typicality_mean: float | None
    typicality_sd: float | None
    can_exist_rounds: tuple[bool, ...]
    typicality_rounds: tuple[int | None, ...]
    clash_frequency: dict[ClashKey, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ComboRealism:
    """One combination reduced across its personas.

    Identity + counts: ``combo_label`` (a synthetic ``{slug}`` or ``real_{country}``),
    ``n_personas`` (personas with a successful verdict -- the base for the
    impossibility rate) and ``n_failed`` (personas dropped because every judge call
    failed / the cache file was absent; surfaced so a rate over a shrunken base is
    never silently reported).

    Impossibility: ``impossible_count`` is the number of majority-impossible
    personas; ``impossibility_rate`` is ``impossible_count / n_personas`` (``None``
    when ``n_personas == 0``). ``impossible_indicators`` is the per-persona 0/1
    impossibility series -- **the sampling unit for the bootstrap CI** (one element
    = one persona), so the stats layer resamples personas, not rounds.
    ``possibility_fractions`` retains each persona's ``p_i``.

    Typicality distribution: ``typicality_means`` holds the per-persona mean
    typicality over the **majority-possible** personas only -- the ``can_exist``
    subset whose spread the stats layer characterises against the SCB reference.

    Clash taxonomy: ``clash_taxonomy`` maps each :class:`ClashKey` to the number of
    personas that exhibited it in at least one round (a persona-presence count, not
    a round-occurrence count).

    Reliability inputs: ``can_exist_rounds_by_persona`` and
    ``typicality_rounds_by_persona`` are the ragged per-persona round series
    (one row per successful persona) the stats layer feeds to Krippendorff's alpha
    / ICC. ``typicality_rounds_by_persona`` rows carry ``None`` for impossible
    rounds (no typicality), handled natively by the alpha computation.
    """

    combo_label: str
    n_personas: int
    n_failed: int
    impossible_count: int
    impossibility_rate: float | None
    impossible_indicators: tuple[int, ...]
    possibility_fractions: tuple[float, ...]
    typicality_means: tuple[float, ...]
    clash_taxonomy: dict[ClashKey, int] = field(default_factory=dict)
    can_exist_rounds_by_persona: tuple[tuple[bool, ...], ...] = ()
    typicality_rounds_by_persona: tuple[tuple[int | None, ...], ...] = ()


@dataclass(frozen=True)
class LoadedPersona:
    """One persona read back from its ``raw/persona_XXXXX.json`` cache file.

    Carries the persona identity, the mapped ``attributes`` dict (needed by the
    hard-rules validation subset), the successful ``rounds`` as re-validated
    :class:`RoundVerdict`s, and ``failed_rounds`` (the round-level failure count
    the runner recorded -- distinct from a persona-level failure, which leaves no
    file at all).
    """

    persona_id: str
    attributes: dict[str, Any]
    rounds: tuple[RoundVerdict, ...]
    failed_rounds: int


def reduce_persona(rounds: list[RoundVerdict] | tuple[RoundVerdict, ...], *, persona_id: str = "") -> PersonaVerdict:
    """Reduce one persona's successful rounds into a :class:`PersonaVerdict`.

    ``rounds`` must be non-empty: a persona with zero successful rounds is a
    *failed* persona, which is never cached and must be represented as ``None`` at
    the combo layer instead (:func:`reduce_combo`). Passing an empty list here is a
    programming error and raises, rather than silently producing a degenerate
    record that would corrupt the possibility base.
    """
    n = len(rounds)
    if n == 0:
        raise ValueError(
            f"reduce_persona requires >=1 successful round for persona {persona_id!r}; "
            "a fully-failed persona must enter reduce_combo as None, not here"
        )

    can_exist_rounds = tuple(r.can_exist for r in rounds)
    typicality_rounds = tuple(r.typicality for r in rounds)
    n_possible = sum(1 for c in can_exist_rounds if c)
    p_possible = n_possible / n

    scored = [t for t in typicality_rounds if t is not None]
    typicality_mean = _stats.mean(scored)  # None when no round scored a typicality
    typicality_sd = _stats.stddev(scored)  # None for <2 scored rounds (sample SD)

    # Per-round clash detection frequency: count the rounds in which each
    # (sorted-pair, severity) clash appeared at least once (a clash repeated
    # within one round still counts that round once).
    clash_frequency: dict[ClashKey, int] = {}
    for r in rounds:
        seen: set[ClashKey] = set()
        for issue in r.issues:
            seen.add(ClashKey(pair=tuple(sorted(issue.attributes)), severity=issue.severity))
        for key in seen:
            clash_frequency[key] = clash_frequency.get(key, 0) + 1

    return PersonaVerdict(
        persona_id=persona_id,
        n_rounds=n,
        n_possible=n_possible,
        p_possible=float(p_possible),
        possible_majority=p_possible >= 0.5,
        typicality_mean=typicality_mean,
        typicality_sd=typicality_sd,
        can_exist_rounds=can_exist_rounds,
        typicality_rounds=typicality_rounds,
        clash_frequency=clash_frequency,
    )


def reduce_combo(personas: list[PersonaVerdict | None], combo_label: str) -> ComboRealism:
    """Reduce a combination's personas into a :class:`ComboRealism`.

    ``personas`` is the list of per-persona reductions, with a ``None`` entry for
    every persona whose judge calls all failed / whose cache file was absent (the
    caller supplies these ``None`` slots -- typically from
    :func:`load_combo_verdicts` with an ``expected_ids`` roster). ``None`` slots
    are counted in ``n_failed`` and excluded from every rate/distribution, keeping
    "call failed" distinct from "judged possible".
    """
    present = [pv for pv in personas if pv is not None]
    n_failed = sum(1 for pv in personas if pv is None)
    n_personas = len(present)

    indicators = tuple(0 if pv.possible_majority else 1 for pv in present)
    impossible_count = sum(indicators)
    impossibility_rate = impossible_count / n_personas if n_personas else None
    possibility_fractions = tuple(pv.p_possible for pv in present)

    # Typicality distribution over the can_exist (majority-possible) subset only.
    typicality_means = tuple(
        pv.typicality_mean
        for pv in present
        if pv.possible_majority and pv.typicality_mean is not None
    )

    # Clash taxonomy: number of personas exhibiting each clash in >=1 round.
    clash_taxonomy: dict[ClashKey, int] = {}
    for pv in present:
        for key in pv.clash_frequency:
            clash_taxonomy[key] = clash_taxonomy.get(key, 0) + 1

    return ComboRealism(
        combo_label=combo_label,
        n_personas=n_personas,
        n_failed=n_failed,
        impossible_count=impossible_count,
        impossibility_rate=impossibility_rate,
        impossible_indicators=indicators,
        possibility_fractions=possibility_fractions,
        typicality_means=typicality_means,
        clash_taxonomy=clash_taxonomy,
        can_exist_rounds_by_persona=tuple(pv.can_exist_rounds for pv in present),
        typicality_rounds_by_persona=tuple(pv.typicality_rounds for pv in present),
    )


# --------------------------------------------------------------------------- #
# Cache loader (input boundary; round-trips Phase 2's asdict cache)           #
# --------------------------------------------------------------------------- #


def _round_from_cache(raw_round: dict[str, Any]) -> RoundVerdict:
    """Rebuild one :class:`RoundVerdict` from a cached round dict.

    The cache stored each verdict via ``dataclasses.asdict`` + ``json.dump``, so a
    round dict has the *same* shape as a raw judge response (``can_exist``,
    ``typicality``, ``issues[{attributes, severity, explanation}]``, ``reasoning``).
    Rather than re-implement validation, we re-dump and route it back through
    :func:`judge.parse_round_verdict` -- the single normalization boundary -- so a
    corrupted cache fails loud with the same contract as a live judge response.
    """
    return parse_round_verdict(json.dumps(raw_round))


def load_persona_verdicts(path: str | Path) -> LoadedPersona:
    """Read one ``raw/persona_XXXXX.json`` cache file into a :class:`LoadedPersona`.

    Raises ``ValueError`` (with file context) on a malformed cache file or a
    contract-violating round -- the cache is durable analysis input and a silent
    default here would corrupt every downstream statistic.
    """
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read persona cache {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"persona cache {path} did not parse to a mapping")
    for key in ("persona_id", "attributes", "rounds"):
        if key not in payload:
            raise ValueError(f"persona cache {path} is missing required key {key!r}")
    raw_rounds = payload["rounds"]
    if not isinstance(raw_rounds, list):
        raise ValueError(f"persona cache {path} 'rounds' must be a list")
    try:
        rounds = tuple(_round_from_cache(r) for r in raw_rounds)
    except ValueError as exc:
        raise ValueError(f"persona cache {path} has a contract-violating round: {exc}") from exc
    if not rounds:
        raise ValueError(f"persona cache {path} holds zero rounds (a cached persona must have >=1)")
    return LoadedPersona(
        persona_id=str(payload["persona_id"]),
        attributes=dict(payload["attributes"]),
        rounds=rounds,
        failed_rounds=int(payload.get("failed_rounds", 0)),
    )


def load_combo_verdicts(
    raw_dir: str | Path,
    *,
    expected_ids: list[str] | None = None,
) -> dict[str, LoadedPersona | None]:
    """Load a combo's ``raw/`` cache into ``{persona_id: LoadedPersona | None}``.

    Globs ``raw/persona_*.json`` and loads each into a :class:`LoadedPersona`.
    Fully-failed personas are absent from the cache by construction (the runner
    never writes them); passing ``expected_ids`` -- the roster of persona ids that
    were *selected* to be judged -- maps every selected id without a cache file to
    ``None`` (a **failed/absent** persona, kept distinct from a loaded one). Without
    ``expected_ids`` the result contains only the personas present on disk (all
    non-``None``), and the caller must supply the failed count some other way.

    The returned dict is ordered by persona id (sorted) so a downstream reduction
    and any seeded subsampling are stable across runs.
    """
    raw_dir = Path(raw_dir)
    found: dict[str, LoadedPersona] = {}
    if raw_dir.is_dir():
        for cache_file in sorted(raw_dir.glob("persona_*.json")):
            loaded = load_persona_verdicts(cache_file)
            found[loaded.persona_id] = loaded

    if expected_ids is None:
        return {pid: found[pid] for pid in sorted(found)}

    result: dict[str, LoadedPersona | None] = {}
    for pid in sorted(expected_ids):
        result[pid] = found.get(pid)  # None == selected-but-failed/absent
    # Surface any on-disk persona not in the roster rather than dropping it silently.
    for pid in sorted(found):
        if pid not in result:
            result[pid] = found[pid]
    return result

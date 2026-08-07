"""runner.py -- resumable, parallel judge-call fan-out with cost telemetry.

Turns an already-loaded mapped population into a per-persona verdict cache at the
combo root (no ``raw/`` subdir): ``<out_dir>/persona_XXXXX.json`` holds that
persona's successful ``RoundVerdict``s, and its sibling
``<out_dir>/persona_XXXXX.jsonl`` records every judge call's tokens/timing for the
Phase-4 cost chain (one telemetry file per persona, 1:1 with the verdict cache).

Orchestration mirrors ``scripts/generate/generate_identities_parallel.py``:
a ``ThreadPoolExecutor`` fan-out over PERSONAS (not rounds) and a
*round-count-aware* per-persona resume gate. Each persona is one unit of work:
the judge client **owned by the worker thread that picked it up** judges that
persona's shortfall rounds sequentially (with per-round retry of only the rounds
that fail), and the persona writes its OWN verdict json and telemetry jsonl the
moment its rounds finish -- so a long run reports incremental progress and an
interrupt keeps every persona already completed. Because each persona owns its
two distinct files (written atomically via ``tmp``+``replace``), no cross-thread
write lock or shared telemetry buffer is needed.

The judge client is **per worker thread, not per persona**. ``ClaudeCodeClient``
is a *persistent* CLI wrapper: its ``_ensure_process`` keeps one live ``claude``
subprocess and relaunches only when the model or system prompt changes -- and the
system prompt is invariant across personas (``prompt.build_prompts`` passes it
through verbatim), so every persona after a thread's first reuses that process.
Creating a client per persona instead spawned one full ``claude`` process *per
persona* -- hundreds of ~400 MB process launches per combo, thousands per sweep --
which starved the host machine. Clients are closed when the pool drains, not
between personas; the retry path stays correct because a failed call closes the
underlying process itself and ``_ensure_process`` relaunches on the next call.

Resume is *round-count-aware* (not binary-exists): a persona is skipped only when
its cached file already holds ``>= n_rounds`` successful rounds. A file left by an
earlier, smaller ``--rounds`` (or by earlier permanently-failed rounds) is
*topped up* -- the runner judges only the shortfall and **appends** the new rounds
to both the verdict json and the telemetry jsonl (so cumulative cost stays
correct). ``force`` re-judges from scratch, truncating both files. A fresh persona
is written truncate-mode; a fully-failed fresh persona (no successful round) is
left uncached and has no telemetry file at all (retryable on a later run).

Layer boundary -- this module must NOT compute statistics, render charts, or
resolve the analysis registry / output dir. It receives an already-resolved
``out_dir`` and the analyzed-axis list from the caller (the Phase-5 script), and
delegates rendering to ``prompt`` and parsing/validation to ``judge`` (the single
normalization point). A judge call that FAILED is represented distinctly from a
persona judged possible: a persona whose every round failed is counted as
``failed`` and is *not* written to the cache (so a later run retries it), never
serialized as a verdict.

Config is the single source of truth: :class:`~population_synthetic.analysis.persona_realism.config.JudgeConfig`
(:mod:`population_synthetic.analysis.persona_realism.config`) loads ``judge.yaml``
and raises on any missing/malformed key (fail-fast). It lives in its own module so
the config can be loaded without importing this module's LLM client layer.
"""

from __future__ import annotations

import atexit
import dataclasses
import json
import logging
import random
import re
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from population_synthetic.analysis.persona_realism.config import JudgeConfig
from population_synthetic.analysis.persona_realism.judge import RoundVerdict, parse_round_verdict
from population_synthetic.analysis.persona_realism.prompt import build_prompts, load_prompt_template
from population_synthetic.generators.synthetic.llm_interaction_log import (
    LLMInteractionCollector,
    LLMInteractionEntry,
)

__all__ = ["RunnerSummary", "run_combo_judgements"]

_LOGGER = logging.getLogger(__name__)

# The verdict/telemetry filename shape the sibling readers glob for: ``artifacts.py``
# on ``persona_*.jsonl`` and ``reduce.py`` on ``persona_[0-9]*.json``. A cache key
# outside this shape is invisible to both, so :func:`_persona_key` enforces it.
_PERSONA_KEY_RE = re.compile(r"persona_\d+")

# Bounded number of fan-out passes: one initial pass plus retries of the calls
# that failed (transient CLI errors the client's own retry did not clear, or a
# ragged JSON the parser rejected). Bounded so a persistently-malformed judge
# cannot loop forever; mirrors the client's own ``max_retries`` default of 3.
_MAX_JUDGE_PASSES = 3

# Category/method tags written into the interaction log so the Phase-4 cost chain
# (which parses the same JSONL) can attribute these calls to this process.
_LOG_CATEGORY = "persona_realism"
_LOG_METHOD = "judge"

# Process-wide registry of live judge clients, drained on interpreter exit so a
# crash mid-run never leaks `claude` subprocesses (mirrors the generation script).
_ACTIVE_CLIENTS: set = set()
_ACTIVE_LOCK = threading.Lock()


def _atexit_cleanup() -> None:
    with _ACTIVE_LOCK:
        clients = list(_ACTIVE_CLIENTS)
    for client in clients:
        try:
            client.close()
        except Exception:
            pass


atexit.register(_atexit_cleanup)


@dataclass(frozen=True)
class RunnerSummary:
    """Outcome of one combo's judge fan-out. All counts are over the sampled set.

    The three "made progress" outcomes are kept distinct: ``written`` (fresh
    personas newly cached this run, incl. ``--force`` rewrites), ``topped_up``
    (personas that already had a partial cache and gained >= 1 appended round toward
    ``n_rounds``), and ``skipped`` (personas whose cache already held >= ``n_rounds``
    successful rounds). ``failed`` counts only *fresh* personas whose every round
    failed (left uncached, retryable); a top-up that adds zero new rounds keeps its
    prior cache and is counted in none of these.

    ``selected_ids`` is the **roster**: the verdict-cache key of every persona this
    run selected, sorted. It is the honest denominator for the artifact layer --
    without it ``load_combo_realism`` sees only the personas present on disk and so
    reports ``n_failed == 0`` by construction, silently hiding the personas whose
    every round failed (which are deliberately left uncached and therefore leave no
    trace of their own).
    """

    combo_label: str
    n_selected: int          # personas selected (after sampling), before the resume gate
    requested: int           # personas judged this run (fresh + topped-up); selected - skipped
    written: int             # fresh personas newly cached this run (>= 1 successful round)
    topped_up: int           # existing personas that gained >= 1 appended round toward n_rounds
    skipped: int             # personas skipped: cache already held >= n_rounds successful rounds
    failed: int              # fresh personas whose every round failed (not cached)
    total_rounds: int        # new rounds attempted this run (== successful_rounds + failed_rounds)
    successful_rounds: int   # new successful rounds this run
    failed_rounds: int       # new failed rounds this run
    passes: int              # max per-persona judge attempts any persona used (1 + retries); 0 if none judged
    out_dir: Path
    selected_ids: tuple[str, ...] = ()   # verdict-cache key of every selected persona (sorted)


@dataclass(frozen=True)
class _PersonaOutcome:
    """One persona worker's return value, aggregated by the main thread into the summary.

    ``status`` is one of ``"written"`` (fresh persona newly cached), ``"topped_up"``
    (existing cache gained >= 1 appended round), ``"failed"`` (fresh persona whose every
    round failed -- left uncached, retryable), or ``"topup_noop"`` (a top-up that added
    zero rounds this run -- prior cache kept, counted in none of the progress buckets).
    """

    idx: int
    status: str
    n_ok: int              # successful new rounds this run for this persona
    n_failed_rounds: int   # shortfall rounds that failed after retry
    passes_used: int       # max attempts any of this persona's rounds needed (1..MAX)


def _default_client_factory(cfg: JudgeConfig) -> Any:
    """Construct a real judge client (lazy import; keeps the module CLI-free)."""
    from population_synthetic.clients.claude_code_client import ClaudeCodeClient

    return ClaudeCodeClient(
        model_name=cfg.judge_model,
        default_config={"temperature": cfg.temperature},
        timeout=cfg.timeout_seconds,
    )


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


def _build_entry(
    *,
    persona_id: str,
    round_idx: int,
    attempt: int,
    prompt: str,
    raw: str | None,
    verdict: RoundVerdict | None,
    error: str | None,
    meta: dict[str, Any],
) -> LLMInteractionEntry:
    """Build one judge call's telemetry record from the client's ``last_metadata``.

    Pure construction -- no file handle, no lock. The caller appends the returned
    entry to that persona's LOCAL list, which is flushed to the persona's own
    ``.jsonl`` once its rounds finish.
    """
    parsed = None
    if verdict is not None:
        parsed = {"can_exist": verdict.can_exist, "typicality": verdict.typicality}
    return LLMInteractionEntry(
        category=_LOG_CATEGORY,
        method=_LOG_METHOD,
        step=f"round_{round_idx}",
        prompt=prompt,
        raw_response=raw or "",
        parsed_value=parsed,
        error=error,
        attempt=attempt,
        persona_id=persona_id,
        call_index=round_idx,
        provider=meta.get("provider"),
        model=meta.get("model"),
        request_sent_at=meta.get("request_sent_at"),
        response_received_at=meta.get("response_received_at"),
        elapsed_ms=meta.get("elapsed_ms"),
        prompt_tokens=meta.get("prompt_tokens"),
        completion_tokens=meta.get("completion_tokens"),
        total_tokens=meta.get("total_tokens"),
        cache_read_tokens=meta.get("cache_read_tokens"),
        cache_creation_tokens=meta.get("cache_creation_tokens"),
        error_category=meta.get("error_category"),
    )


def _judge_one_round(
    client: Any,
    *,
    persona_id: str,
    round_idx: int,
    attempt: int,
    system_str: str,
    user_str: str,
    cfg: JudgeConfig,
    entries: list[LLMInteractionEntry],
) -> tuple[RoundVerdict | None, str | None]:
    """Run one judge call for one (persona, round) on *client*; never raises.

    Reuses the persona's own client (the persona worker owns its lifecycle), appends
    the call's telemetry -- success or failure -- to that persona's LOCAL ``entries``
    list, and returns the verdict or a string error. A parse/contract violation from
    :func:`parse_round_verdict` is caught here and surfaced as a failed round
    (retryable), keeping failure distinct from a possible verdict.
    """
    raw: str | None = None
    verdict: RoundVerdict | None = None
    error: str | None = None
    try:
        raw = client.generate_content(
            user_str, model=cfg.judge_model, system_instruction=system_str
        )
        verdict = parse_round_verdict(raw)
    except Exception as exc:  # noqa: BLE001 -- a failed round is retryable, not fatal
        error = f"{type(exc).__name__}: {exc}"
    meta = getattr(client, "last_metadata", {}) or {}
    entries.append(
        _build_entry(
            persona_id=persona_id, round_idx=round_idx, attempt=attempt,
            prompt=user_str, raw=raw, verdict=verdict, error=error, meta=meta,
        )
    )
    return verdict, error


def _read_cached_rounds(path: Path, *, expected_id: str) -> list[dict[str, Any]]:
    """Return the successful round dicts already cached for a persona (fail-fast).

    Used by the round-count-aware resume gate to decide skip vs top-up. The list
    length is the count of successful rounds already stored. A malformed cache
    raises (a silent default here would corrupt the resume/top-up decision).

    ``expected_id`` is the key the caller resolved from the mapped record. A stored
    ``persona_id`` that disagrees means the file was written against a different
    capped population (or was renamed by hand): its rounds describe another persona,
    so reusing them would silently mis-attribute verdicts. That raises rather than
    being repaired, because the correct repair (re-judge, or restore the matching
    cap) is a decision about cost that this layer cannot make.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read persona cache {path}: {exc}") from exc
    stored = payload.get("persona_id")
    if stored != expected_id:
        raise ValueError(
            f"persona cache {path} holds verdicts for {stored!r}, not {expected_id!r}. "
            f"The cache was written against a different capped population; re-run with "
            f"--force to re-judge, or restore the cap this cache belongs to."
        )
    rounds = payload.get("rounds")
    if not isinstance(rounds, list):
        raise ValueError(f"persona cache {path} has no 'rounds' list to resume from")
    return rounds


def _write_persona_file(
    path: Path,
    *,
    persona_id: str,
    combo_label: str,
    cfg: JudgeConfig,
    persona: dict[str, Any],
    analyzed_attrs: list[str],
    existing_rounds: list[dict[str, Any]],
    new_verdicts: list[RoundVerdict],
) -> None:
    """Atomically write one persona's cache file (existing rounds + newly-judged ones).

    ``existing_rounds`` are the round dicts already on disk (``[]`` for a fresh or
    ``--force`` write); ``new_verdicts`` are this pass's successful rounds, appended
    as ``dataclasses.asdict`` records so a ``rounds=1`` file topped up with
    ``rounds=2`` ends holding 2 rounds. ``n_rounds`` is the configured target; the
    stored ``successful_rounds`` is the combined length and ``status`` is
    ``complete`` once it reaches the target, else ``partial``.

    Stored ``attributes`` are resolved through the canonical accessor
    :func:`attr_value` (not raw ``persona[attr]`` indexing) so a real mapped record
    -- which carries the integer ``age`` rather than a pre-binned ``age_group`` --
    has its ``age_group`` bracket derived on demand, matching what the analyzed
    scheme and hard-rules expect (and mirroring ``prompt.render_persona_block``).
    """
    # Lazy import (mirrors prompt.render_persona_block): keep this resumable IO layer
    # from pulling the statistics stack (numpy/scipy via evaluator) at import time.
    from population_synthetic.analysis.fidelity.evaluator import attr_value

    rounds = list(existing_rounds) + [dataclasses.asdict(v) for v in new_verdicts]
    successful = len(rounds)
    payload = {
        "persona_id": persona_id,
        "combo": combo_label,
        "judge_model": cfg.judge_model,
        "n_rounds": cfg.n_rounds,
        "successful_rounds": successful,
        "failed_rounds": max(cfg.n_rounds - successful, 0),
        "status": "complete" if successful >= cfg.n_rounds else "partial",
        "attributes": {attr: attr_value(persona, attr) for attr in analyzed_attrs},
        "rounds": rounds,
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _flush_telemetry(path: Path, entries: list[LLMInteractionEntry], *, append: bool) -> None:
    """Write one persona's buffered telemetry to ``persona_XXXXX.jsonl`` (sequential).

    ``append`` (a top-up onto an existing persona) opens the collector in append
    mode so prior passes' calls are retained and cumulative cost stays correct;
    otherwise (fresh persona / ``--force``) it truncates. Called from within a
    persona's own task; the handle targets only that persona's ``.jsonl`` (distinct
    per persona), so concurrent personas never share it.
    """
    if not entries:
        return
    collector = LLMInteractionCollector(path, append=append)
    try:
        for entry in entries:
            collector.record(entry)
    finally:
        collector.close()


def run_combo_judgements(
    population: list[dict[str, Any]],
    combo_label: str,
    analyzed_attrs: list[str],
    out_dir: str | Path,
    cfg: JudgeConfig,
    *,
    force: bool = False,
    plan_only: bool = False,
    sample_size_override: int | None = None,
    client_factory: Callable[[], Any] | None = None,
    logger: logging.Logger | None = None,
) -> RunnerSummary:
    """Judge every selected persona N times and cache the verdicts under *out_dir*.

    Parameters
    ----------
    population:
        The mapped ``individuals`` list (each a flat attribute dict).
    combo_label:
        The combination label (a synthetic ``{slug}`` or ``real_{country}``);
        recorded in each persona file and log line.
    analyzed_attrs:
        The country's config-sourced analyzed axis (deprecated axis already
        excluded), resolved by the caller via ``scheme_attributes(country)``.
    out_dir:
        The already-resolved combo output directory (the caller owns registry /
        output-dir resolution).
    cfg:
        The loaded :class:`JudgeConfig`.
    force:
        Re-judge every selected persona from scratch, truncating both the verdict
        json and the telemetry jsonl (ignores any cached rounds).
    sample_size_override:
        When not ``None``, overrides ``cfg.sample_size`` for THIS call and selects
        the personas as a deterministic FIRST-N prefix (indices 0..N-1) rather than
        the seeded random draw. Used for the real-reference cap (``real_sample_size``):
        the SCB population is already an i.i.d. sample, so a prefix is a valid random
        subsample, reproducible across runs, and reuses already-cached prefix personas.
        The synthetic combos leave this ``None`` and keep the seeded ``sample_size`` draw.
    client_factory:
        Zero-arg factory returning a judge client (duck-typed ``generate_content``
        + ``last_metadata`` + optional ``close``). Defaults to a real
        ``ClaudeCodeClient``; tests inject a stub.
    plan_only:
        Resolve the persona roster and the resume gate, then return **without judging
        anything** -- guaranteed zero LLM calls, no client ever constructed, no file
        written. Used by the artifact-rewrite path, which needs the roster (so
        ``n_failed`` counts the personas that left no cache file) but must not incur
        judge cost. A persona below the round-count target is logged, not judged.

    Returns a :class:`RunnerSummary`. Raises (fail-fast) if a selected persona is
    missing an analyzed axis -- a data-schema error, distinct from a judge failure.
    """
    logger = logger or _LOGGER
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if client_factory is None:
        def client_factory() -> Any:  # noqa: E306
            return _default_client_factory(cfg)

    system_str, user_template = load_prompt_template(cfg.prompt_template)

    # The real-reference cap (sample_size_override) uses a deterministic first-N prefix;
    # synthetic combos use the seeded random draw governed by cfg.sample_size.
    if sample_size_override is not None:
        selected = _select_prefix_indices(len(population), sample_size_override)
    else:
        selected = _select_indices(len(population), cfg.sample_size, cfg.bootstrap.get("seed"))

    # Round-count-aware resume gate. For each selected persona decide skip / top-up /
    # fresh, recording the already-cached rounds (``existing[idx]``) to extend and
    # whether its telemetry must be appended (top-up) or truncated (fresh / force).
    to_judge: list[int] = []
    skipped = 0
    existing: dict[int, list[dict[str, Any]]] = {}
    append_jsonl: dict[int, bool] = {}
    keys: dict[int, str] = {idx: _persona_key(population, idx, combo_label) for idx in selected}
    for idx in selected:
        persona_file = out_dir / f"{keys[idx]}.json"
        if persona_file.exists() and not force:
            cached = _read_cached_rounds(persona_file, expected_id=keys[idx])
            if len(cached) >= cfg.n_rounds:
                skipped += 1  # already at/above the target round count
                continue
            existing[idx] = cached      # top-up: extend these
            append_jsonl[idx] = True
        else:
            existing[idx] = []          # fresh / force: truncate write
            append_jsonl[idx] = False
        to_judge.append(idx)

    # Plan-only: resolve the roster and the resume gate, then stop before any judge call.
    # This is what makes the caller's artifact-rewrite path zero-cost *by construction*
    # rather than by the operator remembering to match --rounds to the cached round count:
    # a config whose n_rounds sits above what is cached would otherwise silently top every
    # persona up, turning a "just rewrite the files" run into a full re-judge.
    if plan_only:
        if to_judge:
            logger.warning(
                "combo %s: plan-only run -- %d persona(s) are below the %d-round target and were "
                "NOT judged (no LLM call made). Re-run without --rewrite-artifacts to top them up.",
                combo_label, len(to_judge), cfg.n_rounds,
            )
        return RunnerSummary(
            combo_label=combo_label, n_selected=len(selected), requested=0,
            written=0, topped_up=0, skipped=skipped, failed=0,
            total_rounds=0, successful_rounds=0, failed_rounds=0, passes=0,
            out_dir=out_dir, selected_ids=tuple(sorted(keys[idx] for idx in selected)),
        )

    # Render each persona's prompts once (fail-fast on a missing analyzed axis --
    # a data error that must abort, not be recorded as a judge-round failure).
    prompts: dict[int, tuple[str, str]] = {}
    for idx in to_judge:
        try:
            prompts[idx] = build_prompts(population[idx], analyzed_attrs, system_str, user_template)
        except KeyError as exc:
            raise RuntimeError(
                f"combo {combo_label!r} {keys[idx]}: {exc}"
            ) from exc

    total_new_rounds = sum(cfg.n_rounds - len(existing[idx]) for idx in to_judge)

    # One judge client PER WORKER THREAD (see the module docstring): created on that
    # thread's first persona and reused for every later one, so the live `claude`
    # subprocess count is bounded by `cfg.workers` instead of scaling with the
    # persona count. Registered in `_ACTIVE_CLIENTS` for the atexit drain and closed
    # in `_close_pool_clients` once the executor has drained.
    thread_state = threading.local()
    pool_clients: list[Any] = []
    pool_clients_lock = threading.Lock()

    def _thread_client() -> Any:
        """Return this worker thread's judge client, creating it on first use."""
        client = getattr(thread_state, "client", None)
        if client is not None:
            return client
        client = client_factory()
        thread_state.client = client
        with pool_clients_lock:
            pool_clients.append(client)
        if hasattr(client, "close"):
            with _ACTIVE_LOCK:
                _ACTIVE_CLIENTS.add(client)
        return client

    def _close_pool_clients() -> None:
        """Close every client this pool created; safe to call when none were made."""
        with pool_clients_lock:
            clients = list(pool_clients)
            pool_clients.clear()
        for client in clients:
            if not hasattr(client, "close"):
                continue
            try:
                client.close()
            except Exception:  # teardown must never mask the run's own outcome
                logger.debug("combo %s: judge client close() failed", combo_label, exc_info=True)
            with _ACTIVE_LOCK:
                _ACTIVE_CLIENTS.discard(client)

    def _judge_and_write_persona(idx: int) -> _PersonaOutcome:
        """Judge one persona's shortfall rounds, then write ITS OWN files immediately.

        Owns a single judge client for this persona (created here, ``close()``d in a
        ``finally``); judges rounds ``range(len(existing[idx]), n_rounds)`` sequentially
        with per-round retry up to ``_MAX_JUDGE_PASSES`` of only the rounds that fail;
        collects verdicts + telemetry into LOCAL lists. On >= 1 successful round it
        atomically writes ``persona_XXXXX.json`` and flushes ``persona_XXXXX.jsonl``
        (append for a top-up, truncate for a fresh/force write) -- so this persona is
        durable the instant its rounds finish, independent of every sibling. A fresh
        persona with zero successful rounds is left uncached (retryable, no telemetry);
        a top-up that adds zero rounds keeps its prior cache untouched.
        """
        persona_id = keys[idx]
        system_str, user_str = prompts[idx]
        n_existing = len(existing[idx])
        is_topup = append_jsonl[idx]

        new_verdicts: list[RoundVerdict] = []
        local_entries: list[LLMInteractionEntry] = []
        passes_used = 1

        client = _thread_client()
        for r in range(n_existing, cfg.n_rounds):
            for attempt in range(1, _MAX_JUDGE_PASSES + 1):
                passes_used = max(passes_used, attempt)
                verdict, error = _judge_one_round(
                    client,
                    persona_id=persona_id, round_idx=r, attempt=attempt,
                    system_str=system_str, user_str=user_str, cfg=cfg,
                    entries=local_entries,
                )
                if verdict is not None:
                    new_verdicts.append(verdict)
                    break
                if attempt < _MAX_JUDGE_PASSES:
                    logger.info(
                        "combo %s %s round %d failed (attempt %d/%d), retrying: %s",
                        combo_label, persona_id, r, attempt, _MAX_JUDGE_PASSES, error,
                    )
                else:
                    logger.warning(
                        "combo %s %s round %d failed after %d attempt(s): %s",
                        combo_label, persona_id, r, _MAX_JUDGE_PASSES, error,
                    )

        n_ok = len(new_verdicts)
        n_failed_rounds = (cfg.n_rounds - n_existing) - n_ok

        if n_ok == 0:
            if is_topup:
                logger.warning(
                    "combo %s %s: top-up added 0 of %d requested round(s); %d cached round(s) kept",
                    combo_label, persona_id, cfg.n_rounds - n_existing, n_existing,
                )
                status = "topup_noop"
            else:
                logger.error(
                    "combo %s %s: all %d rounds failed after %d pass(es) — not cached",
                    combo_label, persona_id, cfg.n_rounds, passes_used,
                )
                status = "failed"
            return _PersonaOutcome(idx, status, n_ok, n_failed_rounds, passes_used)

        # >= 1 new round: write this persona's OWN files now (atomic tmp+replace on the
        # json; distinct per-persona paths, so no cross-thread write lock is needed).
        _write_persona_file(
            out_dir / f"{persona_id}.json",
            persona_id=persona_id,
            combo_label=combo_label,
            cfg=cfg,
            persona=population[idx],
            analyzed_attrs=analyzed_attrs,
            existing_rounds=existing[idx],
            new_verdicts=new_verdicts,
        )
        _flush_telemetry(out_dir / f"{persona_id}.jsonl", local_entries, append=is_topup)
        logger.info("combo %s %s: wrote %d round(s)", combo_label, persona_id, n_ok)
        return _PersonaOutcome(idx, "topped_up" if is_topup else "written", n_ok, n_failed_rounds, passes_used)

    # Fan out one task PER persona (each doing its rounds sequentially): effective
    # concurrency is unchanged (cfg.workers personas in flight) but writes are now
    # incremental and interrupt-safe. The main thread aggregates the returned outcomes
    # -- no shared mutable counters/buffer across threads.
    written = 0
    topped_up = 0
    failed_personas = 0
    successful_rounds = 0
    failed_rounds = 0
    passes = 0
    if to_judge:
        try:
            with ThreadPoolExecutor(max_workers=cfg.workers) as executor:
                futures = [executor.submit(_judge_and_write_persona, idx) for idx in to_judge]
                for future in as_completed(futures):
                    outcome = future.result()
                    successful_rounds += outcome.n_ok
                    failed_rounds += outcome.n_failed_rounds
                    passes = max(passes, outcome.passes_used)
                    if outcome.status == "written":
                        written += 1
                    elif outcome.status == "topped_up":
                        topped_up += 1
                    elif outcome.status == "failed":
                        failed_personas += 1
                    # "topup_noop": prior cache kept, counted in no progress bucket.
        finally:
            # The pool has drained (normally or by exception), so no worker thread can
            # still be using its client: tear them down here rather than per persona.
            _close_pool_clients()

    summary = RunnerSummary(
        combo_label=combo_label,
        n_selected=len(selected),
        requested=len(to_judge),
        written=written,
        topped_up=topped_up,
        skipped=skipped,
        failed=failed_personas,
        total_rounds=total_new_rounds,
        successful_rounds=successful_rounds,
        failed_rounds=failed_rounds,
        passes=passes,
        out_dir=out_dir,
        selected_ids=tuple(sorted(keys[idx] for idx in selected)),
    )
    logger.info(
        "combo %s judged: written=%d topped_up=%d skipped=%d failed=%d "
        "(new rounds ok=%d failed=%d, passes=%d)",
        combo_label, written, topped_up, skipped, failed_personas,
        successful_rounds, failed_rounds, passes,
    )
    return summary

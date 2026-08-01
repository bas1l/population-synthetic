"""runner.py -- resumable, parallel judge-call fan-out with cost telemetry.

Turns an already-loaded mapped population into a per-persona verdict cache at the
combo root (no ``raw/`` subdir): ``<out_dir>/persona_XXXXX.json`` holds that
persona's successful ``RoundVerdict``s, and its sibling
``<out_dir>/persona_XXXXX.jsonl`` records every judge call's tokens/timing for the
Phase-4 cost chain (one telemetry file per persona, 1:1 with the verdict cache).

Orchestration mirrors ``scripts/generate/generate_identities_parallel.py``:
a ``ThreadPoolExecutor`` fan-out over PERSONAS (not rounds) and a
*round-count-aware* per-persona resume gate. Each persona is one unit of work:
its own throwaway judge client judges that persona's shortfall rounds
sequentially (with per-round retry of only the rounds that fail), and the
persona writes its OWN verdict json and telemetry jsonl the moment its rounds
finish -- so a long run reports incremental progress and an interrupt keeps
every persona already completed. Because each persona owns its two distinct
files (written atomically via ``tmp``+``replace``), no cross-thread write lock
or shared telemetry buffer is needed.

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

Config is the single source of truth: :class:`JudgeConfig` loads
``judge.yaml`` and raises on any missing/malformed key (fail-fast).
"""

from __future__ import annotations

import atexit
import dataclasses
import json
import logging
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from population_synthetic.analysis.persona_realism.judge import RoundVerdict, parse_round_verdict
from population_synthetic.analysis.persona_realism.prompt import build_prompts, load_prompt_template
from population_synthetic.generators.synthetic.llm_interaction_log import (
    LLMInteractionCollector,
    LLMInteractionEntry,
)

__all__ = ["JudgeConfig", "RunnerSummary", "run_combo_judgements"]

_LOGGER = logging.getLogger(__name__)

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
class JudgeConfig:
    """The persona-realism judge configuration, loaded once from ``judge.yaml``.

    All fields are required in the YAML; :meth:`load` raises on any missing or
    malformed key. ``prompt_template`` is resolved to an absolute path relative to
    the config directory. Fields beyond Phase 2's needs (``severity_weights``,
    ``impossibility_severities``, ``bootstrap``) are carried through so downstream
    phases share this one config DTO.
    """

    judge_model: str
    model_options: tuple[str, ...]
    n_rounds: int
    temperature: float
    severity_weights: dict[str, float]
    impossibility_severities: tuple[str, ...]
    sample_size: int | None
    real_sample_size: int | None
    bootstrap: dict[str, Any]
    workers: int
    timeout_seconds: int
    prompt_template: Path
    config_dir: Path
    reliability: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, config_dir: str | Path) -> JudgeConfig:
        """Read ``<config_dir>/judge.yaml`` into a validated config (fail-fast)."""
        config_dir = Path(config_dir)
        judge_path = config_dir / "judge.yaml"
        if not judge_path.exists():
            raise FileNotFoundError(f"judge config not found: {judge_path}")
        data = yaml.safe_load(judge_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"judge config {judge_path} did not parse to a mapping")

        required = [
            "judge_model", "model_options", "n_rounds", "temperature",
            "severity_weights", "impossibility_severities", "sample_size",
            "real_sample_size", "bootstrap", "workers", "timeout_seconds",
            "prompt_template",
        ]
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"judge config {judge_path} is missing required keys: {missing}")

        template_path = (config_dir / str(data["prompt_template"])).resolve()
        if not template_path.exists():
            raise FileNotFoundError(f"prompt template not found: {template_path}")

        n_rounds = int(data["n_rounds"])
        if n_rounds < 1:
            raise ValueError(f"judge config 'n_rounds' must be >= 1, got {n_rounds}")
        workers = int(data["workers"])
        if workers < 1:
            raise ValueError(f"judge config 'workers' must be >= 1, got {workers}")
        timeout_seconds = int(data["timeout_seconds"])
        if timeout_seconds < 1:
            raise ValueError(f"judge config 'timeout_seconds' must be >= 1, got {timeout_seconds}")

        sample_size = data["sample_size"]
        if sample_size is not None:
            sample_size = int(sample_size)
            if sample_size < 1:
                raise ValueError(f"judge config 'sample_size' must be >= 1 or null, got {sample_size}")

        real_sample_size = data["real_sample_size"]
        if real_sample_size is not None:
            real_sample_size = int(real_sample_size)
            if real_sample_size < 1:
                raise ValueError(
                    f"judge config 'real_sample_size' must be >= 1 or null, got {real_sample_size}"
                )

        return cls(
            judge_model=str(data["judge_model"]),
            model_options=tuple(str(m) for m in data["model_options"]),
            n_rounds=n_rounds,
            temperature=float(data["temperature"]),
            severity_weights=dict(data["severity_weights"]),
            impossibility_severities=tuple(str(s) for s in data["impossibility_severities"]),
            sample_size=sample_size,
            real_sample_size=real_sample_size,
            bootstrap=dict(data["bootstrap"]),
            workers=workers,
            timeout_seconds=timeout_seconds,
            prompt_template=template_path,
            config_dir=config_dir,
            reliability=dict(data.get("reliability") or {}),
        )


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


def _read_cached_rounds(path: Path) -> list[dict[str, Any]]:
    """Return the successful round dicts already cached for a persona (fail-fast).

    Used by the round-count-aware resume gate to decide skip vs top-up. The list
    length is the count of successful rounds already stored. A malformed cache
    raises (a silent default here would corrupt the resume/top-up decision).
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read persona cache {path}: {exc}") from exc
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
    for idx in selected:
        persona_file = out_dir / f"persona_{idx:05d}.json"
        if persona_file.exists() and not force:
            cached = _read_cached_rounds(persona_file)
            if len(cached) >= cfg.n_rounds:
                skipped += 1  # already at/above the target round count
                continue
            existing[idx] = cached      # top-up: extend these
            append_jsonl[idx] = True
        else:
            existing[idx] = []          # fresh / force: truncate write
            append_jsonl[idx] = False
        to_judge.append(idx)

    # Render each persona's prompts once (fail-fast on a missing analyzed axis --
    # a data error that must abort, not be recorded as a judge-round failure).
    prompts: dict[int, tuple[str, str]] = {}
    for idx in to_judge:
        try:
            prompts[idx] = build_prompts(population[idx], analyzed_attrs, system_str, user_template)
        except KeyError as exc:
            raise RuntimeError(
                f"combo {combo_label!r} persona_{idx:05d}: {exc}"
            ) from exc

    total_new_rounds = sum(cfg.n_rounds - len(existing[idx]) for idx in to_judge)

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
        persona_id = f"persona_{idx:05d}"
        system_str, user_str = prompts[idx]
        n_existing = len(existing[idx])
        is_topup = append_jsonl[idx]

        new_verdicts: list[RoundVerdict] = []
        local_entries: list[LLMInteractionEntry] = []
        passes_used = 1

        client = client_factory()
        registered = hasattr(client, "close")
        if registered:
            with _ACTIVE_LOCK:
                _ACTIVE_CLIENTS.add(client)
        try:
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
        finally:
            if registered:
                try:
                    client.close()
                except Exception:
                    pass
                with _ACTIVE_LOCK:
                    _ACTIVE_CLIENTS.discard(client)

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
    )
    logger.info(
        "combo %s judged: written=%d topped_up=%d skipped=%d failed=%d "
        "(new rounds ok=%d failed=%d, passes=%d)",
        combo_label, written, topped_up, skipped, failed_personas,
        successful_rounds, failed_rounds, passes,
    )
    return summary

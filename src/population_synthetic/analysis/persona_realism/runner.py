"""runner.py -- resumable, parallel judge-call fan-out with cost telemetry.

Turns an already-loaded mapped population into a per-persona verdict cache at the
combo root (no ``raw/`` subdir): ``<out_dir>/persona_XXXXX.json`` holds that
persona's successful ``RoundVerdict``s, and its sibling
``<out_dir>/persona_XXXXX.jsonl`` records every judge call's tokens/timing for the
Phase-4 cost chain (one telemetry file per persona, 1:1 with the verdict cache).

Orchestration mirrors ``scripts/generate/generate_identities_parallel.py``:
a ``ThreadPoolExecutor`` fan-out, a *round-count-aware* per-persona resume gate,
and round-based retry of only the failed calls. During the parallel fan-out each
call's telemetry is appended to a thread-safe in-memory buffer (no per-persona
file handles are opened concurrently); the buffers are flushed sequentially at
end-of-run, one throwaway ``LLMInteractionCollector`` handle at a time.

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
from collections import defaultdict
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


class _AppendingCollector(LLMInteractionCollector):
    """A throwaway ``LLMInteractionCollector`` that APPENDS instead of truncating.

    Used only at end-of-run when topping up an existing persona's telemetry so cost
    accumulates across passes. Overrides only the file-open mode (``"a"`` instead of
    the parent's ``"w"``); it does NOT modify the shared collector class. Constructed
    one at a time, sequentially, after the parallel fan-out has finished.
    """

    def _ensure_open(self) -> None:  # type: ignore[override]
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self._path, "a", encoding="utf-8")


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
            "bootstrap", "workers", "timeout_seconds", "prompt_template",
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

        return cls(
            judge_model=str(data["judge_model"]),
            model_options=tuple(str(m) for m in data["model_options"]),
            n_rounds=n_rounds,
            temperature=float(data["temperature"]),
            severity_weights=dict(data["severity_weights"]),
            impossibility_severities=tuple(str(s) for s in data["impossibility_severities"]),
            sample_size=sample_size,
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
    passes: int              # fan-out passes actually run (1 + retries)
    out_dir: Path


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


def _record_call(
    buffer: dict[str, list[LLMInteractionEntry]],
    lock: threading.Lock,
    *,
    persona_id: str,
    round_idx: int,
    attempt: int,
    prompt: str,
    raw: str | None,
    verdict: RoundVerdict | None,
    error: str | None,
    meta: dict[str, Any],
) -> None:
    """Append one judge call's telemetry to the persona's in-memory buffer (thread-safe).

    No file handle is opened here: buffering keeps the parallel fan-out lock-cheap
    and defers all per-persona ``.jsonl`` writes to the sequential end-of-run flush.
    """
    parsed = None
    if verdict is not None:
        parsed = {"can_exist": verdict.can_exist, "typicality": verdict.typicality}
    entry = LLMInteractionEntry(
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
    with lock:
        buffer[persona_id].append(entry)


def _judge_call(
    *,
    persona_index: int,
    persona_id: str,
    round_idx: int,
    attempt: int,
    system_str: str,
    user_str: str,
    cfg: JudgeConfig,
    client_factory: Callable[[], Any],
    buffer: dict[str, list[LLMInteractionEntry]],
    buffer_lock: threading.Lock,
) -> tuple[int, int, RoundVerdict | None, str | None]:
    """Run one judge call for one (persona, round); never raises.

    Instantiates one client for this call (mirrors ``_generate_one``), records the
    call's telemetry whether it succeeds or fails, and returns the verdict or a
    string error. A parse/contract violation from :func:`parse_round_verdict` is
    caught here and surfaced as a failed round (retryable), keeping failure
    distinct from a possible verdict.
    """
    client = client_factory()
    registered = hasattr(client, "close")
    if registered:
        with _ACTIVE_LOCK:
            _ACTIVE_CLIENTS.add(client)

    raw: str | None = None
    verdict: RoundVerdict | None = None
    error: str | None = None
    try:
        raw = client.generate_content(
            user_str, model=cfg.judge_model, system_instruction=system_str
        )
        verdict = parse_round_verdict(raw)
    except Exception as exc:  # noqa: BLE001 -- fan-out worker must not crash the pool
        error = f"{type(exc).__name__}: {exc}"
    finally:
        meta = getattr(client, "last_metadata", {}) or {}
        _record_call(
            buffer, buffer_lock,
            persona_id=persona_id, round_idx=round_idx, attempt=attempt,
            prompt=user_str, raw=raw, verdict=verdict, error=error, meta=meta,
        )
        if registered:
            try:
                client.close()
            except Exception:
                pass
            with _ACTIVE_LOCK:
                _ACTIVE_CLIENTS.discard(client)

    return persona_index, round_idx, verdict, error


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

    ``append`` (a top-up onto an existing persona) opens a throwaway
    :class:`_AppendingCollector` so prior passes' calls are retained and cumulative
    cost stays correct; otherwise (fresh persona / ``--force``) a plain
    :class:`LLMInteractionCollector` truncates. One handle at a time, opened and
    closed here -- never during the parallel fan-out.
    """
    if not entries:
        return
    collector = _AppendingCollector(path) if append else LLMInteractionCollector(path)
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

    # Per-call telemetry accumulates in memory during the parallel fan-out; the
    # per-persona ``.jsonl`` files are written sequentially at end-of-run. Only the
    # shortfall rounds (``n_rounds`` minus already-cached) are judged for each persona,
    # numbered continuing from the existing count.
    buffer: dict[str, list[LLMInteractionEntry]] = defaultdict(list)
    buffer_lock = threading.Lock()

    results: dict[tuple[int, int], RoundVerdict] = {}
    pending = [(idx, r) for idx in to_judge for r in range(len(existing[idx]), cfg.n_rounds)]
    total_new_rounds = len(pending)
    passes = 0
    while pending:
        passes += 1
        with ThreadPoolExecutor(max_workers=cfg.workers) as executor:
            futures = [
                executor.submit(
                    _judge_call,
                    persona_index=idx,
                    persona_id=f"persona_{idx:05d}",
                    round_idx=r,
                    attempt=passes,
                    system_str=prompts[idx][0],
                    user_str=prompts[idx][1],
                    cfg=cfg,
                    client_factory=client_factory,
                    buffer=buffer,
                    buffer_lock=buffer_lock,
                )
                for (idx, r) in pending
            ]
            for future in as_completed(futures):
                idx, r, verdict, error = future.result()
                if verdict is not None:
                    results[(idx, r)] = verdict
                else:
                    logger.warning(
                        "combo %s persona_%05d round %d failed: %s",
                        combo_label, idx, r, error,
                    )

        failed_units = [unit for unit in pending if unit not in results]
        if not failed_units or passes >= _MAX_JUDGE_PASSES:
            break
        logger.info(
            "combo %s: retrying %d failed judge call(s) (pass %d/%d)",
            combo_label, len(failed_units), passes + 1, _MAX_JUDGE_PASSES,
        )
        pending = failed_units

    # Assemble per-persona caches + telemetry. A *fresh* persona with no successful
    # round is failed and left uncached (retryable, no telemetry). A *top-up* always
    # keeps its prior cache; it is rewritten (and its telemetry appended) only when it
    # gained >= 1 new round this pass.
    written = 0
    topped_up = 0
    failed_personas = 0
    successful_rounds = 0
    failed_rounds = 0
    for idx in to_judge:
        persona_id = f"persona_{idx:05d}"
        n_existing = len(existing[idx])
        new_verdicts = [results[(idx, r)] for r in range(n_existing, cfg.n_rounds) if (idx, r) in results]
        n_ok = len(new_verdicts)
        successful_rounds += n_ok
        failed_rounds += (cfg.n_rounds - n_existing) - n_ok
        is_topup = append_jsonl[idx]

        if n_ok == 0:
            if is_topup:
                logger.warning(
                    "combo %s %s: top-up added 0 of %d requested round(s); %d cached round(s) kept",
                    combo_label, persona_id, cfg.n_rounds - n_existing, n_existing,
                )
            else:
                failed_personas += 1
                logger.error(
                    "combo %s %s: all %d rounds failed after %d pass(es) — not cached",
                    combo_label, persona_id, cfg.n_rounds, passes,
                )
            continue

        persona_file = out_dir / f"{persona_id}.json"
        jsonl_file = out_dir / f"{persona_id}.jsonl"
        _write_persona_file(
            persona_file,
            persona_id=persona_id,
            combo_label=combo_label,
            cfg=cfg,
            persona=population[idx],
            analyzed_attrs=analyzed_attrs,
            existing_rounds=existing[idx],
            new_verdicts=new_verdicts,
        )
        _flush_telemetry(jsonl_file, buffer.get(persona_id, []), append=is_topup)
        if is_topup:
            topped_up += 1
        else:
            written += 1

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

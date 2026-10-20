"""stage2.py -- classify WHY each stage-1 S3 clash arose, from the persona's own raw answers.

Stage 1 (``runner``) judges a persona from its mapped categories alone. For every
persona that holds at least one S3 clash in a round, stage 2 shows a judge the raw
free-text answers the generating model wrote (``identity.json``), the mapped categories
stage 1 saw, and stage 1's explanation for each S3 clash of that round, and asks for one
class per clash (``raw_impossible`` / ``label_clash`` / ``ambiguous`` / ``mapping_error``
/ ``judge_error``, defined in ``config/analysis/persona_realism/stage2_prompt.md``).

One call per ``(persona, round with >= 1 S3 clash)``, through the same client path as
stage 1 (``runner._default_client_factory``: a fresh ``claude -p`` process per call,
whose metadata must report :data:`~population_synthetic.analysis.persona_realism.runner.JUDGE_CONTEXT_ISOLATION`).

Cache and resume
----------------
``<combo>/stage2/persona_XXXXX.json`` holds the persona's classified rounds and
``<combo>/stage2/persona_XXXXX.jsonl`` its call telemetry -- in a sub-directory, so the
stage-1 readers' ``persona_[0-9]*.json`` glob never sees them. Each cached round carries
the **fingerprint** of the stage-1 S3 clashes it classified (pair + explanation), so a
stage-2 verdict is tied to the exact stage-1 verdict it read. Resume classifies only the
rounds that are missing; a cached round whose fingerprint no longer matches the stage-1
cache, a cache written under another stage-2 prompt, judge model or isolation regime, or
for a persona whose raw answers changed, raises -- re-run with ``--force``, which
re-judges stage 1 and re-classifies stage 2 from scratch. A round whose every attempt
failed is not cached (retryable) and is reported as ``unclassified``.

The real reference has no free text: its S3 clashes get the class
``not_applicable_no_free_text`` and no call is made.

Layer boundary: like ``runner`` this module resolves no registry path and computes no
statistic; the caller hands it the combination directory and a raw-identity reader.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from population_synthetic.analysis.persona_realism.config import JudgeConfig
from population_synthetic.analysis.persona_realism.prompt import (
    PERSONA_PLACEHOLDER,
    load_prompt_template,
    render_persona_block,
)
from population_synthetic.analysis.persona_realism.reduce import LoadedPersona, round_clashes
from population_synthetic.analysis.utils.realism_stage2_csv import (
    NOT_APPLICABLE,
    STAGE2_CLASSES,
    UNCLASSIFIED,
    Stage2IssueRow,
)
from population_synthetic.generators.synthetic.llm_interaction_log import (
    LLMInteractionCollector,
    LLMInteractionEntry,
)

__all__ = [
    "STAGE2_SUBDIR",
    "Stage2Summary",
    "parse_stage2_response",
    "render_stage2_block",
    "run_combo_stage2",
    "s3_rounds",
    "stage2_issue_rows",
]

_LOGGER = logging.getLogger(__name__)

#: Sub-directory of a combination directory holding the stage-2 cache + telemetry.
STAGE2_SUBDIR = "stage2"
_MAX_PASSES = 3
_LOG_CATEGORY = "persona_realism"
_LOG_METHOD = "stage2"
_S3 = "S3"


@dataclass(frozen=True)
class Stage2Summary:
    """One combination's stage-2 outcome (counts of rounds, i.e. of stage-2 calls)."""

    combo_label: str
    personas_with_s3: int
    rounds_with_s3: int
    classified: int          # rounds classified by a call this run
    skipped: int             # rounds already cached
    failed: int              # rounds whose every attempt failed this run (left uncached)
    not_applicable: int      # rounds of a persona without free text (no call)


# --------------------------------------------------------------------------- #
# pure helpers                                                                 #
# --------------------------------------------------------------------------- #


def s3_rounds(persona: LoadedPersona) -> dict[int, list[tuple[tuple[str, str], str]]]:
    """``{round_index: [(sorted pair, stage-1 explanation), ...]}`` for rounds with an S3 clash.

    Uses the stage-1 within-round dedupe (:func:`reduce.round_clashes`), so the pairs are
    exactly the S3 rows of the per-clash contract.
    """
    out: dict[int, list[tuple[tuple[str, str], str]]] = {}
    for idx, verdict in enumerate(persona.rounds):
        s3 = [(key.pair, expl) for key, expl in round_clashes(verdict).items() if key.severity == _S3]
        if s3:
            out[idx] = s3
    return out


def _fingerprint(issues: Sequence[tuple[tuple[str, str], str]]) -> str:
    payload = json.dumps([[list(pair), expl] for pair, expl in issues], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_json(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def render_stage2_block(
    raw_identity: Mapping[str, Any],
    persona: LoadedPersona,
    analyzed_attrs: list[str],
    issues: Sequence[tuple[tuple[str, str], str]],
    *,
    rendering: dict[str, dict[str, str]],
) -> str:
    """The persona block stage 2 reads: raw answers, mapped categories, the round's S3 clashes.

    The mapped categories are rendered exactly as stage 1 saw them (same accessor, same
    judge-facing labels), from the stage-1 cache's own ``attributes``.
    """
    lines = ["RAW ANSWERS (the generating model's own free-text answers):"]
    lines += [f"  {k}: {v}" for k, v in raw_identity.items()]
    lines += ["", "MAPPED CATEGORIES (what stage 1 saw; age is shown as age_group):"]
    mapped = render_persona_block(persona.attributes, analyzed_attrs, rendering=rendering)
    lines += [f"  {line}" for line in mapped.splitlines()]
    lines += ["", "STAGE-1 S3 ISSUES:"]
    for n, (pair, explanation) in enumerate(issues, 1):
        lines += [f"  {n}. attributes: {pair[0]} x {pair[1]}", f"     stage-1 explanation: {explanation}"]
    return "\n".join(lines)


def _strip_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        body = text.splitlines()[1:]
        if body and body[-1].strip().startswith("```"):
            body = body[:-1]
        text = "\n".join(body).strip()
    return text


def parse_stage2_response(raw: str, expected_pairs: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    """Validate one stage-2 response; return one issue dict per expected pair, in that order.

    Raises ``ValueError`` on anything off-contract (the runner retries): not one JSON
    object, an issue list that does not name exactly the expected pairs, an unknown
    class, a ``mapping_error`` without a ``misread_attribute``, an empty reason. The
    model's own ``persona_class`` is kept as provenance only; the pipeline recomputes the
    persona class from the issue classes under the configured order.
    """
    text = _strip_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"stage-2 response is not valid JSON ({exc}); snippet {text[:200]!r}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("issues"), list):
        raise ValueError("stage-2 response must be an object with an 'issues' list")
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for i, obj in enumerate(data["issues"]):
        if not isinstance(obj, dict):
            raise ValueError(f"stage-2 issue[{i}] is not an object")
        attrs = obj.get("attributes")
        if not isinstance(attrs, list) or len(attrs) != 2 or not all(isinstance(a, str) for a in attrs):
            raise ValueError(f"stage-2 issue[{i}] must name exactly two attributes, got {attrs!r}")
        pair = tuple(sorted(attrs))
        if pair in by_pair:
            raise ValueError(f"stage-2 issue pair {pair} appears twice")
        cls = obj.get("class")
        if cls not in STAGE2_CLASSES:
            raise ValueError(f"stage-2 issue[{i}] has class {cls!r}, not one of {list(STAGE2_CLASSES)}")
        misread = obj.get("misread_attribute")
        if cls == "mapping_error" and (not isinstance(misread, str) or not misread):
            raise ValueError(f"stage-2 issue[{i}] is mapping_error but names no misread_attribute")
        reason = obj.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"stage-2 issue[{i}] has no reason")
        legal_fact = obj.get("legal_fact")
        quotes = obj.get("raw_quotes")
        if quotes is not None and not isinstance(quotes, dict):
            raise ValueError(f"stage-2 issue[{i}] raw_quotes must be an object")
        by_pair[pair] = {
            "pair": list(pair),
            "class": cls,
            "misread_attribute": misread if cls == "mapping_error" else None,
            "legal_fact": legal_fact if isinstance(legal_fact, str) and legal_fact else None,
            "reason": reason.strip(),
            "raw_quotes": {str(k): str(v) for k, v in (quotes or {}).items()},
        }
    expected = [tuple(sorted(p)) for p in expected_pairs]
    if set(by_pair) != set(expected):
        raise ValueError(
            f"stage-2 issues name {sorted(by_pair)}, expected exactly the stage-1 S3 pairs {sorted(expected)}"
        )
    return [by_pair[p] for p in expected]


# --------------------------------------------------------------------------- #
# cache IO                                                                     #
# --------------------------------------------------------------------------- #


def _stage1_identity(persona: LoadedPersona) -> dict[str, Any]:
    return {
        "prompt_template_sha256": persona.prompt_template_sha256,
        "persona_rendering_sha256": persona.persona_rendering_sha256,
    }


def _read_cache(
    path: Path,
    *,
    persona: LoadedPersona,
    stage2_sha: str,
    judge_model: str,
    isolation: str,
    raw_sha: str,
    rounds: Mapping[int, Sequence[tuple[tuple[str, str], str]]],
) -> dict[int, dict[str, Any]]:
    """Return the cached, still-valid rounds of one persona (fail-fast on any staleness)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read stage-2 cache {path}: {exc}") from exc
    expected = {
        "persona_id": persona.persona_id,
        "stage2_prompt_sha256": stage2_sha,
        "judge_model": judge_model,
        "context_isolation": isolation,
        "raw_identity_sha256": raw_sha,
        "stage1": _stage1_identity(persona),
    }
    stale = {k: payload.get(k) for k, v in expected.items() if payload.get(k) != v}
    if stale:
        raise ValueError(
            f"stage-2 cache {path} does not match the current run ({stale}); it classified another "
            "prompt, judge, persona or stage-1 verdict -- re-run with --force to re-judge."
        )
    cached: dict[int, dict[str, Any]] = {}
    for entry in payload.get("rounds", []):
        idx = int(entry["round_index"])
        if idx not in rounds or entry.get("stage1_fingerprint") != _fingerprint(rounds[idx]):
            raise ValueError(
                f"stage-2 cache {path} round {idx} classified a different stage-1 verdict than the "
                "cache now holds -- re-run with --force to re-judge."
            )
        cached[idx] = entry
    return cached


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_stage2_cache(combo_dir: Path, persona_id: str) -> dict[int, dict[str, Any]]:
    """The classified rounds cached for *persona_id* (``{}`` when there is no cache file)."""
    path = Path(combo_dir) / STAGE2_SUBDIR / f"{persona_id}.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(e["round_index"]): e for e in payload.get("rounds", [])}


def stage2_prompt_sha256(cfg: JudgeConfig) -> str:
    return hashlib.sha256(Path(cfg.stage2_prompt_template).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# fan-out                                                                      #
# --------------------------------------------------------------------------- #


def run_combo_stage2(
    present: Sequence[LoadedPersona],
    combo_label: str,
    analyzed_attrs: list[str],
    out_dir: str | Path,
    cfg: JudgeConfig,
    *,
    selected_ids: Sequence[str],
    raw_identity: Callable[[str], dict[str, Any]] | None,
    force: bool = False,
    client_factory: Callable[[], Any] | None = None,
    logger: logging.Logger | None = None,
) -> Stage2Summary:
    """Classify every not-yet-classified S3 round of *present* (the loaded stage-1 cache).

    *selected_ids* is the roster stage 1 judged
    (:func:`~population_synthetic.analysis.persona_realism.selection.selected_persona_ids`
    over the capped mapped population), and *present* must be the selected personas'
    loaded caches (``load_combo_verdicts(..., expected_ids=selected_ids)``): stage 2
    classifies the analysed sample only, never a leftover cache file of a persona an
    earlier cap selected. A persona of *present* outside the roster raises. *force*
    clears the stage-2 files of the selected personas only; a leftover's are kept.

    *raw_identity* maps a persona id to its raw ``identity.json`` dict; ``None`` marks a
    combination without free text (the real reference): nothing is called and every S3
    round counts as not applicable. *force* discards the stage-2 cache of every persona
    with an S3 round and classifies it again.
    """
    from population_synthetic.analysis.persona_realism.runner import (
        JUDGE_CONTEXT_ISOLATION,
        _default_client_factory,
    )

    logger = logger or _LOGGER
    out_dir = Path(out_dir)
    if not cfg.stage2_enabled:
        raise ValueError("run_combo_stage2 called while judge.yaml stage2.enabled is false")
    roster = set(selected_ids)
    outside = sorted(lp.persona_id for lp in present if lp.persona_id not in roster)
    if outside:
        raise ValueError(
            f"combo {combo_label!r}: stage 2 was handed {len(outside)} persona(s) outside the "
            f"selected roster ({outside[:5]}); load the stage-1 cache with the roster "
            "(load_combo_verdicts(..., expected_ids=selected_ids)), never by globbing the folder."
        )
    s3_by_persona = {lp.persona_id: (lp, s3_rounds(lp)) for lp in present}
    s3_by_persona = {pid: v for pid, v in s3_by_persona.items() if v[1]}
    n_rounds = sum(len(r) for _, r in s3_by_persona.values())
    if raw_identity is None:
        return Stage2Summary(combo_label, len(s3_by_persona), n_rounds, 0, 0, 0, n_rounds)

    system_str, user_template = load_prompt_template(cfg.stage2_prompt_template)
    stage2_sha = stage2_prompt_sha256(cfg)
    s2_dir = out_dir / STAGE2_SUBDIR

    jobs: list[tuple[LoadedPersona, dict[str, Any], dict[int, dict[str, Any]], list[int]]] = []
    skipped = 0
    for pid in sorted(s3_by_persona):
        lp, rounds = s3_by_persona[pid]
        raw = raw_identity(pid)
        raw_sha = _sha256_json(raw)
        path = s2_dir / f"{pid}.json"
        cached: dict[int, dict[str, Any]] = {}
        if path.is_file() and not force:
            cached = _read_cache(
                path, persona=lp, stage2_sha=stage2_sha, judge_model=cfg.judge_model,
                isolation=JUDGE_CONTEXT_ISOLATION, raw_sha=raw_sha, rounds=rounds,
            )
        todo = [idx for idx in sorted(rounds) if idx not in cached]
        skipped += len(rounds) - len(todo)
        if todo:
            jobs.append((lp, raw, cached, todo))

    if client_factory is None:
        def client_factory() -> Any:  # noqa: E306
            return _default_client_factory(cfg)

    local = threading.local()
    clients: list[Any] = []
    lock = threading.Lock()

    def _client() -> Any:
        client = getattr(local, "client", None)
        if client is None:
            client = client_factory()
            local.client = client
            with lock:
                clients.append(client)
        return client

    def _one(job: tuple[LoadedPersona, dict[str, Any], dict[int, dict[str, Any]], list[int]]) -> tuple[int, int]:
        lp, raw, cached, todo = job
        rounds = s3_by_persona[lp.persona_id][1]
        entries: list[LLMInteractionEntry] = []
        new: dict[int, dict[str, Any]] = {}
        failed = 0
        client = _client()
        for idx in todo:
            issues = rounds[idx]
            block = render_stage2_block(raw, lp, analyzed_attrs, issues, rendering=cfg.persona_rendering)
            user_str = user_template.replace(PERSONA_PLACEHOLDER, block)
            result = None
            for attempt in range(1, _MAX_PASSES + 1):
                text, error, parsed = None, None, None
                try:
                    text = client.generate_content(user_str, model=cfg.judge_model, system_instruction=system_str)
                    parsed = parse_stage2_response(text, [pair for pair, _ in issues])
                except Exception as exc:  # noqa: BLE001 -- a failed call is retryable
                    error = f"{type(exc).__name__}: {exc}"
                meta = getattr(client, "last_metadata", {}) or {}
                if parsed is not None and meta.get("context_isolation") != JUDGE_CONTEXT_ISOLATION:
                    raise RuntimeError(
                        f"{combo_label} {lp.persona_id} stage-2 round {idx}: client reported "
                        f"context_isolation={meta.get('context_isolation')!r}, not {JUDGE_CONTEXT_ISOLATION!r}"
                    )
                entries.append(
                    LLMInteractionEntry(
                        category=_LOG_CATEGORY, method=_LOG_METHOD, step=f"stage2_round_{idx}",
                        prompt=user_str, raw_response=text or "", parsed_value=None if parsed is None else
                        {"classes": [p["class"] for p in parsed]}, error=error, attempt=attempt,
                        persona_id=lp.persona_id, call_index=idx, provider=meta.get("provider"),
                        model=meta.get("model"), request_sent_at=meta.get("request_sent_at"),
                        response_received_at=meta.get("response_received_at"), elapsed_ms=meta.get("elapsed_ms"),
                        prompt_tokens=meta.get("prompt_tokens"), completion_tokens=meta.get("completion_tokens"),
                        total_tokens=meta.get("total_tokens"), cache_read_tokens=meta.get("cache_read_tokens"),
                        cache_creation_tokens=meta.get("cache_creation_tokens"),
                        error_category=meta.get("error_category"),
                    )
                )
                if parsed is not None:
                    try:
                        model_class = json.loads(_strip_fence(text)).get("persona_class")
                    except (json.JSONDecodeError, AttributeError):
                        model_class = None
                    result = {
                        "round_index": idx,
                        "stage1_fingerprint": _fingerprint(issues),
                        "issues": parsed,
                        "model_persona_class": model_class,
                    }
                    break
                logger.info("combo %s %s stage-2 round %d attempt %d failed: %s",
                            combo_label, lp.persona_id, idx, attempt, error)
            if result is None:
                failed += 1
                logger.warning("combo %s %s stage-2 round %d failed after %d attempts (unclassified)",
                               combo_label, lp.persona_id, idx, _MAX_PASSES)
            else:
                new[idx] = result
        if new:
            merged = {**cached, **new}
            _write_cache(
                s2_dir / f"{lp.persona_id}.json",
                {
                    "persona_id": lp.persona_id,
                    "combo": combo_label,
                    "judge_model": cfg.judge_model,
                    "context_isolation": JUDGE_CONTEXT_ISOLATION,
                    "stage2_prompt_sha256": stage2_sha,
                    "raw_identity_sha256": _sha256_json(raw),
                    "stage1": _stage1_identity(lp),
                    "rounds": [merged[i] for i in sorted(merged)],
                },
            )
        if entries:
            collector = LLMInteractionCollector(s2_dir / f"{lp.persona_id}.jsonl", append=bool(cached))
            try:
                for entry in entries:
                    collector.record(entry)
            finally:
                collector.close()
        return len(new), failed

    if force and s2_dir.is_dir():
        # --force re-judged stage 1 from scratch, so every stage-2 file of a selected
        # persona (including those that no longer hold an S3 clash) is stale: the cost
        # sum reads the selected personas' telemetry, and an old call left here would be
        # billed again. A leftover file of a persona outside the roster is not ours to
        # delete; every reader ignores it.
        for pid in sorted(roster):
            for stale in (s2_dir / f"{pid}.json", s2_dir / f"{pid}.jsonl"):
                if stale.is_file():
                    stale.unlink()

    classified = failed = 0
    try:
        with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
            for fut in as_completed([pool.submit(_one, job) for job in jobs]):
                ok, bad = fut.result()
                classified += ok
                failed += bad
    finally:
        for client in clients:
            if hasattr(client, "close"):
                try:
                    client.close()
                except Exception:  # noqa: BLE001 -- teardown must not mask the outcome
                    pass
    summary = Stage2Summary(combo_label, len(s3_by_persona), n_rounds, classified, skipped, failed, 0)
    logger.info("combo %s stage 2: %s", combo_label, summary)
    return summary


# --------------------------------------------------------------------------- #
# artifact rows                                                                #
# --------------------------------------------------------------------------- #


def stage2_issue_rows(
    present: Sequence[LoadedPersona],
    combo_dir: str | Path,
    *,
    raw_identity: Callable[[str], dict[str, Any]] | None,
    enabled: bool,
) -> list[Stage2IssueRow]:
    """One :class:`Stage2IssueRow` per S3 clash of *present* (the per-clash S3 grain).

    A classified round contributes its cached classes; a round without a cached
    classification is ``unclassified``; a combination without free text
    (*raw_identity* ``None``) is ``not_applicable_no_free_text`` throughout. A cached
    round whose fingerprint no longer matches the stage-1 verdict raises.
    """
    combo_dir = Path(combo_dir)
    rows: list[Stage2IssueRow] = []
    for lp in sorted(present, key=lambda p: p.persona_id):
        rounds = s3_rounds(lp)
        if not rounds:
            continue
        raw = raw_identity(lp.persona_id) if raw_identity is not None else {}
        cached = load_stage2_cache(combo_dir, lp.persona_id) if (enabled and raw_identity is not None) else {}
        for idx, issues in rounds.items():
            entry = cached.get(idx)
            if entry is not None and entry.get("stage1_fingerprint") != _fingerprint(issues):
                raise ValueError(
                    f"{combo_dir}: stage-2 cache of {lp.persona_id} round {idx} classified a different "
                    "stage-1 verdict -- re-run with --force."
                )
            answers = {tuple(i["pair"]): i for i in entry["issues"]} if entry else {}
            for pair, _expl in issues:
                ans = answers.get(tuple(pair))
                if raw_identity is None:
                    cls = NOT_APPLICABLE
                elif ans is None:
                    cls = UNCLASSIFIED
                else:
                    cls = ans["class"]
                rows.append(
                    Stage2IssueRow(
                        persona_id=lp.persona_id,
                        round_index=idx,
                        attr_a=pair[0],
                        attr_b=pair[1],
                        stage2_class=cls,
                        misread_attribute=(ans or {}).get("misread_attribute") or "",
                        legal_fact=(ans or {}).get("legal_fact") or "",
                        reason=(ans or {}).get("reason") or "",
                        raw_a="" if raw.get(pair[0]) is None else str(raw.get(pair[0])),
                        raw_b="" if raw.get(pair[1]) is None else str(raw.get(pair[1])),
                        raw_quotes=json.dumps((ans or {}).get("raw_quotes") or {}, ensure_ascii=False)
                        if ans else "",
                    )
                )
    return rows

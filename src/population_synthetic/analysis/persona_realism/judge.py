"""judge.py -- one judge call -> one parsed, validated ``RoundVerdict``.

This module is the **single normalization/validation boundary** for the
persona-realism process (pipe-and-filter error boundary, 02-architecture guide
sect. 8). Everything downstream (``reduce``, ``stats``, sinks) consumes the
frozen DTOs defined here and never re-parses raw judge text. Consequently, any
malformed or contract-violating judge output must RAISE here with context -- it
must not be silently ``.get``-defaulted, and a call that failed must never be
collapsed into a "possible" verdict by this layer (the runner records the
failure distinctly instead).

Must NOT know about: aggregation, plotting, paths, config resolution. The only
inputs are the two prompt strings, an ``LLMClient`` (duck-typed:
``generate_content(prompt, model=..., system_instruction=...)``), and the raw
response string. ``judge_model`` is passed in by the caller from config.

Contract enforced by :func:`parse_round_verdict` (mirrors the JSON schema in
``config/analysis/persona_realism/judge_prompt.md``):

* the response is a single JSON object (a leading/trailing ```` ``` ```` fence is
  tolerated, nothing else);
* ``can_exist`` is present and a real ``bool``;
* ``typicality`` is an integer in ``[0, 10]`` when ``can_exist`` is true, and
  ``null`` (and only ``null``) when ``can_exist`` is false;
* ``issues`` is a list of well-formed issue objects -- each names exactly two
  string attributes and carries a severity in ``{S1, S2, S3}``;
* when ``can_exist`` is false at least one issue has severity ``S3`` (the
  impossibility driver the schema mandates).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

__all__ = ["Issue", "RoundVerdict", "parse_round_verdict", "judge_persona"]

# Severity labels are a STRUCTURAL constant of the judge protocol (defined by the
# prompt schema in judge_prompt.md), not a tunable threshold -- allowed in code.
_VALID_SEVERITIES: frozenset[str] = frozenset({"S1", "S2", "S3"})

# Typicality is an ordinal integer on this closed range (prompt-schema constant).
_TYPICALITY_MIN = 0
_TYPICALITY_MAX = 10


@dataclass(frozen=True)
class Issue:
    """One attribute pair the judge flagged as in tension.

    ``attributes`` names exactly two axes from the persona; ``severity`` is one
    of ``S1``/``S2``/``S3`` (S3 is the hard-contradiction / impossibility level).
    """

    attributes: tuple[str, str]
    severity: str
    explanation: str


@dataclass(frozen=True)
class RoundVerdict:
    """One judge call's canonical, validated verdict for one persona.

    ``typicality`` is ``None`` iff ``can_exist`` is ``False`` (enforced at parse
    time). ``issues`` is an immutable tuple (possibly empty). ``reasoning`` is
    free-text provenance, not load-bearing for any statistic.
    """

    can_exist: bool
    typicality: int | None
    issues: tuple[Issue, ...]
    reasoning: str = ""


def _strip_code_fence(raw: str) -> str:
    """Remove a single surrounding ```` ```json ... ``` ```` fence if present.

    The prompt asks for no fence; tolerating one is benign normalization, not
    leniency toward malformed JSON (which still raises downstream).
    """
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    lines = lines[1:]  # drop the opening ``` / ```json line
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_issue(obj: Any, index: int) -> Issue:
    """Validate one raw issue object into an :class:`Issue` (fail-loud)."""
    if not isinstance(obj, dict):
        raise ValueError(f"issue[{index}] must be a JSON object, got {type(obj).__name__}")
    if "attributes" not in obj:
        raise ValueError(f"issue[{index}] is missing required key 'attributes'")
    attrs = obj["attributes"]
    if not isinstance(attrs, (list, tuple)) or len(attrs) != 2:
        raise ValueError(
            f"issue[{index}] 'attributes' must name exactly two attributes, got {attrs!r}"
        )
    if not all(isinstance(a, str) for a in attrs):
        raise ValueError(f"issue[{index}] 'attributes' entries must be strings, got {attrs!r}")
    severity = obj.get("severity")
    if severity not in _VALID_SEVERITIES:
        raise ValueError(
            f"issue[{index}] has invalid severity {severity!r}; "
            f"expected one of {sorted(_VALID_SEVERITIES)}"
        )
    explanation = obj.get("explanation", "")
    explanation = "" if explanation is None else str(explanation)
    return Issue(attributes=(attrs[0], attrs[1]), severity=severity, explanation=explanation)


def parse_round_verdict(raw: str) -> RoundVerdict:
    """Parse and validate one raw judge response into a :class:`RoundVerdict`.

    This is the single normalization point: it raises ``ValueError`` on any
    malformed or contract-violating response (with a context snippet), rather
    than substituting defaults. See the module docstring for the full contract.
    """
    text = _strip_code_fence(raw)
    if not text:
        raise ValueError("judge returned an empty response")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"judge response is not valid JSON ({exc}); raw snippet: {text[:200]!r}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(f"judge response must be a JSON object, got {type(data).__name__}")

    if "can_exist" not in data:
        raise ValueError("judge response is missing required key 'can_exist'")
    can_exist = data["can_exist"]
    if not isinstance(can_exist, bool):
        raise ValueError(
            f"'can_exist' must be a boolean, got {type(can_exist).__name__}: {can_exist!r}"
        )

    if "typicality" not in data:
        raise ValueError("judge response is missing required key 'typicality'")
    typicality = data["typicality"]
    if can_exist:
        # bool is an int subclass -- reject it explicitly so `true`/`false` are
        # never accepted as a typicality score.
        if isinstance(typicality, bool) or not isinstance(typicality, int):
            raise ValueError(
                f"'typicality' must be an integer {_TYPICALITY_MIN}-{_TYPICALITY_MAX} "
                f"when can_exist is true, got {typicality!r}"
            )
        if not (_TYPICALITY_MIN <= typicality <= _TYPICALITY_MAX):
            raise ValueError(
                f"'typicality' out of range {_TYPICALITY_MIN}-{_TYPICALITY_MAX} "
                f"when can_exist is true: {typicality}"
            )
    else:
        if typicality is not None:
            raise ValueError(
                f"'typicality' must be null when can_exist is false, got {typicality!r}"
            )

    if "issues" not in data:
        raise ValueError("judge response is missing required key 'issues'")
    raw_issues = data["issues"]
    if not isinstance(raw_issues, list):
        raise ValueError(f"'issues' must be a list, got {type(raw_issues).__name__}")
    issues = tuple(_parse_issue(obj, i) for i, obj in enumerate(raw_issues))

    if not can_exist and not any(issue.severity == "S3" for issue in issues):
        raise ValueError(
            "'can_exist' is false but no issue has severity 'S3' "
            "(the schema requires an S3 hard contradiction to drive impossibility)"
        )

    reasoning = data.get("reasoning", "")
    reasoning = "" if reasoning is None else str(reasoning)

    return RoundVerdict(
        can_exist=can_exist,
        typicality=typicality,
        issues=issues,
        reasoning=reasoning,
    )


def judge_persona(client: Any, system_str: str, user_str: str, judge_model: str) -> RoundVerdict:
    """Issue one judge call and return the parsed verdict.

    Convenience wrapper over ``client.generate_content`` + :func:`parse_round_verdict`.
    Raises whatever the client raises on a call failure, and ``ValueError`` on a
    contract-violating response. The runner inlines this two-step sequence when it
    also needs the raw response for cost telemetry.
    """
    raw = client.generate_content(user_str, model=judge_model, system_instruction=system_str)
    return parse_round_verdict(raw)

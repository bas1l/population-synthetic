"""prompt.py -- render one persona tuple + system prompt from the config template.

Pure rendering layer (pipe-and-filter first filter). Given a persona dict, the
analyzed-axis list (already resolved by the caller from
``scheme_attributes(country)`` -- the deprecated ``birth_location`` axis is
excluded there, matching ``ComparisonScheme.attributes``), and the parsed prompt
template, it produces ``(system_str, user_str)`` ready to hand to the judge.

Must NOT know about: matplotlib, the CLI, statistics, config/registry
resolution. The one disk touch is :func:`load_prompt_template`, which reads and
parses the template file the caller located from config -- a thin, pure parse
assigned to this layer by the plan (task 2.1).

Template contract (see ``config/analysis/persona_realism/judge_prompt.md``):

* the file is split by two sentinel lines, each appearing alone on its own line:
  ``<!-- SYSTEM -->`` then ``<!-- USER -->`` (matched by exact line equality, so
  the prose references to the sentinels inside the leading header comment are not
  mistaken for the real delimiters);
* the text between them is the system prompt; the text after ``<!-- USER -->`` is
  the user template, which contains exactly one ``{persona_block}`` placeholder;
* substitution is a literal string replace of ``{persona_block}`` only -- never
  ``str.format`` (the system section contains a literal ``{...}`` JSON schema
  that must survive verbatim).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = [
    "SYSTEM_SENTINEL",
    "USER_SENTINEL",
    "PERSONA_PLACEHOLDER",
    "parse_prompt_template",
    "load_prompt_template",
    "render_persona_block",
    "build_prompts",
]

SYSTEM_SENTINEL = "<!-- SYSTEM -->"
USER_SENTINEL = "<!-- USER -->"
PERSONA_PLACEHOLDER = "{persona_block}"


def parse_prompt_template(text: str) -> tuple[str, str]:
    """Split raw template text into ``(system_str, user_template)`` (fail-loud).

    Sentinels are matched by exact stripped-line equality so that the mentions of
    ``<!-- SYSTEM -->`` / ``<!-- USER -->`` inside the file's leading HTML header
    comment (which carry surrounding backticks and prose) are not treated as
    delimiters. Raises ``ValueError`` on a missing/duplicated sentinel, an empty
    system section, or a user section without exactly one ``{persona_block}``.
    """
    lines = text.splitlines()
    sys_idx: int | None = None
    user_idx: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == SYSTEM_SENTINEL:
            if sys_idx is not None:
                raise ValueError(f"prompt template has multiple {SYSTEM_SENTINEL!r} sentinel lines")
            sys_idx = i
        elif stripped == USER_SENTINEL:
            if user_idx is not None:
                raise ValueError(f"prompt template has multiple {USER_SENTINEL!r} sentinel lines")
            user_idx = i

    if sys_idx is None:
        raise ValueError(f"prompt template is missing the {SYSTEM_SENTINEL!r} sentinel line")
    if user_idx is None:
        raise ValueError(f"prompt template is missing the {USER_SENTINEL!r} sentinel line")
    if user_idx < sys_idx:
        raise ValueError(
            f"prompt template sentinel order is wrong: {USER_SENTINEL!r} precedes {SYSTEM_SENTINEL!r}"
        )

    system_str = "\n".join(lines[sys_idx + 1 : user_idx]).strip()
    user_template = "\n".join(lines[user_idx + 1 :]).strip()

    if not system_str:
        raise ValueError("prompt template SYSTEM section is empty")
    placeholder_count = user_template.count(PERSONA_PLACEHOLDER)
    if placeholder_count != 1:
        raise ValueError(
            f"prompt template USER section must contain exactly one {PERSONA_PLACEHOLDER!r} "
            f"placeholder, found {placeholder_count}"
        )

    return system_str, user_template


def load_prompt_template(path: str | Path) -> tuple[str, str]:
    """Read the template file at *path* and return ``(system_str, user_template)``."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"prompt template not found: {path}")
    return parse_prompt_template(path.read_text(encoding="utf-8"))


def render_persona_block(persona: dict[str, Any], analyzed_attrs: list[str]) -> str:
    """Render the analyzed tuple as raw ``attribute: value`` lines (one per line).

    Iterates *analyzed_attrs* in order (the config-sourced comparison axis, which
    already excludes the deprecated axis). Each value is resolved through the
    canonical accessor :func:`attr_value` so that a real mapped record -- which
    stores the raw integer ``age`` rather than a pre-binned ``age_group`` -- has its
    ``age_group`` derived on demand from ``age`` (matching how the fidelity pipeline
    reads the same populations). Raises ``KeyError`` naming the axis when the value
    resolves to ``None`` (axis genuinely absent, or ``age`` missing/out-of-range) --
    the caller adds persona/combo context (fail-fast per the plan's edge-case
    contract).
    """
    # Lazy import: this pure rendering layer must not pull the statistics stack
    # (numpy/scipy, via evaluator) at module import time. ``attr_value`` is the
    # single source of truth for age_group derivation.
    from population_synthetic.analysis.fidelity.evaluator import attr_value

    lines: list[str] = []
    for attr in analyzed_attrs:
        value = attr_value(persona, attr)
        if value is None:
            raise KeyError(
                f"persona is missing analyzed axis {attr!r} "
                f"(present axes: {sorted(persona)})"
            )
        lines.append(f"{attr}: {value}")
    return "\n".join(lines)


def build_prompts(
    persona: dict[str, Any],
    analyzed_attrs: list[str],
    system_str: str,
    user_template: str,
) -> tuple[str, str]:
    """Return ``(system_str, user_str)`` for one persona.

    The system prompt is passed through verbatim; the user string is the template
    with its single ``{persona_block}`` literally replaced by the rendered tuple.
    Pure -- no side effects.
    """
    block = render_persona_block(persona, analyzed_attrs)
    user_str = user_template.replace(PERSONA_PLACEHOLDER, block)
    return system_str, user_str

"""Generic, label-free text helpers for the synthetic mapper.

Separator normalisation and UTF-8 double-encoding repair — the string primitives
the config-driven flat-path engine in ``base.py`` relies on. They carry no
demographic labels or mappings; all label -> schema-label translation lives in the
country mapping JSON files under ``config/mapping/{scb,istat}/``.
"""

from __future__ import annotations

import re

_SEP_RE = re.compile(r"[\s_\-]+")


def _sep_norm(s: str) -> str:
    """Collapse underscores, hyphens, and whitespace runs to single spaces.

    Applied symmetrically to mapping keys and lookup inputs so snake_case /
    kebab-case LLM output (e.g. ``two_biological_parents``, ``upper-middle``)
    matches the space-form keys curated in category_mappings.json.
    """
    return _SEP_RE.sub(" ", s).strip()


_UTF8_DOUBLE_ENCODING_REPAIRS: dict[str, str] = {
    "√§": "ä", "√∂": "ö", "√•": "å",
    "√Ñ": "Ä", "√ñ": "Ö", "√Ö": "Å",
    "Ã¤": "ä", "Ã¶": "ö", "Ã¥": "å",
    "Ã": "Ä", "Ã": "Ö", "Ã": "Å",
}


def _repair_utf8_double_encoding(text: str) -> str:
    for bad, good in _UTF8_DOUBLE_ENCODING_REPAIRS.items():
        text = text.replace(bad, good)
    return text

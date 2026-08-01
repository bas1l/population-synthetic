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


#: Double-encoded UTF-8 repairs, applied in declaration order by
#: :func:`_repair_utf8_double_encoding`. Every key is a distinct two-character
#: sequence and no key is a prefix of another, so the pass is order-independent;
#: the longest-match-first layout (two-character mojibake pairs only, never a bare
#: lead byte) is kept deliberately -- a single-character ``"Ã"`` entry would
#: strip the trailing byte off every other pair before it could match.
#: Two intermediate decodings are covered for the uppercase letters: latin-1
#: (raw C1 controls U+0084/U+0096/U+0085) and cp1252 (U+201E/U+2013/U+2026).
_UTF8_DOUBLE_ENCODING_REPAIRS: dict[str, str] = {
    "√§": "ä", "√∂": "ö", "√•": "å",
    "√Ñ": "Ä", "√ñ": "Ö", "√Ö": "Å",
    "Ã¤": "ä", "Ã¶": "ö", "Ã¥": "å",
    "Ã": "Ä", "Ã": "Ö", "Ã": "Å",
    "Ã„": "Ä", "Ã–": "Ö", "Ã…": "Å",
}


def _repair_utf8_double_encoding(text: str) -> str:
    for bad, good in _UTF8_DOUBLE_ENCODING_REPAIRS.items():
        text = text.replace(bad, good)
    return text


#: Typographic punctuation LLMs emit interchangeably with its ASCII form, folded to
#: ASCII so a matcher token written with a plain hyphen/apostrophe still matches.
#: Without this, ``IT‑tjänster`` (U+2011) and ``IT-tjänster`` (U+002D) are distinct
#: strings and only the latter resolves. Dashes fold to ``-`` rather than to a space
#: because :func:`mapping_engine.normalize` deliberately preserves hyphens (the
#: ``upper-secondary`` vs ``upper secondary`` distinction).
#:
#: **Order matters at the call site**: this must run *after*
#: :func:`_repair_utf8_double_encoding`, whose cp1252 keys ("Ã–", "Ã…") contain
#: U+2013 and U+2026 -- folding first would rewrite those keys out of existence.
_UNICODE_PUNCTUATION_FOLDS: dict[str, str] = {
    "‐": "-",  # hyphen
    "‑": "-",  # non-breaking hyphen
    "‒": "-",  # figure dash
    "–": "-",  # en dash
    "—": "-",  # em dash
    "―": "-",  # horizontal bar
    "−": "-",  # minus sign
    "‘": "'",  # left single quote
    "’": "'",  # right single quote / typographic apostrophe
    "“": '"',  # left double quote
    "”": '"',  # right double quote
    " ": " ",  # no-break space
    " ": " ",  # narrow no-break space
}


def _fold_unicode_punctuation(text: str) -> str:
    """Fold typographic dashes, quotes, and no-break spaces to their ASCII forms."""
    for fancy, plain in _UNICODE_PUNCTUATION_FOLDS.items():
        text = text.replace(fancy, plain)
    return text

#!/usr/bin/env python3
"""Build browsable HTML twins of the comparison-metrics deep-dive notes.

The deep-dive notes under ``docs/architecture/comparison-metrics/*.md`` are the
source of truth; the HTML report (``comparison-metrics-report.html``) links to
``*.html`` siblings so the notes are browsable in a plain browser. This script
regenerates those ``*.html`` files from the Markdown, sharing ``notes.css``.

Run after editing any note::

    python scripts/dev/build_metric_note_html.py

No third-party dependencies -- it implements the small Markdown subset the notes
use (headings, paragraphs, fenced code, GFM pipe tables, blockquotes, lists,
inline code/bold/italic/links). Intra-repo ``.md`` links are rewritten to their
``.html`` twins (and the guide link to the HTML report) so navigation stays
inside the browsable set.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

NOTES_DIR = Path(__file__).resolve().parents[2] / "docs" / "architecture" / "comparison-metrics"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — comparison metrics</title>
<link rel="stylesheet" href="notes.css">
</head>
<body>
<main class="note-wrap">
<p class="breadcrumb"><a href="../comparison-metrics-report.html">&#9666; Comparison metrics — field guide</a></p>
{body}
</main>
</body>
</html>
"""

# Block-level tags whose raw HTML (e.g. an inline <figure> holding an <svg>) is
# passed through verbatim, so notes can embed hand-authored visuals. The block
# must open at column 0 and close with the matching </tag> alone on its own line.
BLOCK_HTML_TAGS = {"figure", "div", "svg", "table", "aside", "section", "details"}

_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITAL = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def _rewrite_link(url: str) -> str:
    """Point intra-repo Markdown links at their browsable HTML twins."""
    if url.startswith(("http://", "https://", "#", "mailto:")):
        return url
    if url == "../comparison-metrics.md":
        return "../comparison-metrics-report.html"
    if url.endswith(".md"):
        return url[:-3] + ".html"
    return url


def render_inline(text: str) -> str:
    text = html.escape(text, quote=False)
    spans: list[str] = []

    def _stash(m: re.Match) -> str:
        spans.append(f"<code>{m.group(1)}</code>")
        return f"\x00{len(spans) - 1}\x00"

    text = _CODE.sub(_stash, text)
    text = _LINK.sub(lambda m: f'<a href="{_rewrite_link(m.group(2))}">{m.group(1)}</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITAL.sub(r"<em>\1</em>", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)
    return text


def _is_table_sep(line: str) -> bool:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def _align(cell: str) -> str:
    cell = cell.strip()
    if cell.startswith(":") and cell.endswith(":"):
        return " class=\"center\""
    if cell.endswith(":"):
        return " class=\"right\""
    return ""


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def convert(md: str) -> tuple[str, str]:
    lines = md.split("\n")
    out: list[str] = []
    title = "Note"
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Fenced code block
        if stripped.startswith("```"):
            i += 1
            code: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # closing fence
            body = html.escape("\n".join(code), quote=False)
            out.append(f"<pre><code>{body}</code></pre>")
            continue

        # Raw HTML block (verbatim passthrough, e.g. an embedded <figure>/<svg>)
        html_open = re.match(r"<([a-zA-Z][\w-]*)", stripped)
        if html_open and html_open.group(1).lower() in BLOCK_HTML_TAGS:
            tag = html_open.group(1)
            close = f"</{tag}>"
            buf = [line]
            if close in line:  # single-line block
                out.append(line)
                i += 1
                continue
            i += 1
            while i < n and lines[i].strip() != close:
                buf.append(lines[i])
                i += 1
            if i < n:  # the closing line
                buf.append(lines[i])
                i += 1
            out.append("\n".join(buf))
            continue

        # Heading
        m = re.match(r"(#{1,6})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            content = render_inline(m.group(2).strip())
            if level == 1 and title == "Note":
                title = re.sub(r"<[^>]+>", "", content)
            tag = f"h{min(level, 3)}"
            out.append(f"<{tag}>{content}</{tag}>")
            i += 1
            continue

        # Horizontal rule
        if re.fullmatch(r"-{3,}", stripped):
            out.append("<hr>")
            i += 1
            continue

        # Table (header row + separator row)
        if "|" in line and i + 1 < n and _is_table_sep(lines[i + 1]):
            headers = _split_row(line)
            aligns = [_align(c) for c in _split_row(lines[i + 1])]
            i += 2
            rows: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            thead = "".join(
                f"<th{aligns[j] if j < len(aligns) else ''}>{render_inline(h)}</th>"
                for j, h in enumerate(headers)
            )
            tbody = ""
            for row in rows:
                cells = "".join(
                    f"<td{aligns[j] if j < len(aligns) else ''}>{render_inline(c)}</td>"
                    for j, c in enumerate(row)
                )
                tbody += f"<tr>{cells}</tr>"
            out.append(
                f'<div class="table-wrap"><table><thead><tr>{thead}</tr></thead>'
                f"<tbody>{tbody}</tbody></table></div>"
            )
            continue

        # Blockquote
        if stripped.startswith(">"):
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = render_inline(" ".join(q.strip() for q in quote if q.strip()))
            out.append(f"<blockquote><p>{inner}</p></blockquote>")
            continue

        # Lists (unordered / ordered), one level
        if re.match(r"[-*]\s+", stripped) or re.match(r"\d+\.\s+", stripped):
            ordered = bool(re.match(r"\d+\.\s+", stripped))
            tag = "ol" if ordered else "ul"
            items: list[str] = []
            while i < n and lines[i].strip():
                lm = re.match(r"\s*(?:[-*]|\d+\.)\s+(.*)", lines[i])
                if lm:
                    items.append(lm.group(1))
                    i += 1
                elif lines[i].startswith((" ", "\t")) and items:
                    items[-1] += " " + lines[i].strip()  # continuation line
                    i += 1
                else:
                    break
            body = "".join(f"<li>{render_inline(it)}</li>" for it in items)
            out.append(f"<{tag}>{body}</{tag}>")
            continue

        # Paragraph
        para: list[str] = []
        while i < n and lines[i].strip() and not lines[i].strip().startswith(("#", ">", "```")):
            if re.match(r"[-*]\s+", lines[i].strip()) or re.match(r"\d+\.\s+", lines[i].strip()):
                break
            if "|" in lines[i] and i + 1 < n and _is_table_sep(lines[i + 1]):
                break
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{render_inline(' '.join(para))}</p>")

    return title, "\n".join(out)


def main() -> None:
    md_files = sorted(NOTES_DIR.glob("*.md"))
    if not md_files:
        raise SystemExit(f"No .md notes found in {NOTES_DIR}")
    for md_path in md_files:
        title, body = convert(md_path.read_text(encoding="utf-8"))
        html_path = md_path.with_suffix(".html")
        html_path.write_text(PAGE.format(title=html.escape(title), body=body), encoding="utf-8")
        print(f"  {md_path.name}  ->  {html_path.name}")
    print(f"Built {len(md_files)} HTML note(s) in {NOTES_DIR}")


if __name__ == "__main__":
    main()

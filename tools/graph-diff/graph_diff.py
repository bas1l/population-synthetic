#!/usr/bin/env python3
"""graph_diff — CLI entrypoint for the standalone graph-diff tool.

Responsibility
--------------
Parse CLI arguments and wire the three decoupled stages — checkout, extract,
diff, render — for two git refs, owning the output directory and the on-stdout
summary. This module *orchestrates only*; it holds no graph logic of its own.

Must NOT know about
-------------------
- any host-project package, package names, or country/domain specifics,
- grimp internals or the shape of the import graph,
- how the delta is computed or how artifacts are serialised.

Everything repository-specific arrives as a CLI argument. The tool is
self-contained and repo-agnostic: point ``--package-path`` / ``--base-ref`` /
``--head-ref`` at any Python package in any git repo and it runs unchanged.

Pipeline
--------
For each of the two refs, a throwaway detached ``git worktree`` is created (never
touching the caller's working tree, index, or branch), the target package's
import graph is extracted from it, and the worktree is torn down — guaranteed by
the context manager, on both the success and failure paths. The two graphs are
set-differenced into a ``Delta`` which is rendered to the requested artifacts.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Make the sibling ``graphdiff`` package importable when this script is run
# directly (``python tools/graph-diff/graph_diff.py ...``) from any cwd.
_TOOL_ROOT = Path(__file__).resolve().parent
if str(_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOL_ROOT))

from graphdiff.diff import compute_delta  # noqa: E402 — after sys.path bootstrap
from graphdiff.extract import extract_graph  # noqa: E402
from graphdiff.render import ALL_FORMATS, render_delta  # noqa: E402
from graphdiff.worktree import worktree  # noqa: E402

_DEFAULT_OUTPUT = "graph-diff-out"


def _parse_csv(value: str | None) -> list[str]:
    """Split a comma-separated argument into a list of trimmed, non-empty items."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _current_branch(repo_root: str | None) -> str:
    """Return the current branch name (``git rev-parse --abbrev-ref HEAD``).

    Raises loudly (via the exit path in :func:`main`) if git cannot report it —
    e.g. a detached HEAD returns ``HEAD``, which is still a resolvable ref.
    """
    cmd = ["git"]
    if repo_root:
        cmd += ["-C", str(repo_root)]
    cmd += ["rev-parse", "--abbrev-ref", "HEAD"]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Could not determine the current branch for the default --head-ref "
            f"(git rev-parse --abbrev-ref HEAD failed): {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse CLI matching the documented contract."""
    parser = argparse.ArgumentParser(
        prog="graph_diff.py",
        description=(
            "Render the change in a Python package's import/dependency graph "
            "between two git refs (added edges green, removed red, unchanged "
            "grey), plus JSON and Markdown summaries. Standalone and "
            "repo-agnostic — everything is a CLI argument."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--package-path",
        required=True,
        help="Target package to analyse: a filesystem path (e.g. src/mypkg) or "
        "a dotted package name (e.g. mypkg.sub), resolved inside each ref's tree.",
    )
    parser.add_argument(
        "--base-ref",
        required=True,
        help="Base git ref (branch, tag, or SHA) — the 'before' side of the diff.",
    )
    parser.add_argument(
        "--head-ref",
        default=None,
        help="Head git ref — the 'after' side. Defaults to the current branch.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository to operate on. Defaults to the git top-level of the cwd.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Collapse modules to their N-th-level package prefix (legibility for "
        "large graphs). Omit for full module granularity.",
    )
    parser.add_argument(
        "--output",
        default=_DEFAULT_OUTPUT,
        help="Directory to write artifacts into (created if absent).",
    )
    parser.add_argument(
        "--format",
        default=",".join(ALL_FORMATS),
        help="Comma-separated subset of {svg,png,dot,json,md}. Defaults to all.",
    )
    parser.add_argument(
        "--exclude",
        default=None,
        help="Comma-separated module-name substrings to drop (e.g. 'tests,__pycache__').",
    )
    return parser


def _extract_at_ref(
    ref: str,
    repo_root: str | None,
    package_path: str,
    depth: int | None,
    exclude: list[str],
):
    """Open a throwaway worktree at ``ref`` and extract the package graph from it.

    The worktree is created and torn down within this call; nothing about it
    escapes. Returns the canonical :class:`~graphdiff.diff.Graph`.
    """
    with worktree(ref, repo_root=repo_root) as tree_root:
        return extract_graph(tree_root, package_path, depth=depth, exclude=exclude)


def _print_summary(
    delta,
    base_ref: str,
    head_ref: str,
    out_dir: Path,
    written: dict[str, Path],
) -> None:
    """Print a concise, human-readable run summary to stdout."""
    print(f"graph-diff: {base_ref} -> {head_ref}")
    print(
        f"  nodes:  +{delta.added_node_count} added  "
        f"-{delta.removed_node_count} removed  "
        f"({delta.unchanged_node_count} unchanged)"
    )
    print(
        f"  edges:  +{delta.added_edge_count} added  "
        f"-{delta.removed_edge_count} removed  "
        f"({delta.unchanged_edge_count} unchanged)"
    )
    if delta.is_empty:
        print("  (no structural change — base and head graphs are identical)")
    print(f"  output: {out_dir.resolve()}")
    for fmt in sorted(written):
        print(f"    {fmt:4s} -> {written[fmt].name}")


def main(argv: list[str] | None = None) -> int:
    """Run the graph-diff pipeline. Returns 0 on success, nonzero on error."""
    args = build_parser().parse_args(argv)

    formats = _parse_csv(args.format)
    exclude = _parse_csv(args.exclude)
    out_dir = Path(args.output)

    try:
        head_ref = args.head_ref or _current_branch(args.repo_root)
        base_graph = _extract_at_ref(
            args.base_ref, args.repo_root, args.package_path, args.depth, exclude
        )
        head_graph = _extract_at_ref(
            head_ref, args.repo_root, args.package_path, args.depth, exclude
        )
        delta = compute_delta(base_graph, head_graph)
        title = f"{args.base_ref} -> {head_ref}"
        written = render_delta(delta, out_dir, title, formats)
    except Exception as exc:  # noqa: BLE001 — CLI boundary: report cleanly, exit nonzero
        print(f"graph-diff error: {exc}", file=sys.stderr)
        return 1

    _print_summary(delta, args.base_ref, head_ref, out_dir, written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""extract — build the canonical import graph of a package under a tree root.

Responsibility
--------------
Given the root of a checked-out source tree and a target package (as a
filesystem path *or* a dotted name), run ``grimp`` to produce the exact static
import graph, apply the optional ``depth`` collapse and ``exclude`` filter, and
return the canonical :class:`~graphdiff.diff.Graph` — a ``(nodes, edges)`` pair
consumed unchanged by the diff stage.

Must NOT know about
-------------------
- git (refs, worktrees, checkouts) — it receives an already-materialised tree,
- rendering or artifact serialisation,
- the *other* ref being compared (it extracts exactly one graph).

Notes
-----
grimp performs *static* analysis: the target package need not be installed or
importable-at-runtime, but grimp's finder locates it via ``sys.path``. This
module therefore temporarily puts the package's source root on ``sys.path`` and
purges any cached ``sys.modules`` entries for the top-level package, so a graph
built from one tree root is never contaminated by a same-named package cached
from another. Caching inside grimp is disabled (``cache_dir=None``) for the same
reason.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

import grimp

from graphdiff.diff import Edge, Graph, Node

# Characters that mark a package spec as a filesystem path rather than a dotted
# module name.
_PATH_SEPARATORS = ("/", "\\")


def _resolve_package(tree_root: Path, package_path: str) -> tuple[Path, str]:
    """Resolve ``package_path`` to ``(source_root, package_name)`` under ``tree_root``.

    ``source_root`` is the directory that must be on ``sys.path`` for grimp to
    import the package; ``package_name`` is the dotted name grimp is given.

    Two input forms are accepted:

    - a filesystem path (absolute, or relative to ``tree_root``), e.g.
      ``src/mypkg`` → source root ``<tree_root>/src``, name ``mypkg``;
    - a dotted package name whose top-level package lives directly under
      ``tree_root``, e.g. ``mypkg.sub`` → source root ``<tree_root>``, name
      ``mypkg.sub``.

    Raises
    ------
    FileNotFoundError
        If neither interpretation resolves to a directory under ``tree_root``.
    """
    tree_root = Path(tree_root).resolve()
    if not tree_root.is_dir():
        raise FileNotFoundError(f"tree_root is not a directory: {tree_root}")

    raw = str(package_path)

    # 1) Try as a filesystem path (relative to tree_root, or absolute).
    as_path = Path(raw)
    candidate = as_path if as_path.is_absolute() else tree_root / as_path
    if candidate.is_dir():
        pkg_dir = candidate.resolve()
        return pkg_dir.parent, pkg_dir.name

    # 2) Try as a dotted name whose top-level package sits under tree_root.
    if "." in raw and not any(sep in raw for sep in _PATH_SEPARATORS):
        dotted_dir = tree_root.joinpath(*raw.split("."))
        if dotted_dir.is_dir():
            return tree_root, raw

    raise FileNotFoundError(
        f"Package path {package_path!r} does not resolve to a directory under "
        f"{tree_root} (tried filesystem path and dotted-name interpretations)."
    )


@contextlib.contextmanager
def _package_on_path(source_root: Path, top_level: str) -> Iterator[None]:
    """Temporarily front-load ``source_root`` on ``sys.path`` for grimp's finder.

    Purges cached ``sys.modules`` entries for ``top_level`` before and after so
    grimp resolves the package from ``source_root`` and leaves no residue that
    could taint a later extraction of a same-named package from a different
    tree.
    """

    def _purge() -> None:
        for name in [
            mod
            for mod in sys.modules
            if mod == top_level or mod.startswith(top_level + ".")
        ]:
            del sys.modules[name]

    source_str = str(source_root)
    _purge()
    importlib.invalidate_caches()
    sys.path.insert(0, source_str)
    try:
        yield
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(source_str)
        _purge()
        importlib.invalidate_caches()


def _raw_graph(source_root: Path, package_name: str) -> tuple[set[Node], set[Edge]]:
    """Run grimp and collect the internal ``(nodes, edges)`` of ``package_name``.

    Only imports whose endpoints are both inside the package are kept (external
    packages are excluded at build time). Raises loudly if grimp cannot build
    the graph.
    """
    top_level = package_name.split(".")[0]
    with _package_on_path(source_root, top_level):
        try:
            graph = grimp.build_graph(
                package_name,
                include_external_packages=False,
                cache_dir=None,
            )
        except Exception as exc:  # noqa: BLE001 — re-raised with context, fail-fast
            raise RuntimeError(
                f"grimp failed to build the import graph for {package_name!r} "
                f"under {source_root}: {exc}"
            ) from exc

        nodes: set[Node] = set(graph.modules)
        edges: set[Edge] = set()
        for module in nodes:
            for imported in graph.find_modules_directly_imported_by(module):
                if imported in nodes:
                    edges.add((module, imported))
    return nodes, edges


def _apply_exclude(
    nodes: set[Node], edges: set[Edge], exclude: Iterable[str] | None
) -> tuple[set[Node], set[Edge]]:
    """Drop nodes whose name contains any exclude substring, and edges touching them."""
    substrings = [s for s in (exclude or []) if s]
    if not substrings:
        return nodes, edges
    dropped = {n for n in nodes if any(sub in n for sub in substrings)}
    kept_nodes = nodes - dropped
    kept_edges = {
        (src, dst) for src, dst in edges if src not in dropped and dst not in dropped
    }
    return kept_nodes, kept_edges


def _collapse(name: Node, depth: int) -> Node:
    """Collapse a dotted name to its first ``depth`` components."""
    return ".".join(name.split(".")[:depth])


def _apply_depth(
    nodes: set[Node], edges: set[Edge], depth: int | None
) -> tuple[set[Node], set[Edge]]:
    """Collapse every node to its ``depth``-level prefix; drop resulting self-loops."""
    if depth is None:
        return nodes, edges
    if depth < 1:
        raise ValueError(f"depth must be a positive integer, got {depth!r}")
    collapsed_nodes = {_collapse(n, depth) for n in nodes}
    collapsed_edges: set[Edge] = set()
    for src, dst in edges:
        csrc, cdst = _collapse(src, depth), _collapse(dst, depth)
        if csrc != cdst:  # intra-node edges become self-loops — drop them
            collapsed_edges.add((csrc, cdst))
    return collapsed_nodes, collapsed_edges


def extract_graph(
    tree_root: Path | str,
    package_path: str,
    depth: int | None = None,
    exclude: Iterable[str] | None = None,
) -> Graph:
    """Extract the canonical import :class:`Graph` for a package under a tree root.

    Parameters
    ----------
    tree_root:
        Root of the source tree to analyse (e.g. a git worktree path).
    package_path:
        The target package, either as a filesystem path relative to
        ``tree_root`` (``src/mypkg``) or a dotted name (``mypkg.sub``).
    depth:
        If given, collapse each module to its first ``depth`` dotted components;
        edges internal to a collapsed node (self-loops) are dropped.
    exclude:
        Iterable of substrings; any node whose name contains one is dropped
        along with every edge touching it.

    Returns
    -------
    Graph
        The canonical ``(nodes, edges)`` graph, ready for :func:`compute_delta`.

    Raises
    ------
    FileNotFoundError
        If ``package_path`` does not resolve under ``tree_root``.
    RuntimeError
        If grimp fails to build the graph.
    """
    source_root, package_name = _resolve_package(Path(tree_root), package_path)
    nodes, edges = _raw_graph(source_root, package_name)
    nodes, edges = _apply_exclude(nodes, edges, exclude)
    nodes, edges = _apply_depth(nodes, edges, depth)
    return Graph.of(nodes, edges)

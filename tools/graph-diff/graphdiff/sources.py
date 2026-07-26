"""sources — capture per-module source text and AST signatures under a tree root.

Responsibility
--------------
Given the root of a checked-out source tree and a target package (filesystem
path *or* dotted name), walk every ``.py`` module in the package, read its
source (UTF-8), and AST-extract readable signature strings for its top-level
functions/classes and class methods. Returns a ``{dotted_module -> ModuleSource}``
map for one ref, consumed unchanged by the explorer stage.

Must NOT know about
-------------------
- git (refs, worktrees, checkouts) — it receives an already-materialised tree,
- rendering or HTML serialisation,
- the *other* ref being compared (it captures exactly one ref's sources).

Path→module resolution is delegated to :func:`graphdiff.extract.iter_package_modules`
so the source map keys exactly match the graph's node ids.

Fail-fast
---------
A ``.py`` file whose source will not parse raises loudly, naming the offending
module — it is never silently dropped.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from graphdiff.extract import iter_package_modules


@dataclass(frozen=True)
class ModuleSource:
    """The captured source + signatures of a single module at one ref.

    Attributes
    ----------
    module:
        The dotted module name (matches the graph node id).
    path:
        Repo-relative POSIX path of the ``.py`` file (relative to the tree root).
    source:
        The full UTF-8 source text of the module.
    signatures:
        Readable signature strings for top-level ``def``/``async def``/``class``
        and class methods, in source order.
    line_count:
        Number of lines in the source.
    """

    module: str
    path: str
    source: str
    signatures: list[str] = field(default_factory=list)
    line_count: int = 0


def _has_unparse() -> bool:
    """True when ``ast.unparse`` is available (Python 3.9+)."""
    return hasattr(ast, "unparse")


def _unparse(node: ast.AST | None) -> str | None:
    """Best-effort ``ast.unparse``; ``None`` if unavailable or it fails."""
    if node is None or not _has_unparse():
        return None
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 — annotations are best-effort, never fatal
        return None


def _arg_names(args: ast.arguments) -> str:
    """Fallback arg rendering (names only) for Python builds without ``ast.unparse``."""
    names: list[str] = []
    for arg in list(getattr(args, "posonlyargs", [])) + list(args.args):
        names.append(arg.arg)
    if args.vararg is not None:
        names.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        names.append("*")
    for arg in args.kwonlyargs:
        names.append(arg.arg)
    if args.kwarg is not None:
        names.append("**" + args.kwarg.arg)
    return ", ".join(names)


def _format_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render a function's argument list — full spec if ``ast.unparse`` exists."""
    rendered = _unparse(node.args)
    if rendered is not None:
        return rendered
    return _arg_names(node.args)


def _format_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, indent: str = ""
) -> str:
    """Render ``[async ]def name(args)[ -> ret]`` for a function/method node."""
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    ret = _unparse(node.returns)
    ret_str = f" -> {ret}" if ret else ""
    return f"{indent}{prefix}{node.name}({_format_args(node)}){ret_str}"


def _format_class(node: ast.ClassDef) -> str:
    """Render ``class Name(bases, keyword=...)`` for a class node."""
    parts: list[str] = []
    for base in node.bases:
        rendered = _unparse(base)
        if rendered is not None:
            parts.append(rendered)
    for kw in node.keywords:
        rendered = _unparse(kw.value)
        if rendered is not None:
            parts.append(f"{kw.arg}={rendered}" if kw.arg else f"**{rendered}")
    bases = f"({', '.join(parts)})" if parts else ""
    return f"class {node.name}{bases}"


_FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _extract_signatures(source: str, module: str) -> list[str]:
    """AST-extract top-level and class-method signatures from ``source``.

    Raises
    ------
    SyntaxError
        Re-raised with the module name if the source will not parse (fail-fast).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SyntaxError(
            f"Could not parse module {module!r} for signature extraction: {exc}"
        ) from exc

    signatures: list[str] = []
    for node in tree.body:
        if isinstance(node, _FUNC_TYPES):
            signatures.append(_format_function(node))
        elif isinstance(node, ast.ClassDef):
            signatures.append(_format_class(node))
            for member in node.body:
                if isinstance(member, _FUNC_TYPES):
                    signatures.append(_format_function(member, indent="    "))
    return signatures


def capture_sources(
    tree_root: Path | str,
    package_path: str,
    exclude: Iterable[str] | None = None,
) -> dict[str, ModuleSource]:
    """Capture ``{dotted_module -> ModuleSource}`` for a package under ``tree_root``.

    Parameters
    ----------
    tree_root:
        Root of the materialised source tree (e.g. a git worktree path).
    package_path:
        The target package, a filesystem path relative to ``tree_root``
        (``src/mypkg``) or a dotted name (``mypkg.sub``).
    exclude:
        Iterable of substrings; any module whose dotted name contains one is
        dropped (matching the graph extractor's ``--exclude`` semantics).

    Returns
    -------
    dict[str, ModuleSource]
        One entry per captured module, keyed by dotted name.

    Raises
    ------
    FileNotFoundError
        If ``package_path`` does not resolve under ``tree_root``.
    SyntaxError
        If any captured module's source will not parse (fail-fast, named).
    """
    tree_root = Path(tree_root).resolve()
    substrings = [s for s in (exclude or []) if s]

    captured: dict[str, ModuleSource] = {}
    for module, py_file in iter_package_modules(tree_root, package_path):
        if any(sub in module for sub in substrings):
            continue
        source = py_file.read_text(encoding="utf-8")
        signatures = _extract_signatures(source, module)
        rel_path = py_file.relative_to(tree_root).as_posix()
        captured[module] = ModuleSource(
            module=module,
            path=rel_path,
            source=source,
            signatures=signatures,
            line_count=len(source.splitlines()),
        )
    return captured

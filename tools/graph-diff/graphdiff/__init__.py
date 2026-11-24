"""graphdiff — standalone, repo-agnostic dependency-graph diffing.

This package computes and renders the change in a codebase's import/module
dependency graph between two states. It is intentionally self-contained: it
does NOT import from any host project, reference any project-specific package
names, or hardcode any repository paths. Everything repo-specific is supplied
by the caller (CLI arguments in later phases).

Public building blocks (Phase 1):
- ``diff``   — pure set-difference over ``(nodes, edges)`` graphs.
- ``render`` — serialise a computed ``Delta`` to JSON and Markdown artifacts.
"""

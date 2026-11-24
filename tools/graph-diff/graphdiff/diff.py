"""diff — pure set-difference over two dependency graphs.

Responsibility
--------------
Given two graphs, each a canonical ``(nodes, edges)`` pair, compute the
structural delta between them: which nodes and edges were added, which were
removed, and which are unchanged. This is the entire responsibility of this
module and nothing more.

Must NOT know about
-------------------
- git (refs, worktrees, checkouts),
- grimp or any import-graph extraction,
- rendering or artifact serialisation,
- file paths or any I/O.

This module is pure Python operating on in-memory sets. It performs no I/O and
has no dependencies beyond the standard library, so it is unit-testable in
complete isolation from git and grimp.

Canonical representation
------------------------
A graph is a :class:`Graph`: a set of node identifiers (dotted module names,
opaque strings to this module) and a set of directed edges ``(src, dst)`` where
``src`` imports/depends-on ``dst``. Both are held as ``frozenset`` so a
``Graph`` (and a :class:`Delta`) is immutable and value-comparable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# An edge is a directed (src, dst) pair of node identifiers.
Node = str
Edge = tuple[str, str]


@dataclass(frozen=True)
class Graph:
    """A dependency graph: a node set and a directed-edge set.

    Node identifiers are opaque strings to this module (they happen to be
    dotted module names in practice). Edges are ``(src, dst)`` tuples meaning
    ``src`` depends on ``dst``. Held as frozensets so the graph is immutable
    and compares by value.
    """

    nodes: frozenset[Node]
    edges: frozenset[Edge]

    @classmethod
    def of(cls, nodes: Iterable[Node], edges: Iterable[Edge]) -> "Graph":
        """Build a :class:`Graph` from any node/edge iterables.

        Every edge endpoint is validated to be present in ``nodes`` — a graph
        whose edges reference an unknown node is malformed input and raises
        loudly rather than being silently repaired.
        """
        node_set: frozenset[Node] = frozenset(nodes)
        edge_set: frozenset[Edge] = frozenset(
            _validate_edge(edge) for edge in edges
        )
        dangling = {
            endpoint
            for src, dst in edge_set
            for endpoint in (src, dst)
            if endpoint not in node_set
        }
        if dangling:
            raise ValueError(
                "Graph edges reference nodes absent from the node set: "
                f"{sorted(dangling)}"
            )
        return cls(nodes=node_set, edges=edge_set)


def _validate_edge(edge: Edge) -> Edge:
    """Validate a single edge is a 2-tuple of strings; raise otherwise."""
    if (
        not isinstance(edge, tuple)
        or len(edge) != 2
        or not all(isinstance(part, str) for part in edge)
    ):
        raise ValueError(
            f"Edge must be a (src, dst) tuple of two strings, got: {edge!r}"
        )
    return edge


@dataclass(frozen=True)
class Delta:
    """The structural difference between a base graph and a head graph.

    Sets are defined relative to base → head:
    ``added_*`` are present in head but not base; ``removed_*`` are present in
    base but not head; ``unchanged_*`` are present in both. All are frozensets
    so a ``Delta`` is immutable and value-comparable.
    """

    added_nodes: frozenset[Node]
    removed_nodes: frozenset[Node]
    unchanged_nodes: frozenset[Node]
    added_edges: frozenset[Edge]
    removed_edges: frozenset[Edge]
    unchanged_edges: frozenset[Edge]

    @property
    def is_empty(self) -> bool:
        """True when nothing was added or removed (base and head coincide)."""
        return not (
            self.added_nodes
            or self.removed_nodes
            or self.added_edges
            or self.removed_edges
        )

    @property
    def added_node_count(self) -> int:
        return len(self.added_nodes)

    @property
    def removed_node_count(self) -> int:
        return len(self.removed_nodes)

    @property
    def unchanged_node_count(self) -> int:
        return len(self.unchanged_nodes)

    @property
    def added_edge_count(self) -> int:
        return len(self.added_edges)

    @property
    def removed_edge_count(self) -> int:
        return len(self.removed_edges)

    @property
    def unchanged_edge_count(self) -> int:
        return len(self.unchanged_edges)


def compute_delta(base: Graph, head: Graph) -> Delta:
    """Set-difference two graphs into a :class:`Delta`.

    ``added = head − base``, ``removed = base − head``,
    ``unchanged = base ∩ head`` — applied independently to the node sets and
    the edge sets. Deterministic and side-effect-free.
    """
    if not isinstance(base, Graph) or not isinstance(head, Graph):
        raise TypeError(
            "compute_delta expects two Graph instances, got "
            f"{type(base).__name__} and {type(head).__name__}"
        )
    return Delta(
        added_nodes=head.nodes - base.nodes,
        removed_nodes=base.nodes - head.nodes,
        unchanged_nodes=base.nodes & head.nodes,
        added_edges=head.edges - base.edges,
        removed_edges=base.edges - head.edges,
        unchanged_edges=base.edges & head.edges,
    )

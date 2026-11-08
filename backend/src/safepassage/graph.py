"""A directed weighted graph backed by an adjacency list."""

from __future__ import annotations

from typing import Hashable
from copy import deepcopy


class Graph:
    """Store each node's outgoing ``(neighbor, weight)`` edges."""

    def __init__(self) -> None:
        self.adj: dict[Hashable, list[tuple[Hashable, float, dict[str, object]]]] = {}

    def add_node(self, node: Hashable) -> None:
        """Add a node if it is not already present."""
        if node not in self.adj:
            self.adj[node] = []

    def add_edge(
        self,
        u: Hashable,
        v: Hashable,
        weight: float,
        bidirectional: bool = True,
        attributes: dict[str, object] | None = None,
    ) -> None:
        """Add an edge, optionally adding its reverse edge as well."""
        if weight < 0:
            raise ValueError("weight cannot be negative")
        self.add_node(u)
        self.add_node(v)
        self.adj[u].append((v, weight, dict(attributes or {})))
        if bidirectional:
            self.adj[v].append((u, weight, dict(attributes or {})))

    def remove_edge(self, u: Hashable, v: Hashable, bidirectional: bool = True) -> None:
        """Remove all matching edges, including the reverse if requested."""
        if u in self.adj:
            self.adj[u] = [edge for edge in self.adj[u] if edge[0] != v]
        if bidirectional and v in self.adj:
            self.adj[v] = [edge for edge in self.adj[v] if edge[0] != u]

    def neighbors(self, node: Hashable) -> list[tuple[Hashable, float]]:
        """Return a copy of a node's outgoing edges, or an empty list."""
        return [(neighbor, weight) for neighbor, weight, _ in self.adj.get(node, [])]

    def edge_records(self, node: Hashable) -> list[tuple[Hashable, float, dict[str, object]]]:
        """Return outgoing edges with independent copies of their attributes."""
        return [(neighbor, weight, deepcopy(attributes)) for neighbor, weight, attributes in self.adj.get(node, [])]

    def has_node(self, node: Hashable) -> bool:
        return node in self.adj

    def node_count(self) -> int:
        return len(self.adj)

    def edge_count(self) -> int:
        """Return the number of directed edges stored in the graph."""
        return sum(len(edges) for edges in self.adj.values())

    def nodes(self) -> list[Hashable]:
        """Return all graph nodes as a new list."""
        return list(self.adj)

    def reversed(self) -> Graph:
        """Return a graph with every directed edge reversed."""
        result = Graph()
        for node in self.nodes():
            result.add_node(node)
        for source in self.nodes():
            for target, weight, attributes in self.adj[source]:
                result.add_edge(target, source, weight, bidirectional=False, attributes=attributes)
        return result

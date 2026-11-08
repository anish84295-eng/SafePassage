"""Result type shared by shortest-path algorithms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable


@dataclass(frozen=True)
class PathResult:
    """A path, its cost, and search expansion details."""

    distance: float
    path: list[Hashable]
    nodes_explored: int
    visited_order: list[Hashable]
    length_m: float | None = field(default=None, compare=False)
    cost: float | None = field(default=None, compare=False)
    flooded_edges: int = field(default=0, compare=False)


def add_route_details(graph, result: PathResult) -> PathResult:
    """Return a route result with physical length, optimized cost, and flood count."""
    length = 0.0
    flooded = 0
    for source, target in zip(result.path, result.path[1:]):
        edge = min(
            ((weight, attributes) for neighbor, weight, attributes in graph.adj.get(source, [])
             if neighbor == target),
            key=lambda item: item[0],
            default=None,
        )
        if edge is not None:
            weight, attributes = edge
            length += float(attributes.get("length_m", weight))
            flooded += bool(attributes.get("flooded", False))
    return PathResult(
        result.distance, result.path, result.nodes_explored, result.visited_order,
        length_m=length, cost=result.distance, flooded_edges=flooded,
    )

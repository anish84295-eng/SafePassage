"""Breadth-first shortest paths by number of edges."""

from __future__ import annotations

from collections import deque
from math import inf
from typing import Hashable

from safepassage.algorithms.result import PathResult, add_route_details
from safepassage.graph import Graph


def bfs(graph: Graph, source: Hashable, target: Hashable) -> PathResult:
    """Find a path with the fewest edges using a FIFO queue."""
    if not graph.has_node(source):
        raise ValueError(f"source node {source!r} is not in the graph")
    if not graph.has_node(target):
        raise ValueError(f"target node {target!r} is not in the graph")

    distances: dict[Hashable, int] = {source: 0}
    previous: dict[Hashable, Hashable] = {}
    queue = deque([source])
    visited_order: list[Hashable] = []

    while queue:
        node = queue.popleft()
        visited_order.append(node)
        if node == target:
            break
        for neighbor, _weight in graph.neighbors(node):
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                previous[neighbor] = node
                queue.append(neighbor)

    if target not in distances:
        distance = inf
        path: list[Hashable] = []
    else:
        distance = distances[target]
        path = [target]
        while path[-1] != source:
            path.append(previous[path[-1]])
        path.reverse()
    return add_route_details(graph, PathResult(distance, path, len(visited_order), visited_order))

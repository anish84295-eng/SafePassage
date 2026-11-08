"""A* shortest-path search using the project's custom min-heap."""

from __future__ import annotations

from math import inf
from typing import Callable, Hashable

from safepassage.algorithms.result import PathResult, add_route_details
from safepassage.graph import Graph
from safepassage.structures.heap import MinHeap


Heuristic = Callable[[Hashable, Hashable], float]


def astar(
    graph: Graph,
    source: Hashable,
    target: Hashable,
    heuristic: Heuristic,
    blocked_nodes: set[Hashable] | None = None,
    blocked_edges: set[tuple[Hashable, Hashable]] | None = None,
    include_details: bool = True,
) -> PathResult:
    """Find a weighted shortest path, guided by ``heuristic(node, target)``."""
    if not graph.has_node(source):
        raise ValueError(f"source node {source!r} is not in the graph")
    if not graph.has_node(target):
        raise ValueError(f"target node {target!r} is not in the graph")
    blocked_nodes = blocked_nodes or set()
    blocked_edges = blocked_edges or set()
    if source in blocked_nodes or target in blocked_nodes:
        return PathResult(inf, [], 0, [])

    distances: dict[Hashable, float] = {source: 0.0}
    previous: dict[Hashable, Hashable] = {}
    distances[source] = 0
    frontier: MinHeap[Hashable] = MinHeap()
    frontier.push(heuristic(source, target), source)
    closed: set[Hashable] = set()
    visited_order: list[Hashable] = []

    while not frontier.is_empty():
        estimate, node = frontier.pop()
        current_distance = distances.get(node, inf)
        expected_estimate = current_distance + heuristic(node, target)
        if estimate != expected_estimate or node in closed:
            continue
        closed.add(node)
        visited_order.append(node)
        if node == target:
            break
        for neighbor, weight in graph.neighbors(node):
            if neighbor in blocked_nodes or (node, neighbor) in blocked_edges:
                continue
            candidate = current_distance + weight
            if candidate < distances.get(neighbor, inf):
                distances[neighbor] = candidate
                previous[neighbor] = node
                if neighbor in closed:
                    closed.remove(neighbor)
                frontier.push(candidate + heuristic(neighbor, target), neighbor)

    target_distance = distances.get(target, inf)
    if target_distance == inf:
        path: list[Hashable] = []
    else:
        path = [target]
        while path[-1] != source:
            path.append(previous[path[-1]])
        path.reverse()
    result = PathResult(target_distance, path, len(visited_order), visited_order)
    return add_route_details(graph, result) if include_details else result

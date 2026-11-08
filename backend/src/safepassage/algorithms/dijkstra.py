"""Dijkstra shortest paths for non-negative weighted graphs."""

from __future__ import annotations

from math import inf
from typing import Hashable

from safepassage.graph import Graph
from safepassage.algorithms.result import PathResult, add_route_details
from safepassage.structures.heap import MinHeap


def dijkstra(graph: Graph, source: Hashable) -> tuple[dict[Hashable, float], dict[Hashable, Hashable]]:
    """Return full shortest distances and predecessors from ``source``."""
    if not graph.has_node(source):
        raise ValueError(f"source node {source!r} is not in the graph")

    dist: dict[Hashable, float] = {node: inf for node in graph.nodes()}
    prev: dict[Hashable, Hashable] = {}
    dist[source] = 0
    frontier: MinHeap[Hashable] = MinHeap()
    frontier.push(0, source)

    while not frontier.is_empty():
        distance, node = frontier.pop()
        if distance != dist[node]:  # Ignore an outdated entry after a better route was found.
            continue
        for neighbor, weight in graph.neighbors(node):
            candidate = distance + weight
            if candidate < dist[neighbor]:
                dist[neighbor] = candidate
                prev[neighbor] = node
                frontier.push(candidate, neighbor)
    return dist, prev


def shortest_path(
    graph: Graph,
    source: Hashable,
    target: Hashable,
    blocked_nodes: set[Hashable] | None = None,
    blocked_edges: set[tuple[Hashable, Hashable]] | None = None,
    include_details: bool = True,
) -> PathResult:
    """Return the shortest path and nodes finalized before reaching its target."""
    if not graph.has_node(source):
        raise ValueError(f"source node {source!r} is not in the graph")
    if not graph.has_node(target):
        raise ValueError(f"target node {target!r} is not in the graph")
    blocked_nodes = blocked_nodes or set()
    blocked_edges = blocked_edges or set()
    if source in blocked_nodes or target in blocked_nodes:
        return PathResult(inf, [], 0, [])

    dist: dict[Hashable, float] = {node: inf for node in graph.nodes()}
    prev: dict[Hashable, Hashable] = {}
    dist[source] = 0
    frontier: MinHeap[Hashable] = MinHeap()
    frontier.push(0, source)
    visited_order: list[Hashable] = []

    while not frontier.is_empty():
        distance, node = frontier.pop()
        if distance != dist[node]:
            continue
        visited_order.append(node)
        if node == target:
            break
        for neighbor, weight in graph.neighbors(node):
            if neighbor in blocked_nodes or (node, neighbor) in blocked_edges:
                continue
            candidate = distance + weight
            if candidate < dist[neighbor]:
                dist[neighbor] = candidate
                prev[neighbor] = node
                frontier.push(candidate, neighbor)

    if dist[target] == inf:
        path: list[Hashable] = []
    else:
        path = [target]
        while path[-1] != source:
            path.append(prev[path[-1]])
        path.reverse()
    result = PathResult(
        distance=dist[target],
        path=path,
        nodes_explored=len(visited_order),
        visited_order=visited_order,
    )
    return add_route_details(graph, result) if include_details else result

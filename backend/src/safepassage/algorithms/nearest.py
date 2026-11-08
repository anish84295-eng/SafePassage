"""Nearest-facility searches using the custom Dijkstra heap."""

from __future__ import annotations

from math import inf
from typing import Hashable

from safepassage.algorithms.dijkstra import shortest_path
from safepassage.algorithms.result import PathResult, add_route_details
from safepassage.graph import Graph
from safepassage.structures.heap import MinHeap


def nearest_facility(graph: Graph, source: Hashable, facility_nodes: set[Hashable], k: int = 1) -> list[dict[str, object]]:
    """Return up to k nearest reachable facilities and their routes."""
    if not graph.has_node(source):
        raise ValueError(f"source node {source!r} is not in the graph")
    if k < 1:
        return []
    distances = {node: inf for node in graph.nodes()}
    previous: dict[Hashable, Hashable] = {}
    distances[source] = 0
    heap: MinHeap[Hashable] = MinHeap()
    heap.push(0, source)
    finalized: list[tuple[Hashable, float, int]] = []
    explored = 0
    while not heap.is_empty() and len(finalized) < k:
        distance, node = heap.pop()
        if distance != distances[node]:
            continue
        explored += 1
        if node in facility_nodes:
            finalized.append((node, distance, explored))
        for neighbor, weight in graph.neighbors(node):
            candidate = distance + weight
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                previous[neighbor] = node
                heap.push(candidate, neighbor)
    results = []
    for facility, cost, explored_at_finalization in finalized:
        path = [facility]
        while path[-1] != source:
            path.append(previous[path[-1]])
        path.reverse()
        route = add_route_details(graph, PathResult(cost, path, explored_at_finalization, []))
        results.append({"facility": facility, "path": path, "cost": cost,
                        "nodes_explored": explored_at_finalization, "length_m": route.length_m,
                        "flooded_edges": route.flooded_edges})
    return results


def precompute_nearest_facility_costs(
    graph: Graph, facility_nodes: set[Hashable], reversed_graph: Graph | None = None
) -> tuple[dict[Hashable, float], dict[Hashable, Hashable | None]]:
    """Return every node's cost and nearest facility using reversed multi-source Dijkstra."""
    reversed_graph = reversed_graph or graph.reversed()
    costs = {node: inf for node in graph.nodes()}
    facilities: dict[Hashable, Hashable | None] = {node: None for node in graph.nodes()}
    heap: MinHeap[Hashable] = MinHeap()
    for facility in facility_nodes:
        if graph.has_node(facility):
            costs[facility] = 0
            facilities[facility] = facility
            heap.push(0, facility)
    while not heap.is_empty():
        cost, node = heap.pop()
        if cost != costs[node]:
            continue
        for neighbor, weight in reversed_graph.neighbors(node):
            candidate = cost + weight
            if candidate < costs[neighbor]:
                costs[neighbor] = candidate
                facilities[neighbor] = facilities[node]
                heap.push(candidate, neighbor)
    return costs, facilities

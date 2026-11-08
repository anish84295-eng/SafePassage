"""Yen's algorithm for the k shortest loop-free paths."""

from __future__ import annotations

from typing import Hashable

from safepassage.algorithms.astar import Heuristic, astar
from safepassage.algorithms.dijkstra import shortest_path
from safepassage.algorithms.result import PathResult, add_route_details
from safepassage.graph import Graph
from safepassage.structures.heap import MinHeap


def yen_k_shortest_paths(
    graph: Graph,
    source: Hashable,
    target: Hashable,
    k: int = 3,
    heuristic: Heuristic | None = None,
) -> list[PathResult]:
    """Return up to k distinct simple paths ordered by total cost."""
    if k <= 0:
        return []
    search = (
        (lambda start, goal, blocked_nodes=None, blocked_edges=None, include_details=True: astar(
            graph, start, goal, heuristic, blocked_nodes, blocked_edges, include_details
        ))
        if heuristic is not None
        else (lambda start, goal, blocked_nodes=None, blocked_edges=None, include_details=True: shortest_path(
            graph, start, goal, blocked_nodes, blocked_edges, include_details
        ))
    )
    first = search(source, target)
    if not first.path:
        return []
    accepted = [first]
    candidates: MinHeap[tuple[Hashable, ...]] = MinHeap()
    queued: set[tuple[Hashable, ...]] = set()
    while len(accepted) < k:
        previous_path = accepted[-1].path
        prefix_costs = [0.0]
        for left, right in zip(previous_path, previous_path[1:]):
            edge_cost = min(weight for neighbor, weight in graph.neighbors(left) if neighbor == right)
            prefix_costs.append(prefix_costs[-1] + edge_cost)
        for spur_index in range(len(previous_path) - 1):
            root = previous_path[: spur_index + 1]
            removed_edges = {
                (route.path[spur_index], route.path[spur_index + 1])
                for route in accepted
                if len(route.path) > spur_index + 1 and route.path[: spur_index + 1] == root
            }
            removed_nodes = set(root[:-1])
            current_next = previous_path[spur_index + 1]
            has_divergent_edge = any(
                neighbor != current_next
                and neighbor not in removed_nodes
                and (root[-1], neighbor) not in removed_edges
                for neighbor, _weight in graph.neighbors(root[-1])
            )
            if not has_divergent_edge:
                continue
            spur = search(
                root[-1],
                target,
                removed_nodes,
                removed_edges,
                False,
            )
            if not spur.path:
                continue
            full_path = tuple(root[:-1] + spur.path)
            if any(tuple(route.path) == full_path for route in accepted) or full_path in queued:
                continue
            total_cost = prefix_costs[spur_index] + spur.distance
            combined = PathResult(total_cost, list(full_path), spur.nodes_explored, spur.visited_order)
            # Populate physical metres and flags from the actual chosen path.
            combined = add_route_details(graph, combined)
            candidates.push(total_cost, (len(queued), full_path, combined))
            queued.add(full_path)
        if candidates.is_empty():
            break
        _cost, (_serial, _path, next_route) = candidates.pop()
        accepted.append(next_route)
    return accepted


def shared_edge_ratio(path_a: list[Hashable], path_b: list[Hashable]) -> float:
    """Return common directed edges divided by the shorter route's edge count."""
    edges_a = set(zip(path_a, path_a[1:]))
    edges_b = set(zip(path_b, path_b[1:]))
    denominator = min(len(edges_a), len(edges_b))
    return len(edges_a & edges_b) / denominator if denominator else 0.0


def alternative_routes(
    graph: Graph,
    source: Hashable,
    target: Hashable,
    k: int = 3,
    max_overlap: float = 0.7,
    heuristic: Heuristic | None = None,
) -> list[PathResult]:
    """Generate alternatives by repeatedly penalizing earlier routes' edges."""
    if k <= 0:
        return []
    if not graph.has_node(source) or not graph.has_node(target):
        raise ValueError("source and target must be present in the graph")
    search_heuristic = heuristic or (lambda _node, _target: 0.0)
    best = astar(graph, source, target, search_heuristic)
    if not best.path:
        return []
    candidates = [best]
    edge_usage: dict[tuple[Hashable, Hashable], int] = {}
    for left, right in zip(best.path, best.path[1:]):
        edge_usage[(left, right)] = 1

    # A base route plus k-1 penalized passes bounds the number of full graph scans.
    for _ in range(max(0, k - 1)):
        penalized = Graph()
        for node in graph.nodes():
            penalized.add_node(node)
        for left in graph.nodes():
            for right, weight, attributes in graph.adj[left]:
                factor = 1.5 ** edge_usage.get((left, right), 0)
                penalized.add_edge(left, right, weight * factor, bidirectional=False, attributes=attributes)
        candidate = astar(penalized, source, target, search_heuristic)
        if not candidate.path:
            break
        original_cost = 0.0
        for left, right in zip(candidate.path, candidate.path[1:]):
            original_cost += min(weight for neighbor, weight in graph.neighbors(left) if neighbor == right)
        candidate = add_route_details(
            graph,
            PathResult(original_cost, candidate.path, candidate.nodes_explored, candidate.visited_order),
        )
        if not any(candidate.path == route.path for route in candidates):
            candidates.append(candidate)
        for left, right in zip(candidate.path, candidate.path[1:]):
            edge_usage[(left, right)] = edge_usage.get((left, right), 0) + 1

    candidates.sort(key=lambda result: result.distance)
    best_length = best.length_m if best.length_m is not None else best.distance
    kept: list[PathResult] = []
    for route in candidates:
        route_length = route.length_m if route.length_m is not None else route.distance
        if route_length > best_length * 1.5:
            continue
        if all(shared_edge_ratio(route.path, existing.path) <= max_overlap for existing in kept):
            kept.append(route)
            if len(kept) == k:
                break
    return kept

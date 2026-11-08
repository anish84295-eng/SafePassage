import math
import random

import pytest

from safepassage.algorithms.astar import astar
from safepassage.algorithms.dijkstra import shortest_path
from safepassage.algorithms.geo import haversine, make_haversine_heuristic
from safepassage.graph import Graph


def test_zero_heuristic_matches_dijkstra():
    graph = Graph()
    graph.add_edge("S", "A", 4)
    graph.add_edge("S", "B", 1)
    graph.add_edge("B", "A", 2)
    graph.add_edge("A", "T", 3)
    for source in graph.nodes():
        for target in graph.nodes():
            result = astar(graph, source, target, lambda _node, _target: 0)
            assert result.distance == shortest_path(graph, source, target).distance


def test_unreachable_source_target_and_errors():
    graph = Graph()
    graph.add_node("A")
    graph.add_node("B")
    assert math.isinf(astar(graph, "A", "B", lambda _n, _t: 0).distance)
    assert astar(graph, "A", "A", lambda _n, _t: 0).path == ["A"]
    with pytest.raises(ValueError, match="source"):
        astar(graph, "missing", "A", lambda _n, _t: 0)
    with pytest.raises(ValueError, match="target"):
        astar(graph, "A", "missing", lambda _n, _t: 0)


def test_random_admissible_heuristics_match_dijkstra():
    rng = random.Random(991)
    for _ in range(220):
        count = rng.randint(2, 10)
        coords = {
            node: (19.0 + rng.uniform(-0.08, 0.08), 72.8 + rng.uniform(-0.08, 0.08))
            for node in range(count)
        }
        graph = Graph()
        for node in range(count):
            graph.add_node(node)
        for u in range(count):
            for v in range(u + 1, count):
                if rng.random() < 0.35:
                    straight = haversine(*coords[u], *coords[v])
                    weight = straight + rng.uniform(0, 2000)
                    graph.add_edge(u, v, weight)
        heuristic = make_haversine_heuristic(coords)
        source = rng.randrange(count)
        target = rng.randrange(count)
        assert astar(graph, source, target, heuristic).distance == shortest_path(
            graph, source, target
        ).distance


def test_astar_expands_no_more_than_dijkstra_on_geographic_grid():
    graph = Graph()
    coords = {}
    side = 12
    for row in range(side):
        for col in range(side):
            node = (row, col)
            coords[node] = (19.076 + row * 0.001, 72.877 + col * 0.001)
            graph.add_node(node)
            if row > 0:
                other = (row - 1, col)
                distance = haversine(*coords[node], *coords[other]) * 1.05
                graph.add_edge(node, other, distance)
            if col > 0:
                other = (row, col - 1)
                distance = haversine(*coords[node], *coords[other]) * 1.05
                graph.add_edge(node, other, distance)
    source, target = (0, 0), (side - 1, side - 1)
    dijkstra_result = shortest_path(graph, source, target)
    astar_result = astar(graph, source, target, make_haversine_heuristic(coords))
    print(f"Dijkstra nodes_explored={dijkstra_result.nodes_explored}")
    print(f"A*       nodes_explored={astar_result.nodes_explored}")
    assert astar_result.distance == pytest.approx(dijkstra_result.distance)
    assert astar_result.nodes_explored <= dijkstra_result.nodes_explored

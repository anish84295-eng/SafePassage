import math
import random

import networkx as nx
import pytest

from safepassage.algorithms.dijkstra import PathResult, dijkstra, shortest_path
from safepassage.graph import Graph


def test_known_shortest_path():
    graph = Graph()
    graph.add_edge("A", "B", 4)
    graph.add_edge("A", "C", 1)
    graph.add_edge("C", "B", 2)
    graph.add_edge("B", "D", 1)
    graph.add_edge("C", "D", 5)
    result = shortest_path(graph, "A", "D")
    assert result == PathResult(4, ["A", "C", "B", "D"], 4, ["A", "C", "B", "D"])
    assert result.length_m == 4
    assert result.cost == 4
    assert result.flooded_edges == 0


def test_unreachable_node():
    graph = Graph()
    graph.add_node("island")
    graph.add_edge("A", "B", 2)
    distances, _ = dijkstra(graph, "A")
    assert math.isinf(distances["island"])
    result = shortest_path(graph, "A", "island")
    assert result.distance == math.inf
    assert result.path == []
    assert result.nodes_explored == 2
    assert result.visited_order == ["A", "B"]


def test_source_equals_target():
    graph = Graph()
    graph.add_node("A")
    result = shortest_path(graph, "A", "A")
    assert result.distance == 0
    assert result.path == ["A"]
    assert result.nodes_explored == 1
    assert result.visited_order == ["A"]


def test_one_way_edges():
    graph = Graph()
    graph.add_edge("A", "B", 3, bidirectional=False)
    assert shortest_path(graph, "A", "B").distance == 3
    assert shortest_path(graph, "A", "B").path == ["A", "B"]
    unreachable = shortest_path(graph, "B", "A")
    assert unreachable.distance == math.inf
    assert unreachable.path == []


def test_zero_weight_edges():
    graph = Graph()
    graph.add_edge("A", "B", 0, bidirectional=False)
    graph.add_edge("B", "C", 2, bidirectional=False)
    result = shortest_path(graph, "A", "C")
    assert result.distance == 2
    assert result.path == ["A", "B", "C"]


def test_early_exit_matches_full_dijkstra_distance():
    graph = Graph()
    graph.add_edge("S", "A", 2, bidirectional=False)
    graph.add_edge("S", "B", 1, bidirectional=False)
    graph.add_edge("B", "A", 1, bidirectional=False)
    graph.add_edge("A", "T", 2, bidirectional=False)
    graph.add_edge("B", "T", 10, bidirectional=False)
    full_distances, _ = dijkstra(graph, "S")
    result = shortest_path(graph, "S", "T")
    assert result.distance == full_distances["T"] == 4


def test_visited_order_and_nodes_explored():
    graph = Graph()
    graph.add_edge("S", "A", 2, bidirectional=False)
    graph.add_edge("S", "B", 1, bidirectional=False)
    graph.add_edge("B", "A", 0, bidirectional=False)
    graph.add_edge("A", "T", 2, bidirectional=False)
    result = shortest_path(graph, "S", "T")
    assert result.visited_order[0] == "S"
    assert result.visited_order == ["S", "B", "A", "T"]
    assert result.nodes_explored == len(result.visited_order)
    finalized_distances, _ = dijkstra(graph, "S")
    order_distances = [finalized_distances[node] for node in result.visited_order]
    assert order_distances == sorted(order_distances)


def test_missing_source_or_target_raises():
    graph = Graph()
    graph.add_node("A")
    with pytest.raises(ValueError, match="source"):
        dijkstra(graph, "missing")
    with pytest.raises(ValueError, match="target"):
        shortest_path(graph, "A", "missing")


def test_random_graphs_match_networkx():
    rng = random.Random(2026)
    for _ in range(200):
        node_count = rng.randint(2, 9)
        nodes = list(range(node_count))
        graph = Graph()
        reference = nx.DiGraph()
        graph_nodes = nodes.copy()
        rng.shuffle(graph_nodes)
        for node in graph_nodes:
            graph.add_node(node)
            reference.add_node(node)
        for u in nodes:
            for v in nodes:
                if u != v and rng.random() < 0.22:
                    weight = rng.randint(0, 20)
                    graph.add_edge(u, v, weight, bidirectional=False)
                    reference.add_edge(u, v, weight=weight)
        for source in nodes:
            actual, _ = dijkstra(graph, source)
            expected = nx.single_source_dijkstra_path_length(reference, source, weight="weight")
            for target in nodes:
                assert actual[target] == expected.get(target, math.inf)

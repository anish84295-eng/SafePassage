import math
import random

import networkx as nx

from safepassage.algorithms.bfs import bfs
from safepassage.graph import Graph


def test_hand_made_graph_fewest_edges():
    graph = Graph()
    graph.add_edge("S", "A", 100)
    graph.add_edge("A", "T", 100)
    graph.add_edge("S", "B", 1)
    graph.add_edge("B", "C", 1)
    graph.add_edge("C", "T", 1)
    result = bfs(graph, "S", "T")
    assert result.distance == 2
    assert result.path == ["S", "A", "T"]
    assert result.visited_order[0] == "S"
    assert result.nodes_explored == len(result.visited_order)


def test_unreachable_and_source_target():
    graph = Graph()
    graph.add_node("A")
    graph.add_node("island")
    unreachable = bfs(graph, "A", "island")
    assert math.isinf(unreachable.distance)
    assert unreachable.path == []
    same = bfs(graph, "A", "A")
    assert same.distance == 0
    assert same.path == ["A"]
    assert same.visited_order == ["A"]


def test_random_hop_counts_match_networkx():
    rng = random.Random(442)
    for _ in range(100):
        graph = Graph()
        reference = nx.DiGraph()
        nodes = list(range(rng.randint(2, 10)))
        for node in nodes:
            graph.add_node(node)
            reference.add_node(node)
        for u in nodes:
            for v in nodes:
                if u != v and rng.random() < 0.2:
                    graph.add_edge(u, v, 1, bidirectional=False)
                    reference.add_edge(u, v)
        for source in nodes:
            for target in nodes:
                result = bfs(graph, source, target)
                expected = nx.single_source_shortest_path_length(reference, source)
                assert result.distance == expected.get(target, math.inf)

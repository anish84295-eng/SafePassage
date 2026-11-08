import random

import networkx as nx

from safepassage.algorithms.yen import alternative_routes, shared_edge_ratio, yen_k_shortest_paths
from safepassage.graph import Graph


def test_known_routes_and_fewer_than_k():
    graph = Graph()
    graph.add_edge("s", "a", 1)
    graph.add_edge("a", "t", 1)
    graph.add_edge("s", "b", 2)
    graph.add_edge("b", "t", 2)
    graph.add_edge("a", "b", 5)
    results = yen_k_shortest_paths(graph, "s", "t", 3)
    assert [route.distance for route in results] == [2, 4, 8]
    assert len({tuple(route.path) for route in results}) == 3
    simple = Graph()
    simple.add_edge("s", "t", 2)
    assert len(yen_k_shortest_paths(simple, "s", "t", 3)) == 1


def test_random_small_graphs_match_networkx_simple_paths():
    rng = random.Random(117)
    for _ in range(35):
        graph = Graph()
        reference = nx.DiGraph()
        nodes = list(range(6))
        for node in nodes:
            graph.add_node(node)
            reference.add_node(node)
        for source in nodes:
            for target in nodes:
                if source != target and rng.random() < 0.28:
                    weight = rng.randint(1, 9)
                    graph.add_edge(source, target, weight, bidirectional=False)
                    reference.add_edge(source, target, weight=weight)
        try:
            expected = list(nx.shortest_simple_paths(reference, 0, 5, weight="weight"))[:3]
        except nx.NetworkXNoPath:
            expected = []
        actual = yen_k_shortest_paths(graph, 0, 5, 3)
        assert [route.distance for route in actual] == [
            sum(reference[u][v]["weight"] for u, v in zip(path, path[1:])) for path in expected
        ]


def test_shared_edge_ratio_and_alternative_filtering():
    assert shared_edge_ratio([1, 2, 3, 4], [1, 2, 5, 4]) == 1 / 3
    graph = Graph()
    graph.add_edge("s", "a", 1)
    graph.add_edge("a", "t", 1)
    graph.add_edge("s", "b", 1)
    graph.add_edge("b", "t", 1)
    graph.add_edge("s", "c", 1)
    graph.add_edge("c", "t", 1)
    routes = alternative_routes(graph, "s", "t", k=3, max_overlap=0.7)
    assert len(routes) == 3
    assert all(shared_edge_ratio(a.path, b.path) <= 0.7 for i, a in enumerate(routes) for b in routes[i + 1 :])


def test_alternative_routes_returns_fewer_when_not_distinct():
    graph = Graph()
    graph.add_edge("s", "a", 1)
    graph.add_edge("a", "b", 1)
    graph.add_edge("b", "t", 1)
    graph.add_edge("a", "t", 1)
    routes = alternative_routes(graph, "s", "t", k=3, max_overlap=0.5)
    assert len(routes) < 3

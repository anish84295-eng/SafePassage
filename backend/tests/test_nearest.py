import math
import random

import networkx as nx

from safepassage.algorithms.nearest import nearest_facility, precompute_nearest_facility_costs
from safepassage.graph import Graph


def test_one_way_nearest_facility_and_reverse_multisource():
    graph = Graph()
    graph.add_edge("a", "b", 2, bidirectional=False)
    graph.add_edge("b", "h1", 3, bidirectional=False)
    graph.add_edge("a", "h2", 8, bidirectional=False)
    graph.add_node("isolated")
    results = nearest_facility(graph, "a", {"h1", "h2"}, 2)
    assert [result["facility"] for result in results] == ["h1", "h2"]
    assert results[0]["path"] == ["a", "b", "h1"]
    costs, facilities = precompute_nearest_facility_costs(graph, {"h1", "h2"})
    assert costs["a"] == 5
    assert facilities["a"] == "h1"
    assert math.isinf(costs["isolated"])


def test_random_nearest_costs_match_networkx():
    rng = random.Random(929)
    for _ in range(40):
        graph = Graph()
        reference = nx.DiGraph()
        nodes = list(range(8))
        for node in nodes:
            graph.add_node(node)
            reference.add_node(node)
        for source in nodes:
            for target in nodes:
                if source != target and rng.random() < 0.2:
                    weight = rng.randint(1, 20)
                    graph.add_edge(source, target, weight, bidirectional=False)
                    reference.add_edge(source, target, weight=weight)
        facilities = {2, 6}
        costs, _ = precompute_nearest_facility_costs(graph, facilities)
        for node in nodes:
            candidates = [nx.shortest_path_length(reference, node, facility, weight="weight")
                          for facility in facilities if nx.has_path(reference, node, facility)]
            assert costs[node] == (min(candidates) if candidates else math.inf)

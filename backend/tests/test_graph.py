import pytest

from safepassage.graph import Graph


def test_add_edge_creates_both_nodes():
    graph = Graph()
    graph.add_edge("A", "B", 5)
    assert graph.has_node("A") and graph.has_node("B")


def test_bidirectional_edge():
    graph = Graph()
    graph.add_edge("A", "B", 5)
    assert ("B", 5) in graph.neighbors("A")
    assert ("A", 5) in graph.neighbors("B")


def test_one_way_edge():
    graph = Graph()
    graph.add_edge("A", "B", 5, bidirectional=False)
    assert graph.neighbors("A") == [("B", 5)]
    assert graph.neighbors("B") == []


def test_remove_edge():
    graph = Graph()
    graph.add_edge("A", "B", 5)
    graph.remove_edge("A", "B")
    assert graph.neighbors("A") == []
    assert graph.neighbors("B") == []


def test_negative_weight_rejected():
    with pytest.raises(ValueError):
        Graph().add_edge("A", "B", -1)


def test_neighbors_of_unknown_node_is_empty_and_copy_safe():
    graph = Graph()
    assert graph.neighbors("Z") == []
    graph.add_edge("A", "B", 1)
    result = graph.neighbors("A")
    result.clear()
    assert graph.neighbors("A") == [("B", 1)]


def test_counts():
    graph = Graph()
    graph.add_edge("A", "B", 1)
    graph.add_edge("B", "C", 1)
    assert graph.node_count() == 3
    assert graph.edge_count() == 4

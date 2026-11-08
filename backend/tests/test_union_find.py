from safepassage.graph import Graph
from safepassage.scenarios import apply_scenario
from safepassage.structures.union_find import UnionFind, find_cut_off_nodes


def test_union_find_merges_and_compresses():
    union_find = UnionFind([1, 2, 3, 4])
    union_find.union(1, 2)
    union_find.union(2, 3)
    assert union_find.find(1) == union_find.find(3)
    assert union_find.find(4) != union_find.find(3)
    assert len(union_find.components()) == 2


def test_cut_off_nodes_and_road_closure():
    graph = Graph()
    graph.add_edge(1, 2, 1, bidirectional=False)
    graph.add_edge(2, 3, 1, bidirectional=False)
    graph.add_edge(3, 4, 1, bidirectional=False)
    graph.add_edge(4, 5, 1, bidirectional=False)
    cutoff, components = find_cut_off_nodes(graph, {5})
    assert cutoff == set()
    assert len(components) == 1
    closed = apply_scenario(graph, "road_closed", closed_ids={3})
    cutoff, components = find_cut_off_nodes(closed, {5})
    assert cutoff == {1, 2, 3}
    assert len(components) == 3

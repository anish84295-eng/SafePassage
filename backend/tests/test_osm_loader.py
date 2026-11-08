from safepassage.osm_loader import graph_from_overpass


def fixture():
    elements = []
    points = {
        1: (19.00, 72.80), 2: (19.01, 72.80), 3: (19.02, 72.80),
        4: (19.02, 72.81), 5: (19.03, 72.81), 10: (19.04, 72.81),
    }
    for node_id, (lat, lon) in points.items():
        elements.append({"type": "node", "id": node_id, "lat": lat, "lon": lon})
    elements.extend([
        {"type": "way", "id": 100, "nodes": [1, 2, 3], "tags": {"highway": "primary", "name": "Main Road"}},
        {"type": "way", "id": 101, "nodes": [3, 4, 5], "tags": {"highway": "secondary", "oneway": "yes"}},
        {"type": "way", "id": 102, "nodes": [5, 10], "tags": {"highway": "residential", "oneway": "-1"}},
    ])
    return {"elements": elements}


def test_oneway_shape_simplification_and_largest_component():
    graph, coords = graph_from_overpass(fixture())
    assert set(graph.nodes()) == {1, 3, 5, 10}
    assert graph.neighbors(5) == []
    assert graph.neighbors(3) == [(1, graph.neighbors(3)[0][1]), (5, graph.neighbors(3)[1][1])]
    assert graph.edge_count() == 4
    assert 2 not in coords and 4 not in coords
    attrs = graph.edge_records(1)[0][2]
    assert attrs["road_type"] == "primary"
    assert attrs["name"] == "Main Road"
    # Simplified 1->3 length includes the omitted shape node 2.
    from safepassage.algorithms.geo import haversine
    expected = haversine(19.00, 72.80, 19.01, 72.80) + haversine(19.01, 72.80, 19.02, 72.80)
    assert graph.edge_records(1)[0][1] == expected


def test_reverse_oneway_direction_is_respected():
    graph, _ = graph_from_overpass(fixture())
    assert graph.neighbors(10)[0][0] == 5
    assert all(neighbor != 10 for neighbor, _weight in graph.neighbors(5))

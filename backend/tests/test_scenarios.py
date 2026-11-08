from safepassage.graph import Graph
from safepassage.scenarios import apply_scenario


def sample_graph():
    graph = Graph()
    graph.add_edge(1, 2, 100, attributes={"length_m": 100, "road_type": "primary", "name": "A"})
    graph.add_edge(2, 3, 100, attributes={"length_m": 100, "road_type": "residential", "name": "B"})
    return graph


def test_normal_copy_matches_original_and_does_not_alias():
    original = sample_graph()
    normal = apply_scenario(original, "normal")
    assert normal.edge_records(1) == original.edge_records(1)
    assert normal is not original


def test_heavy_rain_costs_and_marks_flooded_edges():
    original = sample_graph()
    coords = {1: (19.0, 72.8), 2: (19.0, 72.801), 3: (19.0, 72.9)}
    spots = [{"lat": 19.0, "lng": 72.8005, "radius_m": 1000}]
    rainy = apply_scenario(original, "heavy_rain", coords, flood_spots=spots)
    assert rainy.edge_records(1)[0][1] == 360
    assert rainy.edge_records(1)[0][2]["flooded"] is True
    assert rainy.edge_records(2)[0][1] > original.edge_records(2)[0][1]
    assert original.edge_records(1)[0][1] == 100


def test_road_closures_remove_edges_by_id_name_or_radius():
    graph = sample_graph()
    assert apply_scenario(graph, "road_closed", closed_names={"A"}).edge_count() == 2
    assert apply_scenario(graph, "road_closed", closed_ids={2}).edge_count() == 0
    coords = {1: (19, 72.8), 2: (19, 72.801), 3: (19, 72.9)}
    closed = apply_scenario(graph, "road_closed", coords, closure_point=(19, 72.8005), closure_radius_m=100)
    assert closed.edge_count() == 2

import pytest
from test_client import TestClient

from safepassage.api.main import create_app
from safepassage.api.services import AppState
from safepassage.graph import Graph
from safepassage.spatial import SpatialIndex
from safepassage.structures.trie import Trie


def make_state(node_count: int = 5) -> AppState:
    graph = Graph()
    coords = {
        1: (19.010, 72.810), 2: (19.011, 72.810), 3: (19.012, 72.810),
        4: (19.010, 72.812), 5: (19.080, 72.890),
    }
    for node in range(1, node_count + 1):
        graph.add_node(node)
    graph.add_edge(1, 2, 150, attributes={"length_m": 150, "road_type": "primary", "name": "Alpha Road"})
    graph.add_edge(2, 3, 150, attributes={"length_m": 150, "road_type": "residential", "name": "Alpha Road"})
    graph.add_edge(1, 4, 180, attributes={"length_m": 180, "road_type": "secondary", "name": "Beta Road"})
    graph.add_edge(4, 3, 180, attributes={"length_m": 180, "road_type": "secondary", "name": "Beta Road"})
    if node_count > 5:
        for node in range(6, node_count + 1):
            coords[node] = (19.01 + (node - 1) * 0.000001, 72.81)
            graph.add_edge(node - 1, node, 1, attributes={"length_m": 1, "road_type": "residential", "name": "Long Road"})
    hospitals = [{"name": "Alpha Hospital", "lat": coords[3][0], "lng": coords[3][1], "node": 3}]
    trie = Trie()
    trie.insert("Alpha Road", 1, coords[1])
    return AppState(
        graph=graph,
        coords=coords,
        hospitals=hospitals,
        flood_spots=[{"name": "Test Flood Spot", "lat": coords[2][0], "lng": coords[2][1], "radius_m": 200}],
        spatial=SpatialIndex(coords),
        trie=trie,
        bbox={"south": 19.0, "west": 72.8, "north": 19.1, "east": 72.9},
    )


@pytest.fixture
def client():
    with TestClient(create_app(make_state())) as test_client:
        yield test_client


def route_body(**overrides):
    body = {
        "origin": {"lat": 19.010, "lng": 72.810},
        "destination": {"lat": 19.012, "lng": 72.810},
        "scenario": "normal",
    }
    body.update(overrides)
    return body


def test_health_meta_search_and_static(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    meta = client.get("/api/meta").json()
    assert meta["node_count"] == 5
    assert meta["hospital_count"] == 1
    assert client.get("/api/search?q=ALP").json()[0]["name"] == "Alpha Road"
    assert client.get("/api/hospitals").json()[0]["name"] == "Alpha Hospital"
    assert client.get("/api/flood-zones").json()["illustrative"] is True
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("algorithm", ["astar", "dijkstra", "bfs"])
def test_route_algorithms_and_alternatives(client, algorithm):
    response = client.post("/api/route", json=route_body(algorithm=algorithm, alternatives=2))
    assert response.status_code == 200
    data = response.json()
    assert data["route"]["path"][0] == [19.01, 72.81]
    assert data["route"]["distance_m"] > 0
    assert data["route"]["cost"] > 0
    assert len(data["alternatives"]) <= 2
    assert data["scenario"] == "normal"
    assert data["snapped_origin_label"] == "Alpha Road"


def test_alternatives_endpoint_returns_paths_after_main_route(client):
    response = client.post("/api/alternatives", json=route_body(alternatives=2))
    assert response.status_code == 200
    assert len(response.json()["alternatives"]) <= 2


def test_closure_graph_cache_is_reused_and_bounded():
    state = make_state()
    first = state.scenario_graph("normal", [{"lat": 19.01, "lng": 72.81, "radius_m": 30}])
    same = state.scenario_graph("normal", [{"lat": 19.01, "lng": 72.81, "radius_m": 30}])
    assert same is first
    for index in range(12):
        state.scenario_graph("normal", [{"lat": 19.01 + index * 0.00001, "lng": 72.81, "radius_m": 30}])
    assert len(state.closure_graphs) == 8


def test_rain_and_closures_can_be_combined_and_keep_flood_metrics(client):
    body = route_body(
        scenario="heavy_rain",
        closures=[{"lat": 19.010, "lng": 72.812, "radius_m": 180}],
    )
    response = client.post("/api/route", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["route"] is not None
    assert data["route"]["safety_score"] < 100
    assert data["route"]["flooded_edges"] > 0
    assert data["route"]["flooded_length_m"] > 0
    assert data["normal_route_flooded_edges"] > 0


def test_bbox_no_road_unreachable_and_error_shape(client):
    outside = client.post("/api/route", json=route_body(origin={"lat": 18.9, "lng": 72.81}))
    assert outside.status_code == 422
    assert outside.json()["error"]["code"] == "outside_area"
    no_road = client.post("/api/route", json=route_body(origin={"lat": 19.05, "lng": 72.85}))
    assert no_road.status_code == 400
    assert no_road.json()["error"]["code"] == "no_road_nearby"
    assert no_road.json()["error"]["message"] == "No road node is within 500 m of origin."
    isolated = client.post("/api/route", json=route_body(destination={"lat": 19.08, "lng": 72.89}))
    assert isolated.status_code == 200
    assert isolated.json()["route"] is None
    assert isolated.json()["message"]
    invalid = client.post("/api/route", json=route_body(alternatives=10))
    assert invalid.status_code == 422
    assert set(invalid.json()) == {"error"}


def test_unreachable_nearest_and_cut_off(client):
    # Node 5 has no road edge and is deliberately in the map bbox but far from nodes 1-4.
    body = {"origin": {"lat": 19.012, "lng": 72.810}, "destination": {"lat": 19.012, "lng": 72.810}}
    result = client.post("/api/route", json=route_body(destination={"lat": 19.010, "lng": 72.812})).json()
    assert result["route"]["distance_m"] > 0
    nearest = client.post("/api/nearest-hospitals", json={"origin": body["origin"], "k": 3}).json()
    assert nearest["hospitals"][0]["name"] == "Alpha Hospital"
    assert nearest["cut_off"] is False
    # A node without an edge cannot be represented by a coordinate within 500 m here; use a one-node hospital state.
    state = make_state()
    state.hospitals = [{"name": "Far Hospital", "lat": 19.08, "lng": 72.89, "node": 5}]
    with TestClient(create_app(state)) as isolated_client:
        missing = isolated_client.post("/api/nearest-hospitals", json={"origin": body["origin"]}).json()
        assert missing["hospitals"] == []
        assert missing["cut_off"] is True


def test_road_closures_are_validated_and_unreachable_is_200(client):
    closures = [{"lat": 19.011, "lng": 72.810, "radius_m": 100} for _ in range(6)]
    response = client.post("/api/route", json=route_body(scenario="road_closed", closures=closures))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_origin_cut_off_has_distinct_error(client):
    response = client.post("/api/route", json=route_body(closures=[{"lat": 19.010, "lng": 72.810, "radius_m": 150}]))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "origin_cut_off"


def test_destination_cut_off_has_distinct_error(client):
    response = client.post("/api/route", json=route_body(closures=[{"lat": 19.01125, "lng": 72.8105, "radius_m": 75}]))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "destination_cut_off"


def test_disconnected_roads_under_closures_return_no_path():
    state = make_state()
    state.graph = Graph()
    for node in range(1, 6):
        state.graph.add_node(node)
    state.graph.add_edge(1, 2, 150, bidirectional=False)
    state.graph.add_edge(2, 3, 150, bidirectional=False)
    state.graph.add_edge(4, 3, 150, bidirectional=False)
    with TestClient(create_app(state)) as isolated_client:
        response = isolated_client.post("/api/route", json=route_body(
            closures=[{"lat": 19.0115, "lng": 72.810, "radius_m": 40}]))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "no_path"


def test_compare_caps_visited_order():
    state = make_state(1601)
    with TestClient(create_app(state)) as large_client:
        body = {"origin": {"lat": 19.010, "lng": 72.810},
                "destination": {"lat": 19.0116, "lng": 72.810}}
        response = large_client.post("/api/compare", json=body)
        assert response.status_code == 200
        for result in response.json()["results"].values():
            assert len(result["visited_order"]) <= 1500


@pytest.mark.skip(reason="Optional manual real-data latency check; run separately when needed.")
def test_real_graph_route_under_two_seconds():
    from safepassage.api.services import load_state
    state = load_state()
    point = state.coords[state.graph.nodes()[0]]
    body = {"origin": {"lat": point[0], "lng": point[1]},
            "destination": {"lat": point[0], "lng": point[1]}}
    with TestClient(create_app(state)) as real_client:
        response = real_client.post("/api/route", json=body)
        assert response.status_code == 200
        assert response.json()["compute_ms"] < 2000

"""Application state and routing services for API endpoints."""

from __future__ import annotations

import json
from collections import Counter, OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from functools import lru_cache
from typing import Any

from safepassage.algorithms.astar import astar
from safepassage.algorithms.bfs import bfs
from safepassage.algorithms.dijkstra import shortest_path
from safepassage.algorithms.geo import make_haversine_heuristic, haversine
from safepassage.algorithms.nearest import nearest_facility
from safepassage.algorithms.nearest import precompute_nearest_facility_costs
from safepassage.algorithms.yen import alternative_routes
from safepassage.algorithms.result import PathResult
from safepassage.graph import Graph
from safepassage.osm_loader import load_processed_graph
from safepassage.scenarios import apply_scenario
from safepassage.spatial import SpatialIndex
from safepassage.structures.trie import Trie, build_name_index
from safepassage.structures.union_find import find_cut_off_nodes

ROOT = Path(__file__).resolve().parents[4]
DATA_ATTRIBUTION = "© OpenStreetMap contributors, ODbL"
DEFAULT_BBOX = {"south": 19.05, "west": 72.82, "north": 19.19, "east": 72.87}
SPEED_KMH = {
    "motorway": 60.0, "trunk": 45.0, "primary": 35.0, "secondary": 30.0,
    "tertiary": 25.0, "unclassified": 20.0, "residential": 20.0,
    "motorway_link": 30.0, "trunk_link": 25.0, "primary_link": 25.0,
    "secondary_link": 20.0, "tertiary_link": 20.0,
}


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass
class AppState:
    graph: Graph
    coords: dict[int, tuple[float, float]]
    hospitals: list[dict[str, Any]]
    flood_spots: list[dict[str, Any]]
    spatial: SpatialIndex
    trie: Trie
    bbox: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_BBOX))
    scenario_graphs: dict[str, Graph] = field(default_factory=dict)
    closure_graphs: OrderedDict[tuple[Any, ...], Graph] = field(default_factory=OrderedDict)
    route_cache: OrderedDict[tuple[Any, ...], dict[str, Any]] = field(default_factory=OrderedDict)
    heuristic: Any = None
    reversed_graph: Graph | None = None
    hospital_precompute: Any = None
    node_labels: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_labels:
            names: dict[int, Counter[str]] = {int(node): Counter() for node in self.graph.nodes()}
            for source in self.graph.nodes():
                for target, _weight, attributes in self.graph.edge_records(source):
                    name = str(attributes.get("name", "")).strip()
                    if name:
                        names[int(source)][name] += 1
                        names[int(target)][name] += 1
            self.node_labels = {
                node: counts.most_common(1)[0][0]
                for node, counts in names.items() if counts
            }

    def scenario_graph(self, scenario: str, closures: list[dict[str, float]] | None = None) -> Graph:
        """Get a cached named graph or apply temporary road closures."""
        # Legacy road_closed requests mean normal conditions plus closures.
        base_scenario = "normal" if scenario == "road_closed" else scenario
        if base_scenario not in {"normal", "heavy_rain"}:
            raise ValueError(f"unsupported scenario: {scenario}")
        if base_scenario not in self.scenario_graphs:
            self.scenario_graphs[base_scenario] = apply_scenario(
                self.graph, base_scenario, coords=self.coords, flood_spots=self.flood_spots
            )
        if not closures:
            return self.scenario_graphs[base_scenario]
        key = (base_scenario, *sorted((round(c["lat"], 6), round(c["lng"], 6), round(c["radius_m"], 1)) for c in closures))
        if key in self.closure_graphs:
            self.closure_graphs.move_to_end(key)
            return self.closure_graphs[key]
        result = apply_scenario(
            self.scenario_graphs[base_scenario], "road_closed", coords=self.coords,
            closure_circles=[(c["lat"], c["lng"], c["radius_m"]) for c in closures],
        )
        self.closure_graphs[key] = result
        self.closure_graphs.move_to_end(key)
        while len(self.closure_graphs) > 8:
            self.closure_graphs.popitem(last=False)
        return result


def load_state() -> AppState:
    """Load real routing data once at application startup."""
    graph, coords = load_processed_graph()
    hospitals_path = ROOT / "data" / "spots" / "hospitals.json"
    flood_path = ROOT / "data" / "spots" / "flood_spots.json"
    hospitals = json.loads(hospitals_path.read_text(encoding="utf-8")) if hospitals_path.exists() else []
    flood_spots = json.loads(flood_path.read_text(encoding="utf-8")) if flood_path.exists() else []
    state = AppState(graph, coords, hospitals, flood_spots, SpatialIndex(coords), build_name_index(graph, coords))
    state.heuristic = make_haversine_heuristic(coords)
    state.scenario_graph("normal")
    state.scenario_graph("heavy_rain")
    state.reversed_graph = state.graph.reversed()
    state.hospital_precompute = precompute_nearest_facility_costs(
        state.graph, {int(h["node"]) for h in hospitals}, state.reversed_graph
    )
    return state


def check_point(state: AppState, point: Any, label: str) -> int:
    """Validate bbox and snap a coordinate, enforcing the 500 m limit."""
    bounds = state.bbox
    if not (bounds["south"] <= point.lat <= bounds["north"] and bounds["west"] <= point.lng <= bounds["east"]):
        raise APIError(422, "outside_area", f"{label} must be inside the Mumbai road-data area.")
    node = state.spatial.snap_to_node(point.lat, point.lng)
    node_lat, node_lng = state.coords[node]
    if haversine(point.lat, point.lng, node_lat, node_lng) > 500:
        raise APIError(400, "no_road_nearby", f"No road node is within 500 m of {label}.")
    return int(node)


def validate_closures(state: AppState, scenario: str, closures: list[Any]) -> list[dict[str, float]]:
    if len(closures) > 5:
        raise APIError(422, "too_many_closures", "At most 5 closure circles are allowed.")
    prepared = []
    for closure in closures:
        check_point(state, closure, "closure point")
        if closure.radius_m > 1000:
            raise APIError(422, "closure_radius_too_large", "Closure radius cannot exceed 1000 m.")
        prepared.append(closure.model_dump())
    return prepared


def path_metrics(graph: Graph, result: Any, coords: dict[int, tuple[float, float]], scenario: str) -> dict[str, Any]:
    """Build API route fields; duration uses road speeds and rain slowdown."""
    distance = float(result.length_m or 0.0)
    flooded_length = 0.0
    flooded_edges = 0
    duration = 0.0
    for source, target in zip(result.path, result.path[1:]):
        edges = [(weight, attrs) for neighbor, weight, attrs in graph.adj.get(source, []) if neighbor == target]
        if not edges:
            continue
        weight, attributes = min(edges, key=lambda pair: pair[0])
        length = float(attributes.get("length_m", weight))
        road_type = str(attributes.get("road_type", "residential"))
        speed = SPEED_KMH.get(road_type, 20.0)
        if scenario == "heavy_rain":
            speed *= 0.75
        duration += length / (speed * 1000 / 3600)
        if attributes.get("flooded"):
            flooded_length += length
            flooded_edges += 1
    safety_score = round(100 * (1 - flooded_length / distance)) if distance > 0 else 100
    return {
        "distance_m": round(distance, 1),
        "duration_s": round(duration, 1),
        "cost": round(float(result.cost if result.cost is not None else result.distance), 1),
        "flooded_edges": flooded_edges,
        "flooded_length_m": round(flooded_length, 1),
        "safety_score": max(0, min(100, safety_score)),
        "path": [[coords[node][0], coords[node][1]] for node in result.path],
    }


def normal_route_flooded_edges(state: AppState, source: int, target: int, scenario: str) -> int:
    normal = state.scenario_graph("normal")
    normal_result = shortest_path(normal, source, target)
    rain_graph = state.scenario_graph("heavy_rain")
    return path_metrics(rain_graph, normal_result, state.coords, "heavy_rain")["flooded_edges"] if normal_result.path else 0


def evenly_sample(points: list[Any], limit: int = 1500) -> list[Any]:
    if len(points) <= limit:
        return points
    if limit <= 1:
        return [points[0]]
    return [points[round(index * (len(points) - 1) / (limit - 1))] for index in range(limit)]


def route_search(graph: Graph, algorithm: str, source: int, target: int, state: AppState):
    if algorithm == "dijkstra":
        return shortest_path(graph, source, target)
    if algorithm == "bfs":
        return bfs(graph, source, target)
    return astar(graph, source, target, state.heuristic or make_haversine_heuristic(state.coords))


def route_response(state: AppState, request: Any) -> dict[str, Any]:
    closures = validate_closures(state, request.scenario, request.closures)
    source = check_point(state, request.origin, "origin")
    target = check_point(state, request.destination, "destination")
    graph = state.scenario_graph(request.scenario, closures)
    cache_key = (source, target, request.scenario, request.algorithm, request.alternatives,
                 tuple(sorted((c["lat"], c["lng"], c["radius_m"]) for c in closures)))
    if cache_key in state.route_cache:
        state.route_cache.move_to_end(cache_key)
        return deepcopy(state.route_cache[cache_key])
    started = perf_counter()
    result = route_search(graph, request.algorithm, source, target, state)
    route = None
    alternatives = []
    message = None
    if result.path:
        route = {"id": "main", "label": "Fastest route", **path_metrics(graph, result, state.coords, request.scenario)}
        if request.alternatives:
            heuristic = state.heuristic or make_haversine_heuristic(state.coords)
            candidates = alternative_routes(graph, source, target, request.alternatives + 1, 0.7, heuristic)
            for index, candidate in enumerate((item for item in candidates if item.path != result.path), 1):
                if index > request.alternatives:
                    break
                alternatives.append({"id": f"alternative-{index}", "label": f"Alternative {index}", **path_metrics(graph, candidate, state.coords, request.scenario)})
    else:
        message = "No route is reachable between these points under the selected scenario."
        if closures:
            base = state.scenario_graph(request.scenario)
            if base.neighbors(source) and not graph.neighbors(source):
                raise APIError(409, "origin_cut_off", "Closures block every road from the start point. Remove a closure and try again.")
            reverse = graph.reversed()
            if base.reversed().neighbors(target) and not reverse.neighbors(target):
                raise APIError(409, "destination_cut_off", "Closures block every road into the destination. Remove a closure and try again.")
            if route_search(base, "dijkstra", source, target, state).path:
                raise APIError(409, "no_path", "The start and destination are reachable, but closures disconnect their routes.")
    if request.include_normal_comparison:
        normal_flooded = normal_route_flooded_edges(state, source, target, request.scenario)
    else:
        normal_flooded = None
    response = {
        "route": route,
        "alternatives": alternatives,
        "message": message,
        "algorithm": request.algorithm,
        "nodes_explored": result.nodes_explored,
        "compute_ms": round((perf_counter() - started) * 1000, 2),
        "scenario": request.scenario,
        "snapped_origin": source,
        "snapped_destination": target,
        "snapped_origin_label": state.node_labels.get(source, ""),
        "snapped_destination_label": state.node_labels.get(target, ""),
        "normal_route_flooded_edges": normal_flooded,
    }
    state.route_cache[cache_key] = deepcopy(response)
    state.route_cache.move_to_end(cache_key)
    while len(state.route_cache) > 16:
        state.route_cache.popitem(last=False)
    return response


def alternatives_response(state: AppState, request: Any) -> dict[str, Any]:
    """Compute alternative paths separately so the recommended route can render first."""
    closures = validate_closures(state, request.scenario, request.closures)
    source = check_point(state, request.origin, "origin")
    target = check_point(state, request.destination, "destination")
    graph = state.scenario_graph(request.scenario, closures)
    key = ("alternatives", source, target, request.scenario, request.alternatives,
           tuple(sorted((c["lat"], c["lng"], c["radius_m"]) for c in closures)))
    if key in state.route_cache:
        state.route_cache.move_to_end(key)
        return deepcopy(state.route_cache[key])
    started = perf_counter()
    main = route_search(graph, "astar", source, target, state)
    alternatives = []
    if main.path:
        candidates = alternative_routes(graph, source, target, request.alternatives + 1, 0.7,
                                        state.heuristic or make_haversine_heuristic(state.coords))
        for index, candidate in enumerate((item for item in candidates if item.path != main.path), 1):
            if index > request.alternatives:
                break
            alternatives.append({"id": f"alternative-{index}", "label": f"Alternative {index}",
                                 **path_metrics(graph, candidate, state.coords, request.scenario)})
    response = {"alternatives": alternatives, "compute_ms": round((perf_counter() - started) * 1000, 2)}
    response["normal_route_flooded_edges"] = normal_route_flooded_edges(
        state, source, target, request.scenario
    ) if main.path else 0
    state.route_cache[key] = deepcopy(response)
    state.route_cache.move_to_end(key)
    while len(state.route_cache) > 16:
        state.route_cache.popitem(last=False)
    return response


def nearest_response(state: AppState, request: Any) -> dict[str, Any]:
    closures = validate_closures(state, request.scenario, request.closures)
    source = check_point(state, request.origin, "origin")
    graph = state.scenario_graph(request.scenario, closures)
    facilities = {int(item["node"]) for item in state.hospitals}
    results = nearest_facility(graph, source, facilities, request.k)
    by_node: dict[int, dict[str, Any]] = {}
    for hospital in state.hospitals:
        by_node.setdefault(int(hospital["node"]), hospital)
    hospitals = []
    for result in results:
        node = int(result["facility"])
        hospital = by_node.get(node, {})
        path = result["path"]
        path_result = PathResult(
            float(result["cost"]), list(path), int(result["nodes_explored"]), [],
            length_m=float(result.get("length_m") or 0.0), cost=float(result["cost"]),
            flooded_edges=int(result.get("flooded_edges") or 0),
        )
        metrics = path_metrics(graph, path_result, state.coords, request.scenario)
        hospitals.append({
            "name": hospital.get("name", "Unnamed hospital"), "lat": hospital.get("lat"),
            "lng": hospital.get("lng"), "node": node, **metrics,
        })
    cut_off, _components = find_cut_off_nodes(graph, facilities)
    return {"hospitals": hospitals, "cut_off": source in cut_off, "scenario": request.scenario,
            "snapped_origin": source, "nodes_cut_off": len(cut_off)}


def compare_response(state: AppState, request: Any) -> dict[str, Any]:
    closures = validate_closures(state, request.scenario, request.closures)
    source = check_point(state, request.origin, "origin")
    target = check_point(state, request.destination, "destination")
    graph = state.scenario_graph(request.scenario, closures)
    output = {}
    for algorithm in ("dijkstra", "astar", "bfs"):
        started = perf_counter()
        result = route_search(graph, algorithm, source, target, state)
        elapsed = (perf_counter() - started) * 1000
        visited = [[state.coords[node][0], state.coords[node][1]] for node in result.visited_order]
        flooded_edges = 0
        for u, v in zip(result.path, result.path[1:]):
            edge = next((attributes for neighbor, _weight, attributes in graph.adj.get(u, []) if neighbor == v), {})
            flooded_edges += bool(edge.get("flooded"))
        output[algorithm] = {
            "nodes_explored": result.nodes_explored,
            "compute_ms": round(elapsed, 2),
            "distance_m": round(float(result.length_m or 0), 1),
            "flooded_edges": flooded_edges,
            "final_path": [[state.coords[node][0], state.coords[node][1]] for node in result.path],
            "visited_order": evenly_sample(visited),
        }
    return {"scenario": request.scenario, "results": output, "snapped_origin": source, "snapped_destination": target}

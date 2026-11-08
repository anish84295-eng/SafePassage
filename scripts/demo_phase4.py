"""Demonstrate facility search, cut-off detection, Yen routes, and autocomplete."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from safepassage.algorithms.dijkstra import shortest_path
from safepassage.algorithms.geo import make_haversine_heuristic
from safepassage.algorithms.nearest import nearest_facility
from safepassage.algorithms.yen import alternative_routes, yen_k_shortest_paths
from safepassage.osm_loader import load_processed_graph
from safepassage.scenarios import apply_scenario
from safepassage.structures.trie import build_name_index
from safepassage.structures.union_find import find_cut_off_nodes


def load_hospitals() -> list[dict[str, object]]:
    path = ROOT / "data" / "spots" / "hospitals.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def show_route(label: str, result) -> None:
    preview = result.path[:4]
    if len(result.path) > 8:
        preview = preview + ["..."] + result.path[-4:]
    elif len(result.path) > 4:
        preview += result.path[4:]
    print(
        f"{label}: length_m={result.length_m:.1f} cost={result.cost:.1f} "
        f"flooded_edges={result.flooded_edges} path_nodes={len(result.path)} path={preview}"
    )


def count_flooded_edges(graph, path: list[int]) -> int:
    """Count route edges marked flooded in a scenario graph."""
    count = 0
    for source, target in zip(path, path[1:]):
        matching = [
            (weight, attributes)
            for neighbor, weight, attributes in graph.adj.get(source, [])
            if neighbor == target
        ]
        if matching:
            _weight, attributes = min(matching, key=lambda item: item[0])
            count += bool(attributes.get("flooded"))
    return count


def main() -> None:
    graph, coords = load_processed_graph()
    hospitals = load_hospitals()
    facility_nodes = {int(item["node"]) for item in hospitals}
    hospital_names: dict[int, str] = {}
    for item in hospitals:
        hospital_names.setdefault(int(item["node"]), str(item.get("name") or "Unnamed OSM hospital"))
    if not facility_nodes:
        raise SystemExit("No snapped hospitals found; run download_hospitals.py first.")
    normal = apply_scenario(graph, "normal", coords=coords)
    rainy = apply_scenario(graph, "heavy_rain", coords=coords)
    heuristic = make_haversine_heuristic(coords)
    rng = random.Random(405)

    print("A) Route changed by heavy rain")
    candidates = list(coords)
    rng.shuffle(candidates)
    changed = None
    for source in candidates[:35]:
        for target in candidates[35:55]:
            normal_route = shortest_path(normal, source, target)
            rain_route = shortest_path(rainy, source, target)
            if normal_route.path and rain_route.path and normal_route.path != rain_route.path:
                changed = source, target, normal_route, rain_route
                break
        if changed:
            break
    if changed:
        source, target, normal_route, rain_route = changed
        print(f"Pair {source} -> {target}")
        show_route("normal", normal_route)
        show_route("heavy_rain", rain_route)
        normal_flooded = count_flooded_edges(rainy, normal_route.path)
        rain_flooded = count_flooded_edges(rainy, rain_route.path)
        extra_length = (rain_route.length_m or 0) - (normal_route.length_m or 0)
        extra_percent = extra_length / normal_route.length_m * 100 if normal_route.length_m else 0
        print(f"under heavy_rain: normal route flooded_edges={normal_flooded}; heavy_rain route flooded_edges={rain_flooded}")
        print(f"extra physical length={extra_length:.1f} m ({extra_percent:.1f}%)")
    else:
        source, target = candidates[0], candidates[-1]
        print("No changed route found among sampled pairs.")

    hospital_node = int(hospitals[0]["node"])
    start = next((node for node in candidates if node not in facility_nodes), candidates[0])
    print("\nB) Nearest 3 hospitals")
    for scenario_name, scenario_graph in (("normal", normal), ("heavy_rain", rainy)):
        results = nearest_facility(scenario_graph, start, facility_nodes, k=3)
        print(f"{scenario_name} from {start}:")
        for result in results:
            facility = int(result["facility"])
            print(f"  {hospital_names.get(facility, facility)} (node {facility}) cost={result['cost']:.1f} length_m={result['length_m']:.1f} nodes_explored={result['nodes_explored']}")

    print("\nC) Road closure cut-off simulation")
    route = shortest_path(normal, start, hospital_node)
    close_node = route.path[len(route.path) // 2] if len(route.path) > 2 else start
    closed = apply_scenario(graph, "road_closed", coords=coords, closed_ids={close_node})
    cutoff, components = find_cut_off_nodes(closed, facility_nodes)
    print(f"Closed node {close_node}; cut-off nodes={len(cutoff)}; undirected components={len(components)}")

    print("\nD) Three alternate routes")
    timer = perf_counter()
    yen_routes = yen_k_shortest_paths(normal, source, target, k=3, heuristic=heuristic)
    elapsed_ms = (perf_counter() - timer) * 1000
    print(f"Yen A* spurs k=3 elapsed={elapsed_ms:.2f} ms")
    timer = perf_counter()
    alternates = alternative_routes(normal, source, target, k=3, max_overlap=0.7, heuristic=heuristic)
    alternate_ms = (perf_counter() - timer) * 1000
    print(f"Edge-penalty alternatives k=3 elapsed={alternate_ms:.2f} ms ({len(alternates)} routes)")
    for index, result in enumerate(alternates, 1):
        show_route(f"route {index}", result)

    print("\nE) Road-name autocomplete examples")
    trie = build_name_index(graph, coords)
    for prefix in ("ma", "ba"):
        print(f"{prefix!r}: {trie.search(prefix, limit=5)}")


if __name__ == "__main__":
    main()

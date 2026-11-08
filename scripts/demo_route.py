"""Show Dijkstra and A* routes on the downloaded Mumbai road graph."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from safepassage.algorithms.astar import astar
from safepassage.algorithms.dijkstra import shortest_path
from safepassage.algorithms.geo import make_haversine_heuristic
from safepassage.osm_loader import load_processed_graph
from safepassage.scenarios import apply_scenario


def main() -> None:
    graph, coords = load_processed_graph()
    if graph.node_count() < 2:
        raise SystemExit("Processed graph has fewer than two nodes; run download_osm.py first.")
    nodes = graph.nodes()
    source, target = nodes[0], nodes[-1]
    heuristic = make_haversine_heuristic(coords)
    print(f"Route: {source} -> {target}")
    print(f"{'Scenario':<12} {'Algorithm':<10} {'Length (m)':>12} {'Cost':>12} {'Flooded':>9} {'Explored':>10}")
    for scenario in ("normal", "heavy_rain"):
        scenario_graph = apply_scenario(graph, scenario, coords=coords)
        for name, search in (
            ("Dijkstra", lambda: shortest_path(scenario_graph, source, target)),
            ("A*", lambda: astar(scenario_graph, source, target, heuristic)),
        ):
            result = search()
            print(f"{scenario:<12} {name:<10} {result.length_m or 0:>12.1f} {result.cost or 0:>12.1f} {result.flooded_edges:>9} {result.nodes_explored:>10}")


if __name__ == "__main__":
    main()

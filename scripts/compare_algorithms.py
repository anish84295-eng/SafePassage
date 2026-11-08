"""Compare Dijkstra, A*, and BFS on a geographic grid near Mumbai."""

from __future__ import annotations

import random
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from safepassage.algorithms.astar import astar
from safepassage.algorithms.bfs import bfs
from safepassage.algorithms.dijkstra import shortest_path
from safepassage.algorithms.geo import haversine, make_haversine_heuristic
from safepassage.graph import Graph


def build_grid(side: int = 40) -> tuple[Graph, dict[tuple[int, int], tuple[float, float]]]:
    """Build a bidirectional grid with edge costs in metres."""
    graph = Graph()
    coords: dict[tuple[int, int], tuple[float, float]] = {}
    for row in range(side):
        for col in range(side):
            node = (row, col)
            coords[node] = (19.076 + row * 0.001, 72.877 + col * 0.001)
            graph.add_node(node)
            if row > 0:
                neighbor = (row - 1, col)
                graph.add_edge(node, neighbor, haversine(*coords[node], *coords[neighbor]) * 1.08)
            if col > 0:
                neighbor = (row, col - 1)
                graph.add_edge(node, neighbor, haversine(*coords[node], *coords[neighbor]) * 1.08)
    return graph, coords


def main() -> None:
    graph, coords = build_grid()
    heuristic = make_haversine_heuristic(coords)
    side = 40
    pairs = [((0, 0), (side - 1, side - 1))]
    rng = random.Random(402)
    pairs.extend(
        ((rng.randrange(side), rng.randrange(side)), (rng.randrange(side), rng.randrange(side)))
        for _ in range(3)
    )
    print(f"{'Pair':<19} {'Algorithm':<10} {'Distance (m)':>14} {'Nodes':>8} {'Time (ms)':>11}")
    print("-" * 68)
    for source, target in pairs:
        for name, search in (
            ("Dijkstra", lambda: shortest_path(graph, source, target)),
            ("A*", lambda: astar(graph, source, target, heuristic)),
            ("BFS", lambda: bfs(graph, source, target)),
        ):
            started = perf_counter()
            result = search()
            elapsed_ms = (perf_counter() - started) * 1000
            print(
                f"{str(source) + ' -> ' + str(target):<19} {name:<10} "
                f"{result.distance:>14.1f} {result.nodes_explored:>8} {elapsed_ms:>11.3f}"
            )


if __name__ == "__main__":
    main()

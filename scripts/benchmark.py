"""Run reproducible algorithm benchmarks against the processed Mumbai graph."""

from __future__ import annotations

import heapq  # Benchmark-only comparison; production algorithms use MinHeap.
import json
import os
import platform
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from safepassage.algorithms.astar import astar
from safepassage.algorithms.bfs import bfs
from safepassage.algorithms.dijkstra import shortest_path
from safepassage.algorithms.geo import haversine, make_haversine_heuristic
from safepassage.algorithms.nearest import nearest_facility, precompute_nearest_facility_costs
from safepassage.algorithms.yen import alternative_routes, yen_k_shortest_paths
from safepassage.osm_loader import load_processed_graph
from safepassage.structures.heap import MinHeap

SEED = 20261106
PAIRS_PER_BAND = 200
BANDS = {"short_under_2km": (0.0, 2000.0), "medium_2_to_6km": (2000.0, 6000.0), "long_over_6km": (6000.0, 20_000.0)}


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def summary(values: list[float]) -> dict[str, float]:
    return {"median": statistics.median(values), "p95": percentile(values, 0.95)}


def machine_info() -> dict[str, Any]:
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    memory = MemoryStatus()
    memory.dwLength = ctypes.sizeof(MemoryStatus)
    ram_gb = None
    if hasattr(ctypes, "windll") and ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        ram_gb = round(memory.ullTotalPhys / (1024 ** 3), 2)
    cpu_name = platform.processor()
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    return {"os": platform.platform(), "cpu": cpu_name, "logical_cpus": os.cpu_count(),
            "ram_gb": ram_gb, "python": platform.python_version()}


def sample_pairs(coords: dict[int, tuple[float, float]], seed: int) -> dict[str, list[tuple[int, int, float]]]:
    rng = random.Random(seed)
    nodes = list(coords)
    samples: dict[str, list[tuple[int, int, float]]] = {key: [] for key in BANDS}
    attempts = 0
    limit = PAIRS_PER_BAND * len(BANDS) * 300
    while any(len(items) < PAIRS_PER_BAND for items in samples.values()) and attempts < limit:
        attempts += 1
        source, target = rng.sample(nodes, 2)
        a, b = coords[source], coords[target]
        distance = haversine(a[0], a[1], b[0], b[1])
        for name, (minimum, maximum) in BANDS.items():
            if minimum <= distance < maximum and len(samples[name]) < PAIRS_PER_BAND:
                samples[name].append((source, target, distance))
                break
    missing = {name: len(items) for name, items in samples.items() if len(items) != PAIRS_PER_BAND}
    if missing:
        raise RuntimeError(f"Could not sample 200 pairs for every distance band: {missing}")
    return samples


def benchmark_algorithms(graph, coords, samples) -> dict[str, Any]:
    heuristic = make_haversine_heuristic(coords)
    functions: dict[str, Callable] = {
        "dijkstra": lambda a, b: shortest_path(graph, a, b),
        "astar_haversine": lambda a, b: astar(graph, a, b, heuristic),
        "bfs": lambda a, b: bfs(graph, a, b),
    }
    raw: dict[str, Any] = {}
    for band, pairs in samples.items():
        print(f"Benchmarking 200 pairs: {band}", flush=True)
        first = pairs[0]
        for run in functions.values():
            run(first[0], first[1])  # Warm up graph and interpreter paths.
        band_data = {}
        for name, run in functions.items():
            times: list[float] = []
            explored: list[int] = []
            for source, target, _straight in pairs:
                start = time.perf_counter()
                result = run(source, target)
                times.append((time.perf_counter() - start) * 1000)
                explored.append(result.nodes_explored)
            band_data[name] = {"time_ms": summary(times), "median_nodes_explored": statistics.median(explored),
                               "times_ms": times, "nodes_explored": explored}
        ratios = [a / d if d else 0.0 for a, d in zip(band_data["astar_haversine"]["nodes_explored"], band_data["dijkstra"]["nodes_explored"])]
        band_data["astar_dijkstra_explored_ratio"] = statistics.median(ratios)
        band_data["pair_straight_line_m"] = [row[2] for row in pairs]
        band_data["pairs"] = [[row[0], row[1]] for row in pairs]
        raw[band] = band_data
    return raw


def run_full_dijkstra(graph, source: int, use_heapq: bool) -> int:
    distances = {node: float("inf") for node in graph.nodes()}
    distances[source] = 0.0
    if use_heapq:
        frontier = [(0.0, source)]
    else:
        frontier: MinHeap[int] = MinHeap()
        frontier.push(0.0, source)
    finalized = 0
    while frontier if use_heapq else not frontier.is_empty():
        distance, node = heapq.heappop(frontier) if use_heapq else frontier.pop()
        if distance != distances[node]:
            continue
        finalized += 1
        for neighbor, weight in graph.neighbors(node):
            candidate = distance + weight
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                if use_heapq:
                    heapq.heappush(frontier, (candidate, neighbor))
                else:
                    frontier.push(candidate, neighbor)
    return finalized


def benchmark_heaps(graph, source: int, repeats: int = 7) -> dict[str, Any]:
    run_full_dijkstra(graph, source, False)
    run_full_dijkstra(graph, source, True)
    results = {}
    for name, use_heapq in (("MinHeap", False), ("heapq", True)):
        times = []
        finalized = 0
        for _ in range(repeats):
            start = time.perf_counter()
            finalized = run_full_dijkstra(graph, source, use_heapq)
            times.append((time.perf_counter() - start) * 1000)
        results[name] = {"time_ms": summary(times), "finalized_nodes": finalized, "times_ms": times}
    return results


def benchmark_alternatives(graph, source: int, target: int, coords) -> dict[str, Any]:
    heuristic = make_haversine_heuristic(coords)
    outputs = {}
    for name, run in (("yen_k3", lambda: yen_k_shortest_paths(graph, source, target, 3, heuristic)),
                      ("edge_penalty_k3", lambda: alternative_routes(graph, source, target, 3, 0.7, heuristic))):
        run()  # Warm-up before the reported samples.
        times, counts, lengths = [], [], []
        for _ in range(3):
            start = time.perf_counter()
            routes = run()
            times.append((time.perf_counter() - start) * 1000)
            counts.append(len(routes))
            lengths.append([round(float(route.length_m or 0), 1) for route in routes])
        outputs[name] = {"time_ms": summary(times), "route_counts": counts, "route_lengths_m": lengths, "times_ms": times}
    return outputs


def benchmark_nearest(graph, facility_nodes: set[int], sample_nodes: list[int]) -> dict[str, Any]:
    precompute_nearest_facility_costs(graph, facility_nodes)  # Warm-up
    nearest_facility(graph, sample_nodes[0], facility_nodes, 1)
    precompute_times, repeated_times = [], []
    for _ in range(3):
        start = time.perf_counter()
        precompute_nearest_facility_costs(graph, facility_nodes)
        precompute_times.append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        for node in sample_nodes:
            nearest_facility(graph, node, facility_nodes, 1)
        repeated_times.append((time.perf_counter() - start) * 1000)
    return {"precompute_all_nodes_ms": summary(precompute_times), "precompute_times_ms": precompute_times,
            "single_source_sample_nodes": len(sample_nodes), "single_source_sample_ms": summary(repeated_times),
            "single_source_times_ms": repeated_times}


def make_charts(results: dict[str, Any]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = ROOT / "docs" / "benchmarks"
    output.mkdir(parents=True, exist_ok=True)
    bands = list(BANDS)
    names = ["dijkstra", "astar_haversine", "bfs"]
    labels = ["Dijkstra", "A*", "BFS"]
    width = 0.24
    figure, axis = plt.subplots(figsize=(9, 5))
    for index, (name, label) in enumerate(zip(names, labels)):
        values = [results["algorithms"][band][name]["time_ms"]["median"] for band in bands]
        positions = [i + (index - 1) * width for i in range(len(bands))]
        axis.bar(positions, values, width, label=label)
    axis.set_xticks(range(len(bands)), ["Short <2 km", "Medium 2–6 km", "Long >6 km"])
    axis.set_ylabel("Median compute time (ms)")
    axis.set_title("Route search time by straight-line distance band")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(output / "algorithm_latency.png", dpi=150)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(9, 5))
    for name, label in zip(names, labels):
        values = [results["algorithms"][band][name]["median_nodes_explored"] for band in bands]
        axis.plot(range(len(bands)), values, marker="o", label=label)
    axis.set_xticks(range(len(bands)), ["Short <2 km", "Medium 2–6 km", "Long >6 km"])
    axis.set_ylabel("Median finalized nodes")
    axis.set_title("Search work by distance band")
    axis.legend()
    axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(output / "algorithm_nodes.png", dpi=150)
    plt.close(figure)


def main() -> None:
    graph, coords = load_processed_graph()
    hospitals_path = ROOT / "data" / "spots" / "hospitals.json"
    hospitals = json.loads(hospitals_path.read_text(encoding="utf-8"))
    facility_nodes = {int(item["node"]) for item in hospitals}
    samples = sample_pairs(coords, SEED)
    algorithms = benchmark_algorithms(graph, coords, samples)
    print("Benchmarking custom heap against heapq", flush=True)
    long_source, long_target = algorithms["long_over_6km"]["pairs"][0]
    heap_source = algorithms["medium_2_to_6km"]["pairs"][0][0]
    rng = random.Random(SEED + 1)
    sample_nodes = rng.sample(list(coords), 12)
    heap_comparison = benchmark_heaps(graph, heap_source)
    print("Benchmarking k=3 route alternatives", flush=True)
    alternatives = benchmark_alternatives(graph, long_source, long_target, coords)
    print("Benchmarking nearest-hospital searches", flush=True)
    nearest_results = benchmark_nearest(graph, facility_nodes, sample_nodes)
    results = {
        "seed": SEED, "pairs_per_band": PAIRS_PER_BAND,
        "straight_line_distance_bands_m": {key: list(value) for key, value in BANDS.items()},
        "graph": {"nodes": graph.node_count(), "directed_edges": graph.edge_count(), "hospitals": len(facility_nodes)},
        "machine": machine_info(), "algorithms": algorithms,
        "heap_comparison": heap_comparison,
        "alternatives": alternatives,
        "nearest_facilities": nearest_results,
    }
    output = ROOT / "docs" / "benchmarks"
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    make_charts(results)
    print(f"Saved benchmark results and charts under {output}")
    for band, data in algorithms.items():
        print(f"{band}: Dijkstra median={data['dijkstra']['time_ms']['median']:.2f} ms, "
              f"A* median={data['astar_haversine']['time_ms']['median']:.2f} ms, "
              f"BFS median={data['bfs']['time_ms']['median']:.2f} ms, "
              f"A*/Dijkstra nodes={data['astar_dijkstra_explored_ratio']:.3f}")
    print(f"Heap: MinHeap={results['heap_comparison']['MinHeap']['time_ms']['median']:.2f} ms, "
          f"heapq={results['heap_comparison']['heapq']['time_ms']['median']:.2f} ms")
    print(f"Alternatives k=3: Yen={results['alternatives']['yen_k3']['time_ms']['median']:.2f} ms, "
          f"edge penalty={results['alternatives']['edge_penalty_k3']['time_ms']['median']:.2f} ms")
    print(f"Nearest: one multi-source pass={results['nearest_facilities']['precompute_all_nodes_ms']['median']:.2f} ms; "
          f"12 single-source searches={results['nearest_facilities']['single_source_sample_ms']['median']:.2f} ms")


if __name__ == "__main__":
    main()

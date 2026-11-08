# SafePassage benchmark report

All figures below were measured by [`scripts/benchmark.py`](../scripts/benchmark.py) on the real processed Mumbai graph. Raw per-pair timings and counts are in [`results.json`](benchmarks/results.json); charts are in this directory.

## Machine and graph

- OS: Windows 11 (10.0.26300-SP0)
- CPU: Intel(R) N100, 4 logical CPUs
- RAM: 7.70 GiB
- Python: 3.14.7
- Graph: 17,787 nodes and 40,950 directed edges
- Hospital data: 115 entries snapped to 111 distinct graph nodes

## Service profile from this fix round

Startup now prewarms both normal and heavy-rain scenario graphs, the reversed base graph, hospital costs, and the A* heuristic coordinates. Measured startup was **4.01 s** with process RSS **124.3 MiB** at readiness.

The real-data pair was origin `(19.1597, 72.8399)` to destination `(19.1105, 72.8420)`. Each request asked for A* and the same closure circle where applicable. The first full `/api/route` call with three alternatives took **3.11 s** normal, **1.81 s** heavy rain, and **2.34 s** with one closure; identical repeats took **40 ms**, **22 ms**, and **17 ms**. Those first calls included the alternatives and normal-route flood comparison in the main response.

The UI now requests the main route first, with alternatives and the normal-route comparison deferred. On the warmed application, first main-route HTTP times were **348 ms** normal, **115 ms** heavy rain, and **631 ms** with one closure; repeats were **20 ms**, **25 ms**, and **11 ms**. Follow-up calls loading two alternatives and the normal-route comparison took **699 ms**, **931 ms**, and **812 ms** respectively. Direct `/api/route` requests still support alternatives in one response; repeated identical three-alternative requests stayed below one second in the measured run (56 ms normal, 31 ms rain, 220 ms closures).

A `cProfile` run on uncached scenario pairs showed alternative generation as the largest cost: `alternative_routes` accumulated **2.29 s** normal, **3.36 s** rain, and **2.47 s** closures. Repeated A* searches accumulated **1.33 s**, **2.75 s**, and **1.55 s**. Scenario graph creation accumulated **1.19 s** for the first normal graph and **1.94 s** for the first closure graph. These instrumented totals include profiler overhead. Prewarming normal and heavy-rain graphs removes the normal copy from the first route; the one-pass bounded closure graph cache removes repeat closure copies. UI main-route timings exclude lazy follow-up work by design.

## Method

A deterministic seed (`20261106`) selected 200 random node pairs for each band by haversine straight-line distance: short below 2 km, medium 2–6 km, and long above 6 km. Each algorithm received a warm-up call before that band’s timed samples. Timings use `time.perf_counter`; table latency is median / p95 in milliseconds, and node counts are medians. The A*/Dijkstra column is the median pairwise ratio of finalized nodes.

The heap comparison runs full single-source Dijkstra from the same node with the custom MinHeap and with Python `heapq`; only this benchmark script imports `heapq`. Yen and edge-penalty alternatives use the same long-band pair, A* haversine heuristic, and k=3, after one warm-up and three timed runs. The nearest comparison is one multi-source pass for all graph nodes versus 12 single-source nearest-facility searches per timed sample; those have different coverage and are not an apples-to-apples speed ratio.

## Route search

| Straight-line band | Algorithm | Median / p95 (ms) | Median nodes explored | A*/Dijkstra explored ratio |
| --- | --- | ---: | ---: | ---: |
| Short <2 km | Dijkstra | 7.70 / 20.91 | 1,189 | — |
| Short <2 km | A* (haversine) | 1.78 / 9.72 | 246 | 0.225 |
| Short <2 km | BFS | 2.13 / 9.66 | 1,304 | — |
| Medium 2–6 km | Dijkstra | 47.08 / 88.25 | 7,022 | — |
| Medium 2–6 km | A* (haversine) | 19.39 / 51.38 | 1,498 | 0.221 |
| Medium 2–6 km | BFS | 14.04 / 30.47 | 6,678 | — |
| Long >6 km | Dijkstra | 89.08 / 121.07 | 14,648 | — |
| Long >6 km | A* (haversine) | 54.99 / 148.37 | 4,484 | 0.344 |
| Long >6 km | BFS | 24.08 / 33.79 | 13,750 | — |

BFS is fast because it minimizes edge count and does not optimize road cost, so its route is not a weighted-distance substitute. A* reduced median work in all bands, but it was not uniformly faster: its long-band p95 (148.37 ms) exceeded Dijkstra’s (121.07 ms). Individual A* runs can still lose due to heuristic overhead and graph shape.

## Other comparisons

| Comparison | Median / p95 (ms) | Notes |
| --- | ---: | --- |
| Custom MinHeap, full Dijkstra | 104.26 / 114.45 | Same graph and source as heapq run |
| `heapq`, full Dijkstra | 53.14 / 60.95 | About 1.96× lower median in this benchmark |
| Exact Yen, k=3 | 5,695.86 / 5,803.90 | Three routes returned; route lengths 11,880.9, 11,881.5, 11,881.5 m |
| Edge-penalty alternatives, k=3 | 471.77 / 557.34 | Three routes returned; lengths 11,880.9, 12,506.5, 13,073.0 m |
| Multi-source nearest-facility pass | 280.65 / 288.68 | Computes costs for every node in one reversed-graph run |
| 12 single-source nearest searches | 55.33 / 57.71 | Only answers for 12 sampled origins |

Exact Yen’s second and third routes in this sample were only about 0.6 m longer than the best route, so a mathematically valid k-shortest route set may still be visually redundant. The edge-penalty strategy returned more separated lengths and was about 9× faster here, but it is a heuristic alternative generator rather than exact k-shortest enumeration. The nearest comparison favors repeated searches only because it answers for 12 origins rather than every graph node.

## Reproduction and limits

Run from the repository root with `backend\.venv\Scripts\python.exe scripts\benchmark.py`, or from `backend` with `.venv\Scripts\python.exe ..\scripts\benchmark.py`. Timings depend on CPU scheduling, Python build, and cache state; these are one-machine measurements, not service-level guarantees. Re-run after code, data, or hardware changes. The script uses the production MinHeap for application-like paths; `heapq` is isolated to the benchmark comparison.

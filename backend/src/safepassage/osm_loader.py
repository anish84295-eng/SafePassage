"""Parse and persist a simplified OpenStreetMap road graph."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from safepassage.algorithms.geo import haversine
from safepassage.graph import Graph

ROOT = Path(__file__).resolve().parents[3]
PROCESSED_PATH = ROOT / "data" / "processed" / "mumbai_graph.json"


def graph_from_overpass(data: dict[str, Any]) -> tuple[Graph, dict[int, tuple[float, float]]]:
    """Convert Overpass JSON roads into a largest-component junction graph."""
    nodes = {
        element["id"]: (float(element["lat"]), float(element["lon"]))
        for element in data.get("elements", [])
        if element.get("type") == "node"
    }
    ways = [
        element for element in data.get("elements", [])
        if element.get("type") == "way" and element.get("tags", {}).get("highway")
    ]
    use_count: dict[int, int] = defaultdict(int)
    for way in ways:
        for node_id in way.get("nodes", []):
            use_count[node_id] += 1

    graph = Graph()
    coords: dict[int, tuple[float, float]] = {}
    for way in ways:
        refs = way.get("nodes", [])
        tags = way.get("tags", {})
        road_type = str(tags.get("highway", "unknown"))
        name = str(tags.get("name", ""))
        oneway = str(tags.get("oneway", "")).lower()
        if oneway == "-1":
            refs = list(reversed(refs))
        bidirectional = oneway not in {"yes", "true", "1", "-1"} and tags.get("junction") != "roundabout"

        # Retain endpoints and shared junctions; measure through intermediate shape points.
        anchors = [index for index, node_id in enumerate(refs) if index in (0, len(refs) - 1) or use_count[node_id] > 1]
        for index in anchors:
            node_id = refs[index]
            if node_id in nodes:
                graph.add_node(node_id)
                coords[node_id] = nodes[node_id]
        for start_index, end_index in zip(anchors, anchors[1:]):
            segment_refs = refs[start_index : end_index + 1]
            if any(node_id not in nodes for node_id in segment_refs):
                continue
            length = sum(
                haversine(*nodes[left], *nodes[right])
                for left, right in zip(segment_refs, segment_refs[1:])
            )
            attributes = {"length_m": length, "road_type": road_type, "name": name}
            graph.add_edge(refs[start_index], refs[end_index], length, bidirectional, attributes)

    if not graph.nodes():
        return graph, coords
    reverse_neighbors: dict[int, set[int]] = defaultdict(set)
    for source in graph.nodes():
        for target, _weight in graph.neighbors(source):
            reverse_neighbors[target].add(source)
    components: list[set[int]] = []
    unseen = set(graph.nodes())
    while unseen:
        start = unseen.pop()
        component = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            neighbors = {neighbor for neighbor, _weight in graph.neighbors(node)} | reverse_neighbors[node]
            for neighbor in neighbors & unseen:
                unseen.remove(neighbor)
                component.add(neighbor)
                queue.append(neighbor)
        components.append(component)
    largest = max(components, key=len)
    filtered = Graph()
    filtered_coords = {node: coords[node] for node in largest}
    for node in largest:
        filtered.add_node(node)
    for node in largest:
        for neighbor, weight, attributes in graph.edge_records(node):
            if neighbor in largest:
                filtered.add_edge(node, neighbor, weight, bidirectional=False, attributes=attributes)
    return filtered, filtered_coords


def save_processed_graph(graph: Graph, coords: dict[int, tuple[float, float]], path: Path = PROCESSED_PATH) -> None:
    """Write graph nodes, coordinates, and attributed directed edges as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    edges = []
    for source in graph.nodes():
        for target, weight, attributes in graph.edge_records(source):
            edges.append({"source": source, "target": target, "weight": weight, "attributes": attributes})
    payload = {"nodes": [{"id": node, "lat": coords[node][0], "lng": coords[node][1]} for node in graph.nodes()], "edges": edges}
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def load_processed_graph(path: Path = PROCESSED_PATH) -> tuple[Graph, dict[int, tuple[float, float]]]:
    """Quickly load a graph previously written by ``save_processed_graph``."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    graph = Graph()
    coords = {}
    for node in payload["nodes"]:
        node_id = int(node["id"])
        graph.add_node(node_id)
        coords[node_id] = (float(node["lat"]), float(node["lng"]))
    for edge in payload["edges"]:
        graph.add_edge(int(edge["source"]), int(edge["target"]), float(edge["weight"]), False, edge["attributes"])
    return graph, coords

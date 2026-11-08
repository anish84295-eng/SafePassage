"""Create scenario-specific copies of a road graph."""

from __future__ import annotations

import json
from math import inf
from pathlib import Path
from typing import Any

from safepassage.algorithms.geo import haversine
from safepassage.graph import Graph

ROOT = Path(__file__).resolve().parents[3]
FLOOD_SPOTS_PATH = ROOT / "data" / "spots" / "flood_spots.json"


def _load_flood_spots() -> list[dict[str, Any]]:
    if not FLOOD_SPOTS_PATH.exists():
        return []
    return json.loads(FLOOD_SPOTS_PATH.read_text(encoding="utf-8"))


def apply_scenario(
    graph: Graph,
    scenario: str,
    coords: dict[int, tuple[float, float]] | None = None,
    flood_spots: list[dict[str, Any]] | None = None,
    rain_factor: float = 3.0,
    general_factor: float = 1.2,
    closed_ids: set[int] | None = None,
    closed_names: set[str] | None = None,
    closure_point: tuple[float, float] | None = None,
    closure_radius_m: float | None = None,
    closure_circles: list[tuple[float, float, float]] | None = None,
) -> Graph:
    """Return a new graph adjusted for normal, heavy-rain, or closure conditions."""
    if scenario not in {"normal", "heavy_rain", "road_closed"}:
        raise ValueError(f"unknown scenario: {scenario}")
    result = Graph()
    for node in graph.nodes():
        result.add_node(node)
    spots = flood_spots if flood_spots is not None else _load_flood_spots()
    closed_ids = closed_ids or set()
    closed_names = closed_names or set()

    for source in graph.nodes():
        for target, weight, original_attributes in graph.edge_records(source):
            attributes = dict(original_attributes)
            remove = scenario == "road_closed" and (
                source in closed_ids
                or target in closed_ids
                or attributes.get("name") in closed_names
            )
            midpoint = None
            if coords and source in coords and target in coords:
                midpoint = (
                    (coords[source][0] + coords[target][0]) / 2,
                    (coords[source][1] + coords[target][1]) / 2,
                )
            if scenario == "road_closed" and midpoint:
                circles = list(closure_circles or [])
                if closure_point and closure_radius_m is not None:
                    circles.append((*closure_point, closure_radius_m))
                remove = remove or any(haversine(*midpoint, lat, lng) <= radius for lat, lng, radius in circles)
            if remove:
                continue

            adjusted_weight = weight
            if scenario == "heavy_rain":
                adjusted_weight *= general_factor
                flooded = False
                if midpoint is not None:
                    for spot in spots:
                        center = (float(spot["lat"]), float(spot["lng"]))
                        if haversine(*midpoint, *center) <= float(spot.get("radius_m", spot.get("radius", 0))):
                            flooded = True
                            break
                if flooded:
                    adjusted_weight *= rain_factor
                    attributes["flooded"] = True
            result.add_edge(source, target, adjusted_weight, bidirectional=False, attributes=attributes)
    return result

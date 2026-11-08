"""Geographic distance and heuristic helpers."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Callable, Hashable

EARTH_RADIUS_METRES = 6_371_000.0


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in metres between two coordinates."""
    latitude_delta = radians(lat2 - lat1)
    longitude_delta = radians(lng2 - lng1)
    value = (
        sin(latitude_delta / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METRES * asin(sqrt(value))


def make_haversine_heuristic(
    coords: dict[Hashable, tuple[float, float]],
) -> Callable[[Hashable, Hashable], float]:
    """Create an A* heuristic using a node-to-coordinate mapping."""
    def heuristic(node: Hashable, target: Hashable) -> float:
        lat1, lng1 = coords[node]
        lat2, lng2 = coords[target]
        return haversine(lat1, lng1, lat2, lng2)

    return heuristic

"""Uniform-grid index for snapping coordinates to road graph nodes."""

from __future__ import annotations

from math import floor
from typing import Hashable

from safepassage.algorithms.geo import haversine


class SpatialIndex:
    """Index node coordinates in small latitude/longitude grid cells."""

    def __init__(self, coords: dict[Hashable, tuple[float, float]], cell_size: float = 0.01):
        self.coords = coords
        self.cell_size = cell_size
        self.cells: dict[tuple[int, int], list[Hashable]] = {}
        for node, (lat, lng) in coords.items():
            self.cells.setdefault(self._cell(lat, lng), []).append(node)

    def _cell(self, lat: float, lng: float) -> tuple[int, int]:
        return floor(lat / self.cell_size), floor(lng / self.cell_size)

    def snap_to_node(self, lat: float, lng: float) -> Hashable:
        """Return the exactly nearest indexed node by haversine distance."""
        if not self.coords:
            raise ValueError("cannot snap against an empty coordinate index")
        query_cell = self._cell(lat, lng)
        ranked_cells = []
        for (lat_cell, lng_cell), nodes in self.cells.items():
            low_lat, high_lat = lat_cell * self.cell_size, (lat_cell + 1) * self.cell_size
            low_lng, high_lng = lng_cell * self.cell_size, (lng_cell + 1) * self.cell_size
            closest_lat = min(max(lat, low_lat), high_lat)
            closest_lng = min(max(lng, low_lng), high_lng)
            lower_bound = haversine(lat, lng, closest_lat, closest_lng)
            cell_offset = abs(lat_cell - query_cell[0]) + abs(lng_cell - query_cell[1])
            ranked_cells.append((lower_bound, cell_offset, nodes))
        best_node = None
        best_distance = float("inf")
        for lower_bound, _offset, nodes in sorted(ranked_cells, key=lambda item: (item[0], item[1])):
            if lower_bound > best_distance:
                break
            for node in nodes:
                distance = haversine(lat, lng, *self.coords[node])
                if distance < best_distance:
                    best_distance, best_node = distance, node
        return best_node


def snap_to_node(
    lat: float,
    lng: float,
    coords: dict[Hashable, tuple[float, float]],
    cell_size: float = 0.01,
) -> Hashable:
    """One-shot convenience wrapper for coordinate snapping."""
    return SpatialIndex(coords, cell_size).snap_to_node(lat, lng)

import random

from safepassage.algorithms.geo import haversine
from safepassage.spatial import SpatialIndex


def test_grid_snap_matches_brute_force():
    rng = random.Random(73)
    coords = {node: (19 + rng.uniform(-0.2, 0.2), 72.8 + rng.uniform(-0.2, 0.2)) for node in range(500)}
    index = SpatialIndex(coords, cell_size=0.01)
    for _ in range(100):
        lat, lng = 19 + rng.uniform(-0.25, 0.25), 72.8 + rng.uniform(-0.25, 0.25)
        expected = min(coords, key=lambda node: haversine(lat, lng, *coords[node]))
        assert index.snap_to_node(lat, lng) == expected

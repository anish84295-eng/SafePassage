import pytest

from safepassage.algorithms.geo import haversine


def test_churchgate_to_borivali_station_distance():
    # Approximate station coordinates; straight-line distance is about 30 km.
    churchgate = (18.9352, 72.8270)
    borivali = (19.2290, 72.8574)
    distance = haversine(*churchgate, *borivali)
    assert distance == pytest.approx(32_800, abs=2_500)


def test_haversine_is_symmetric():
    assert haversine(19.076, 72.877, 19.229, 72.857) == pytest.approx(
        haversine(19.229, 72.857, 19.076, 72.877)
    )

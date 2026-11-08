from safepassage.hospitals import classify_hospital, filter_hospital_entries


def test_emergency_hospital_evidence():
    assert classify_hospital({"name": "Central Hospital"})[0] == "emergency"
    assert classify_hospital({"name": "Community Care", "beds": "40"})[0] == "emergency"
    assert classify_hospital({"name": "", "emergency": "yes"})[0] == "emergency"


def test_specialty_and_unsupported_entries_are_excluded_with_reasons():
    tier, reason = classify_hospital({"name": "Eye Hospital and Lens Clinic", "emergency": "yes"})
    assert tier is None
    assert "clinic" in reason or "eye" in reason or "lens" in reason
    tier, reason = classify_hospital({"name": "Local Care Centre"})
    assert tier is None
    assert "no emergency-capability evidence" == reason
    assert classify_hospital({"name": "", "emergency": "no"})[0] is None


def test_junk_names_are_excluded_even_when_emergency_tagged():
    for name in ("hehehe", "Xy", "Rhythmzz", "123 !!!"):
        tier, reason = classify_hospital({"name": name, "emergency": "yes"})
        assert tier is None
        assert reason.startswith("junk name:")


def test_nearby_normalized_duplicates_are_excluded_auditably():
    entries = [
        {"name": "Central Hospital", "lat": 19.0, "lng": 72.8, "osm_id": 1, "osm_type": "node"},
        {"name": " CENTRAL  Hospital! ", "lat": 19.0005, "lng": 72.8, "osm_id": 2, "osm_type": "way"},
        {"name": "Central Hospital", "lat": 19.01, "lng": 72.8, "osm_id": 3, "osm_type": "node"},
    ]
    kept, excluded = filter_hospital_entries(entries)
    assert [entry["osm_id"] for entry in kept] == [1, 3]
    assert len(excluded) == 1
    assert "nearby duplicate" in excluded[0]["exclusion_reason"]

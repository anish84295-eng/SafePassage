"""Download and snap named or unnamed OSM hospitals within the road bbox."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from download_osm import EAST, NORTH, OVERPASS_URL, SOUTH, WEST
from safepassage.osm_loader import load_processed_graph
from safepassage.spatial import SpatialIndex
from safepassage.algorithms.geo import haversine
from safepassage.hospitals import filter_hospital_entries

RAW_PATH = ROOT / "data" / "raw" / "mumbai_hospitals.json"
OUTPUT_PATH = ROOT / "data" / "spots" / "hospitals.json"
EXCLUDED_PATH = ROOT / "data" / "spots" / "hospitals_excluded.json"


def main() -> None:
    query = (
        f'[out:json][timeout:60];(node["amenity"="hospital"]({SOUTH},{WEST},{NORTH},{EAST});'
        f'way["amenity"="hospital"]({SOUTH},{WEST},{NORTH},{EAST});'
        f'relation["amenity"="hospital"]({SOUTH},{WEST},{NORTH},{EAST}););out center tags;'
    )
    headers = {"User-Agent": "SafePassage student routing project/1.0 (contact: safepassage-project)"}
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=90.0, headers=headers) as client:
            for attempt in range(2):
                try:
                    response = client.post(OVERPASS_URL, data={"data": query})
                    response.raise_for_status()
                    RAW_PATH.write_text(json.dumps(response.json()), encoding="utf-8")
                    break
                except (httpx.HTTPError, ValueError):
                    if attempt == 1:
                        raise
                    print("Overpass hospital request failed; waiting 10 seconds before one retry.")
                    time.sleep(10)
    except (httpx.HTTPError, ValueError) as error:
        print(f"Hospital download failed after one retry: {error}", file=sys.stderr)
        raise SystemExit(1)

    _graph, coords = load_processed_graph()
    index = SpatialIndex(coords)
    payload = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    entries = []
    unnamed = 0
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        center = element.get("center", {})
        lat = element.get("lat", center.get("lat"))
        lng = element.get("lon", center.get("lon"))
        if lat is None or lng is None:
            continue
        if not tags.get("name"):
            unnamed += 1
        record = {
            "name": tags.get("name", ""),
            "lat": float(lat),
            "lng": float(lng),
            "node": index.snap_to_node(float(lat), float(lng)),
            "osm_type": element.get("type"),
            "osm_id": element.get("id"),
            "amenity": tags.get("amenity", ""),
            "emergency": tags.get("emergency", ""),
            "healthcare": tags.get("healthcare", ""),
            "beds": tags.get("beds", ""),
            "operator": tags.get("operator", ""),
            "healthcare:speciality": tags.get("healthcare:speciality", ""),
        }
        entries.append(record)
    hospitals, excluded = filter_hospital_entries(entries)
    tier_counts: dict[str, int] = {}
    for hospital in hospitals:
        tier = str(hospital["tier"])
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(hospitals, indent=2), encoding="utf-8")
    EXCLUDED_PATH.write_text(json.dumps(excluded, indent=2), encoding="utf-8")
    print(f"BBox (south, west, north, east): {SOUTH}, {WEST}, {NORTH}, {EAST}")
    print(f"Hospitals returned by Overpass: {len(payload.get('elements', []))}")
    print(f"Hospitals processed/snapped: {len(hospitals) + len(excluded)}")
    print(f"Kept for routing: {len(hospitals)}; excluded for review: {len(excluded)}")
    print(f"Without a name (retained): {unnamed}")
    print(f"Counts by tier: {tier_counts}")
    center = ((SOUTH + NORTH) / 2, (WEST + EAST) / 2)
    nearest = sorted(hospitals, key=lambda item: haversine(*center, float(item["lat"]), float(item["lng"])))[:15]
    print("15 kept entries nearest bbox center:")
    for item in nearest:
        print(f"  {item['name']} ({item['osm_type']} {item['osm_id']})")
    print(f"Raw response size: {RAW_PATH.stat().st_size:,} bytes")
    print(f"Saved: {OUTPUT_PATH}")
    print(f"Excluded review file: {EXCLUDED_PATH}")


if __name__ == "__main__":
    main()

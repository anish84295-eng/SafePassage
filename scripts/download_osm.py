"""Download a small drivable Mumbai road extract from Overpass."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from safepassage.osm_loader import graph_from_overpass, save_processed_graph

SOUTH, WEST, NORTH, EAST = 19.05, 72.82, 19.19, 72.87
RAW_PATH = ROOT / "data" / "raw" / "mumbai_roads.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HIGHWAYS = [
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "motorway_link", "trunk_link", "primary_link",
    "secondary_link", "tertiary_link",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="download even if raw data exists")
    args = parser.parse_args()
    if RAW_PATH.exists() and not args.force:
        print(f"Raw extract already exists; skipping download: {RAW_PATH}")
    else:
        highway_filter = "|".join(HIGHWAYS)
        query = (
            f'[out:json][timeout:60];(way["highway"~"^({highway_filter})$"]'
            f'({SOUTH},{WEST},{NORTH},{EAST}););(._;>;);out body;'
        )
        headers = {"User-Agent": "SafePassage student routing project/1.0 (contact: safepassage-project)"}
        RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.Client(timeout=90.0, headers=headers) as client:
                for attempt in range(2):
                    try:
                        response = client.post(OVERPASS_URL, data={"data": query})
                        response.raise_for_status()
                        payload = response.json()
                        RAW_PATH.write_text(json.dumps(payload), encoding="utf-8")
                        break
                    except (httpx.HTTPError, ValueError):
                        if attempt == 1:
                            raise
                        print("Overpass request failed; waiting 10 seconds before one retry.")
                        time.sleep(10)
        except (httpx.HTTPError, ValueError) as error:
            print(f"Overpass download failed after one retry: {error}", file=sys.stderr)
            raise SystemExit(1)

    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    graph, coords = graph_from_overpass(raw)
    output_path = ROOT / "data" / "processed" / "mumbai_graph.json"
    save_processed_graph(graph, coords, output_path)
    print(f"BBox (south, west, north, east): {SOUTH}, {WEST}, {NORTH}, {EAST}")
    print(f"Nodes: {graph.node_count()}")
    print(f"Directed edges: {graph.edge_count()}")
    print(f"Raw download size: {RAW_PATH.stat().st_size:,} bytes")
    print(f"Processed graph: {output_path}")


if __name__ == "__main__":
    main()

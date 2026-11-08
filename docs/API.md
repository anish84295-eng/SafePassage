# SafePassage API

The API is served by the same-origin frontend at `/api`. From the repository root in Windows PowerShell, start it with:

```powershell
.\scripts\run.ps1
```

The script runs this exact command from `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn safepassage.api.main:app --app-dir src --reload --reload-dir src
```

Open the app at [http://127.0.0.1:8000](http://127.0.0.1:8000). The backend loads the OSM graph and indexes once during application startup.

## Routes

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness check |
| GET | `/api/meta` | Bounding box, graph counts, scenarios and attribution |
| GET | `/api/hospitals` | Filtered OSM hospitals used for routing |
| GET | `/api/flood-zones` | Illustrative flood zones |
| GET | `/api/search?q=...&limit=8` | Case-insensitive road-name autocomplete |
| POST | `/api/route` | Route and optional alternatives |
| POST | `/api/alternatives` | Compute alternate paths after the main route |
| POST | `/api/nearest-hospitals` | Nearest reachable hospitals |
| POST | `/api/compare` | Dijkstra, A* and BFS search traces |

All route points use `{ "lat": number, "lng": number }` and must fall inside the Mumbai data area. A point more than 500 m from a graph node returns HTTP 400 (`no_road_nearby`); points outside the area return HTTP 422 (`outside_area`). Closure-related route failures return HTTP 409 with one of `origin_cut_off`, `destination_cut_off`, or `no_path`. Every API error uses `{ "error": { "code": string, "message": string } }`. A route that is unreachable without a closure-caused cutoff remains HTTP 200 with `route: null` and a `message`.

| Error code | HTTP | Message |
| --- | ---: | --- |
| `origin_cut_off` | 409 | Closures block every road from the start point. Remove a closure and try again. |
| `destination_cut_off` | 409 | Closures block every road into the destination. Remove a closure and try again. |
| `no_path` | 409 | The start and destination are reachable, but closures disconnect their routes. |
| `no_road_nearby` | 400 | No road node is within 500 m of the specified point. |
| `outside_area` | 422 | The point must be inside the Mumbai road-data area. |

## Route

```json
POST /api/route
{
  "origin": {"lat": 19.1597, "lng": 72.8399},
  "destination": {"lat": 19.1105, "lng": 72.8420},
  "scenario": "heavy_rain",
  "algorithm": "astar",
  "alternatives": 2,
  "closures": []
}
```

The response contains the safety-aware A* route, `alternatives` (when requested), scenario, snapped node IDs, search count and elapsed milliseconds. `include_normal_comparison` defaults to `true`; the UI sets it to `false` on the first request and then obtains that comparison alongside alternatives from `/api/alternatives`, so the route summary appears without waiting for either search. The UI always requests this recommended route independently of Algorithm view; `/api/compare` supplies only search traces and per-algorithm statistics. Route fields include physical `distance_m`, optimized `cost`, estimated `duration_s`, flooded edge count and length, a simulated safety score, and a coordinate path.

ETA uses an estimated speed by road class: motorway 60, trunk 45, primary 35, secondary 30, tertiary 25, and local roads 20 km/h (link roads have lower explicit values). Heavy rain applies a further 25% speed reduction. The safety score is simulated as `round(100 * (1 - flooded_length_m / distance_m))`, clamped to 0–100; it is not a real-world safety prediction. Flood zones are illustrative, not official risk data.

The full speed estimates in km/h are: motorway 60, trunk 45, primary 35, secondary 30, tertiary 25, unclassified/residential 20, motorway_link 30, trunk_link/primary_link 25, and secondary_link/tertiary_link 20.

## Nearest hospitals

```json
POST /api/nearest-hospitals
{
  "origin": {"lat": 19.1597, "lng": 72.8399},
  "scenario": "normal",
  "k": 3,
  "closures": []
}
```

Returns reachable filtered hospitals with their path, distance, duration and cost. `cut_off` is true when the snapped origin cannot reach any kept hospital in the directed road graph.

## Compare algorithms

```json
POST /api/compare
{
  "origin": {"lat": 19.1597, "lng": 72.8399},
  "destination": {"lat": 19.1105, "lng": 72.8420},
  "scenario": "normal"
}
```

The response has a result for Dijkstra, A* and BFS, with expansion count, runtime, distance, flooded edge count, exact final path and an evenly sampled visited order capped at 1,500 points. The UI draws these traces and paths as a separate visualization; selecting an algorithm never replaces the recommended route card, alternatives, or safety score.

## Closures and errors

Closures may be combined with any scenario. For example, use `scenario: "heavy_rain"` with a nonempty `closures` list to apply rain costs first and then remove roads inside each closure circle. The legacy `scenario: "road_closed"` request remains supported and means normal conditions with closures. Up to five circles may be sent; each radius must be greater than zero and at most 1,000 m. Requests with invalid closure counts or radii return a consistent JSON error.

When closures block every outgoing road at the snapped origin, the API returns `origin_cut_off`; when they block every incoming road at the destination, it returns `destination_cut_off`. If both endpoints retain roads but closures disconnect them, the API returns `no_path`. The UI offers to remove the latest closure for these failures and warns when a closure circle contains either endpoint.

## Example real-data result

The data verification used two snapped nodes near the western suburbs. Example response fields (the coordinate path is abbreviated; timings vary by machine and cache state):

```json
{
  "route": {"distance_m": 9873.5, "cost": 9873.5, "flooded_edges": 0},
  "alternatives": [],
  "algorithm": "astar",
  "scenario": "normal",
  "nodes_explored": 5550,
  "compute_ms": 1079.7,
  "normal_route_flooded_edges": 30
}
```

The example above is an older sample; current round measurements and the first-route/lazy-alternatives split are in [BENCHMARKS.md](BENCHMARKS.md#service-profile-from-this-fix-round).

Road and facility source data is © OpenStreetMap contributors (ODbL).

## Tile configuration and deployment safety

`GET /api/meta` returns a `tiles` object with the URL template, attribution, and optional API key. Set these environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `TILE_URL` | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | Leaflet tile URL template; `{api_key}` is replaced in the browser |
| `TILE_ATTRIBUTION` | OpenStreetMap contributors link | Attribution shown on the map |
| `TILE_API_KEY` | empty | Optional key passed to the browser as a URL-template substitution |

The default public OpenStreetMap tile server is suitable for local development only. Do not use it for a public deployment. Select a tile provider with a plan that covers your usage and configure its URL, key and exact attribution. Browser tile keys are visible to visitors by design; restrict them by domain/referrer and product scope. Never commit a real key. Before deployment, check the provider's current free-plan eligibility, request/traffic limits, caching rules, attribution requirements, and public/commercial-use terms. See [`.env.example`](../.env.example) and the [deployment guide](../infrastructure/DEPLOY_AWS.md).

## Request limits, rate limits and CORS

The service caps request bodies at 1 MiB by default (`MAX_REQUEST_BODY_BYTES`). It uses an in-memory per-direct-peer-IP limiter of 180 requests per 60 seconds by default (`RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`). Configure `RATE_LIMIT_ENABLED=false` to disable it; injected test apps default to disabled, and tests can explicitly enable it. Counters reset on restart and are local to a process. Behind a proxy, the peer IP is the proxy unless a trusted proxy strategy is added; do not trust arbitrary forwarded-IP headers. Use an edge limiter for a multi-process public deployment.

CORS is disabled by default, which is appropriate for the same-origin UI. To allow a separate frontend, set `CORS_ORIGINS` to a comma-separated list of exact origins; wildcard origins and credentials are not enabled. The middleware rejects oversized bodies with HTTP 413 and rate-limited requests with HTTP 429 using the normal JSON error shape.

The dark map treatment applies a CSS filter to the default OSM tiles. A configured provider can supply its own styling; its terms and attribution still apply.

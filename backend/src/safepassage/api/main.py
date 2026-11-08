"""FastAPI application and thin endpoint handlers for SafePassage."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
import ctypes
import logging
from ctypes import wintypes
from pathlib import Path
from time import perf_counter
from typing import AsyncIterator

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from safepassage.api.schemas import AlternativesRequest, CompareRequest, NearestHospitalsRequest, RouteRequest
from safepassage.api.middleware import RequestGuardMiddleware
from safepassage.api.services import (
    APIError, AppState, DATA_ATTRIBUTION, DEFAULT_BBOX, alternatives_response, compare_response,
    load_state, nearest_response, route_response,
)

ROOT = Path(__file__).resolve().parents[4]
FRONTEND = ROOT / "frontend"
DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def create_app(state: AppState | None = None) -> FastAPI:
    """Create the API; tests may inject a prepared small graph state."""
    rate_limit_enabled = _env_bool("RATE_LIMIT_ENABLED", state is None)
    rate_limit = max(1, int(os.getenv("RATE_LIMIT_REQUESTS", "180")))
    rate_window = max(1, int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))
    max_body_bytes = max(1024, int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576")))
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        started = perf_counter()
        app.state.service_state = state if state is not None else load_state()
        elapsed = (perf_counter() - started) * 1000
        rss_mb = _process_rss_mb()
        logging.getLogger("uvicorn.error").info("SafePassage startup ready in %.1f ms; process RSS %.1f MiB", elapsed, rss_mb)
        app.state.startup_metrics = {"startup_ms": round(elapsed, 1), "rss_mb": round(rss_mb, 1)}
        yield

    app = FastAPI(
        title="SafePassage API",
        version="1.0",
        description=(
            "Flood-aware emergency routing for the Mumbai road extract. "
            "ETA uses road-type speed estimates (slower under heavy rain). "
            "Safety score is simulated: round(100 * (1 - flooded_length_m / distance_m)). "
            "Unreachable routes return HTTP 200 with route=null and a message."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(RequestGuardMiddleware, rate_enabled=rate_limit_enabled,
                       rate_limit=rate_limit, window_seconds=rate_window,
                       max_body_bytes=max_body_bytes)
    cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
    if "*" in cors_origins:
        raise ValueError("CORS_ORIGINS must contain explicit origins; wildcard origins are not allowed.")
    if cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=cors_origins,
                           allow_methods=["GET", "POST", "OPTIONS"],
                           allow_headers=["Content-Type"], allow_credentials=False)

    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = exc.errors()
        message = details[0].get("msg", "Request validation failed") if details else "Request validation failed"
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": str(message)}})

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/meta")
    async def meta(request: Request) -> dict[str, object]:
        data: AppState = request.app.state.service_state
        return {
            "bbox": data.bbox,
            "node_count": data.graph.node_count(),
            "edge_count": data.graph.edge_count(),
            "scenarios": ["normal", "heavy_rain", "road_closed"],
            "hospital_count": len(data.hospitals),
            "algorithms": ["astar", "dijkstra", "bfs"],
            "data_attribution": DATA_ATTRIBUTION,
            "tiles": {
                "url": os.getenv("TILE_URL", DEFAULT_TILE_URL),
                "attribution": os.getenv("TILE_ATTRIBUTION", DEFAULT_TILE_ATTRIBUTION),
                # Tile keys are necessarily visible to browsers; restrict provider keys by allowed referrer.
                "api_key": os.getenv("TILE_API_KEY", ""),
            },
        }

    @app.get("/api/hospitals")
    async def hospitals(request: Request) -> list[dict[str, object]]:
        state_data: AppState = request.app.state.service_state
        return [{"name": item.get("name", ""), "lat": item["lat"], "lng": item["lng"]} for item in state_data.hospitals]

    @app.get("/api/flood-zones")
    async def flood_zones(request: Request) -> dict[str, object]:
        state_data: AppState = request.app.state.service_state
        zones = [{"name": item["name"], "lat": item["lat"], "lng": item["lng"],
                  "radius_m": item.get("radius_m", item.get("radius", 0))}
                 for item in state_data.flood_spots]
        return {"illustrative": True, "zones": zones}

    @app.get("/api/search")
    async def search(
        request: Request,
        q: str = Query(default="", max_length=100),
        limit: int = Query(default=8, ge=1, le=20),
    ) -> list[dict[str, object]]:
        state_data: AppState = request.app.state.service_state
        return state_data.trie.search(q, limit)

    @app.post("/api/route", description=(
        "ETA uses the documented road-type speed table with a 25% heavy-rain reduction. "
        "Safety score is simulated as round(100 * (1 - flooded_length_m / distance_m)). "
        "Unreachable destinations return HTTP 200 with route=null and a message."
    ))
    async def route(body: RouteRequest, request: Request) -> dict[str, object]:
        return route_response(request.app.state.service_state, body)

    @app.post("/api/alternatives")
    async def alternatives(body: AlternativesRequest, request: Request) -> dict[str, object]:
        return alternatives_response(request.app.state.service_state, body)

    @app.post("/api/nearest-hospitals")
    async def nearest_hospitals(body: NearestHospitalsRequest, request: Request) -> dict[str, object]:
        return nearest_response(request.app.state.service_state, body)

    @app.post("/api/compare")
    async def compare(body: CompareRequest, request: Request) -> dict[str, object]:
        return compare_response(request.app.state.service_state, body)

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(FRONTEND / "index.html")

    app.mount("/static", StaticFiles(directory=FRONTEND / "src"), name="static")
    return app


def _process_rss_mb() -> float:
    """Return current process RSS on Windows without a runtime dependency."""
    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return counters.WorkingSetSize / (1024 * 1024)
    return 0.0


app = create_app()

"""Pydantic request models for the SafePassage HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Point(BaseModel):
    lat: float
    lng: float


class Closure(Point):
    radius_m: float = Field(gt=0, le=1000)


class RouteRequest(BaseModel):
    origin: Point
    destination: Point
    scenario: Literal["normal", "heavy_rain", "road_closed"] = "normal"
    algorithm: Literal["astar", "dijkstra", "bfs"] = "astar"
    alternatives: int = Field(default=0, ge=0, le=3)
    include_normal_comparison: bool = True
    closures: list[Closure] = Field(default_factory=list, max_length=5)


class AlternativesRequest(BaseModel):
    origin: Point
    destination: Point
    scenario: Literal["normal", "heavy_rain", "road_closed"] = "normal"
    alternatives: int = Field(default=2, ge=1, le=3)
    closures: list[Closure] = Field(default_factory=list, max_length=5)


class NearestHospitalsRequest(BaseModel):
    origin: Point
    scenario: Literal["normal", "heavy_rain", "road_closed"] = "normal"
    k: int = Field(default=3, ge=1, le=5)
    closures: list[Closure] = Field(default_factory=list, max_length=5)


class CompareRequest(BaseModel):
    origin: Point
    destination: Point
    scenario: Literal["normal", "heavy_rain", "road_closed"] = "normal"
    closures: list[Closure] = Field(default_factory=list, max_length=5)

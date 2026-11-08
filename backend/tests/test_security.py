import pytest
import httpx
from test_client import TestClient

from safepassage.api.main import create_app
from test_api import make_state


def test_test_apps_have_rate_limiting_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_ENABLED", raising=False)
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    with TestClient(create_app(make_state())) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health").status_code == 200


def test_rate_limit_can_be_enabled_in_tests(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    with TestClient(create_app(make_state())) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health").status_code == 200
        response = client.get("/api/health")
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limited"


def test_request_body_size_limit(monkeypatch):
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "1024")
    with TestClient(create_app(make_state())) as client:
        response = client.post("/api/route", content=b"x" * 1025,
                               headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_streamed_request_body_size_limit(monkeypatch):
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "1024")

    class OversizedChunks(httpx.SyncByteStream):
        def __iter__(self):
            yield b"x" * 600
            yield b"x" * 600

    with TestClient(create_app(make_state())) as client:
        response = client.post("/api/route", content=OversizedChunks(),
                               headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_cors_is_disabled_by_default_and_can_be_allowlisted(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with TestClient(create_app(make_state())) as client:
        response = client.get("/api/health", headers={"Origin": "https://other.example"})
        assert "access-control-allow-origin" not in response.headers
    monkeypatch.setenv("CORS_ORIGINS", "https://safe.example")
    with TestClient(create_app(make_state())) as client:
        allowed = client.get("/api/health", headers={"Origin": "https://safe.example"})
        denied = client.get("/api/health", headers={"Origin": "https://other.example"})
        assert allowed.headers["access-control-allow-origin"] == "https://safe.example"
        assert "access-control-allow-origin" not in denied.headers


def test_tile_configuration_is_exposed_by_meta_without_transforming_key(monkeypatch):
    monkeypatch.setenv("TILE_URL", "https://tiles.example/{z}/{x}/{y}?key={api_key}")
    monkeypatch.setenv("TILE_ATTRIBUTION", "Example tiles")
    monkeypatch.setenv("TILE_API_KEY", "public-restricted-test-key")
    with TestClient(create_app(make_state())) as client:
        tiles = client.get("/api/meta").json()["tiles"]
    assert tiles == {
        "url": "https://tiles.example/{z}/{x}/{y}?key={api_key}",
        "attribution": "Example tiles",
        "api_key": "public-restricted-test-key",
    }


def test_cors_rejects_wildcard_origin(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="explicit origins"):
        create_app(make_state())

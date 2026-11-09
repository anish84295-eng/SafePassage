"""Cross-platform process metrics and app startup checks."""

import asyncio
import ctypes
import sys
from pathlib import Path
from types import SimpleNamespace

import safepassage.api.main as main
from safepassage.api.services import AppState
from safepassage.graph import Graph
from safepassage.spatial import SpatialIndex
from safepassage.structures.trie import Trie


def test_process_rss_windows_uses_mocked_apis(monkeypatch):
    class FakeCall:
        restype = None
        argtypes = None

        def __call__(self, *_args):
            return 1

    monkeypatch.setattr(main.sys, "platform", "win32")
    fake_windll = SimpleNamespace(
        kernel32=SimpleNamespace(GetCurrentProcess=FakeCall()),
        psapi=SimpleNamespace(GetProcessMemoryInfo=FakeCall()),
    )
    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)
    assert main._process_rss_mb() == 0.0


def test_process_rss_linux_reads_proc_status(monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "linux")
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: "Name:\tpython\nVmRSS:\t204800 kB\n")
    assert main._process_rss_mb() == 200.0


def test_process_rss_linux_failure_returns_none(monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "linux")
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unavailable")))
    monkeypatch.setattr(main, "_resource_rss_mb", lambda: None)
    assert main._process_rss_mb() is None


def test_process_rss_macos_resource_uses_bytes(monkeypatch):
    import sys as system

    monkeypatch.setattr(main.sys, "platform", "darwin")
    fake_resource = SimpleNamespace(
        RUSAGE_SELF=0,
        getrusage=lambda _who: SimpleNamespace(ru_maxrss=64 * 1024 * 1024),
    )
    monkeypatch.setitem(system.modules, "resource", fake_resource)
    assert main._resource_rss_mb() == 64.0


def test_app_lifespan_starts_with_unavailable_rss(monkeypatch):
    monkeypatch.setattr(main, "_process_rss_mb", lambda: None)
    state = AppState(Graph(), {}, [], [], SpatialIndex({}), Trie())
    app = main.create_app(state)

    async def start_app():
        async with app.router.lifespan_context(app):
            assert app.state.service_state is state
            assert app.state.startup_metrics["rss_mb"] is None

    asyncio.run(start_app())

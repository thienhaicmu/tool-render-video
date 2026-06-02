"""Tests for app.core.devtools_safety — the hard-block guard for the devtools
router. The router itself executes arbitrary shell commands, so these tests
exercise the gates that decide whether the router is even reachable.
"""

import pytest

from app.core.devtools_safety import (
    assert_devtools_safe,
    detect_uvicorn_bind_host,
    is_loopback_client,
)


# ─── detect_uvicorn_bind_host ────────────────────────────────────────────────


def test_detect_host_argv_separate_form():
    assert detect_uvicorn_bind_host(
        argv=["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        env={},
    ) == "127.0.0.1"


def test_detect_host_argv_equals_form():
    assert detect_uvicorn_bind_host(argv=["uvicorn", "--host=0.0.0.0"], env={}) == "0.0.0.0"


def test_detect_host_argv_is_lowercased_and_stripped():
    assert detect_uvicorn_bind_host(argv=["uvicorn", "--host", "  LOCALHOST  "], env={}) == "localhost"


def test_detect_host_from_uvicorn_host_env_when_no_argv():
    assert detect_uvicorn_bind_host(argv=["uvicorn"], env={"UVICORN_HOST": "localhost"}) == "localhost"


def test_detect_host_from_host_env_fallback():
    assert detect_uvicorn_bind_host(argv=["uvicorn"], env={"HOST": "0.0.0.0"}) == "0.0.0.0"


def test_detect_host_argv_wins_over_env():
    result = detect_uvicorn_bind_host(
        argv=["uvicorn", "--host", "127.0.0.1"],
        env={"HOST": "0.0.0.0"},
    )
    assert result == "127.0.0.1"


def test_detect_host_uvicorn_host_wins_over_host_when_no_argv():
    result = detect_uvicorn_bind_host(
        argv=["uvicorn"],
        env={"UVICORN_HOST": "::1", "HOST": "0.0.0.0"},
    )
    assert result == "::1"


def test_detect_host_returns_none_when_no_source():
    assert detect_uvicorn_bind_host(argv=["uvicorn"], env={}) is None


def test_detect_host_argv_dangling_flag_returns_none():
    # `--host` with no following value falls through to env (which is empty)
    assert detect_uvicorn_bind_host(argv=["uvicorn", "--host"], env={}) is None


# ─── assert_devtools_safe ────────────────────────────────────────────────────


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]"])
def test_assert_safe_allows_loopback(host):
    # Should not raise
    assert_devtools_safe(host)


def test_assert_safe_refuses_when_host_unknown():
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        assert_devtools_safe(None)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com", "10.0.0.1"])
def test_assert_safe_refuses_non_loopback(host):
    with pytest.raises(RuntimeError, match="REFUSING TO START"):
        assert_devtools_safe(host)


def test_assert_safe_error_mentions_host_in_message():
    with pytest.raises(RuntimeError, match="0.0.0.0"):
        assert_devtools_safe("0.0.0.0")


# ─── is_loopback_client ──────────────────────────────────────────────────────


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_is_loopback_allows_loopback(host):
    assert is_loopback_client(host) is True


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "10.0.0.1", "example.com"])
def test_is_loopback_rejects_non_loopback(host):
    assert is_loopback_client(host) is False


def test_is_loopback_rejects_none():
    assert is_loopback_client(None) is False


# ─── Integration: devtools router rejects non-loopback origins ───────────────


def test_devtools_router_rejects_non_loopback_request(monkeypatch):
    """When the router IS mounted (e.g. for tests), the request-time check
    still rejects simulated non-loopback peers.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routes.devtools import router as devtools_router

    app = FastAPI()
    app.include_router(devtools_router)

    # TestClient sends requests with client.host = "testclient" by default,
    # which is not in the loopback set. So the layer-2 check should fire.
    client = TestClient(app)
    response = client.post("/api/dev/command", json={"command": "/status"})
    assert response.status_code == 403
    assert "loopback-only" in response.json()["detail"]


def test_devtools_router_accepts_loopback_request(monkeypatch):
    """When the loopback check passes, the request reaches the dispatch layer.

    FastAPI's TestClient sets request.client.host = "testclient" by default
    and does not expose a way to override it cleanly across versions. So we
    monkeypatch the loopback helper for this test — the helper itself is
    covered by direct unit tests above.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.routes.devtools as devtools_module

    monkeypatch.setattr(devtools_module, "is_loopback_client", lambda _host: True)

    app = FastAPI()
    app.include_router(devtools_module.router)
    client = TestClient(app)
    response = client.post("/api/dev/command", json={"command": "/features"})
    # /features is a pure-data command (no side effects). The fact that we
    # get 200 with the expected payload proves the request reached
    # execute_dev_command past the loopback gate.
    assert response.status_code == 200
    assert response.json().get("command") == "/features"

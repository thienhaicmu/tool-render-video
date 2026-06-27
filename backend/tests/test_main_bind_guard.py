"""B1 (2026-06-27) — main-API bind guard.

The backend has no authentication. ``app.main`` calls
``assert_main_bind_safe`` at import time and refuses to start when uvicorn
is binding to a non-loopback host without an explicit ``ALLOW_REMOTE=1``
opt-in — otherwise the unauthenticated render/jobs/file API is exposed to
the network.

These tests pin the decision matrix so a future edit cannot silently
weaken it (e.g. flip the default to fail-open on 0.0.0.0).
"""
from __future__ import annotations

import pytest

from app.core.devtools_safety import assert_main_bind_safe


# ── Allowed cases — must NOT raise ──────────────────────────────────────────

@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]"])
def test_loopback_hosts_are_allowed(host):
    # No exception == allowed.
    assert_main_bind_safe(host, allow_remote=False)


def test_none_host_is_allowed_fail_open():
    """Undetectable host (no --host passed) == uvicorn default 127.0.0.1.

    The desktop run-scripts and the pytest suite never pass --host, so this
    path MUST stay fail-open or every test importing app.main would crash.
    """
    assert_main_bind_safe(None, allow_remote=False)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.50", "myhost.local", "::"])
def test_remote_hosts_allowed_only_with_opt_in(host):
    # ALLOW_REMOTE=1 → explicit opt-in, no raise even on a network host.
    assert_main_bind_safe(host, allow_remote=True)


# ── Refused cases — MUST raise ──────────────────────────────────────────────

@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.50", "10.0.0.5", "myhost.local"])
def test_non_loopback_without_opt_in_refuses_startup(host):
    with pytest.raises(RuntimeError) as exc:
        assert_main_bind_safe(host, allow_remote=False)
    # Message must name the risk and the opt-in escape hatch.
    msg = str(exc.value)
    assert "ALLOW_REMOTE" in msg
    assert host in msg

"""Hard-block guard for the devtools router.

Devtools (`POST /api/dev/command`) executes arbitrary shell commands with no
authentication. This module enforces two safety checks:

  1. Detect the uvicorn bind host from --host argv (preferred) or env vars.
  2. Refuse to enable devtools unless the host is a loopback address.

Fails closed: if we cannot determine the host, devtools is refused. The check
must be invoked from `app.main` before the devtools router is mounted.

This module has no side effects on import — safe to import from tests.
"""

from __future__ import annotations

import os
import sys

_SAFE_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
_LOOPBACK_CLIENT_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def detect_uvicorn_bind_host(
    argv: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> str | None:
    """Return the bind host uvicorn was launched with, or None if undetectable.

    Sources checked, in priority order:
      1. ``--host VALUE`` or ``--host=VALUE`` in argv
      2. ``UVICORN_HOST`` env var
      3. ``HOST`` env var (informational convention used elsewhere in the app)
    """
    src_argv = sys.argv if argv is None else argv
    src_env = os.environ if env is None else env

    for i, token in enumerate(src_argv):
        if token == "--host" and i + 1 < len(src_argv):
            return src_argv[i + 1].strip().lower()
        if token.startswith("--host="):
            return token.split("=", 1)[1].strip().lower()

    for key in ("UVICORN_HOST", "HOST"):
        val = src_env.get(key) if isinstance(src_env, dict) else os.getenv(key)
        if val:
            return val.strip().lower()
    return None


def assert_devtools_safe(host: str | None) -> None:
    """Raise RuntimeError unless `host` is a known-safe loopback address."""
    if host is None:
        raise RuntimeError(
            "REFUSING TO START: ENABLE_DEVTOOLS=1 is set but the uvicorn bind "
            "host could not be determined from --host argv, UVICORN_HOST, or "
            "HOST. To enable devtools, pass --host 127.0.0.1 explicitly. "
            "Devtools exposes unauthenticated shell execution — enabling it on "
            "a non-loopback host would expose RCE to the network."
        )
    if host not in _SAFE_LOOPBACK_HOSTS:
        raise RuntimeError(
            f"REFUSING TO START: ENABLE_DEVTOOLS=1 + bind host {host!r} is a "
            "network-exposed shell-execution surface. Devtools is only allowed "
            f"when bound to one of {sorted(_SAFE_LOOPBACK_HOSTS)}."
        )


def is_loopback_client(client_host: str | None) -> bool:
    """Return True if `client_host` is a loopback peer."""
    return client_host is not None and client_host in _LOOPBACK_CLIENT_HOSTS


def assert_main_bind_safe(host: str | None, allow_remote: bool) -> None:
    """Refuse startup when the WHOLE API would bind to a network host.

    B1 (2026-06-27). This guards the main application surface, not just
    devtools: the render / jobs / files endpoints have NO authentication,
    so binding to a non-loopback host exposes the entire offline-first
    desktop API (and its file/render capabilities) to the local network.

    Semantics — deliberately fail OPEN on an undetectable host so the
    desktop run-scripts and the test suite (which never pass ``--host``)
    are unaffected:

      - ``allow_remote=True``        → allowed (explicit operator opt-in,
                                       e.g. the Docker image sets
                                       ``ALLOW_REMOTE=1``).
      - ``host is None``             → allowed. uvicorn's own default bind
                                       is ``127.0.0.1`` when ``--host`` is
                                       omitted, so "undetectable" means
                                       "loopback by default".
      - ``host`` is a loopback addr  → allowed.
      - anything else (0.0.0.0, LAN  → RuntimeError (refuse to start).
        IP, real hostname)

    Raising here fails the import of ``app.main`` before any router is
    mounted — the API never binds on an unsafe host.
    """
    if allow_remote:
        return
    if host is None:
        return
    if host in _SAFE_LOOPBACK_HOSTS:
        return
    raise RuntimeError(
        f"REFUSING TO START: backend is binding to non-loopback host "
        f"{host!r}, which exposes the UNAUTHENTICATED API (render, jobs, "
        f"file access) to the network. This is an offline-first desktop "
        f"app — bind to 127.0.0.1. If network exposure is intentional "
        f"(e.g. a container or trusted LAN), set ALLOW_REMOTE=1 to opt in "
        f"explicitly."
    )

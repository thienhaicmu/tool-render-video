"""UI activation gate — resolves which static directory to serve.

Reads STATIC_UI_VERSION from the environment:
  "v2"     → backend/static-v2/  (if it exists)
  "legacy" → backend/static/     (always)
  missing  → backend/static/     (default, safe rollback)
  invalid  → backend/static/     (fallback with warning)

If STATIC_UI_VERSION=v2 but static-v2 directory is missing, falls back
to legacy and logs a warning.  Never raises; always returns a valid path.

Usage
-----
  from app.core.ui_gate import resolve_static_directory
  static_dir, ui_version = resolve_static_directory(backend_root)
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Env var controlling which static UI is active
ENV_VAR = "STATIC_UI_VERSION"
VERSION_V2     = "v2"
VERSION_LEGACY = "legacy"


def resolve_static_directory(
    backend_root: Path,
    env_value: str | None = None,
) -> tuple[Path, str]:
    """Return (static_dir, version_label) for the requested UI version.

    Parameters
    ----------
    backend_root:
        Path to the ``backend/`` directory (parent of ``app/``).
    env_value:
        Override the environment variable value.  If ``None``, reads
        ``STATIC_UI_VERSION`` from the process environment.

    Returns
    -------
    (static_dir, version_label)
        ``version_label`` is ``"v2"`` or ``"legacy"``.
    """
    raw = env_value if env_value is not None else os.getenv(ENV_VAR, VERSION_LEGACY)
    requested = raw.strip().lower() if raw else VERSION_LEGACY

    legacy_dir = _legacy_dir(backend_root)
    v2_dir     = backend_root / "static-v2"

    if requested == VERSION_V2:
        if v2_dir.is_dir():
            logger.info("[ui-gate] STATIC_UI_VERSION=v2 → serving backend/static-v2/")
            return v2_dir, VERSION_V2
        logger.warning(
            "[ui-gate] STATIC_UI_VERSION=v2 requested but backend/static-v2/ not found "
            "— falling back to legacy"
        )
        return legacy_dir, VERSION_LEGACY

    if requested not in (VERSION_LEGACY, ""):
        logger.warning(
            "[ui-gate] Unknown STATIC_UI_VERSION=%r — falling back to legacy", raw
        )

    logger.info("[ui-gate] Serving legacy static UI (backend/static/)")
    return legacy_dir, VERSION_LEGACY


def _legacy_dir(backend_root: Path) -> Path:
    """Docker-aware legacy static path (mirrors existing main.py logic)."""
    docker_path = Path("/app/static")
    if docker_path.is_dir():
        return docker_path
    return backend_root / "static"

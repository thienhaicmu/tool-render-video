"""Sprint 5.2 backward-compat shim.

The real implementations of ``render_part`` and ``render_part_smart`` now live
in ``app.services.render.base_clip_renderer``. This module re-exports them so
that ``render_engine.render_part`` and other historical import paths continue
to work. New code should import from ``base_clip_renderer`` directly.
"""
from app.services.render.base_clip_renderer import (  # noqa: F401
    render_part,
    render_part_smart,
)

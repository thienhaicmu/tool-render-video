"""Render-pipeline setup stage — payload normalization, channel resolution,
and output-directory preparation.

Sprint 6.D-1.1 — extracted setup_render_pipeline() verbatim from
render_pipeline.py (lines 236–268 of the pre-1.1 file). No logic changes.

Sprint 6.D-1.2 — extracted prepare_output_dir() verbatim from
render_pipeline.py (lines 254–286 of the post-1.1 file). No logic changes.

Responsibilities (in order):
  1. setup_render_pipeline(payload) — derive output_mode, effective_channel,
     started_at, Market Viral cfg, hook flags, and output_dir (no I/O beyond
     ensure_channel in channel mode).
  2. prepare_output_dir(job_id, effective_channel, output_dir) — emit the
     three render.output.prepare.* WebSocket events and mkdir() the
     resolved output_dir. Re-raises on mkdir failure (matches pre-1.2
     behavior — the caller's outer try/except handles propagation).
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.schemas import RenderRequest
from app.features.render.engine.pipeline.render_events import _emit_render_event


@dataclass
class PipelineSetupResult:
    """Bundle of normalized values produced by setup_render_pipeline.

    Field names drop the leading underscores used in run_render_pipeline's
    local scope (e.g. _mv_cfg → mv_cfg). The caller aliases each field
    back to its original local-variable name to keep the rest of the
    function byte-for-byte unchanged.
    """
    effective_channel: str
    started_at: datetime
    mv_cfg: dict
    mv_market: str
    hook_apply_enabled: bool
    hook_applied_text: str
    hook_score: Any
    hook_overlay_enabled: bool
    output_dir: Path


def setup_render_pipeline(payload: RenderRequest) -> PipelineSetupResult:
    """Normalize payload + resolve output_dir.

    Returns:
        PipelineSetupResult with all derived values that the rest of
        run_render_pipeline consumes.
    """
    effective_channel = (payload.channel_code or "").strip() or "manual"
    started_at = datetime.utcnow()

    # Market Viral — resolve target market once; used by all part workers via closure
    _mv_cfg = getattr(payload, "market_viral", None) or {}
    _mv_cfg_enabled = isinstance(_mv_cfg, dict) and bool(_mv_cfg)
    _mv_payload_market = getattr(payload, "ai_target_market", None) or getattr(payload, "viral_market", None)
    _mv_market = str(
        _mv_payload_market
        or ((_mv_cfg.get("target_market") or "US") if isinstance(_mv_cfg, dict) else "US")
    ).upper()
    if _mv_market not in {"US", "EU", "JP"}:
        _mv_market = "US"
    if _mv_cfg_enabled:
        _mv_cfg = {**_mv_cfg, "target_market": _mv_market}
    else:
        _mv_cfg = {}
    _hook_apply_enabled = bool(getattr(payload, "hook_apply_enabled", False))
    _hook_applied_text = str(getattr(payload, "hook_applied_text", None) or "").strip()
    _hook_score = getattr(payload, "hook_score", None)
    _hook_overlay_enabled = bool(getattr(payload, "hook_overlay_enabled", False))
    if not _hook_applied_text:
        _hook_apply_enabled = False
    output_dir = Path(payload.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = (Path.cwd() / output_dir).resolve()

    return PipelineSetupResult(
        effective_channel=effective_channel,
        started_at=started_at,
        mv_cfg=_mv_cfg,
        mv_market=_mv_market,
        hook_apply_enabled=_hook_apply_enabled,
        hook_applied_text=_hook_applied_text,
        hook_score=_hook_score,
        hook_overlay_enabled=_hook_overlay_enabled,
        output_dir=output_dir,
    )


def prepare_output_dir(job_id: str, effective_channel: str, output_dir: Path) -> None:
    """Emit prepare-events around output_dir.mkdir(); re-raise on failure.

    Sprint 6.D-1.2 — extracted verbatim from run_render_pipeline. Emits:
      - render.output.prepare.start (before mkdir)
      - render.output.prepare.success (after successful mkdir)
      - render.output.prepare.error (if mkdir raises; then re-raises)

    Side effects only — no return value. Caller's outer try/except handles
    error propagation (the function intentionally re-raises so the existing
    top-level exception handler in run_render_pipeline catches it).
    """
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.output.prepare.start",
        level="INFO",
        message="Preparing output directory",
        step="render.output.prepare",
        context={"output_dir": str(output_dir)},
    )
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.output.prepare.success",
            level="INFO",
            message="Output directory ready",
            step="render.output.prepare",
            context={"output_dir": str(output_dir)},
        )
    except Exception as output_exc:
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.output.prepare.error",
            level="ERROR",
            message=f"Failed to prepare output directory: {output_exc}",
            step="render.output.prepare",
            context={"output_dir": str(output_dir)},
            exception=output_exc,
            traceback_text=traceback.format_exc(),
        )
        raise

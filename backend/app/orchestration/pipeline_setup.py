"""Render-pipeline setup stage — payload normalization + channel resolution.

Sprint 6.D-1.1 — extracted verbatim from render_pipeline.py
(lines 236–268 of the pre-extraction file). No logic changes;
pure relocation.

Responsibilities (in order):
  1. Normalize output_mode, effective_channel, started_at.
  2. Resolve Market Viral target market (US/EU/JP).
  3. Resolve hook-apply / hook-overlay flags.
  4. Ensure channel subdir + resolve output_dir for channel mode;
     fall back to absolute payload.output_dir for non-channel mode.

This function is the first thing run_render_pipeline executes and has no
side effects beyond:
  - ensure_channel(effective_channel) in channel mode
  - May raise RuntimeError if render_output_subdir is missing in channel mode

The mkdir + WebSocket prepare-events block (formerly lines 269–301) stays
in run_render_pipeline for now — that's Sprint 6.D-1.2 scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.schemas import RenderRequest
from app.services.channel_service import ensure_channel
from app.orchestration.pipeline_config import _resolve_output_dir


@dataclass
class PipelineSetupResult:
    """Bundle of normalized values produced by setup_render_pipeline.

    Field names drop the leading underscores used in run_render_pipeline's
    local scope (e.g. _mv_cfg → mv_cfg). The caller aliases each field
    back to its original local-variable name to keep the rest of the
    function byte-for-byte unchanged.
    """
    output_mode: str
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
    """Normalize payload + resolve channel/output_dir.

    Returns:
        PipelineSetupResult with all derived values that the rest of
        run_render_pipeline consumes.

    Raises:
        RuntimeError: when output_mode == "channel" and render_output_subdir
                      is empty (validated to match the caller's existing
                      pre-Sprint 6.D-1.1 behavior).
    """
    output_mode = (payload.output_mode or "channel").strip().lower()
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
    if output_mode == "channel":
        ensure_channel(effective_channel)
        if not (payload.render_output_subdir or "").strip():
            raise RuntimeError("render_output_subdir is required")
        output_dir = _resolve_output_dir(effective_channel, payload.output_dir, payload.render_output_subdir)
    else:
        output_dir = Path(payload.output_dir).expanduser()
        if not output_dir.is_absolute():
            output_dir = (Path.cwd() / output_dir).resolve()

    return PipelineSetupResult(
        output_mode=output_mode,
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

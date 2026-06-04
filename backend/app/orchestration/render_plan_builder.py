"""
render_plan_builder.py — adapter shim: LLMSegment list + RenderRequest → RenderPlan.

Sprint 2.2 deliverable. This builder is intentionally a SHIM:

- The AI provider (Gemini/Claude/OpenAI) currently emits only segment
  selection (LLMSegment list). The other decisions a RenderPlan needs
  (subtitle policy, camera strategy, audio plan, output config) live
  scattered across `stages/part_asset_planner.py`,
  `stages/part_render_setup.py`, and the RenderRequest payload itself.
- This builder pulls those decisions together so the rest of the
  pipeline can read a single `RenderPlan` object.
- In Sprint 4 the AI provider will emit a full RenderPlan directly and
  this shim will be replaced by an AI-driven builder. The interface
  upstream of this file does NOT have to change at that point — only
  the internals.

Sacred Contract guards:
- This module is in the AI / orchestration tier. Every public entry
  point catches all exceptions and returns a safe default (None or an
  empty RenderPlan) — never raises. The orchestrator decides whether a
  None means 'use legacy path' (Sprint 2.3 fallback) or hard-fail.
- No file I/O, no subprocess, no DB write. Persistence is the caller's
  responsibility (`jobs_repo.update_render_plan`).
"""
from __future__ import annotations

import logging
from typing import Optional

from app.ai.llm.parser import LLMSegment
from app.domain.render_plan import (
    AudioPlan,
    CameraStrategy,
    ClipPlan,
    OutputConfig,
    RenderPlan,
    SubtitlePolicy,
)


logger = logging.getLogger("app.orchestration.render_plan_builder")


# ── Public entry point ───────────────────────────────────────────────────


def build_render_plan(
    llm_segments: list[LLMSegment] | None,
    payload,
    *,
    creator_context_id: str = "",
) -> Optional[RenderPlan]:
    """Assemble a RenderPlan from the LLM segment list + RenderRequest payload.

    Returns None on any error so the caller (Sprint 2.3 pipeline
    integration) can fall back to the legacy path. Never raises.

    Args:
        llm_segments: Output of the LLM segment-selection stage. Empty
            list and None are both treated as 'no clips' — a plan with
            an empty clips list is returned (subsequent stages can
            decide whether to bail out). A return of None from this
            function instead signals an internal builder error.
        payload: The deserialised RenderRequest. The builder reads
            scattered decisions (subtitle style, camera mode, voice
            settings, output config) from this object using
            `getattr(..., default)` so missing attributes never raise.
        creator_context_id: optional opaque ID referencing the
            CreatorContext that informed AI choices. Sprint 3 will
            populate this; Sprint 2.2 just threads it through.
    """
    try:
        clips = _build_clips(llm_segments or [])
        return RenderPlan(
            clips=clips,
            subtitle_policy=_build_subtitle_policy(payload),
            camera_strategy=_build_camera_strategy(payload),
            audio_plan=_build_audio_plan(payload),
            output_config=_build_output_config(payload),
            overlays=_build_overlays(payload),
            creator_context_id=str(creator_context_id or ""),
        )
    except Exception as exc:
        logger.warning("build_render_plan failed (%s) — returning None for fallback", exc, exc_info=True)
        return None


# ── Sub-builders ─────────────────────────────────────────────────────────


def _build_clips(segments: list[LLMSegment]) -> list[ClipPlan]:
    """Map LLMSegment → ClipPlan. Rank is the 1-based position in the
    incoming list — the LLM stage already sorts by score before handing
    over (parser.py:110). Missing extended fields stay at the LLMSegment
    defaults (0.0 / "")."""
    clips: list[ClipPlan] = []
    for rank, seg in enumerate(segments, start=1):
        try:
            clips.append(
                ClipPlan(
                    start=float(getattr(seg, "start", 0.0)),
                    end=float(getattr(seg, "end", 0.0)),
                    rank=rank,
                    score=float(getattr(seg, "score", 0.0)),
                    clip_name=str(getattr(seg, "clip_name", "")),
                    title=str(getattr(seg, "title", "")),
                    reason=str(getattr(seg, "reason", "")),
                    hook_type=str(getattr(seg, "hook_type", "")),
                    content_type=str(getattr(seg, "content_type", "")),
                    viral_score=float(getattr(seg, "viral_score", 0.0)),
                    hook_score=float(getattr(seg, "hook_score", 0.0)),
                    retention_score=float(getattr(seg, "retention_score", 0.0)),
                    speech_density=float(getattr(seg, "speech_density", 0.0)),
                    duration_fit=float(getattr(seg, "duration_fit", 0.0)),
                    cover_offset_ratio=float(getattr(seg, "cover_offset_ratio", 0.0)),
                )
            )
        except (TypeError, ValueError) as exc:
            # One bad segment doesn't sink the plan — log and skip it.
            logger.warning("build_render_plan: skipping malformed segment %s — %s", seg, exc)
    return clips


def _build_subtitle_policy(payload) -> SubtitlePolicy:
    """Capture the current backend-derived subtitle decision so Sprint 2.3
    consumers can read a stable shape. The raw `payload.subtitle_style`
    (e.g. 'tiktok_bounce_v1') is preserved verbatim — Sprint 4 will
    move the 'style normalisation' decision up into the AI layer."""
    style = str(getattr(payload, "subtitle_style", "") or "") if _attr_present(payload, "subtitle_style") else ""
    market = _resolve_market(payload)
    emphasis = bool(getattr(payload, "subtitle_only_viral_high", False))
    return SubtitlePolicy(
        style=style,
        market=market,
        emphasis_pass=emphasis,
        line_break_rule="",  # market default — Sprint 4 will let AI override
    )


def _build_camera_strategy(payload) -> CameraStrategy:
    motion = bool(getattr(payload, "motion_aware_crop", False))
    reframe_raw = str(getattr(payload, "reframe_mode", "") or "")
    # Normalise the legacy 'subject' → 'track' label so downstream code
    # speaks the RenderPlan vocabulary. Keep the original if it already
    # matches the new vocabulary.
    reframe = {"subject": "track"}.get(reframe_raw, reframe_raw)
    return CameraStrategy(
        motion_aware_crop=motion,
        reframe_mode=reframe,
        tracker="",  # auto — Sprint 4 will let AI hint a tracker
    )


def _build_audio_plan(payload) -> AudioPlan:
    voice_enabled = bool(getattr(payload, "voice_enabled", False))
    voice_provider = str(getattr(payload, "tts_engine", "") or "")
    bgm_enabled = bool(getattr(payload, "reup_bgm_enable", False))
    return AudioPlan(
        voice_enabled=voice_enabled,
        voice_provider=voice_provider,
        bgm_enabled=bgm_enabled,
        cta_audio="",
    )


def _build_output_config(payload) -> OutputConfig:
    codec = str(getattr(payload, "video_codec", "") or "")
    preset = str(getattr(payload, "video_preset", "") or "")
    crf = _coerce_int(getattr(payload, "video_crf", None), 0)
    fps = _coerce_int(getattr(payload, "output_fps", None), 0)
    return OutputConfig(
        codec=codec,
        preset=preset,
        crf=crf,
        fps=fps,
        width=0,
        height=0,
    )


def _build_overlays(payload) -> list[dict]:
    overlays: list[dict] = []
    if bool(getattr(payload, "add_title_overlay", False)):
        text = str(getattr(payload, "title_overlay_text", "") or "")
        if text:
            overlays.append({"kind": "title", "text": text})
    if bool(getattr(payload, "cta_enabled", False)):
        overlays.append({
            "kind": "cta",
            "type": str(getattr(payload, "cta_type", "") or "auto"),
        })
    if bool(getattr(payload, "hook_overlay_enabled", False)):
        hook_text = str(getattr(payload, "hook_applied_text", "") or "")
        overlays.append({"kind": "hook", "text": hook_text})
    return overlays


# ── Helpers ──────────────────────────────────────────────────────────────


def _attr_present(payload, name: str) -> bool:
    return hasattr(payload, name) and getattr(payload, name) is not None


def _coerce_int(value, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_market(payload) -> str:
    """Pick whichever market hint the payload exposes — the schema carries
    two parallel fields (`viral_market` and `ai_target_market`) from
    different epochs of the pipeline. Empty if neither is set."""
    for attr in ("ai_target_market", "viral_market"):
        value = getattr(payload, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""

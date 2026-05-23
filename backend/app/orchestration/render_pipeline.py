
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import traceback
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable
from fastapi import HTTPException
from app.models.schemas import RenderRequest
from app.services.db import upsert_job, update_job_progress, upsert_job_part, list_job_parts, close_thread_conn
from app.services.channel_service import ensure_channel
from app.services.downloader import download_youtube, slugify
from app.services.scene_detector import detect_scenes
from app.services.segment_builder import build_segments_from_scenes, refine_segment_boundaries, refine_cuts_for_naturalness
from app.services.clip_scorer import score_scenes_clip, CLIP_SCORER_VERSION
from app.services.subtitle_engine import (
    srt_to_ass_bounce, srt_to_ass_karaoke, slice_srt_by_time,
    slice_srt_to_text, slice_srt_to_output_timeline,
    has_audio_stream, apply_market_line_break_to_srt,
    apply_market_hook_text_to_srt, apply_hook_subtitle_format, resolve_hook_overlay_text,
    subtitle_emphasis_pass, parse_srt_blocks, write_srt_blocks,
    resegment_srt_for_readability,
)
from app.services.subtitle_transcription_adapters import transcribe_with_adapter
from app.services.render_engine import cut_video, render_part_smart, render_base_clip, composite_overlays_on_base_clip, nvenc_available, resolve_ffmpeg_threads, detect_silence_trim_offset, apply_micro_pacing, detect_bad_first_frame, set_thread_cancel_event, content_type_crf_delta as _crf_delta_for_content_type, extract_thumbnail_frame
from app.services import cancel_registry
from app.services.job_manager import MAX_CONCURRENT_JOBS as _MAX_CONCURRENT_JOBS
from app.services.viral_scorer import score_segments, apply_retention_proxy
from app.services.viral_scoring import score_part_for_market as _mv_score_part
from app.services.report_service import append_rows
from app.core.config import TEMP_DIR, CHANNELS_DIR, LOGS_DIR
from app.core.stage import JobStage, JobPartStage, STAGE_TO_EVENT
from app.services.bin_paths import get_ffprobe_bin, get_ffmpeg_bin, _summarize_ffmpeg_stderr
from app.services.text_overlay import normalize_text_layers, MAX_TEXT_LAYERS
from app.services.tts_service import generate_narration_mp3, generate_narration_audio
from app.services.audio_mix_service import mix_narration_audio
from app.services.audio_cleanup_adapters import cleanup_audio_with_adapter
from app.services.translation_service import translate_srt_file
from app.services.remotion_adapter import (
    generate_hook_intro, prepend_intro_clip, resolve_intro_preset,
    append_outro_clip, apply_logo_watermark,  # UP27
)
from app.ai.visibility.ai_visibility_summary import attach_ai_visibility_summaries
from app.domain.timeline import TimelineMap
from app.domain.manifests import BaseClipManifest
from app.services.manifest_writer import write_manifest, manifest_path as _manifest_path
from app.orchestration.render_events import (
    _JOB_LOG_DIRS,
    _append_json_line,
    _emit_render_event,
    _event_from_stage,
    _job_log,
    _render_error_code,
    _render_progress_timer,
    _resolve_job_log_dir,
    _safe_unlink,
)
from app.orchestration.asset_pipeline import (
    _maybe_append_asset_outro,
    _maybe_apply_asset_logo,
    _maybe_prepend_asset_intro,
    _maybe_prepend_remotion_hook_intro,
)
from app.orchestration.audio_pipeline import (
    _maybe_cleanup_narration_audio,
)
from app.orchestration.qa_pipeline import (
    _assess_output_quality,
    _duration_tolerance,
    _failed_part_progress,
    _render_part_failure_detail,
    _resume_output_valid,
    _stall_deadline,
    _validate_render_output,
)

# Feature flag: generate a no-overlay base clip as a parallel artifact before the
# final render.  OFF by default.  Set FEATURE_BASE_CLIP_FIRST=1 to enable.
# The base clip is never fed into the final output — render_part_smart() always
# produces the final video unless FEATURE_OVERLAY_AFTER_BASE_CLIP is also enabled.
_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"

# Feature flag: composite subtitle overlays onto base_clip.mp4 as the final output.
# Requires FEATURE_BASE_CLIP_FIRST=1.  OFF by default.
# When both flags are ON: overlay composite path → fallback render_part_smart() on failure.
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"

logger = logging.getLogger("app.render")


def _safe_output_name(text: str) -> str:
    """Human-readable safe filename stem. Preserves case and apostrophes."""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r'[\\/:*?"<>|]', '-', text)
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'-{2,}', '-', text)
    text = re.sub(r' {2,}', ' ', text)
    text = text.strip('- ')
    if len(text) > 80:
        text = text[:80].rsplit(' ', 1)[0] or text[:80]
    return text.strip('- ')


def _smart_output_stem(hook_text: str, source_title: str, job_id: str) -> str:
    """Fallback chain: AI hook → source title → render_{job_id[:8]}."""
    for candidate in [hook_text, source_title]:
        safe = _safe_output_name(candidate)
        if safe:
            return safe
    return f"render_{job_id[:8]}"


# UP28 — Render cache helpers (transcription + scene detection)
_RENDER_CACHE_TTL_SEC = 72 * 3600  # 72 h


def _render_cache_key(*parts) -> str:
    return hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()


def _scene_cache_get(source_path: str) -> list | None:
    try:
        sp = Path(source_path)
        if not sp.exists():
            return None
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size)
        cache_file = Path(tempfile.gettempdir()) / "render_cache" / "scene_detect" / f"{key}.json"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _RENDER_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _scene_cache_put(source_path: str, scenes: list) -> None:
    try:
        sp = Path(source_path)
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size)
        cache_dir = Path(tempfile.gettempdir()) / "render_cache" / "scene_detect"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{key}.json").write_text(json.dumps(scenes), encoding="utf-8")
    except Exception:
        pass


def _transcription_cache_get(source_path: str, model_name: str, cache_suffix: str) -> Path | None:
    try:
        sp = Path(source_path)
        if not sp.exists():
            return None
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size, model_name, cache_suffix)
        cache_file = Path(tempfile.gettempdir()) / "render_cache" / "transcription" / f"{key}.srt"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _RENDER_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        return cache_file
    except Exception:
        return None


def _transcription_cache_put(source_path: str, model_name: str, cache_suffix: str, srt_path: Path) -> None:
    try:
        if not srt_path.exists() or srt_path.stat().st_size == 0:
            return
        sp = Path(source_path)
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size, model_name, cache_suffix)
        cache_dir = Path(tempfile.gettempdir()) / "render_cache" / "transcription"
        cache_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(srt_path), str(cache_dir / f"{key}.srt"))
    except Exception:
        pass


def _score_cache_get(key: str) -> list | None:
    try:
        cache_file = Path(tempfile.gettempdir()) / "render_cache" / "segment_scores" / f"{key}.json"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _RENDER_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _score_cache_put(key: str, scored: list) -> None:
    try:
        cache_dir = Path(tempfile.gettempdir()) / "render_cache" / "segment_scores"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{key}.json").write_text(json.dumps(scored), encoding="utf-8")
    except Exception:
        pass


_PLAY_RES_Y_MAP = {"9:16": 1920, "1:1": 1080, "3:4": 1440, "4:5": 1440, "16:9": 1080}

# UP13 — Multi-variant intelligence: content-type-aware subtitle style per variant.
_VARIANT_AGGRESSIVE_SUB: dict[str, str] = {
    "interview": "viral", "commentary": "viral",
    "vlog": "viral", "tutorial": "viral", "montage": "gaming",
}
_VARIANT_STORY_SUB: dict[str, str] = {
    "interview": "clean", "commentary": "story",
    "vlog": "story", "tutorial": "clean", "montage": "story",
}

# UP14 — Platform-aware editing: small editorial biases per distribution platform.
# All values are lightweight nudges — no pipeline rewrite, no platform-specific render engine.
_PLATFORM_PROFILES: dict[str, dict] = {
    "tiktok": {
        # P4 hardening: increased from 0.04 → 0.08 so pacing difference is perceptible.
        # At 1.07 base: 1.15x output. On 30s clip: ~26s. On 60s clip: ~52s.
        "speed_delta":     0.08,
        "hook_sort_bonus": 6,      # adds up to 6pts to hook-strong clips in initial sort
        "sub_bias": {
            "interview": "viral", "commentary": "viral",
            "vlog": "viral", "tutorial": "viral", "montage": "gaming",
        },
    },
    "youtube_shorts": {
        "speed_delta":     0.0,
        "hook_sort_bonus": 0,
        "sub_bias": {},            # inherit content-type defaults — already tuned for YT
    },
    "instagram_reels": {
        # P4 hardening: increased from -0.03 → -0.06 so polished-pace difference is perceptible.
        # At 1.07 base: 1.01x output. On 30s clip: ~30s. On 60s clip: ~59s.
        "speed_delta":    -0.06,
        "hook_sort_bonus": 0,
        "sub_bias": {
            "interview": "clean", "commentary": "clean",
            "vlog": "clean", "tutorial": "clean", "montage": "gaming",
        },
    },
}


def _select_cover_frame_time(
    clip_duration: float,
    hook_score: float,
    srt_meta: dict,
    target_platform: str,
    variant_type: str,
    cover_hint_ratio: float | None = None,
) -> tuple[float, str]:
    """Score thumbnail candidate offsets and return (offset_sec, reason).

    Uses only existing pipeline signals — no new models, no face detection here.
    Platform and variant nudge where in the clip to look. Hook score biases toward
    earlier frames when the content opens strong. Subtitle timing adds a penalty
    to avoid text-heavy frames.

    cover_hint_ratio (S3.3): advisory ratio [0.05, 0.90] from AI plan assembly.
    RC6: adds at most one extra candidate. UP15 scoring remains authoritative.
    cover_hint_ratio=None → exact no-op (bit-identical to pre-S3.3).
    """
    dur = max(2.0, float(clip_duration or 0))

    # Candidate offsets expressed as fractions of clip duration.
    # Range [0.10, 0.58] avoids opening cuts and mid-roll dropout at the end.
    _FRACS = [0.10, 0.20, 0.32, 0.44, 0.58]
    candidates = [round(max(0.5, min(dur - 0.5, dur * f)), 3) for f in _FRACS]

    # S3.3 RC6: advisory hint adds at most one extra candidate.
    # Deduplicates against existing candidates before appending.
    if cover_hint_ratio is not None:
        try:
            _hint_t = round(max(0.5, min(dur - 0.5, dur * float(cover_hint_ratio))), 3)
            if _hint_t not in candidates:
                candidates.append(_hint_t)
        except (TypeError, ValueError):
            pass

    # Platform position preference: lower value = prefer earlier in clip.
    _plat_bias = {"tiktok": 0.15, "instagram_reels": 0.48, "youtube_shorts": 0.30}
    preferred_pos = _plat_bias.get(str(target_platform).lower(), 0.30)

    # Variant nudge on top of platform preference.
    if variant_type == "aggressive":
        preferred_pos = max(0.05, preferred_pos - 0.10)
    elif variant_type == "story_first":
        preferred_pos = min(0.60, preferred_pos + 0.10)

    # Subtitle window to avoid (first dense text block = worst time for thumbnail).
    # Keys match slice_srt_by_time() output: "first_start" / "first_end" (not "first_sub_*").
    sub_s = float((srt_meta or {}).get("first_start") or -1)
    sub_e = float((srt_meta or {}).get("first_end") or -1)

    best_t, best_score, best_reason = candidates[0], -9999.0, "default"
    for t in candidates:
        norm = t / dur
        score = 0.0

        # Position score: peak when norm == preferred_pos, falls off with distance.
        score += max(0.0, 10.0 - abs(norm - preferred_pos) * 35.0)

        # Hook bonus: strong hook content → earlier frame is more attention-worthy.
        score += (float(hook_score or 0) / 100.0) * (1.0 - norm) * 5.0

        # Stability bonus: middle range has fewer transition artifacts.
        if 0.22 <= norm <= 0.60:
            score += 1.5

        # Subtitle penalty: avoid frames during the first subtitle block.
        if sub_s >= 0 and sub_e > sub_s and sub_s <= t <= sub_e:
            score -= 6.0

        if score > best_score:
            best_score = score
            best_t = t
            best_reason = (
                f"pos={norm:.2f} preferred={preferred_pos:.2f} "
                f"hook={float(hook_score or 0):.0f} platform={target_platform} "
                f"variant={variant_type or 'none'} score={score:.1f}"
            )

    return best_t, best_reason


# UP16 — CTA / Series Intelligence: deterministic end-card text library.
# Content-type keys match content_type_hint values. cta_type keys: comment / part_2 / follow.
# All text is neutral and platform-agnostic — no hype language, no emojis, no cringe.
_CTA_TEXTS: dict[str, dict[str, list[str]]] = {
    "tutorial":   {
        "comment": ["Let me know if this helped.", "Questions? Drop them below."],
        "part_2":  ["Want part 2? Let me know.", "More in the next one."],
        "follow":  ["Follow for more tips.", "More creator tips coming."],
    },
    "commentary": {
        "comment": ["Agree or disagree?", "What would you do?", "Thoughts?"],
        "part_2":  ["More on this coming.", "Continued next."],
        "follow":  ["Follow for more.", "More takes soon."],
    },
    "vlog": {
        "comment": ["What do you think?", "Would you do this?"],
        "part_2":  ["More soon.", "Next part coming."],
        "follow":  ["Follow for more.", "More coming."],
    },
    "interview":  {
        "comment": ["Thoughts on this?", "What's your take?"],
        "part_2":  ["More soon.", "Continued next."],
        "follow":  ["Follow for more.", "More interviews soon."],
    },
    "montage":    {
        "comment": ["What's your favorite moment?", "Which clip?"],
        "part_2":  ["More clips coming.", "Next one soon."],
        "follow":  ["Follow for more.", "More clips soon."],
    },
    "gaming":     {
        "comment": ["What would you have done?", "Which play?"],
        "part_2":  ["More clips coming.", "Next session soon."],
        "follow":  ["Follow for more clips.", "More gaming soon."],
    },
}

# Auto-type: which CTA type fits each content type by default when cta_type=="auto".
_CTA_AUTO_TYPE: dict[str, str] = {
    "tutorial": "part_2", "commentary": "comment", "vlog": "comment",
    "interview": "comment", "montage": "follow", "gaming": "follow",
}


def _select_cta_text(
    content_type: str, target_platform: str, cta_type: str, variant_type: str = ""
) -> str:
    """Return a deterministic CTA string. Pure function — no I/O, no randomness.

    When cta_type="auto" and a variant is active, variant intent shapes the CTA type:
      aggressive → "comment"  (punchy, engagement-first)
      story_first → "follow"  (soft, natural ending)
      balanced / none → content-type auto mapping (existing behaviour)
    Creator's explicit cta_type choice always overrides variant logic.
    """
    ct = str(content_type or "vlog").lower()
    vt = str(variant_type or "").lower()
    if cta_type == "auto":
        if vt == "aggressive":
            cta_type = "comment"    # punchy hook variant → invite engagement
        elif vt == "story_first":
            cta_type = "follow"     # payoff variant → soft natural ending
        else:
            cta_type = _CTA_AUTO_TYPE.get(ct, "follow")
    if cta_type not in ("comment", "part_2", "follow"):
        cta_type = "follow"
    ct_texts = _CTA_TEXTS.get(ct, _CTA_TEXTS["vlog"])
    options = ct_texts.get(cta_type, ct_texts.get("follow", ["More soon."]))
    # Aggressive variant or TikTok: prefer shorter option (index 1) when available.
    if (str(target_platform).lower() == "tiktok" or vt == "aggressive") and len(options) > 1:
        return options[1]
    return options[0]


def _append_cta_block_to_srt(
    srt_path: str, cta_text: str, after_sec: float, clip_end_sec: float
) -> bool:
    """Append a CTA subtitle block to an existing SRT file. Returns True on success."""
    try:
        blocks = parse_srt_blocks(srt_path)
        if not blocks:
            return False
        cta_start = max(float(after_sec) + 0.3, float(clip_end_sec) - 3.0)
        cta_end = min(cta_start + 2.5, float(clip_end_sec) - 0.1)
        if cta_end <= cta_start or cta_start >= float(clip_end_sec):
            return False
        blocks.append({"start": cta_start, "end": cta_end, "text": cta_text})
        write_srt_blocks(blocks, srt_path)
        return True
    except Exception:
        return False


def _get_effective_playback_speed(payload, target_platform: str) -> float:
    """Single source of truth for the playback speed used by both the renderer and the validator.

    Combines the creator-selected base speed with the platform speed delta so that
    expected_duration in output validation matches the actual render output duration.
    """
    platform_delta = _PLATFORM_PROFILES.get(target_platform, {}).get("speed_delta", 0.0)
    return max(0.5, min(1.5, float(payload.playback_speed or 1.0) + platform_delta))


def _read_srt_meta(srt_path: str) -> dict:
    """Read timing metadata from an existing per-part SRT — mirrors slice_srt_by_time return shape.

    Used on the resume path (needs_srt=False) so CTA and logging have correct timestamps.
    """
    try:
        blocks = parse_srt_blocks(srt_path)
        if not blocks:
            return {"subtitle_count": 0, "first_start": None, "first_end": None,
                    "last_start": None, "last_end": None}
        return {
            "subtitle_count": len(blocks),
            "first_start": blocks[0]["start"],
            "first_end":   blocks[0]["end"],
            "last_start":  blocks[-1]["start"],
            "last_end":    blocks[-1]["end"],
        }
    except Exception:
        return {}


def _build_variant_segments(scored: list[dict], payload) -> list[dict]:
    """Select three purposeful segments from the scored pool (aggressive, balanced, story-first).

    Shared compute: scene detection + scoring run once.  Only branching logic lives here.
    Each returned dict carries variant_type / variant_label / variant_subtitle_style /
    variant_playback_speed so the downstream render loop can treat them as normal parts.
    """
    if not scored:
        return scored
    base_speed = float(getattr(payload, "playback_speed", None) or 1.07)
    base_sub = (getattr(payload, "subtitle_style", "") or "").strip()

    def _ct(s: dict) -> str:
        return str(s.get("content_type_hint") or "vlog")

    def _agg_score(s: dict) -> float:
        return (
            float(s.get("hook_score", 0) or 0) * 0.50
            + float(s.get("motion_score", 0) or 0) * 0.25
            + float(s.get("viral_score", 0) or 0) * 0.25
        )

    def _bal_score(s: dict) -> float:
        # scene_quality_score replaces retention_score — retention was never computed
        # by the viral scorer (always 0). scene_quality_score is always populated.
        return (
            float(s.get("viral_score", 0) or 0) * 0.35
            + float(s.get("hook_score", 0) or 0) * 0.20
            + float(s.get("scene_quality_score", 0) or 0) * 0.20
            + float(s.get("speech_density_score", 0) or 0) * 0.10
            + float(s.get("market_score", 0) or 0) * 0.10
            + float(s.get("duration_fit_score", 0) or 0) * 0.05
        )

    _max_start = max((float(s.get("start", 0) or 0) for s in scored), default=1.0) or 1.0

    def _story_score(s: dict) -> float:
        # scene_quality_score replaces retention_score — retention was never computed
        # by the viral scorer (always 0). scene_quality_score reflects visual clarity
        # and transition quality, a real proxy for payoff-worthy content.
        return (
            float(s.get("scene_quality_score", 0) or 0) * 0.45
            + float(s.get("start", 0) or 0) / _max_start * 100 * 0.30
            + float(s.get("viral_score", 0) or 0) * 0.25
        )

    agg   = dict(max(scored, key=_agg_score))
    bal   = dict(max(scored, key=_bal_score))
    story = dict(max(scored, key=_story_score))

    agg["variant_type"]            = "aggressive"
    agg["variant_label"]           = "Aggressive"
    agg["variant_subtitle_style"]  = _VARIANT_AGGRESSIVE_SUB.get(_ct(agg), "viral")
    agg["variant_playback_speed"]  = round(min(1.15, base_speed + 0.05), 3)
    agg["selection_reason"]        = "Aggressive: hook-forward selection"

    bal["variant_type"]            = "balanced"
    bal["variant_label"]           = "Balanced"
    bal["variant_subtitle_style"]  = base_sub or None
    bal["variant_playback_speed"]  = base_speed
    bal["selection_reason"]        = "Balanced: overall best-quality selection"

    story["variant_type"]          = "story_first"
    story["variant_label"]         = "Story-first"
    story["variant_subtitle_style"] = _VARIANT_STORY_SUB.get(_ct(story), "story")
    story["variant_playback_speed"] = round(max(0.97, base_speed - 0.05), 3)
    story["selection_reason"]      = "Story-first: payoff-forward selection"

    # P3 — Small-pool honesty: warn when variants overlap (limited source variety).
    # No artificial diversity injection — honest about what the pool contains.
    _v_starts = [
        round(float(agg.get("start", 0) or 0), 1),
        round(float(bal.get("start", 0) or 0), 1),
        round(float(story.get("start", 0) or 0), 1),
    ]
    _unique_starts = len(set(_v_starts))
    if _unique_starts == 1:
        _pool_note = " [limited source variety — all variants share same source clip]"
        for _v in (agg, bal, story):
            _v["selection_reason"] = _v["selection_reason"] + _pool_note
        logger.warning(
            "multi_variant_collapsed pool_size=%d all_start=%.1f — source too short for distinct variants",
            len(scored), _v_starts[0],
        )
    elif _unique_starts == 2:
        _dup_starts: dict[float, list] = {}
        for _v, _s in zip((agg, bal, story), _v_starts):
            _dup_starts.setdefault(_s, []).append(_v)
        for _dup_group in _dup_starts.values():
            if len(_dup_group) > 1:
                for _v in _dup_group:
                    _v["selection_reason"] = _v["selection_reason"] + " [shares source clip with another variant]"
        logger.info(
            "multi_variant_partial_collapse pool_size=%d unique_starts=%d",
            len(scored), _unique_starts,
        )

    logger.info(
        "multi_variant_selected agg_start=%.1f bal_start=%.1f story_start=%.1f unique_segs=%d",
        float(agg.get("start", 0) or 0),
        float(bal.get("start", 0) or 0),
        float(story.get("start", 0) or 0),
        _unique_starts,
    )
    return [agg, bal, story]


def _aspect_play_res_y(aspect_ratio: str) -> int:
    ar = (aspect_ratio or "").strip()
    val = _PLAY_RES_Y_MAP.get(ar)
    if val is None:
        logger.warning("_aspect_play_res_y: unrecognised aspect_ratio=%r, defaulting to 1440", ar)
        return 1440
    return val

def resolve_combined_score_weights(
    target_market: "str | None",
    has_market_score: bool,
    has_hook_score: bool,
    duration: "float | None",
    adaptive_enabled: bool,
) -> dict:
    """Return combined-score weights that always sum to 1.0.

    When adaptive_enabled=False returns fixed P3-2 defaults.
    When True applies market/availability/duration adjustments then normalizes.
    """
    BASE_VIRAL  = 0.50
    BASE_MARKET = 0.30
    BASE_HOOK   = 0.20

    if not adaptive_enabled:
        return {
            "viral_weight":  BASE_VIRAL,
            "market_weight": BASE_MARKET,
            "hook_weight":   BASE_HOOK,
            "reason":        "fixed",
        }

    w_v = BASE_VIRAL
    w_m = BASE_MARKET
    w_h = BASE_HOOK
    reasons: list[str] = []

    # ── Market adjustment ──────────────────────────────────────────────────
    market = (target_market or "US").upper()
    if market == "US":
        w_h += 0.05; w_v += 0.05; w_m -= 0.10
        reasons.append("US:hook+viral")
    elif market == "EU":
        w_m += 0.10; w_h -= 0.05; w_v -= 0.05
        reasons.append("EU:market+")
    elif market == "JP":
        w_m += 0.05; w_h += 0.05; w_v -= 0.10
        reasons.append("JP:market+hook")

    # ── Missing score redistribution ───────────────────────────────────────
    if not has_market_score:
        half = w_m / 2.0
        w_v += half; w_h += half; w_m = 0.0
        reasons.append("no_mv:redistribute")

    if not has_hook_score:
        half = w_h / 2.0
        w_v += half; w_m += half; w_h = 0.0
        reasons.append("no_hook:redistribute")

    # ── Duration adjustment ────────────────────────────────────────────────
    dur = float(duration or 0)
    if dur > 90:
        w_v += 0.05; w_h -= 0.05
        reasons.append("long:viral+")
    elif 0 < dur < 10:
        w_h += 0.05; w_m -= 0.05
        reasons.append("short:hook+")
    # 10–90 s: no change

    # ── Clamp each active weight to [0.10, 0.70] ──────────────────────────
    W_MIN, W_MAX = 0.10, 0.70
    w_v = max(W_MIN, min(W_MAX, w_v))
    if has_market_score and w_m > 0:
        w_m = max(W_MIN, min(W_MAX, w_m))
    if has_hook_score and w_h > 0:
        w_h = max(W_MIN, min(W_MAX, w_h))

    # ── Normalize → sum = 1.0 ─────────────────────────────────────────────
    total = w_v + w_m + w_h
    if total > 0:
        w_v /= total; w_m /= total; w_h /= total
    else:
        w_v, w_m, w_h = 1.0, 0.0, 0.0

    return {
        "viral_weight":  round(w_v, 4),
        "market_weight": round(w_m, 4),
        "hook_weight":   round(w_h, 4),
        "reason":        ";".join(reasons) or "adaptive_default",
    }


def _score_component(value, default: float = 50.0) -> float:
    """Return a clamped 0-100 score, using neutral default only when missing."""
    if value is None or value == "":
        return default
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return default


# _maybe_prepend_remotion_hook_intro, _maybe_prepend_asset_intro,
# _maybe_append_asset_outro, _maybe_apply_asset_logo
# → moved to app.orchestration.asset_pipeline (Phase 4B)



# _maybe_cleanup_narration_audio → moved to app.orchestration.audio_pipeline (Phase 4D)


def _first_score(seg: dict, names: list[str], default: float = 50.0) -> float:
    for name in names:
        if name in seg and seg.get(name) not in (None, ""):
            return _score_component(seg.get(name), default=default)
    return default


_RANKING_WEIGHTS: dict[str, float] = {
    "segment_viral_score":  0.35,
    "hook_score":           0.20,
    "retention_score":      0.20,
    "speech_density_score": 0.10,
    "market_score":         0.10,
    "duration_fit_score":   0.05,
}


def _output_ranking_detail(components: dict) -> dict:
    contribs = {k: components.get(k, 50.0) * w for k, w in _RANKING_WEIGHTS.items()}
    total = sum(contribs.values()) or 1.0
    ranked = sorted(contribs.items(), key=lambda x: x[1], reverse=True)
    top_signal, top_contrib = ranked[0]
    material = [s for s, c in ranked if c >= top_contrib * 0.60]
    suppressed = [s for s, c in ranked[1:] if c < top_contrib * 0.60 and components.get(s, 50.0) >= 65]
    return {
        "dominant_signal": top_signal,
        "dominant_pct": round(top_contrib / total * 100, 1),
        "material_signals": material,
        "suppressed_signals": suppressed,
    }


def _output_ranking_reason(components: dict) -> str:
    content_type = str(components.get("content_type_hint") or "")
    detail = _output_ranking_detail(components)

    def _label(signal: str, raw: float) -> "str | None":
        if signal == "segment_viral_score":
            if raw >= 65:
                if content_type == "montage":
                    return "High visual energy"
                if content_type in ("interview", "tutorial"):
                    return "Strong spoken segment"
                return "Strong segment"
        elif signal == "hook_score":
            if raw >= 60:
                return ("Strong spoken hook" if content_type in ("interview", "commentary", "tutorial", "podcast")
                        else "Strong opening hook")
            if raw < 40:
                return "Weak opening"
        elif signal == "retention_score":
            if raw >= 65:
                return ("High engagement energy" if content_type in ("interview", "tutorial") else "Good retention")
        elif signal == "speech_density_score":
            if raw >= 60 and content_type in ("interview", "commentary", "tutorial", "podcast"):
                return "Dense spoken content"
            if raw < 20 and content_type == "montage":
                return "Pure visual"
        elif signal == "market_score":
            if raw >= 65:
                return "Good market match"
        elif signal == "duration_fit_score":
            if raw >= 75:
                return "Ideal duration"
        return None

    reasons: list[str] = []
    for sig in detail["material_signals"]:
        if len(reasons) >= 2:
            break
        label = _label(sig, components.get(sig, 50.0))
        if label and label not in reasons:
            reasons.append(label)

    if not reasons:
        if content_type == "montage":
            reasons.append("High-energy montage")
        elif content_type in ("interview", "commentary", "tutorial"):
            reasons.append("Quality spoken content")
        else:
            reasons.append("Balanced clip signals")

    return ", ".join(reasons[:2])


def _compute_output_ranking_entry(part_no: int, seg: dict, output_file: str, payload_hook_score=None) -> dict:
    segment_viral_score = _first_score(seg, ["viral_score"], default=50.0)
    hook_score = _first_score(
        seg,
        ["hook_text_score", "hook_timing_score", "hook_score", "hook_opening_score"],
        default=_score_component(payload_hook_score, default=50.0),
    )
    retention_score = _first_score(seg, ["retention_score"], default=50.0)
    speech_density_score = _first_score(seg, ["speech_density_score"], default=50.0)
    market_score = _first_score(seg, ["mv_viral_score", "market_viral_score"], default=50.0)
    duration_fit_score = _first_score(seg, ["duration_fit_score"], default=50.0)
    continuity_score = _first_score(seg, ["continuity_score"], default=50.0)

    raw_score = (
        segment_viral_score * 0.35
        + hook_score * 0.20
        + retention_score * 0.20
        + speech_density_score * 0.10
        + market_score * 0.10
        + duration_fit_score * 0.05
    )
    output_score = round(max(0.0, min(100.0, raw_score)), 1)
    components = {
        "segment_viral_score": round(segment_viral_score, 1),
        "hook_score": round(hook_score, 1),
        "retention_score": round(retention_score, 1),
        "speech_density_score": round(speech_density_score, 1),
        "market_score": round(market_score, 1),
        "duration_fit_score": round(duration_fit_score, 1),
        "continuity_score": round(continuity_score, 1),
        "content_type_hint": str(seg.get("content_type_hint") or ""),
    }

    _detail = _output_ranking_detail(components)
    return {
        "part_no": part_no,
        "output_file": output_file,
        "output_rank": 0,
        "output_score": output_score,
        "is_best_clip": False,
        "ranking_reason": _output_ranking_reason(components),
        "ranking_components": components,
        "dominant_signal": _detail["dominant_signal"],
        "suppressed_signals": _detail["suppressed_signals"],
        "selection_reason": seg.get("selection_reason", ""),
        # Backward-compatible aliases consumed by existing render UI.
        "output_rank_score": output_score,
        "is_best_output": False,
        "reasons": [
            f"segment_viral={components['segment_viral_score']}",
            f"hook={components['hook_score']}",
            f"retention={components['retention_score']}",
            f"speech_density={components['speech_density_score']}",
            f"market={components['market_score']}",
            f"duration_fit={components['duration_fit_score']}",
        ],
    }


# _PROGRESS_TICK_SEC, _render_progress_timer → moved to app.orchestration.render_events (Phase 4D)

# _resume_output_valid → moved to app.orchestration.qa_pipeline (Phase 4C)


# ---------------------------------------------------------------------------
# Resource throttling
# ---------------------------------------------------------------------------
# JOB_SEMAPHORE caps how many render pipelines can be in the FFmpeg-encode
# section simultaneously.  This prevents CPU saturation when multiple jobs
# are dispatched by the scheduler at the same time.
# Default derives from MAX_CONCURRENT_JOBS so the semaphore never silently
# under-utilises slots that the scheduler has already granted.
# Override with MAX_RENDER_JOBS env var to set an explicit ceiling.
_JOB_SEM_VALUE: int = max(1, int(os.getenv("MAX_RENDER_JOBS", str(_MAX_CONCURRENT_JOBS))))
JOB_SEMAPHORE = threading.Semaphore(_JOB_SEM_VALUE)
_render_active_lock = threading.Lock()
_render_active_count: list[int] = [0]   # mutable int; guarded by _render_active_lock


def _apply_subtitle_edits_to_srt(srt_path: str, edits: list) -> None:
    """Patch specific SRT blocks in-place with user-supplied text.

    Matches by index (0-based segment position in file).  For each edit,
    verifies that the block's start-time is within 0.5 s of the stored value
    to guard against offset drift.  On any mismatch or error the edit is
    silently skipped and the original block is preserved.
    """
    import re as _re
    if not edits:
        return
    edit_map = {}
    for e in edits:
        try:
            edit_map[int(e['index'])] = e
        except (KeyError, TypeError, ValueError):
            pass
    if not edit_map:
        return

    _srt_ts_re = _re.compile(
        r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})'
    )

    def _ts_to_sec(h, m, s, ms):
        return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0

    try:
        raw = Path(srt_path).read_text(encoding='utf-8', errors='replace')
    except Exception:
        return

    blocks = _re.split(r'\n{2,}', raw.strip())
    changed = False
    out_blocks = []
    for blk_idx, blk in enumerate(blocks):
        lines = blk.strip().splitlines()
        if blk_idx in edit_map and len(lines) >= 3:
            edit = edit_map[blk_idx]
            ts_match = _srt_ts_re.search(blk)
            if ts_match:
                blk_start = _ts_to_sec(*ts_match.groups()[:4])
                try:
                    expected_start = float(edit.get('start', blk_start))
                except (TypeError, ValueError):
                    expected_start = blk_start
                if abs(blk_start - expected_start) <= 0.5:
                    seq_line = lines[0]
                    ts_line  = lines[1]
                    new_blk  = f"{seq_line}\n{ts_line}\n{str(edit['text']).strip()}"
                    out_blocks.append(new_blk)
                    changed = True
                    continue
        out_blocks.append(blk)

    if changed:
        try:
            Path(srt_path).write_text('\n\n'.join(out_blocks) + '\n', encoding='utf-8')
        except Exception as exc:
            logger.warning("subtitle_edits: failed to write patched SRT (%s): %s", srt_path, exc)


# _duration_tolerance, _stall_deadline → moved to app.orchestration.qa_pipeline (Phase 4C)


# _render_progress_timer → moved to app.orchestration.render_events (Phase 4D)


HIGH_MOTION_MIN_SCORE = 60
HIGH_MOTION_MIN_KEEP = 3
# _JOB_LOG_DIRS, _job_log, _append_json_line, _render_error_code, _emit_render_event
# → moved to app.orchestration.render_events (Phase 4B)


# _event_from_stage, _resolve_job_log_dir → moved to app.orchestration.render_events (Phase 4D)


def _validate_text_layers_or_400(payload: RenderRequest) -> list[dict]:
    try:
        raw_layers = [x.model_dump() if hasattr(x, "model_dump") else dict(x) for x in (payload.text_layers or [])]
        if len(raw_layers) > MAX_TEXT_LAYERS:
            raise ValueError(f"text_layers exceeds maximum {MAX_TEXT_LAYERS}")
        return normalize_text_layers(raw_layers)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid text_layers: {exc}") from exc


def _resolve_profile(payload: RenderRequest):
    profile = (payload.render_profile or "quality").lower()
    defaults = {
        # fast: quick turnaround, acceptable quality — base keeps CPU transcription fast
        "fast":     {"video_preset": "veryfast", "video_crf": 23, "whisper_model": "base",     "transition_sec": 0.05},
        # balanced: good quality/speed — small keeps CPU latency acceptable (~30s vs 90-120s for large-v3)
        "balanced": {"video_preset": "medium",   "video_crf": 18, "whisper_model": "small",    "transition_sec": 0.06},
        # quality: high quality — large-v3 gives near-perfect transcript accuracy
        "quality":  {"video_preset": "slow",     "video_crf": 15, "whisper_model": "large-v3", "transition_sec": 0.06},
        # best: maximum quality — large-v3 is the ceiling for open-weight ASR
        "best":     {"video_preset": "slower",   "video_crf": 13, "whisper_model": "large-v3", "transition_sec": 0.08},
    }
    picked = defaults.get(profile, defaults["quality"])
    if payload.video_preset:
        logger.info("profile_override_used: video_preset=%s (profile=%s default=%s)", payload.video_preset, profile, picked["video_preset"])
    if payload.video_crf is not None:
        logger.info("profile_override_used: video_crf=%s (profile=%s default=%s)", payload.video_crf, profile, picked["video_crf"])
    whisper_model = payload.whisper_model
    if (whisper_model or "auto").lower() == "auto":
        whisper_model = picked["whisper_model"]
    return {
        "video_preset": payload.video_preset or picked["video_preset"],
        "video_crf": max(12, min(32, int(payload.video_crf or picked["video_crf"]))),
        "whisper_model": whisper_model,
        "transition_sec": max(0.0, min(1.5, float(payload.transition_sec if payload.transition_sec is not None else picked["transition_sec"]))),
    }


def _probe_video_duration(video_path: Path) -> int:
    cmd = [
        get_ffprobe_bin(),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return max(0, int(float((r.stdout or "0").strip() or 0)))
    except Exception:
        return 0


def extract_text_from_srt(srt_path: str) -> str:
    import re
    try:
        text_lines = []
        with open(srt_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if re.match(r"^\d+$", line):
                    continue
                if "-->" in line:
                    continue
                text_lines.append(line)
        text = " ".join(text_lines)
        text = re.sub(r" {2,}", " ", text).strip()
        if text and text[-1] not in ".!?":
            text += "."
        return text
    except Exception:
        return ""


def _reserve_source_path_in_dir(source_dir: Path, slug: str, ext: str = ".mp4") -> Path:
    source_dir.mkdir(parents=True, exist_ok=True)
    base = source_dir / f"{slug}{ext}"
    if not base.exists():
        return base
    idx = 1
    while True:
        candidate = source_dir / f"{slug}_{idx}{ext}"
        if not candidate.exists():
            return candidate
        idx += 1


def _reserve_source_path(channel_code: str, slug: str, ext: str = ".mp4") -> Path:
    return _reserve_source_path_in_dir(CHANNELS_DIR / channel_code / "upload" / "source", slug, ext=ext)


# _safe_unlink → moved to app.orchestration.render_events (Phase 4B)


# _failed_part_progress → moved to app.orchestration.qa_pipeline (Phase 4C)


# _validate_render_output → moved to app.orchestration.qa_pipeline (Phase 4C)


# _assess_output_quality → moved to app.orchestration.qa_pipeline (Phase 4C)


# _render_part_failure_detail → moved to app.orchestration.qa_pipeline (Phase 4C)


def _sanitize_channel_subdir(value: str | None) -> str:
    raw = (value or "Video").strip().replace("\\", "/")
    raw = raw.strip("/")
    if not raw:
        return "Video"
    parts = [p for p in raw.split("/") if p not in ("", ".", "..")]
    safe = "/".join(parts).strip()
    return safe or "Video"


def _resolve_output_dir(channel_code: str, raw_output_dir: str, render_output_subdir: str | None = None) -> Path:
    raw = (raw_output_dir or "").strip()
    channel_base = (CHANNELS_DIR / channel_code).resolve()
    fallback = channel_base / _sanitize_channel_subdir(render_output_subdir)
    if not raw:
        return fallback

    norm = raw.replace("\\", "/")
    legacy_prefix = f"/data/channels/{channel_code}/"
    legacy_prefix_no_slash = f"data/channels/{channel_code}/"
    if norm.startswith(legacy_prefix):
        rel = norm[len(legacy_prefix):]
        return (channel_base / rel).resolve()
    if norm.startswith(legacy_prefix_no_slash):
        rel = norm[len(legacy_prefix_no_slash):]
        return (channel_base / rel).resolve()
    if norm.startswith("/data/channels/"):
        return fallback

    p = Path(raw)
    if p.is_absolute():
        return p
    return (Path.cwd() / p).resolve()


def run_render_pipeline(
    job_id: str,
    payload: RenderRequest,
    resume_mode: bool = False,
    *,
    load_session_fn: Callable,
    cleanup_session_fn: Callable,
):
    output_mode = (payload.output_mode or "channel").strip().lower()
    effective_channel = (payload.channel_code or "").strip() or "manual"
    started_at = datetime.utcnow()

    # Market Viral — resolve target market once; used by all part workers via closure
    _mv_cfg = getattr(payload, "market_viral", None) or {}
    _mv_cfg_enabled = isinstance(_mv_cfg, dict) and bool(_mv_cfg)
    _mv_payload_market = getattr(payload, "viral_market", None)
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
    _JOB_LOG_DIRS[job_id] = _resolve_job_log_dir(output_dir, output_mode, effective_channel)
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    tuned = _resolve_profile(payload)
    retry_count = max(0, min(5, int(payload.retry_count)))
    current_stage = JobStage.STARTING
    current_progress = 1

    def _set_stage(stage: str, progress: int, message: str):
        nonlocal current_stage, current_progress
        current_stage = stage
        current_progress = max(0, min(99, int(progress)))
        update_job_progress(job_id, stage, progress, message)
        _job_log(effective_channel, job_id, f"[STAGE] {stage} | {message}")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event=_event_from_stage(stage),
            level="INFO",
            message=message,
            step=stage,
            context={"progress_percent": progress},
        )

    _job_log(
        effective_channel,
        job_id,
        f"Render started | resume={resume_mode} | profile={payload.render_profile} | codec={payload.video_codec} | reup_mode={payload.reup_mode} | source_mode={payload.source_mode} | output_mode={output_mode}",
    )
    _job_log(
        effective_channel,
        job_id,
        f"Market Viral hook | market={_mv_market} | hook_apply_enabled={_hook_apply_enabled} | hook_score={_hook_score}",
    )
    _preset_name = str(getattr(payload, "render_preset", None) or "").strip() or "custom"
    _preset_id = str(getattr(payload, "render_preset_id", None) or _preset_name or "").strip() or "custom"
    _preset_label = str(getattr(payload, "render_preset_label", None) or "").strip()
    if not _preset_label:
        _preset_label = "Custom" if _preset_id.lower() == "custom" else _preset_id
    if _preset_id and _preset_id.lower() != "custom":
        _job_log(
            effective_channel,
            job_id,
            f"Render preset applied | id={_preset_id} | label={_preset_label}",
        )
    _job_log(
        effective_channel, job_id,
        f"profile_resolved | render_profile={payload.render_profile} | preset={tuned['video_preset']} crf={tuned['video_crf']} whisper={tuned['whisper_model']} trans={tuned['transition_sec']:.2f}",
    )
    if payload.video_preset:
        _job_log(effective_channel, job_id, f"profile_override_used video_preset={payload.video_preset}", kind="warning")
    if payload.video_crf is not None:
        _job_log(effective_channel, job_id, f"profile_override_used video_crf={payload.video_crf}", kind="warning")
    try:
        normalized_text_layers = _validate_text_layers_or_400(payload)
    except Exception as layer_exc:
        normalized_text_layers = []
        _job_log(effective_channel, job_id, f"Text layer parse warning: {layer_exc}", kind="warning")
        update_job_progress(
            job_id, "starting", 0,
            f"⚠️ Text overlays skipped (parse error): {layer_exc}",
        )
    _job_log(
        effective_channel,
        job_id,
        f"Text overlay layers accepted: {len(normalized_text_layers)}",
    )
    for layer_idx, layer in enumerate(normalized_text_layers, start=1):
        _job_log(
            effective_channel,
            job_id,
            f"Text layer {layer_idx}: order={layer.get('order', layer_idx-1)} "
            f"pos={layer.get('position', 'bottom-center')} "
            f"xy={float(layer.get('x_percent', 50) or 50):.1f}%,{float(layer.get('y_percent', 90) or 90):.1f}% "
            f"time={float(layer.get('start_time', 0) or 0):.2f}->{float(layer.get('end_time', 0) or 0):.2f}",
            kind="debug",
        )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.text_layers.accepted",
        level="INFO",
        message=f"Accepted {len(normalized_text_layers)} text layer(s)",
        step="render.text_layers",
        context={"layer_count": len(normalized_text_layers)},
    )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.start",
        level="INFO",
        message="Render started",
        step="render.start",
        context={
            "resume_mode": bool(resume_mode),
            "profile": payload.render_profile,
            "codec": payload.video_codec,
            "source_mode": payload.source_mode,
            "output_mode": output_mode,
        },
    )
    upsert_job(
        job_id,
        "render",
        effective_channel,
        "running",
        payload.model_dump(),
        {},
        stage=JobStage.STARTING,
        progress_percent=1,
        message="Resuming render job" if resume_mode else "Initializing render job",
    )
    _final_status = ""  # set to terminal status string on success path; empty means failure/cancelled
    edit_session_id = ""  # assigned inside try; pre-init so finally block can reference it safely
    try:
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.start",
            level="INFO",
            message="Preparing source",
            step="render.prepare_source",
            context={"source_mode": payload.source_mode},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.input.validate.start",
            level="INFO",
            message="Validating render input",
            step="render.input.validate",
        )
        _set_stage(JobStage.DOWNLOADING, 5, "Preparing source video")
        edit_session_id = (getattr(payload, "edit_session_id", None) or "").strip()
        sess = load_session_fn(edit_session_id) if edit_session_id else None
        if edit_session_id and not sess:
            raise RuntimeError(
                f"Editor session '{edit_session_id}' not found — "
                "the session may have expired or the server was restarted. "
                "Please re-open the editor to re-prepare the source."
            )
        detected_source_mode = "session" if sess else ((payload.source_mode or "youtube").lower())
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.detect_input",
            level="INFO",
            message=f"Detecting source type: {detected_source_mode}",
            step="render.prepare_source.detect_input",
            context={"source_mode": detected_source_mode},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.validate_input",
            level="INFO",
            message="Validating source input",
            step="render.prepare_source.validate_input",
        )
        if sess:
            source_path = Path(sess["video_path"])
            if not source_path.exists():
                raise RuntimeError(f"Editor session video not found: {source_path}")
            source = {
                "title": sess.get("title", source_path.stem),
                "slug": slugify(sess.get("title", source_path.stem)),
                "duration": sess.get("duration") or _probe_video_duration(source_path),
                "filepath": str(source_path),
            }
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.prepare_paths",
                level="INFO",
                message="Preparing source paths",
                step="render.prepare_source.prepare_paths",
                context={"source_path": str(source_path), "work_dir": str(work_dir)},
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.select_strategy",
                level="INFO",
                message="Selecting editor-session source strategy",
                step="render.prepare_source.select_strategy",
                context={"strategy": "editor_session"},
            )
            _job_log(effective_channel, job_id, f"Reusing editor session video: {source_path}")
        elif (payload.source_mode or "youtube").lower() == "local":
            source_path = Path(payload.source_video_path or "").expanduser().resolve()
            if not source_path.exists() or not source_path.is_file():
                raise RuntimeError(
                    f"Render stopped: the source video file was not found.\n"
                    f"Path: {source_path}\n"
                    f"Please reopen the editor and verify the file is still accessible."
                )
            source = {
                "title": source_path.stem.replace("_", " ").replace("-", " "),
                "slug": slugify(source_path.stem),
                "duration": _probe_video_duration(source_path),
                "filepath": str(source_path),
            }
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.prepare_paths",
                level="INFO",
                message="Preparing source paths",
                step="render.prepare_source.prepare_paths",
                context={"source_path": str(source_path), "work_dir": str(work_dir)},
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.select_strategy",
                level="INFO",
                message="Selecting local source strategy",
                step="render.prepare_source.select_strategy",
                context={"strategy": "local_source"},
            )
            _job_log(effective_channel, job_id, f"Local source selected: {source_path}")
        else:
            yt_url = (payload.youtube_url or "").strip() or (payload.youtube_urls[0] if payload.youtube_urls else "")
            _job_log(effective_channel, job_id, f"YouTube source URL: {yt_url}")
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.prepare_paths",
                level="INFO",
                message="Preparing source paths",
                step="render.prepare_source.prepare_paths",
                context={"work_dir": str(work_dir)},
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.select_strategy",
                level="INFO",
                message="Selecting YouTube download strategy",
                step="render.prepare_source.select_strategy",
                context={"strategy": "youtube_download", "url": yt_url},
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.download.start",
                level="INFO",
                message="Downloading source from YouTube",
                step="render.download",
                context={"url": yt_url, "source_quality_mode": payload.source_quality_mode},
            )
            source = download_youtube(
                yt_url,
                work_dir,
                quality_mode=payload.source_quality_mode,
                cancel_event=cancel_registry.get_event(job_id),
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.download.success",
                level="INFO",
                message="YouTube source downloaded",
                step="render.download",
                context={
                    "title": source.get("title", ""),
                    "duration": source.get("duration", 0),
                    "format": source.get("selected_format", ""),
                },
            )
            _job_log(
                effective_channel,
                job_id,
                f"Downloaded source: {source['title']} ({source['duration']}s) | "
                f"height={source.get('selected_height', 0)} fps={source.get('selected_fps', 0)} "
                f"format={source.get('selected_format', '')}",
            )
            source_path = Path(source["filepath"])
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.input.validate.success",
            level="INFO",
            message="Render input validated",
            step="render.input.validate",
            context={"source_path": str(source_path)},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.success",
            level="INFO",
            message="Source prepared successfully",
            step="render.prepare_source.success",
            context={"source_mode": detected_source_mode, "source_path": str(source_path)},
        )

        # Compute once; captured by _process_one_part closure and auto_best_export
        _output_stem = _smart_output_stem(_hook_applied_text, source.get("title", ""), job_id)

        # Apply editor edits: trim and/or volume adjustment
        trim_in = float(getattr(payload, "edit_trim_in", 0) or 0)
        trim_out = float(getattr(payload, "edit_trim_out", 0) or 0)
        edit_volume = float(getattr(payload, "edit_volume", 1.0) or 1.0)
        needs_trim = trim_in > 0.5 or (trim_out > 0.5 and trim_out < source["duration"] - 0.5)
        needs_volume = abs(edit_volume - 1.0) > 0.005
        if needs_trim or needs_volume:
            edited_path = work_dir / f"edited_{source_path.stem}.mp4"
            cmd = [get_ffmpeg_bin(), "-y"]
            if trim_in > 0.5:
                cmd += ["-ss", f"{trim_in:.3f}"]
            cmd += ["-i", str(source_path)]
            if needs_trim and trim_out > 0.5 and trim_out < source["duration"] - 0.5:
                duration_t = trim_out - (trim_in if trim_in > 0.5 else 0)
                cmd += ["-t", f"{max(1.0, duration_t):.3f}"]
            if needs_volume:
                cmd += ["-af", f"volume={edit_volume:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k"]
            else:
                cmd += ["-c:v", "copy", "-c:a", "copy"]
            cmd += ["-avoid_negative_ts", "make_zero", str(edited_path)]
            _job_log(effective_channel, job_id, f"Applying edits: trim_in={trim_in:.1f}s trim_out={trim_out:.1f}s volume={edit_volume:.2f}")
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as _preprocess_exc:
                _pp_stderr = _preprocess_exc.stderr or ""
                _pp_diag = _summarize_ffmpeg_stderr(_pp_stderr)
                _pp_tail = _pp_stderr[-2000:].strip()
                _job_log(
                    effective_channel, job_id,
                    f"FFmpeg preprocess failed exit={_preprocess_exc.returncode} diag={_pp_diag!r}",
                    kind="warning",
                )
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="render.ffmpeg.preprocess.error",
                    level="ERROR",
                    message=f"FFmpeg preprocess failed: {_pp_diag}",
                    step="render.preprocess",
                    context={
                        "exit_code": _preprocess_exc.returncode,
                        "diagnostic": _pp_diag,
                        "stderr_tail": _pp_tail,
                        "input_path": str(source_path),
                        "output_path": str(edited_path),
                    },
                )
                raise RuntimeError(f"FFmpeg preprocess failed: {_pp_diag}") from _preprocess_exc
            new_dur = _probe_video_duration(edited_path)
            source["duration"] = new_dur or max(1, source["duration"] - trim_in)
            source_path = edited_path
            source["filepath"] = str(edited_path)
            _job_log(effective_channel, job_id, f"Edits applied → {edited_path} | new_duration={source['duration']}s")

        # Pre-render source preflight: catch local files moved/deleted after initial validation
        _detected_source_mode = (payload.source_mode or "youtube").lower()
        if _detected_source_mode == "local" and not source_path.exists():
            raise RuntimeError(
                f"Render stopped: the source video file was moved or deleted.\n"
                f"Path: {source_path}\n"
                f"Please reopen the editor and confirm the file is still accessible."
            )

        if payload.keep_source_copy:
            ext = source_path.suffix or ".mp4"
            keep_source_dir = output_dir / "source"
            # If output is a typical "video_output/video_out" folder, keep source as sibling under upload/source.
            if output_dir.name.lower() in ("video_output", "video_out"):
                keep_source_dir = output_dir.parent / "source"
            # Only temp-origin files (YouTube downloads, edited locals) need to be
            # persisted into source/. A user's original local file is already permanent —
            # copying it would waste disk space (10 GB+) and slow render startup.
            is_temp_source = str(source_path).startswith(str(TEMP_DIR))
            if is_temp_source:
                keep_path = _reserve_source_path_in_dir(keep_source_dir, source["slug"], ext=ext)
                if not keep_path.exists():
                    # Move instead of copy when source is in temp dir (instant on same drive, saves I/O + disk)
                    try:
                        shutil.move(str(source_path), str(keep_path))
                        _job_log(effective_channel, job_id, f"Source moved (zero-copy) to: {keep_path}")
                    except Exception:
                        shutil.copy2(source_path, keep_path)
                        _job_log(effective_channel, job_id, f"Source copied to: {keep_path}")
                source_path = keep_path
            else:
                # Local original (not temp): render directly from user's file — no copy, no hardlink.
                _job_log(effective_channel, job_id, f"local_source.passthrough path={source_path} (source copy skipped)")

        voice_audio_path = None
        _voice_tts_failed = False
        _voice_mix_ok = []
        _voice_part_tts_attempts = []
        _sub_translate_attempts = []
        _sub_translate_clean = []
        _sub_translate_partial = []
        _sub_translate_failed_parts = []
        _recovery_notes: list[str] = []   # UP24: accumulate fallback events for observability
        if getattr(payload, "voice_enabled", False) and getattr(payload, "voice_source", "manual") == "manual":
            if cancel_registry.is_cancelled(job_id):
                raise cancel_registry.JobCancelledError()
            try:
                update_job_progress(job_id, current_stage, current_progress, "Generating AI voice...")
                _job_log(effective_channel, job_id, "Generating AI narration audio")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="voice_tts_started",
                    level="INFO",
                    message="Generating AI voice",
                    step="voice.tts",
                    context={"language": payload.voice_language, "gender": payload.voice_gender},
                )
                # Infer content type from subtitle_style since manual voice fires before
                # segment scoring. subtitle_style is the best available creator-intent signal.
                _manual_voice_ct = {
                    "viral":   "commentary",
                    "clean":   "tutorial",
                    "story":   "vlog",
                    "gaming":  "montage",
                }.get((payload.subtitle_style or "").strip().lower(), "vlog")
                voice_audio_path = generate_narration_audio(
                    text=str(payload.voice_text or ""),
                    language=payload.voice_language,
                    gender=payload.voice_gender,
                    rate=payload.voice_rate,
                    job_id=job_id,
                    voice_id=getattr(payload, "voice_id", None),
                    content_type=_manual_voice_ct,
                    tts_engine=getattr(payload, "tts_engine", "edge"),
                )
                update_job_progress(job_id, current_stage, current_progress, "AI voice generated")
                _job_log(effective_channel, job_id, f"AI narration audio ready: {voice_audio_path}")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="voice_tts_completed",
                    level="INFO",
                    message="AI voice generated",
                    step="voice.tts",
                    context={"audio_path": str(voice_audio_path), "voice_text_length": len(str(payload.voice_text or ""))},
                )
                voice_audio_path = _maybe_cleanup_narration_audio(
                    str(voice_audio_path),
                    payload,
                    effective_channel=effective_channel,
                    job_id=job_id,
                    source="manual",
                )
            except Exception as voice_exc:
                voice_audio_path = None
                _voice_tts_failed = True
                update_job_progress(job_id, current_stage, current_progress, "AI voice failed - continuing with original audio")
                _job_log(effective_channel, job_id, f"AI voice generation failed: {voice_exc}", kind="error")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="voice_failed",
                    level="ERROR",
                    message=f"AI voice generation failed: {voice_exc}",
                    step="voice.tts",
                    exception=voice_exc,
                    traceback_text=traceback.format_exc(),
                    context={"error_code": "VOICE001"},
                )
                # UP24: recovery — voice is optional, render continues without it
                _recovery_notes.append("AI narration failed — rendered without voice")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="recovery_success",
                    level="INFO",
                    message="Recovery: AI narration failed, rendering without voice (original audio preserved)",
                    step="voice.tts",
                    context={"recovery_strategy": "skip_voice"},
                )

        _set_stage(JobStage.SCENE_DETECTION, 15, "Detecting scenes")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.scene.detect.start",
            level="INFO",
            message="Detecting scenes",
            step="render.scene.detect",
        )
        if cancel_registry.is_cancelled(job_id):
            raise cancel_registry.JobCancelledError()
        _t_scene = time.perf_counter()
        _scene_cache_hit = False
        if payload.auto_detect_scene:
            _cached_scenes = _scene_cache_get(str(source_path))
            if _cached_scenes is not None:
                scenes = _cached_scenes
                _scene_cache_hit = True
            else:
                scenes = detect_scenes(str(source_path))
                _scene_cache_put(str(source_path), scenes)
        else:
            scenes = []
        _scene_ms = int((time.perf_counter() - _t_scene) * 1000)
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.scene.detect.success",
            level="INFO",
            message=f"Detected {len(scenes)} scenes",
            step="render.scene.detect",
            context={"scene_count": len(scenes), "duration_ms": _scene_ms, "cache_hit": _scene_cache_hit},
            duration_ms=_scene_ms,
        )
        _job_log(effective_channel, job_id, f"{'cache_hit' if _scene_cache_hit else 'cache_miss'} type=scene_detect scenes={len(scenes)} elapsed_ms={_scene_ms}")
        _job_log(effective_channel, job_id, f"Scene detection done: {len(scenes)} scenes in {_scene_ms}ms")

        # ── Phase 5.4: Early AI pacing retrieval (before segment building) ─────
        # Runs only when ai_director_enabled=True. Retrieves knowledge to get
        # pacing hints BEFORE build_segments_from_scenes() so they can influence
        # segment duration config. Results are stored in _early_retrieved_knowledge
        # to avoid a second FAISS query in the Phase 5.2/5.3 AI director block.
        # NEVER raises. NEVER modifies payload. NEVER crashes render.
        # Priority: user explicit limits > AI hints > payload defaults.
        _early_retrieved_knowledge: list = []
        _early_pacing_tracer = None
        _pacing_config = None
        if getattr(payload, "ai_director_enabled", False):
            try:
                from app.ai.rag.knowledge_warmup import get_knowledge_index as _get_kidx
                from app.ai.render_mapper import map_knowledge_to_execution_hints as _map_hints
                from app.ai.pacing import build_ai_pacing_config as _build_pacing
                from app.ai.tracing import AITraceLogger as _AITraceLogger

                # Build knowledge filters (same logic as Phase 5.2 block below)
                _early_filters: dict = {}
                try:
                    _early_filters = {
                        k: v for k, v in {
                            "platform": getattr(payload, "render_profile", None) or None,
                            "niche": None,
                            "style": None,
                            "duration": source.get("duration", None),
                            "aspect_ratio": getattr(payload, "aspect_ratio", None) or None,
                            "subtitle_style": getattr(payload, "subtitle_style", None) or None,
                            "target_goal": None,
                        }.items() if v is not None
                    }
                except Exception:
                    _early_filters = {}

                # Early knowledge retrieval
                try:
                    _early_kidx = _get_kidx()
                    if _early_kidx.is_ready():
                        _early_retrieved_knowledge = _early_kidx.query(_early_filters, top_k=10)
                        logger.debug(
                            "phase54_early_knowledge_retrieved job_id=%s count=%d",
                            job_id, len(_early_retrieved_knowledge),
                        )
                except Exception as _early_kr_err:
                    logger.debug("phase54_early_retrieval_failed job_id=%s: %s", job_id, _early_kr_err)
                    _early_retrieved_knowledge = []

                # Map knowledge → execution hints → pacing config
                if _early_retrieved_knowledge:
                    try:
                        _early_hint_result = _map_hints(_early_retrieved_knowledge)
                        _early_exec_hints = _early_hint_result.hints if _early_hint_result else None
                        _pacing_config = _build_pacing(_early_exec_hints, payload)
                    except Exception as _pacing_build_err:
                        logger.debug("phase54_pacing_build_failed job_id=%s: %s", job_id, _pacing_build_err)
                        _pacing_config = None

                # Trace logger for pacing
                try:
                    _early_pacing_tracer = _AITraceLogger(job_id)
                except Exception:
                    _early_pacing_tracer = None

                if _pacing_config is not None and _early_pacing_tracer is not None:
                    try:
                        if _pacing_config.applied:
                            _early_pacing_tracer.log_pacing_applied({
                                "applied": True,
                                "cut_interval_min": _pacing_config.cut_interval_min,
                                "cut_interval_max": _pacing_config.cut_interval_max,
                                "source_knowledge_ids": _pacing_config.source_knowledge_ids,
                                "reason": "valid_ai_pacing_hint",
                            })
                        else:
                            _rejected_reason = _pacing_config.rejected_reason or "no_pacing_hint"
                            _early_pacing_tracer.log_decision_rejected(
                                _rejected_reason,
                                detail={
                                    "hint": "pacing",
                                    "cut_interval_min": _pacing_config.cut_interval_min,
                                    "cut_interval_max": _pacing_config.cut_interval_max,
                                    "reason": _rejected_reason,
                                },
                            )
                    except Exception:
                        pass
            except Exception as _p54_err:
                logger.debug("phase54_early_pacing_block_failed job_id=%s: %s", job_id, _p54_err)

        # Resolve effective segment duration limits:
        # AI pacing hint (if applied) overrides payload defaults; user explicit limits always win.
        # _seg_min_sec and _seg_max_sec are used for ALL segment building calls below.
        _seg_min_sec: int = int(payload.min_part_sec)
        _seg_max_sec: int = int(payload.max_part_sec)
        if (
            _pacing_config is not None
            and _pacing_config.applied
            and _pacing_config.cut_interval_min is not None
            and _pacing_config.cut_interval_max is not None
        ):
            _seg_min_sec = int(_pacing_config.cut_interval_min)
            _seg_max_sec = int(_pacing_config.cut_interval_max)
            logger.info(
                "phase54_pacing_applied job_id=%s seg_min=%s seg_max=%s "
                "(ai hint overrides payload defaults)",
                job_id, _seg_min_sec, _seg_max_sec,
            )

        _set_stage(JobStage.SEGMENT_BUILDING, 25, "Building smart segments")
        if cancel_registry.is_cancelled(job_id):
            raise cancel_registry.JobCancelledError()
        # UP28.1 + R3.5: segment score cache probed BEFORE CLIP scoring.
        # Cache key is independent of CLIP output (file mtime/size + scene count + version),
        # so the probe is safe to hoist.  On hit, cached segments already incorporate CLIP
        # scores from the original cache-miss run — returning them is bit-identical.
        try:
            _src_st = source_path.stat()
            _score_ck = _render_cache_key(
                str(source_path), _src_st.st_mtime, _src_st.st_size,
                _seg_min_sec, _seg_max_sec, len(scenes),
                CLIP_SCORER_VERSION,
            )
            _cached_scored = _score_cache_get(_score_ck)
        except Exception:
            _score_ck = None
            _cached_scored = None
        if _cached_scored is not None:
            scored = _cached_scored
            _job_log(effective_channel, job_id, f"score_cache_hit type=segment_scores segments={len(scored)}")
        else:
            # OQ-5.3: CLIP semantic scoring — enriches scene dicts with clip_semantic_score [-8, +20]
            # Runs only on cache miss; skipped on re-renders of the same source (R3.5).
            if scenes:
                _t_clip = time.perf_counter()
                scenes = score_scenes_clip(str(source_path), scenes)
                _clip_ms = int((time.perf_counter() - _t_clip) * 1000)
                _job_log(effective_channel, job_id, f"clip_scoring_done scenes={len(scenes)} elapsed_ms={_clip_ms}")
            segments = build_segments_from_scenes(scenes, source["duration"], _seg_min_sec, _seg_max_sec)
            scored = score_segments(segments, scenes)
            _job_log(effective_channel, job_id, f"score_cache_miss type=segment_scores segments={len(scored)}")
            if _score_ck:
                _score_cache_put(_score_ck, scored)
        # UP26: Clip exclude — remove creator-blacklisted timestamp ranges before selection
        _clip_exclude = [x for x in (getattr(payload, 'clip_exclude', None) or []) if isinstance(x, dict)]
        if _clip_exclude:
            _before_ex = len(scored)
            def _in_exclude_range(seg, _ranges=_clip_exclude):
                s = float(seg.get('start', 0))
                e = float(seg.get('end', s + 1))
                return any(s < float(ex.get('end_sec', 0)) and e > float(ex.get('start_sec', 0)) for ex in _ranges)
            scored = [seg for seg in scored if not _in_exclude_range(seg)]
            _job_log(effective_channel, job_id,
                     f"clip_exclude: {_before_ex - len(scored)} segments filtered by {len(_clip_exclude)} excluded ranges")
            _emit_render_event(channel_code=effective_channel, job_id=job_id, event="clip_excluded", level="INFO",
                message=f"UP26 clip_exclude: {_before_ex - len(scored)} segments removed", step="render.steering",
                context={"excluded_ranges": len(_clip_exclude), "segments_removed": _before_ex - len(scored)})
        # High-motion preference: boost high-energy clips without hard eviction.
        # Talking-head, interview, and commentary content remain competitive in the pool.
        _high_motion_count = sum(1 for s in scored if int(s.get("motion_score", 0)) >= HIGH_MOTION_MIN_SCORE)
        _apply_motion_boost = _high_motion_count >= HIGH_MOTION_MIN_KEEP
        if _apply_motion_boost:
            _job_log(effective_channel, job_id,
                     f"high_motion_preference: {_high_motion_count} high-energy clips detected — "
                     f"preference boost applied (no eviction); low-motion clips remain in pool")
        # Sort by viral/motion score first for selection (top N), then re-order for output numbering.
        # viral_score is primary — it now incorporates transition quality, not just cut density.
        _target_platform = str(getattr(payload, "target_platform", "") or "youtube_shorts").strip().lower()
        _platform_hook_bonus = _PLATFORM_PROFILES.get(_target_platform, {}).get("hook_sort_bonus", 0)
        # UP20: Creator Style DNA — inferred identity nudges (after platform, before default)
        _dna = getattr(payload, "creator_dna", {}) or {}
        _dna_confident    = bool(_dna.get("confident", False))
        _dna_hook_bonus   = 3 if (_dna_confident and float(_dna.get("hook_forward",  0) or 0) >= 0.5) else 0
        _dna_clean_visual = _dna_confident and float(_dna.get("clean_visual", 0) or 0) >= 0.67
        _dna_action_count = int(_dna.get("action_count", 0) or 0)
        # UP26: Structure bias — gentle ranking re-weight (creator intent, above DNA, below explicit lock)
        _sb = str(getattr(payload, 'structure_bias', '') or 'balanced').strip().lower()
        _sb_hook_mult  = 1.25 if _sb == 'hook'  else (0.85 if _sb == 'story' else 1.0)
        _sb_viral_mult = 0.85 if _sb == 'hook'  else (1.15 if _sb == 'story' else 1.0)
        # UP26: Subtitle emphasis — adjust font size before part loop reads payload.sub_font_size
        _sub_emphasis = str(getattr(payload, 'subtitle_emphasis', '') or 'balanced').strip().lower()
        if _sub_emphasis in ('subtle', 'aggressive'):
            _base_sz = int(getattr(payload, 'sub_font_size', 0) or 46)
            payload.sub_font_size = (max(24, int(_base_sz * 0.82)) if _sub_emphasis == 'subtle'
                                     else min(120, int(_base_sz * 1.20)))
        _combined_enabled = bool(getattr(payload, "combined_scoring_enabled", False))
        if _combined_enabled:
            def _provisional_combined(s):
                vs = float(s.get("viral_score", 0) or 0)
                hs = float(s.get("hook_text_score") or s.get("hook_timing_score") or
                           s.get("hook_opening_score") or s.get("hook_score") or 0)
                # mv not yet computed; fallback = vs → vs*0.50 + vs*0.30 + hs*0.20 = vs*0.80 + hs*0.20
                # UP20.1 Part A: DNA hook bonus — same gentle nudge as standard sort path.
                # UP26: Structure bias multipliers applied after DNA nudge.
                return (vs * 0.80 * _sb_viral_mult) + hs * (0.20 + _dna_hook_bonus / 100) * _sb_hook_mult
            scored.sort(key=_provisional_combined, reverse=True)
        else:
            scored.sort(
                key=lambda x: (
                    int(x.get("viral_score", 0) * _sb_viral_mult)
                    + (8 if _apply_motion_boost and int(x.get("motion_score", 0)) >= HIGH_MOTION_MIN_SCORE else 0)
                    + int(float(x.get("hook_score", 0) or 0) * (_platform_hook_bonus + _dna_hook_bonus) / 100 * _sb_hook_mult),
                    int(x.get("motion_score", 0)),
                ),
                reverse=True,
            )
        # UP73.3: First-render quality floor — drop candidates below viral_score 25.
        # Procedure: sort (already done) → filter → fallback-to-top-1 → slice.
        # Micro-safety: skip when pool is ≤ 2 to avoid over-pruning sparse content.
        if len(scored) > 2:
            _floor_filtered = [s for s in scored if float(s.get("viral_score", 0) or 0) >= 25]
            scored = _floor_filtered if _floor_filtered else scored[:1]
        if payload.max_export_parts and payload.max_export_parts > 0:
            scored = scored[:payload.max_export_parts]
        # UP26: Clip lock — promote creator-selected timestamp ranges to front of pool (after slice)
        _clip_lock = [x for x in (getattr(payload, 'clip_lock', None) or []) if isinstance(x, dict)]
        if _clip_lock:
            def _in_lock_range(seg, _ranges=_clip_lock):
                s = float(seg.get('start', 0))
                e = float(seg.get('end', s + 1))
                return any(s < float(lk.get('end_sec', 0)) and e > float(lk.get('start_sec', 0)) for lk in _ranges)
            _locked = [seg for seg in scored if _in_lock_range(seg)]
            _unlocked = [seg for seg in scored if not _in_lock_range(seg)]
            scored = _locked + _unlocked
            _job_log(effective_channel, job_id,
                     f"clip_lock: {len(_locked)} segments promoted by {len(_clip_lock)} locked ranges")
            _emit_render_event(channel_code=effective_channel, job_id=job_id, event="clip_locked", level="INFO",
                message=f"UP26 clip_lock: {len(_locked)} segments promoted to front", step="render.steering",
                context={"lock_ranges": len(_clip_lock), "segments_promoted": len(_locked)})
        # ── Multi-variant: replace pool with 3 purposeful single-clip selections ──
        _multi_variant = bool(getattr(payload, "multi_variant", False))
        if _multi_variant:
            scored = _build_variant_segments(scored, payload)
            _job_log(
                effective_channel, job_id,
                f"multi_variant: {len(scored)} variants selected "
                f"(aggressive/balanced/story_first) "
                f"segments={[s.get('variant_type') for s in scored]}",
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="multi_variant_selected",
                level="INFO",
                message=f"Multi-variant mode: {len(scored)} purposeful variants",
                step="render.multi_variant",
                context={
                    "variant_types": [s.get("variant_type") for s in scored],
                    "variants": [
                        {
                            "variant": s.get("variant_type"),
                            "start": round(float(s.get("start") or 0), 1),
                            "hook_score": round(float(s.get("hook_score") or 0), 1),
                            "speed": s.get("variant_playback_speed"),
                            "subtitle": s.get("variant_subtitle_style"),
                        }
                        for s in scored
                    ],
                },
            )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="platform_bias_applied",
            level="INFO",
            message=f"Platform-aware editing: {_target_platform}",
            step="render.platform",
            context={
                "target_platform": _target_platform,
                "hook_sort_bonus": _platform_hook_bonus,
                "speed_delta": _PLATFORM_PROFILES.get(_target_platform, {}).get("speed_delta", 0.0),
            },
        )
        _job_log(effective_channel, job_id,
                 f"platform_bias: target={_target_platform} hook_bonus={_platform_hook_bonus}")
        # UP20.1 Part B: DNA observability — always emit confidence; log applied/suppressed separately.
        _dna_hf = float(_dna.get("hook_forward", 0) or 0)
        _dna_cv = float(_dna.get("clean_visual", 0) or 0)
        _dna_ns = float(_dna.get("narrative_structure", 0) or 0)
        _dna_suppressed_signals = _dna.get("suppressed_signals") or []
        _job_log(
            effective_channel, job_id,
            f"dna_confidence: confident={_dna_confident} action_count={_dna_action_count} "
            f"hook_forward={_dna_hf:.2f} clean_visual={_dna_cv:.2f} "
            f"narrative_structure={_dna_ns:.2f} "
            f"suppressed_signals={_dna_suppressed_signals}",
            kind="info",
        )
        if _dna_confident and (_dna_hook_bonus > 0 or _dna_clean_visual):
            _nudges = []
            if _dna_hook_bonus > 0:       _nudges.append(f"hook_bonus={_dna_hook_bonus}")
            if _dna_clean_visual:         _nudges.append("subtitle_clean_bias=active")
            _job_log(
                effective_channel, job_id,
                f"dna_applied: {' '.join(_nudges)}",
                kind="info",
            )
        elif _dna_confident:
            _job_log(
                effective_channel, job_id,
                f"dna_suppressed: all nudges below threshold — "
                f"hook_forward={_dna_hf:.2f}(<0.5) clean_visual={_dna_cv:.2f}(<0.67)",
                kind="info",
            )
        # Re-order for output numbering: timeline = chronological, viral/combined = by score
        part_order = str(getattr(payload, "part_order", "viral") or "viral").strip().lower()
        if part_order == "timeline":
            scored.sort(key=lambda x: float(x.get("start", 0)))
            _job_log(effective_channel, job_id, f"Part order: timeline (chronological)")
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="hook_first_skipped",
                level="INFO",
                message="Hook-first skipped: timeline mode",
                step="render.hook_first",
                context={"reason": "timeline_mode", "total_clips": len(scored)},
            )
        elif part_order == "viral" and _combined_enabled:
            # P4-1: Hook-first sequencing — strongest hook at index 0
            def _hook_score(c):
                return (
                    c.get("combined_score")
                    or c.get("market_viral_score")
                    or c.get("viral_score")
                    or 0
                )
            _sorted = sorted(scored, key=_hook_score, reverse=True)
            _best = _sorted[0]
            _best_score = _hook_score(_best)
            _used_combined = bool(_best.get("combined_score"))
            scored = [_best] + [c for c in _sorted if c is not _best]
            _job_log(effective_channel, job_id, f"Part order: hook-first (combined+viral, best_score={_best_score})")
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="hook_first_applied",
                level="INFO",
                message=f"Hook-first applied: best_part_no=1 score={_best_score} total={len(scored)}",
                step="render.hook_first",
                context={
                    "best_part_no": 1,
                    "best_score": _best_score,
                    "used_combined_score": _used_combined,
                    "total_clips": len(scored),
                },
            )
        elif _combined_enabled:
            scored.sort(key=_provisional_combined, reverse=True)
            _job_log(effective_channel, job_id, "Part order: combined score (viral+hook, experimental)")
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="hook_first_skipped",
                level="INFO",
                message="Hook-first skipped: part_order is not viral",
                step="render.hook_first",
                context={"reason": "part_order_not_viral", "part_order": part_order, "total_clips": len(scored)},
            )
        else:
            _job_log(effective_channel, job_id, f"Part order: viral score (highest first)")
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="hook_first_skipped",
                level="INFO",
                message="Hook-first skipped: combined scoring disabled",
                step="render.hook_first",
                context={"reason": "combined_disabled", "total_clips": len(scored)},
            )

        # ── Story arc sequencing ─────────────────────────────────────────────
        # Lightweight hook → build → payoff reorder applied after score-based
        # selection.  Deterministic heuristic — predictable and explainable.
        #
        # Conditions: non-timeline mode, 3+ clips, non-montage dominant type.
        # For montage: energy-first order is already correct — skip.
        # For 1-2 clips: no meaningful arc — skip.
        if part_order != "timeline" and len(scored) >= 3 and not _multi_variant:
            _ct_counts: dict[str, int] = {}
            for _s in scored:
                _ct = str(_s.get("content_type_hint") or "vlog")
                _ct_counts[_ct] = _ct_counts.get(_ct, 0) + 1
            _dominant_ct = max(_ct_counts, key=_ct_counts.get)

            if _dominant_ct != "montage":
                # Hook: clip with strongest opening signal (starts at scene cut,
                # early position, correct duration).  hook_score = starts_at_cut×40
                # + position_score×40 + duration_score×20.
                _arc_hook = max(scored, key=lambda s: float(s.get("hook_score", 0) or 0))

                # Payoff: latest clip in source video that is not the hook.
                # Protects reveals, answers, punchlines, before/after moments
                # from being buried in the middle of the export.
                _arc_non_hook = [s for s in scored if s is not _arc_hook]
                _arc_payoff = max(_arc_non_hook, key=lambda s: float(s.get("start", 0) or 0))

                # Build: everything between hook and payoff.
                _arc_build = [s for s in scored if s is not _arc_hook and s is not _arc_payoff]

                # Build order by content type:
                #   interview/tutorial/vlog — source chronological preserves the
                #     original logic/explanation/narrative structure
                #   commentary — descending viral score: strongest supporting
                #     evidence before diminishing evidence
                if _dominant_ct in ("interview", "tutorial", "vlog"):
                    _arc_build.sort(key=lambda s: float(s.get("start", 0) or 0))
                else:
                    _arc_build.sort(key=lambda s: float(s.get("viral_score", 0) or 0), reverse=True)

                scored = [_arc_hook] + _arc_build + [_arc_payoff]

                _job_log(
                    effective_channel, job_id,
                    f"story_arc_applied dominant={_dominant_ct} clips={len(scored)} "
                    f"hook_start={float(_arc_hook.get('start', 0) or 0):.1f}s "
                    f"payoff_start={float(_arc_payoff.get('start', 0) or 0):.1f}s "
                    f"hook_score={float(_arc_hook.get('hook_score', 0) or 0):.1f}",
                )
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="story_arc_applied",
                    level="INFO",
                    message=(
                        f"Story arc: hook=part1 payoff=part{len(scored)} "
                        f"dominant={_dominant_ct}"
                    ),
                    step="render.story_arc",
                    context={
                        "dominant_content_type": _dominant_ct,
                        "total_clips": len(scored),
                        "hook_start_sec": round(float(_arc_hook.get("start", 0) or 0), 1),
                        "hook_score": round(float(_arc_hook.get("hook_score", 0) or 0), 1),
                        "payoff_start_sec": round(float(_arc_payoff.get("start", 0) or 0), 1),
                        "build_order": "chronological" if _dominant_ct in ("interview", "tutorial", "vlog") else "score_desc",
                    },
                )
            else:
                _job_log(
                    effective_channel, job_id,
                    f"story_arc_skipped reason=montage clips={len(scored)}",
                )

        if not scored:
            raise RuntimeError("No exportable segments were created")

        total_parts = len(scored)
        rows = []
        outputs = []
        full_srt = work_dir / f"{source['slug']}_full.srt"
        full_srt_available = False
        existing_parts = {int(x["part_no"]): x for x in list_job_parts(job_id)}
        _job_log(effective_channel, job_id, f"Segment building done: {total_parts} parts")
        # Diagnostic: per-segment selection summary (always at INFO for QA traceability)
        for _qi, _qs in enumerate(scored, start=1):
            logger.info(
                "selected_segment part=%d start=%.3f end=%.3f duration=%.3f "
                "viral=%.1f motion=%.1f hook=%.1f content_type=%s variant=%s",
                _qi, float(_qs.get("start", 0)), float(_qs.get("end", 0)),
                float(_qs.get("duration", 0)),
                float(_qs.get("viral_score", 0)), float(_qs.get("motion_score", 0)),
                float(_qs.get("hook_score", 0)), _qs.get("content_type_hint", ""),
                _qs.get("variant_type", ""),
            )
        # Debug artifact: timeline JSON saved to work_dir when RENDER_DEBUG_LOG=1
        import os as _os
        if _os.getenv("RENDER_DEBUG_LOG", "0") == "1":
            try:
                import json as _json
                _tl_path = work_dir / f"{source['slug']}_timeline.json"
                _tl_data = [
                    {
                        "part": _qi,
                        "start": float(_qs.get("start", 0)),
                        "end": float(_qs.get("end", 0)),
                        "duration": float(_qs.get("duration", 0)),
                        "viral_score": float(_qs.get("viral_score", 0)),
                        "motion_score": float(_qs.get("motion_score", 0)),
                        "hook_score": float(_qs.get("hook_score", 0)),
                        "content_type": _qs.get("content_type_hint", ""),
                        "variant": _qs.get("variant_type", ""),
                        "transition_score": float(_qs.get("transition_score", 0)),
                    }
                    for _qi, _qs in enumerate(scored, start=1)
                ]
                _tl_path.write_text(_json.dumps(_tl_data, indent=2), encoding="utf-8")
                logger.debug("debug_artifact timeline_json=%s", _tl_path)
            except Exception as _tl_exc:
                logger.debug("debug_artifact timeline_json_failed: %s", _tl_exc)

        subtitle_cutoff = payload.subtitle_viral_min_score
        subtitle_top_count = max(1, int(total_parts * max(0.1, min(1.0, float(payload.subtitle_viral_top_ratio)))))
        if scored:
            ranked_scores = sorted([int(s.get("viral_score", 0)) for s in scored], reverse=True)
            subtitle_cutoff = max(subtitle_cutoff, ranked_scores[min(subtitle_top_count - 1, len(ranked_scores) - 1)])
        _job_log(effective_channel, job_id, f"Subtitle viral cutoff={subtitle_cutoff}, top_count={subtitle_top_count}")

        subtitle_enabled_by_idx = {}
        for idx, seg in enumerate(scored, start=1):
            subtitle_enabled_by_idx[idx] = payload.add_subtitle and (
                (not payload.subtitle_only_viral_high) or int(seg.get("viral_score", 0)) >= int(subtitle_cutoff)
            )
        if payload.add_subtitle and not any(subtitle_enabled_by_idx.values()):
            # Safety fallback: avoid "no subtitle at all" when viral gates are too strict.
            for idx in range(1, total_parts + 1):
                subtitle_enabled_by_idx[idx] = True
            _job_log(
                effective_channel,
                job_id,
                "No parts passed subtitle viral filters; fallback enabled subtitles for all parts",
                kind="warning",
            )

        if payload.add_subtitle and any(subtitle_enabled_by_idx.values()):
            _set_stage(JobStage.TRANSCRIBING_FULL, 28, "Transcribing full video once")
            if payload.resume_from_last and full_srt.exists() and full_srt.stat().st_size > 0:
                full_srt_available = True
                _job_log(effective_channel, job_id, "Reuse existing full transcription", kind="debug")
            else:
                source_has_audio = has_audio_stream(str(source_path))
                if not source_has_audio:
                    _job_log(effective_channel, job_id, f"subtitle.audio_missing source={source_path}; subtitles skipped", kind="warning")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="subtitle.audio_missing",
                        level="WARNING",
                        message="Source video has no usable audio stream; subtitles skipped",
                        step="subtitle.transcribe",
                        context={"source_path": str(source_path)},
                    )
                else:
                    _whisper_model = tuned["whisper_model"]
                    _src_name = Path(source_path).name
                    # UP28: check transcription cache before running Whisper
                    _transcribe_engine = getattr(payload, "subtitle_transcription_engine", "default")
                    _transcribe_cache_key = f"{_transcribe_engine}_{int(bool(payload.highlight_per_word))}"
                    _cached_srt = _transcription_cache_get(str(source_path), _whisper_model, _transcribe_cache_key)
                    if _cached_srt is not None:
                        shutil.copy2(str(_cached_srt), str(full_srt))
                        full_srt_available = bool(full_srt.exists() and full_srt.stat().st_size > 0)
                        _job_log(effective_channel, job_id, f"cache_hit type=transcription model={_whisper_model} srt_exists={full_srt_available}")
                        _emit_render_event(
                            channel_code=effective_channel, job_id=job_id,
                            event="cache_hit", level="INFO",
                            message=f"Transcription cache hit: model={_whisper_model}",
                            step="subtitle.transcribe",
                            context={"type": "transcription", "whisper_model": _whisper_model, "srt_exists": full_srt_available},
                        )
                    else:
                        _t_transcribe = time.perf_counter()
                        _hb_stop = threading.Event()

                        def _hb_thread_fn(_stop=_hb_stop, _m=_whisper_model, _s=_src_name):
                            _pct = 29
                            while not _stop.wait(12):
                                _elapsed = round(time.perf_counter() - _t_transcribe)
                                update_job_progress(job_id, JobStage.TRANSCRIBING_FULL, _pct, f"Still transcribing… ({_elapsed}s)")
                                _job_log(effective_channel, job_id, f"subtitle_transcription_progress elapsed_sec={_elapsed} model={_m} source={_s}")
                                _emit_render_event(
                                    channel_code=effective_channel, job_id=job_id,
                                    event="subtitle_transcription_progress",
                                    level="INFO",
                                    message=f"Still transcribing… elapsed={_elapsed}s",
                                    step="subtitle.transcribe",
                                    context={"elapsed_sec": _elapsed, "whisper_model": _m, "source": _s},
                                )
                                _pct = _pct + 1 if _pct < 34 else (33 if _pct == 34 else 34)

                        _job_log(effective_channel, job_id, f"subtitle_transcription_started model={_whisper_model} source={_src_name}")
                        _emit_render_event(
                            channel_code=effective_channel, job_id=job_id,
                            event="subtitle_transcription_started",
                            level="INFO",
                            message=f"Transcription started: model={_whisper_model}",
                            step="subtitle.transcribe",
                            context={"whisper_model": _whisper_model, "source": _src_name},
                        )
                        _hb = threading.Thread(target=_hb_thread_fn, daemon=True, name=f"transcribe_hb_{job_id[:8]}")
                        _hb.start()
                        if cancel_registry.is_cancelled(job_id):
                            raise cancel_registry.JobCancelledError()
                        try:
                            _transcription_result = transcribe_with_adapter(
                                str(source_path),
                                str(full_srt),
                                engine=_transcribe_engine,
                                model_name=_whisper_model,
                                retry_count=retry_count,
                                highlight_per_word=payload.highlight_per_word,
                                logger=logger,
                            )
                            if _transcription_result.warnings:
                                _job_log(
                                    effective_channel,
                                    job_id,
                                    "subtitle_transcription_adapter_warning "
                                    f"requested={_transcribe_engine} "
                                    f"used={_transcription_result.engine} "
                                    f"warnings={','.join(_transcription_result.warnings)}",
                                    kind="warning",
                                )
                            full_srt_available = bool(full_srt.exists() and full_srt.stat().st_size > 0)
                            _transcribe_ms = int((time.perf_counter() - _t_transcribe) * 1000)
                            _srt_size = full_srt.stat().st_size if full_srt_available else 0
                            _job_log(effective_channel, job_id, f"subtitle_transcription_completed model={_whisper_model} elapsed_ms={_transcribe_ms} srt_exists={full_srt_available} size_bytes={_srt_size}")
                            _emit_render_event(
                                channel_code=effective_channel, job_id=job_id,
                                event="subtitle_transcription_completed",
                                level="INFO",
                                message=f"Transcription complete: model={_whisper_model} elapsed={_transcribe_ms}ms",
                                step="subtitle.transcribe",
                                context={"whisper_model": _whisper_model, "elapsed_ms": _transcribe_ms, "srt_path": str(full_srt), "file_exists": full_srt_available, "size_bytes": _srt_size},
                            )
                            _transcription_cache_put(str(source_path), _whisper_model, _transcribe_cache_key, full_srt)
                        except Exception as transcribe_exc:
                            full_srt_available = False
                            _safe_unlink(full_srt)
                            _transcribe_ms = int((time.perf_counter() - _t_transcribe) * 1000)
                            _job_log(effective_channel, job_id, f"subtitle_transcription_failed source={source_path} model={_whisper_model} elapsed_ms={_transcribe_ms}: {transcribe_exc}", kind="warning")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="subtitle_transcription_failed",
                                level="WARNING",
                                message=f"Subtitle transcription failed: {transcribe_exc}",
                                step="subtitle.transcribe",
                                context={"source_path": str(source_path), "whisper_model": _whisper_model, "elapsed_ms": _transcribe_ms},
                                exception=transcribe_exc,
                            )
                            # UP24: recovery — subtitles optional, render continues without them
                            _recovery_notes.append("Subtitle transcription failed — rendered without subtitles")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="recovery_success",
                                level="INFO",
                                message="Recovery: subtitle transcription failed, rendering without subtitles",
                                step="subtitle.transcribe",
                                context={"recovery_strategy": "skip_subtitles"},
                            )
                        finally:
                            _hb_stop.set()
                            _hb.join(timeout=2)

        # ── S4.1: Transcript-aware boundary refinement (S4_CANDIDATE_INTELLIGENCE_ENABLED=1) ──
        # Runs after transcription so it works on the first render (no cold-cache requirement).
        # Nudges already-selected segment start/end to align with sentence boundaries (±15% max).
        _s4_before = None  # pre-S4.1 boundaries; forwarded to S4.5 for combined-nudge cap
        if os.getenv("S4_CANDIDATE_INTELLIGENCE_ENABLED") == "1" and full_srt_available and scored:
            try:
                _s4_blocks = parse_srt_blocks(str(full_srt))
                if _s4_blocks:
                    _s4_before = [(s.get("start"), s.get("end")) for s in scored]
                    scored = refine_segment_boundaries(
                        scored, _s4_blocks,
                        float(_seg_min_sec), float(_seg_max_sec),
                    )
                    _s4_adjusted = sum(
                        1 for i, s in enumerate(scored)
                        if s.get("candidate_adjustment_reason") and (s.get("start"), s.get("end")) != _s4_before[i]
                    )
                    _job_log(effective_channel, job_id,
                             f"s4_boundary_refinement segments={len(scored)} adjusted={_s4_adjusted}")
            except Exception as _s4_exc:
                logger.debug("s4_boundary_refinement_failed job_id=%s: %s", job_id, _s4_exc)

        # ── S4.2: Real Retention Proxy (S4_RETENTION_PROXY_ENABLED=1) ──
        # Applies a bounded ±15 adjustment to viral_score using multi-signal
        # retention estimation. Works on first render (uses freshly-generated
        # SRT when available; tier-1 signals fire even without transcript).
        if os.getenv("S4_RETENTION_PROXY_ENABLED") == "1" and scored:
            try:
                _s42_blocks = parse_srt_blocks(str(full_srt)) if full_srt_available else None
                scored = apply_retention_proxy(scored, _s42_blocks)
                _s42_adj = sum(1 for s in scored if s.get("retention_adjustment_reason"))
                _job_log(effective_channel, job_id,
                         f"s4_retention_proxy segments={len(scored)} adjusted={_s42_adj}")
            except Exception as _s42_exc:
                logger.debug("s4_retention_proxy_failed job_id=%s: %s", job_id, _s42_exc)

        # ── S4.5: Speaker-aware cuts (S4_SPEAKER_AWARE_CUTS_ENABLED=1) ──
        # Snaps boundaries to nearby pause midpoints and utterance endpoints.
        # End boundary gets full nudge window (primary); start gets half
        # (detect_silence_trim_offset already handles opening cleanup).
        if os.getenv("S4_SPEAKER_AWARE_CUTS_ENABLED") == "1" and scored:
            try:
                _s45_blocks = parse_srt_blocks(str(full_srt)) if full_srt_available else None
                if _s45_blocks:
                    scored = refine_cuts_for_naturalness(
                        scored, _s45_blocks,
                        float(_seg_min_sec), float(_seg_max_sec),
                        original_segments=[{"start": s, "end": e} for s, e in _s4_before] if _s4_before else None,
                    )
                    _s45_adj = sum(1 for s in scored if s.get("cut_adjustment_reason"))
                    _job_log(effective_channel, job_id,
                             f"s4_natural_cuts segments={len(scored)} adjusted={_s45_adj}")
            except Exception as _s45_exc:
                logger.debug("s4_natural_cuts_failed job_id=%s: %s", job_id, _s45_exc)

        # ── AI Director Phase 1 — safe edit plan (observation only, no override) ──
        _ai_edit_plan = None
        if getattr(payload, "ai_director_enabled", False):
            try:
                from app.ai.director.ai_director import create_ai_edit_plan as _create_ai_plan

                # ── Phase 5.2: Build knowledge filters from payload ────────────────
                _knowledge_filters: dict = {}
                try:
                    _knowledge_filters = {
                        "platform": getattr(payload, "render_profile", None) or None,
                        "niche": None,
                        "style": None,
                        "duration": source.get("duration", None),
                        "aspect_ratio": getattr(payload, "aspect_ratio", None) or None,
                        "subtitle_style": getattr(payload, "subtitle_style", None) or None,
                        "target_goal": None,
                    }
                    # Remove None-valued keys for clarity (query handles None)
                    _knowledge_filters = {k: v for k, v in _knowledge_filters.items() if v is not None}
                except Exception as _kf_err:
                    logger.debug("knowledge_filter_build_failed job_id=%s: %s", job_id, _kf_err)
                    _knowledge_filters = {}

                # ── Phase 5.2: AI Trace Logger ────────────────────────────────────
                _ai_tracer = None
                try:
                    from app.ai.tracing import AITraceLogger
                    _ai_tracer = AITraceLogger(job_id)
                    _ai_tracer.log_input_filters(_knowledge_filters)
                except Exception as _tracer_err:
                    logger.debug("ai_tracer_init_failed job_id=%s: %s", job_id, _tracer_err)

                # ── Phase 5.2: Retrieve knowledge items ───────────────────────────
                # Phase 5.4: Reuse early retrieval results if available (avoids
                # double FAISS query). _early_retrieved_knowledge is set by the
                # Phase 5.4 early pacing block above before segment building.
                _retrieved_knowledge: list = []
                if _early_retrieved_knowledge:
                    # Reuse results from Phase 5.4 early retrieval — no second query needed
                    _retrieved_knowledge = _early_retrieved_knowledge
                    logger.debug(
                        "phase54_knowledge_reused job_id=%s count=%d (skipping second query)",
                        job_id, len(_retrieved_knowledge),
                    )
                    if _ai_tracer is not None:
                        try:
                            _ai_tracer.log_knowledge_retrieved(_retrieved_knowledge)
                        except Exception:
                            pass
                else:
                    try:
                        from app.ai.rag.knowledge_warmup import get_knowledge_index
                        _kidx = get_knowledge_index()
                        if _kidx.is_ready():
                            _retrieved_knowledge = _kidx.query(_knowledge_filters, top_k=10)
                            logger.info(
                                "knowledge_retrieved job_id=%s filters=%s count=%d",
                                job_id, list(_knowledge_filters.keys()), len(_retrieved_knowledge),
                            )
                            if _ai_tracer is not None:
                                _ai_tracer.log_knowledge_retrieved(_retrieved_knowledge)
                        else:
                            logger.debug("knowledge_index_not_ready job_id=%s", job_id)
                            if _ai_tracer is not None:
                                _ai_tracer.log_fallback("no_index", "knowledge index not ready at render time")
                    except Exception as _kr_err:
                        logger.warning("knowledge_retrieval_failed job_id=%s: %s", job_id, _kr_err)
                        _retrieved_knowledge = []
                        if _ai_tracer is not None:
                            try:
                                _ai_tracer.log_fallback("ai_exception", str(_kr_err))
                            except Exception:
                                pass

                if not _retrieved_knowledge:
                    if _ai_tracer is not None:
                        try:
                            _ai_tracer.log_fallback("no_matching_rules", "no knowledge items matched filters")
                        except Exception:
                            pass

                _ai_context = {
                    "job_id": job_id,
                    "srt_path": str(full_srt) if full_srt_available else None,
                    "scenes": scenes,
                    "duration": source.get("duration", 0.0),
                    "market": getattr(payload, "viral_market", None),
                    # Phase 4: source path for optional beat analysis
                    "source_path": str(source_path) if source_path else None,
                    # Phase 5.2: retrieved knowledge items and filters
                    "retrieved_knowledge": _retrieved_knowledge,
                    "knowledge_filters": _knowledge_filters,
                }
                _ai_edit_plan = _create_ai_plan(payload, _ai_context)
                if _ai_edit_plan is not None:
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="ai_director_plan_created",
                        level="INFO",
                        message=(
                            f"AI Director plan: mode={_ai_edit_plan.mode} "
                            f"segments={len(_ai_edit_plan.selected_segments)} "
                            f"fallback={_ai_edit_plan.fallback_used}"
                        ),
                        step="ai_director",
                        context=_ai_edit_plan.to_dict(),
                    )
                    # Phase 5.2: trace render plan summary
                    if _ai_tracer is not None:
                        try:
                            _ai_tracer.log_render_plan_summary({
                                "mode": _ai_edit_plan.mode,
                                "segments": len(_ai_edit_plan.selected_segments),
                                "fallback_used": _ai_edit_plan.fallback_used,
                                "knowledge_items_used": len(_retrieved_knowledge),
                                "warnings": list(_ai_edit_plan.warnings),
                            })
                        except Exception:
                            pass
            except Exception as _ai_err:
                _job_log(
                    effective_channel, job_id,
                    f"ai_director_failed_fallback: {_ai_err}",
                    kind="warning",
                )

        # ── Phase 5.3: Apply execution hints from AI plan (advisory, safe, bounded) ──
        # Reads execution_hints from plan.knowledge_injection (set by ai_director).
        # If ai_director_enabled=False, _ai_edit_plan is None → this block is skipped.
        # If hints are invalid or absent → behavior unchanged, advisory log only.
        # NEVER crashes render. NEVER modifies FFmpeg commands or filter graphs.
        _exec_hints: dict = {}
        _phase53_tracer = _ai_tracer if getattr(payload, "ai_director_enabled", False) else None
        if _ai_edit_plan is not None:
            try:
                _exec_hints = (
                    _ai_edit_plan.knowledge_injection.get("execution_hints") or {}
                ) if isinstance(_ai_edit_plan.knowledge_injection, dict) else {}
            except Exception:
                _exec_hints = {}

            if _exec_hints and _phase53_tracer is not None:
                try:
                    _phase53_tracer.log_execution_hints(
                        _exec_hints,
                        _exec_hints.get("source_knowledge_ids") or [],
                    )
                except Exception:
                    pass

            # Log validation fixups if any
            if _ai_edit_plan is not None and _phase53_tracer is not None:
                try:
                    _fixups_53 = (
                        _ai_edit_plan.knowledge_injection.get("validation_fixups") or []
                    ) if isinstance(_ai_edit_plan.knowledge_injection, dict) else []
                    if _fixups_53:
                        _phase53_tracer.log_validation_fixup(_fixups_53)
                except Exception:
                    pass

            # A. Pacing hint — Phase 5.4: pacing hints are now APPLIED before
            #    segment building via _seg_min_sec/_seg_max_sec (see early pacing
            #    block above). Here we only log for observability — no further action.
            _pacing_cut_min = _exec_hints.get("cut_interval_min")
            _pacing_cut_max = _exec_hints.get("cut_interval_max")
            if _pacing_cut_min is not None or _pacing_cut_max is not None:
                logger.debug(
                    "phase53_pacing_hint_observed job_id=%s cut_min=%s cut_max=%s "
                    "(Phase 5.4: pacing applied before segment building via _seg_min_sec/_seg_max_sec)",
                    job_id, _pacing_cut_min, _pacing_cut_max,
                )

            # B. Subtitle emphasis hint — if a style is suggested, note it.
            #    The actual emphasis style is resolved per-part from payload.subtitle_style
            #    and DNA/platform bias. The hint is advisory and cannot override the
            #    per-part resolution without rewriting that logic (out of scope).
            _sub_emph_hint = _exec_hints.get("subtitle_emphasis_style")
            if _sub_emph_hint is not None:
                logger.info(
                    "phase53_subtitle_emphasis_hint_advisory job_id=%s style=%r "
                    "(advisory only — per-part subtitle style resolved from payload)",
                    job_id, _sub_emph_hint,
                )
                if _phase53_tracer is not None:
                    try:
                        _phase53_tracer.log_decision_rejected(
                            "subtitle_emphasis_hint_advisory_only",
                            detail={
                                "hint": "subtitle_emphasis_style",
                                "value": _sub_emph_hint,
                                "reason": (
                                    "subtitle style is resolved per-part from payload.subtitle_style "
                                    "and DNA/platform bias; hint is advisory"
                                ),
                            },
                        )
                    except Exception:
                        pass

            # C. Hook overlay hint — if explicitly disabled, gate the hook overlay.
            #    This is the one hint that IS applied: hook_overlay_enabled=False → skip overlay.
            #    hook_overlay_enabled=True or None → keep existing behavior (unchanged).
            _hook_enabled_hint = _exec_hints.get("hook_overlay_enabled")
            if _hook_enabled_hint is False:
                # AI says: skip hook overlay for this render job
                if _hook_overlay_enabled:
                    _hook_overlay_enabled = False
                    logger.info(
                        "phase53_hook_overlay_disabled_by_ai job_id=%s "
                        "(knowledge hint hook_overlay_enabled=False overrides payload=True)",
                        job_id,
                    )
                    if _phase53_tracer is not None:
                        try:
                            _phase53_tracer.log_execution_hints(
                                {"hook_overlay_enabled": False, "applied": True},
                                _exec_hints.get("source_knowledge_ids") or [],
                            )
                        except Exception:
                            pass

        # ── Phase 5.5: Build AI subtitle emphasis config ─────────────────────────
        # Runs only when ai_director_enabled=True and _ai_edit_plan is not None.
        # Config is built once per job; applied per-part in the subtitle loop below.
        # NEVER mutates payload. NEVER changes _effective_subtitle_style (preset ID).
        # NEVER alters SRT timestamps. NEVER touches FFmpeg commands.
        # If AI disabled or no hints → _ai_subtitle_emphasis_config.applied=False → no change.
        _ai_subtitle_emphasis_config = None
        if getattr(payload, "ai_director_enabled", False) and _ai_edit_plan is not None:
            try:
                from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config as _build_sub_emph
                _ai_subtitle_emphasis_config = _build_sub_emph(_exec_hints, payload)
                if _phase53_tracer is not None:
                    try:
                        _emph_reason = (
                            "valid_ai_subtitle_hint" if _ai_subtitle_emphasis_config.applied
                            else str(_ai_subtitle_emphasis_config.rejected_reason or "no_subtitle_emphasis_hint")
                        )
                        _phase53_tracer.log_subtitle_emphasis_applied(
                            {**_ai_subtitle_emphasis_config.to_dict(), "reason": _emph_reason}
                        )
                    except Exception:
                        pass
                if not _ai_subtitle_emphasis_config.applied and _phase53_tracer is not None:
                    try:
                        _phase53_tracer.log_decision_rejected(
                            str(_ai_subtitle_emphasis_config.rejected_reason or "no_subtitle_emphasis_hint"),
                            detail={
                                "hint": "subtitle_emphasis_style",
                                "value": _ai_subtitle_emphasis_config.emphasis_style,
                                "phase": "5.5",
                            },
                        )
                    except Exception:
                        pass
                logger.debug(
                    "phase55_subtitle_emphasis_config job_id=%s applied=%s style=%s reason=%s",
                    job_id,
                    _ai_subtitle_emphasis_config.applied,
                    _ai_subtitle_emphasis_config.emphasis_style,
                    _ai_subtitle_emphasis_config.rejected_reason,
                )
            except Exception as _sub55_err:
                logger.warning(
                    "phase55_subtitle_emphasis_config_failed job_id=%s: %s", job_id, _sub55_err
                )
                _ai_subtitle_emphasis_config = None

        # ── Phase 5.7: Build AI visual intensity config ───────────────────────────
        # Runs only when ai_director_enabled=True and _ai_edit_plan is not None.
        # Config is built once per job; logged immediately.
        # Phase 5.7: Safe injection point found — visual_intensity_hint parameter
        #   added to render_part(), render_part_smart(), render_base_clip().
        #   All three accept visual_intensity_hint with default None (backward compat).
        #   Renderer OWNS the mapping from hint to known effect presets.
        #   AI passes only "low"/"medium"/"high" — never a preset name or filter string.
        # Result when applied=True: render_overrides={"visual_intensity_hint": <value>}
        # render_pipeline extracts this value and passes it to renderer calls below.
        # NEVER mutates payload. NEVER changes payload.effect_preset. NEVER touches FFmpeg.
        # If AI disabled or no hints → _ai_visual_intensity_config.applied=False → hint=None.
        _ai_visual_intensity_config = None
        if getattr(payload, "ai_director_enabled", False) and _ai_edit_plan is not None:
            try:
                from app.ai.visual_hints import build_ai_visual_intensity_config as _build_vis_int
                _ai_visual_intensity_config = _build_vis_int(_exec_hints, payload)
                _vis_reason = (
                    str(_ai_visual_intensity_config.rejected_reason)
                    if _ai_visual_intensity_config.rejected_reason
                    else "applied"
                )
                if _phase53_tracer is not None:
                    try:
                        _phase53_tracer.log_visual_intensity_applied(
                            {**_ai_visual_intensity_config.to_dict(), "reason": _vis_reason}
                        )
                    except Exception:
                        pass
                # Log decision_rejected only when NOT applied
                if not _ai_visual_intensity_config.applied and _phase53_tracer is not None:
                    try:
                        _phase53_tracer.log_decision_rejected(
                            _vis_reason,
                            detail={
                                "hint": "visual_intensity",
                                "value": _ai_visual_intensity_config.visual_intensity,
                                "phase": "5.7",
                            },
                        )
                    except Exception:
                        pass
                logger.debug(
                    "phase57_visual_intensity_config job_id=%s applied=%s intensity=%s reason=%s",
                    job_id,
                    _ai_visual_intensity_config.applied,
                    _ai_visual_intensity_config.visual_intensity,
                    _ai_visual_intensity_config.rejected_reason,
                )
                # Phase 5.7: Extract hint from render_overrides when applied=True.
                # _vis_intensity_hint is used below in per-part renderer calls.
                # When applied=False: hint is None → renderer uses effect_preset unchanged.
            except Exception as _vis57_err:
                logger.warning(
                    "phase57_visual_intensity_config_failed job_id=%s: %s", job_id, _vis57_err
                )
                _ai_visual_intensity_config = None
        elif not getattr(payload, "ai_director_enabled", False):
            # AI disabled: skip entirely, log as advisory
            if _phase53_tracer is not None:
                try:
                    _phase53_tracer.log_decision_rejected(
                        "ai_disabled",
                        detail={"hint": "visual_intensity", "phase": "5.7"},
                    )
                except Exception:
                    pass

        # ── Phase 5.7: Extract visual_intensity_hint for per-part renderer calls ──
        # When _ai_visual_intensity_config.applied=True, render_overrides contains
        # {"visual_intensity_hint": <value>}. Extract it for use in renderer calls.
        # When applied=False (disabled, invalid, user override): hint=None.
        # This local variable is read-only — payload.effect_preset is NEVER mutated.
        _vis_intensity_hint: "str | None" = None
        if (
            _ai_visual_intensity_config is not None
            and _ai_visual_intensity_config.applied
        ):
            try:
                _vis_intensity_hint = (
                    _ai_visual_intensity_config.render_overrides.get("visual_intensity_hint")
                )
            except Exception:
                _vis_intensity_hint = None

        # ── AI Execution Mode Resolution (Phase 60D) — control only ─────────────
        # Resolve BEFORE Phase 59 blocks so they can be gated correctly.
        # mode=off blocks all Phase 59 promotion; other modes run Phase 59 normally.
        _ai_exec_mode: str = "safe"
        if _ai_edit_plan is not None:
            try:
                from app.ai.execution_mode.execution_mode_engine import (
                    resolve_execution_mode as _resolve_exec_mode,
                )
                _mode_result = _resolve_exec_mode(payload, context={"job_id": job_id})
                _mode_data = _mode_result.get("ai_execution_mode") or {}
                _ai_exec_mode = str(_mode_data.get("effective_mode") or "safe")
                try:
                    _ai_edit_plan.ai_execution_mode = _mode_data
                except Exception:
                    pass
                logger.info(
                    "ai_execution_mode_resolved job_id=%s mode=%s source=%s",
                    job_id, _ai_exec_mode, _mode_data.get("source", "unknown"),
                )
            except Exception as _mode_err:
                _ai_exec_mode = "safe"
                logger.warning(
                    "ai_execution_mode_resolution_failed job_id=%s: %s", job_id, _mode_err
                )

        # mode=off: write rollback metadata + stub promotion reports, then skip Phase 59
        if _ai_edit_plan is not None and _ai_exec_mode == "off":
            _rollback = {
                "active":          True,
                "reason":          "mode_off",
                "blocked_domains": ["subtitle", "camera", "segment"],
            }
            try:
                _ai_edit_plan.ai_execution_rollback = _rollback
            except Exception:
                pass
            _mode_off_stub = {
                "applied":  False,
                "eligible": True,
                "reason":   "mode_off",
                "blocked":  True,
                "confidence": 0.0,
            }
            try:
                _ai_edit_plan.subtitle_execution_promotion = dict(_mode_off_stub)
                _ai_edit_plan.camera_execution_promotion   = dict(_mode_off_stub)
                _ai_edit_plan.segment_selection_promotion  = dict(_mode_off_stub)
            except Exception:
                pass
            logger.info(
                "ai_execution_rollback_active job_id=%s reason=mode_off blocked=subtitle,camera,segment",
                job_id,
            )

        # ── AI Render Influence (Phase 10) — bounded opt-in payload adjustments ──
        _ai_influence_report: dict = {"enabled": False}
        if _ai_edit_plan is not None and getattr(payload, "ai_render_influence_enabled", False) \
                and _ai_exec_mode != "off":
            try:
                from app.ai.director.render_influence import apply_ai_render_influence as _apply_ai_influence
                payload, _ai_influence_report = _apply_ai_influence(
                    payload,
                    _ai_edit_plan,
                    context={"job_id": job_id},
                )
                logger.info(
                    "ai_render_influence_applied job_id=%s applied=%d skipped=%d",
                    job_id,
                    len(_ai_influence_report.get("applied", [])),
                    len(_ai_influence_report.get("skipped", [])),
                )
            except Exception as _inf_err:
                _ai_influence_report = {
                    "enabled": True,
                    "applied": [],
                    "skipped": [],
                    "warnings": [f"influence_module_error:{type(_inf_err).__name__}"],
                }
                logger.warning("ai_render_influence_module_failed job_id=%s: %s", job_id, _inf_err)
        elif _ai_edit_plan is not None:
            logger.debug("ai_render_influence_skipped job_id=%s (disabled)", job_id)

        # ── AI Beat Execution (Phase 11) — metadata-only beat plan ───────────
        _ai_beat_report: dict = {"enabled": False}
        if _ai_edit_plan is not None and getattr(payload, "ai_beat_execution_enabled", False):
            beat_exec_cached = getattr(_ai_edit_plan, "beat_execution", None)
            if isinstance(beat_exec_cached, dict) and beat_exec_cached.get("beat_available"):
                _ai_beat_report = beat_exec_cached
                logger.info(
                    "ai_beat_execution_planned job_id=%s bpm=%s count=%d enabled=%s",
                    job_id,
                    _ai_beat_report.get("bpm"),
                    _ai_beat_report.get("beat_count", 0),
                    _ai_beat_report.get("enabled", False),
                )
            else:
                try:
                    from app.ai.director.beat_execution import build_beat_execution_plan as _build_beat
                    _ai_beat_report = _build_beat(
                        _ai_edit_plan, payload, context={"job_id": job_id}
                    )
                    _ai_edit_plan.beat_execution = _ai_beat_report
                    logger.info(
                        "ai_beat_execution_planned job_id=%s bpm=%s count=%d enabled=%s",
                        job_id,
                        _ai_beat_report.get("bpm"),
                        _ai_beat_report.get("beat_count", 0),
                        _ai_beat_report.get("enabled", False),
                    )
                except Exception as _beat_err:
                    _ai_beat_report = {
                        "enabled": False,
                        "warnings": [f"beat_execution_module_error:{type(_beat_err).__name__}"],
                    }
                    logger.warning("ai_beat_execution_module_failed job_id=%s: %s", job_id, _beat_err)
        elif _ai_edit_plan is not None:
            logger.debug("ai_beat_execution_skipped job_id=%s (disabled)", job_id)

        # Save original scored order before Phase 59C (used by Phase 59D segment gate)
        _scored_original: list = list(scored)

        # ── AI Segment Selection Promotion (Phase 59C) ───────────────────────
        if _ai_edit_plan is not None and getattr(payload, "ai_render_influence_enabled", False) \
                and _ai_exec_mode != "off":
            try:
                from app.ai.segment_promotion.segment_promotion_engine import (
                    promote_segment_selection as _promote_segments,
                )
                scored, _seg_promo = _promote_segments(
                    scored, _ai_edit_plan, payload, context={"job_id": job_id}
                )
                _promo = _seg_promo.get("segment_selection_promotion") or {}
                try:
                    _ai_edit_plan.segment_selection_promotion = _promo
                except Exception:
                    pass
                if _promo.get("applied"):
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="ai_segment_promotion_applied",
                        level="INFO",
                        message=(
                            f"AI segment promotion: {_promo.get('selected_count', 0)}"
                            f"/{_promo.get('total_count', 0)} segments reordered"
                        ),
                        step="ai_segment_promotion",
                        context=_promo,
                    )
                    logger.info(
                        "ai_segment_promotion_applied job_id=%s selected=%d total=%d conf=%.3f",
                        job_id,
                        _promo.get("selected_count", 0),
                        _promo.get("total_count", 0),
                        _promo.get("confidence", 0.0),
                    )
                else:
                    logger.debug(
                        "ai_segment_promotion_skipped job_id=%s reason=%s",
                        job_id,
                        _promo.get("reason", "not_eligible"),
                    )
            except Exception as _seg_err:
                logger.warning(
                    "ai_segment_promotion_failed job_id=%s: %s", job_id, _seg_err
                )

        # ── AI Quality Gate — Segment (Phase 59D) ────────────────────────────
        if _ai_edit_plan is not None and getattr(payload, "ai_render_influence_enabled", False) \
                and _ai_exec_mode != "off":
            try:
                from app.ai.quality_gate.quality_gate_engine import (
                    apply_segment_quality_gate as _segment_quality_gate,
                )
                scored, _seg_gate = _segment_quality_gate(
                    scored, _scored_original, _ai_edit_plan, context={"job_id": job_id}
                )
                _sg = _seg_gate.get("segment_quality_gate") or {}
                try:
                    existing_qg = getattr(_ai_edit_plan, "quality_gated_influence", {}) or {}
                    existing_qg["segment"] = _sg
                    _ai_edit_plan.quality_gated_influence = existing_qg
                except Exception:
                    pass
                if _sg.get("applied"):
                    logger.info(
                        "ai_segment_quality_gate_applied job_id=%s action=%s reverted=%s",
                        job_id,
                        _sg.get("gate_action"),
                        _sg.get("reverted"),
                    )
                else:
                    logger.debug(
                        "ai_segment_quality_gate_no_change job_id=%s action=%s",
                        job_id,
                        _sg.get("gate_action", "no_change"),
                    )
            except Exception as _qg_err:
                logger.warning(
                    "ai_segment_quality_gate_failed job_id=%s: %s", job_id, _qg_err
                )

        # ── AI Execution Metrics (Phase 60A) — observability only ────────
        if _ai_edit_plan is not None:
            try:
                from app.ai.metrics.ai_execution_metrics_engine import (
                    build_ai_execution_metrics as _build_metrics,
                )
                _metrics_result = _build_metrics(
                    _ai_edit_plan, payload, context={"job_id": job_id}
                )
                try:
                    _ai_edit_plan.ai_execution_metrics = (
                        _metrics_result.get("ai_execution_metrics") or {}
                    )
                    _ai_edit_plan.ai_execution_summary = (
                        _metrics_result.get("ai_execution_summary") or {}
                    )
                except Exception:
                    pass
                _summary = _metrics_result.get("ai_execution_summary") or {}
                logger.info(
                    "ai_execution_metrics_collected job_id=%s "
                    "sub=%s cam=%s seg=%s qg_blocks=%d uo=%d assistance=%s",
                    job_id,
                    _summary.get("subtitle_apply"),
                    _summary.get("camera_apply"),
                    _summary.get("segment_apply"),
                    _summary.get("quality_gate_blocks", 0),
                    _summary.get("user_override_count", 0),
                    _summary.get("overall_ai_assistance", "none"),
                )
            except Exception as _met_err:
                logger.warning(
                    "ai_execution_metrics_failed job_id=%s: %s", job_id, _met_err
                )

        # ── A/B Render Evaluation (Phase 60B) — evaluation only ──────────
        # baseline=None in single renders → returns available=False candidate summary.
        # Full A/B comparison requires an explicit baseline from a prior AI-OFF render.
        if _ai_edit_plan is not None:
            try:
                from app.ai.ab_evaluation.ab_evaluation_engine import (
                    build_ab_evaluation as _build_ab_eval,
                )
                _ab_result = _build_ab_eval(
                    _ai_edit_plan,
                    baseline=None,
                    context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.ai_ab_evaluation = (
                        _ab_result.get("ai_ab_evaluation") or {}
                    )
                except Exception:
                    pass
                _ab = _ab_result.get("ai_ab_evaluation") or {}
                logger.info(
                    "ai_ab_evaluation_collected job_id=%s available=%s winner=%s confidence=%.3f",
                    job_id,
                    _ab.get("available"),
                    _ab.get("winner", "unknown"),
                    float(_ab.get("confidence") or 0.0),
                )
            except Exception as _ab_err:
                logger.warning(
                    "ai_ab_evaluation_failed job_id=%s: %s", job_id, _ab_err
                )

        # ── Creator Benchmark Suite (Phase 60C) — benchmarking only ──────────
        # Evaluates AI quality against creator archetype benchmarks using
        # Phase 60B A/B evaluation signals. No render mutation.
        if _ai_edit_plan is not None:
            try:
                from app.ai.creator_benchmark.creator_benchmark_engine import (
                    build_creator_benchmark as _build_creator_benchmark,
                )
                _cb_result = _build_creator_benchmark(
                    _ai_edit_plan,
                    context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.creator_benchmark_summary = (
                        _cb_result.get("creator_benchmark_summary") or {}
                    )
                except Exception:
                    pass
                _cb = _cb_result.get("creator_benchmark_summary") or {}
                logger.info(
                    "creator_benchmark_collected job_id=%s available=%s "
                    "creator_type=%s status=%s delta=%s",
                    job_id,
                    _cb.get("available"),
                    _cb.get("creator_type", "unknown"),
                    _cb.get("benchmark_status", "unknown"),
                    _cb.get("overall_delta"),
                )
            except Exception as _cb_err:
                logger.warning(
                    "creator_benchmark_failed job_id=%s: %s", job_id, _cb_err
                )

        # ── Creator Archetype Strategy (Phase 61A) — advisory metadata only ──────
        # Maps creator type to deterministic style strategy preferences.
        # Does NOT mutate render execution. Advisory guidance for future influence.
        if _ai_edit_plan is not None:
            try:
                from app.ai.creator_archetype.creator_archetype_engine import (
                    build_creator_archetype_strategy as _build_archetype_strategy,
                )
                _arch_result = _build_archetype_strategy(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.creator_archetype_strategy = (
                        _arch_result.get("creator_archetype_strategy") or {}
                    )
                except Exception:
                    pass
                _arch = _arch_result.get("creator_archetype_strategy") or {}
                logger.info(
                    "creator_archetype_strategy_built job_id=%s available=%s "
                    "creator_type=%s confidence=%.3f",
                    job_id,
                    _arch.get("available"),
                    _arch.get("creator_type", "unknown"),
                    float(_arch.get("confidence") or 0.0),
                )
            except Exception as _arch_err:
                logger.warning(
                    "creator_archetype_strategy_failed job_id=%s: %s", job_id, _arch_err
                )

        # ── Creator Render Strategy Fusion (Phase 61D) — advisory metadata only ──
        # Fuses Phase 61A archetype + creator_preference_profile + platform strategy
        # + quality metadata into a coherent creator-style render strategy.
        # Does NOT mutate render execution. Metadata for UX and future influence.
        if _ai_edit_plan is not None:
            try:
                from app.ai.creator_style.creator_render_strategy_engine import (
                    build_creator_render_strategy as _build_creator_render_strategy,
                )
                _crs_result = _build_creator_render_strategy(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.creator_render_strategy = (
                        _crs_result.get("creator_render_strategy") or {}
                    )
                except Exception:
                    pass
                _crs = _crs_result.get("creator_render_strategy") or {}
                logger.info(
                    "creator_render_strategy_built job_id=%s available=%s "
                    "creator_type=%s confidence=%.3f",
                    job_id,
                    _crs.get("available"),
                    _crs.get("creator_type", "unknown"),
                    float(_crs.get("confidence") or 0.0),
                )
            except Exception as _crs_err:
                logger.warning(
                    "creator_render_strategy_failed job_id=%s: %s", job_id, _crs_err
                )

        # ── Render Outcome Tracking (Phase 62A) — tracking-only, no mutation ────
        # Aggregates Phase 60A/60B/60C/61D metadata into a structured outcome
        # record for audit, debug, and future learning. No render mutation.
        if _ai_edit_plan is not None:
            try:
                from app.ai.outcome_tracking.render_outcome_tracking_engine import (
                    build_render_outcome_tracking as _build_render_outcome_tracking,
                )
                _rot_result = _build_render_outcome_tracking(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.render_outcome_tracking = (
                        _rot_result.get("render_outcome_tracking") or {}
                    )
                except Exception:
                    pass
                _rot = _rot_result.get("render_outcome_tracking") or {}
                logger.info(
                    "render_outcome_tracking_built job_id=%s available=%s "
                    "overall_result=%s ai_effectiveness=%s creator_fit=%s confidence=%.3f",
                    job_id,
                    _rot.get("available"),
                    _rot.get("overall_result", "unknown"),
                    _rot.get("ai_effectiveness", "unknown"),
                    (_rot.get("benchmark_result") or {}).get("creator_fit", "unknown"),
                    float(_rot.get("confidence") or 0.0),
                )
            except Exception as _rot_err:
                logger.warning(
                    "render_outcome_tracking_failed job_id=%s: %s", job_id, _rot_err
                )

        # ── Creator Preference Reinforcement (Phase 62B) — metadata only ─────
        # Converts positive/negative outcomes into bounded preference signals.
        # No render mutation, no autonomous retraining, no external persistence.
        if _ai_edit_plan is not None:
            try:
                from app.ai.outcome_tracking.creator_preference_reinforcement_engine import (
                    build_creator_preference_reinforcement as _build_cpr,
                )
                _cpr_result = _build_cpr(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.creator_preference_reinforcement = (
                        _cpr_result.get("creator_preference_reinforcement") or {}
                    )
                except Exception:
                    pass
                _cpr = _cpr_result.get("creator_preference_reinforcement") or {}
                logger.info(
                    "creator_preference_reinforcement_built job_id=%s available=%s "
                    "domains_reinforced=%d negative_signals=%d confidence=%.3f",
                    job_id,
                    _cpr.get("available"),
                    len(_cpr.get("reinforced_preferences") or {}),
                    len(_cpr.get("negative_signals") or []),
                    float(_cpr.get("confidence") or 0.0),
                )
            except Exception as _cpr_err:
                logger.warning(
                    "creator_preference_reinforcement_failed job_id=%s: %s", job_id, _cpr_err
                )

        # ── Success Pattern Mining (Phase 62C) — pattern metadata only ──────
        # Discovers deterministic success patterns from this render's outcome.
        # No render mutation, no autonomous training, no external persistence.
        if _ai_edit_plan is not None:
            try:
                from app.ai.outcome_tracking.render_success_pattern_engine import (
                    build_render_success_patterns as _build_rsp,
                )
                _rsp_result = _build_rsp(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.render_success_patterns = (
                        _rsp_result.get("render_success_patterns") or {}
                    )
                except Exception:
                    pass
                _rsp = _rsp_result.get("render_success_patterns") or {}
                logger.info(
                    "render_success_patterns_built job_id=%s available=%s "
                    "pattern_count=%d confidence=%.3f",
                    job_id,
                    _rsp.get("available"),
                    len(_rsp.get("patterns") or []),
                    float(_rsp.get("confidence") or 0.0),
                )
            except Exception as _rsp_err:
                logger.warning(
                    "render_success_patterns_failed job_id=%s: %s", job_id, _rsp_err
                )

        # ── Learning-Aware Influence Calibration (Phase 62D) — metadata only ─
        # Calibrates bounded AI influence using patterns/reinforcement signals.
        # No render mutation, no autonomous retraining, no external persistence.
        if _ai_edit_plan is not None:
            try:
                from app.ai.outcome_tracking.learning_influence_calibration_engine import (
                    build_learning_influence_calibration as _build_lic,
                )
                _lic_result = _build_lic(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.learning_influence_calibration = (
                        _lic_result.get("learning_influence_calibration") or {}
                    )
                except Exception:
                    pass
                _lic = _lic_result.get("learning_influence_calibration") or {}
                logger.info(
                    "learning_influence_calibration_built job_id=%s available=%s "
                    "mode=%s pos_domains=%d neg_entries=%d confidence=%.3f",
                    job_id,
                    _lic.get("available"),
                    _lic.get("execution_mode", "unknown"),
                    len(_lic.get("calibration") or {}),
                    len(_lic.get("negative_calibration") or []),
                    float(_lic.get("confidence") or 0.0),
                )
            except Exception as _lic_err:
                logger.warning(
                    "learning_influence_calibration_failed job_id=%s: %s", job_id, _lic_err
                )

        for idx, seg in enumerate(scored, start=1):
            existing = existing_parts.get(idx, {})
            existing_status = (existing.get("status") or "").lower()
            if existing_status == "done" and payload.resume_from_last:
                continue
            upsert_job_part(
                job_id=job_id,
                part_no=idx,
                part_name=f"part_{idx:03d}",
                status=JobPartStage.QUEUED,
                progress_percent=0,
                start_sec=seg["start"],
                end_sec=seg["end"],
                duration=seg["duration"],
                viral_score=seg.get("viral_score", 0),
                motion_score=seg.get("motion_score", 0),
                hook_score=seg.get("hook_score", 0),
            )

        # UP28.1: source stat for motion path cache key — computed once, shared across all parts
        try:
            _src_stat_for_motion = source_path.stat()
        except Exception:
            _src_stat_for_motion = None

        def _process_one_part(idx: int, seg: dict):
            raw_part = work_dir / f"{source['slug']}_part_{idx:03d}_raw.mp4"
            srt_part = work_dir / f"{source['slug']}_part_{idx:03d}.srt"
            ass_part = work_dir / f"{source['slug']}_part_{idx:03d}.ass"
            _variant_type = str(seg.get("variant_type") or "")
            if _variant_type:
                final_part = output_dir / f"{_output_stem}_{_variant_type}.mp4"
                part_name  = f"{_output_stem}_{_variant_type}.mp4"
            else:
                final_part = output_dir / f"{_output_stem}_part_{idx:03d}.mp4"
                part_name  = f"{_output_stem}_part_{idx:03d}.mp4"
            _sub_target_lang = getattr(payload, "subtitle_target_language", "en")
            translated_srt_part = work_dir / f"{source['slug']}_part_{idx:03d}.{_sub_target_lang}.srt"
            _srt_meta: dict = {}  # populated by subtitle slice; used for cover frame scoring (UP15)
            _job_log(effective_channel, job_id, f"Part {idx}/{total_parts} start", kind="debug")
            # Debug artifact: per-part segment metadata JSON
            import os as _os2
            if _os2.getenv("RENDER_DEBUG_LOG", "0") == "1":
                try:
                    import json as _json2
                    _meta_path = work_dir / f"{source['slug']}_part_{idx:03d}_meta.json"
                    _meta_data = {
                        "part": idx,
                        "start": float(seg.get("start", 0)),
                        "end": float(seg.get("end", 0)),
                        "duration": float(seg.get("duration", 0)),
                        "viral_score": float(seg.get("viral_score", 0)),
                        "motion_score": float(seg.get("motion_score", 0)),
                        "hook_score": float(seg.get("hook_score", 0)),
                        "content_type": seg.get("content_type_hint", ""),
                        "variant": seg.get("variant_type", ""),
                        "files": {
                            "raw": str(raw_part),
                            "srt": str(srt_part),
                            "ass": str(ass_part),
                            "output": str(final_part),
                        },
                    }
                    _meta_path.write_text(_json2.dumps(_meta_data, indent=2), encoding="utf-8")
                    logger.debug("debug_artifact segment_meta=%s", _meta_path)
                except Exception as _meta_exc:
                    logger.debug("debug_artifact segment_meta_failed part=%d: %s", idx, _meta_exc)

            # Bail out immediately if job was cancelled before this part started
            if cancel_registry.is_cancelled(job_id):
                raise cancel_registry.JobCancelledError()
            # Expose the cancel event to _run_ffmpeg_with_retry via thread-local so
            # FFmpeg Popen can be killed mid-encode without changing every call site.
            _cancel_ev = cancel_registry.get_event(job_id)
            if _cancel_ev is not None:
                set_thread_cancel_event(_cancel_ev)

            _existing_part_info = existing_parts.get(idx, {})
            if (
                payload.resume_from_last
                and ((_existing_part_info.get("status") or "").lower() == "done")
                and final_part.exists()
                and final_part.stat().st_size > 0
                and _resume_output_valid(final_part)
            ):
                upsert_job_part(job_id, idx, part_name, JobPartStage.DONE, 100, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Skipped (already rendered)")
                _job_log(effective_channel, job_id, f"Part {idx} skipped: final output already exists", kind="debug")
                return {"idx": idx, "output": str(final_part), "row": None, "skipped": True}

            # Worker thread has claimed this part — mark as WAITING before any I/O so
            # the UI can distinguish "queued but not yet started" from "claimed by a thread".
            upsert_job_part(job_id, idx, part_name, JobPartStage.WAITING, 5, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), "", "Waiting for worker")

            # P4 per-output opening optimization state
            _trim_offset = 0.0
            _hook_subtitle_formatted = False
            _srt_count = 0

            # Performance timing — all in milliseconds, logged at part end
            _t_part_start = time.perf_counter()
            _cut_ms = _first_frame_scan_ms = _subtitle_ass_ms = 0
            _render_ms = _micro_pacing_ms = _quality_validation_ms = 0

            # P4-3: Start silence trim — detect and skip leading dead air (all output clips)
            try:
                _trim_offset = detect_silence_trim_offset(str(source_path), seg["start"], seg["end"])
            except Exception:
                _trim_offset = 0.0
            # Safety: don't trim if effective clip would be shorter than 3 seconds
            if _trim_offset > 0 and (seg["end"] - seg["start"] - _trim_offset) < 3.0:
                _trim_offset = 0.0
            if _trim_offset > 0:
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="silence_trim_applied",
                    level="INFO",
                    message=f"Silence trim: {_trim_offset:.3f}s removed from part {idx} start",
                    step="render.silence_trim",
                    context={
                        "part_no": idx,
                        "trim_offset_sec": _trim_offset,
                        "original_start": seg["start"],
                        "effective_start": seg["start"] + _trim_offset,
                    },
                )
                _job_log(effective_channel, job_id, f"Part {idx} silence trim: {_trim_offset:.3f}s offset applied")
            _effective_start = seg["start"] + _trim_offset

            # P4-X: Bad first-frame scan — detect black/dark opening frames and shift start up to 1.0s.
            _visual_trim = 0.0
            _force_accurate_cut = False
            try:
                logger.info("first_frame_scan_started part_no=%d effective_start=%.3f", idx, _effective_start)
                _t_ff = time.perf_counter()
                _visual_trim = detect_bad_first_frame(str(source_path), _effective_start, seg["end"])
                _first_frame_scan_ms = int((time.perf_counter() - _t_ff) * 1000)
                logger.info("first_frame_scan_ms=%d part=%d shift=%.3f", _first_frame_scan_ms, idx, _visual_trim)
            except Exception:
                _visual_trim = 0.0
            if _visual_trim > 0:
                _candidate_total = _trim_offset + _visual_trim
                if (seg["end"] - seg["start"] - _candidate_total) >= 3.0:
                    _trim_offset = _candidate_total
                    _effective_start = seg["start"] + _trim_offset
                    _force_accurate_cut = True
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="first_frame_shift_applied",
                        level="INFO",
                        message=f"Bad first frame detected: shifted part {idx} start by {_visual_trim:.3f}s",
                        step="render.first_frame_scan",
                        context={
                            "part_no": idx,
                            "visual_trim_sec": _visual_trim,
                            "total_trim_sec": _trim_offset,
                            "effective_start": _effective_start,
                            "force_accurate_cut": True,
                        },
                    )
                    _job_log(effective_channel, job_id,
                        f"first_frame_shift_applied part={idx} visual_trim={_visual_trim:.3f}s "
                        f"total_trim={_trim_offset:.3f}s effective_start={_effective_start:.3f}s accurate_cut=True")

            # Build TimelineMap and BaseClipManifest after all trim decisions are
            # final (_effective_start is settled).  Written to disk before cut_video()
            # so a crash leaves a consistent record up to the last completed step.
            _part_platform_delta = float(
                _PLATFORM_PROFILES.get(_target_platform, {}).get("speed_delta", 0.0)
            )
            _part_timeline = TimelineMap(
                source_start=float(_effective_start),
                source_end=float(seg["end"]),
                effective_speed=_get_effective_playback_speed(payload, _target_platform),
                trim_offset=float(_trim_offset),
            )
            _part_manifest = BaseClipManifest(
                job_id=job_id,
                part_no=idx,
                source_path=str(source_path),
                source_start=float(_effective_start),
                source_end=float(seg["end"]),
                payload_speed=float(payload.playback_speed or 1.07),
                platform=_target_platform,
                platform_delta=_part_platform_delta,
                effective_speed=_part_timeline.effective_speed,
                variant_type=seg.get("variant_type"),
                variant_speed=(
                    float(seg["variant_playback_speed"])
                    if seg.get("variant_playback_speed") is not None else None
                ),
                silence_trim_offset=float(_trim_offset - _visual_trim)
                    if _visual_trim > 0 else float(_trim_offset),
                visual_trim_offset=float(_visual_trim),
                timeline=_part_timeline,
                ai_enabled=bool(getattr(payload, "ai_director_enabled", False)),
                ai_mode=getattr(_ai_edit_plan, "mode", None) if _ai_edit_plan is not None else None,
                ai_selected=False,  # not yet wired to AIEditPlan selection
                ai_speed_hint=None,
            )
            write_manifest(work_dir, _part_manifest)

            upsert_job_part(job_id, idx, part_name, JobPartStage.CUTTING, 10, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Cutting raw part")
            if not (payload.resume_from_last and raw_part.exists() and raw_part.stat().st_size > 0):
                _t_cut = time.perf_counter()
                cut_video(str(source_path), str(raw_part), _effective_start, seg["end"],
                          retry_count=retry_count, force_accurate_cut=_force_accurate_cut)
                _cut_ms = int((time.perf_counter() - _t_cut) * 1000)
                logger.info("cut_video_ms=%d part=%d", _cut_ms, idx)
                if _force_accurate_cut:
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="accurate_cut_forced",
                        level="INFO",
                        message=f"Accurate re-encode cut used for part {idx} (bad first frame shift)",
                        step="render.cut",
                        context={"part_no": idx, "effective_start": _effective_start},
                    )
                _job_log(effective_channel, job_id, f"Part {idx} cut done", kind="debug")
            else:
                _job_log(effective_channel, job_id, f"Part {idx} cut skipped (raw exists)", kind="debug")
            _part_manifest.cut_path = str(raw_part)
            write_manifest(work_dir, _part_manifest)

            subtitle_selected_by_rule = subtitle_enabled_by_idx.get(idx, False)
            part_subtitle_enabled = subtitle_selected_by_rule
            if part_subtitle_enabled and not full_srt_available:
                part_subtitle_enabled = False
                _job_log(effective_channel, job_id, f"Part {idx} subtitle skipped: full transcript unavailable", kind="warning")
            if payload.add_subtitle and not part_subtitle_enabled and not subtitle_selected_by_rule:
                _job_log(effective_channel, job_id, f"Part {idx} subtitle skipped (viral={int(seg.get('viral_score', 0))} < cutoff={int(subtitle_cutoff)})")

            if part_subtitle_enabled:
                upsert_job_part(job_id, idx, part_name, JobPartStage.TRANSCRIBING, 35, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Preparing subtitle")
                needs_srt = not (payload.resume_from_last and srt_part.exists() and srt_part.stat().st_size > 0)
                needs_ass = not (payload.resume_from_last and ass_part.exists() and ass_part.stat().st_size > 0)
                _srt_source_is_fresh = needs_srt  # P1: tracks whether mutations must run
                if needs_srt:
                    # P2: match subtitle slice speed to the platform-adjusted render speed so
                    # timing aligns on TikTok (+0.08) and Instagram Reels (-0.06).
                    _eff_speed = _get_effective_playback_speed(payload, _target_platform)
                    _visual_apply_speed = False
                    _srt_meta = slice_srt_by_time(
                        str(full_srt),
                        str(srt_part),
                        _effective_start,
                        seg["end"],
                        rebase_to_zero=True,
                        playback_speed=_eff_speed,
                        apply_playback_speed=_visual_apply_speed,
                    )
                    _srt_count = _srt_meta.get("subtitle_count", 0)
                    _job_log(
                        effective_channel, job_id,
                        f"subtitle_part_sync part_no={idx} subtitle_slice_mode=visual_burn_in "
                        f"start={seg['start']:.1f}s effective_start={_effective_start:.1f}s end={seg['end']:.1f}s "
                        f"playback_speed={_eff_speed} apply_playback_speed={_visual_apply_speed} count={_srt_count}"
                        + (
                            f" first={_srt_meta['first_start']:.3f}->{_srt_meta['first_end']:.3f}s"
                            f" last={_srt_meta['last_start']:.3f}->{_srt_meta['last_end']:.3f}s"
                            if _srt_count > 0 else " (no speech)"
                        ),
                        kind="debug" if _srt_count > 0 else "warning",
                    )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="subtitle_part_sync",
                        level="INFO" if _srt_count > 0 else "WARNING",
                        message=f"Subtitle sliced for part {idx}: {_srt_count} entries",
                        step="subtitle.slice",
                        context={
                            "part_no": idx,
                            "part_start": seg["start"],
                            "part_end": seg["end"],
                            "effective_start": _effective_start,
                            "subtitle_slice_mode": "visual_burn_in",
                            "playback_speed": _eff_speed,
                            "apply_playback_speed": _visual_apply_speed,
                            "subtitle_count": _srt_count,
                            "first_sub_start": _srt_meta.get("first_start"),
                            "first_sub_end": _srt_meta.get("first_end"),
                            "last_sub_start": _srt_meta.get("last_start"),
                            "last_sub_end": _srt_meta.get("last_end"),
                            "part_srt_path": str(srt_part),
                            "resume_cache_hit_srt": False,
                            "resume_cache_hit_ass": not needs_ass,
                        },
                    )
                else:
                    # P0-FIX: resume cache hit — read timing metadata from existing SRT so
                    # CTA (and any callers of _srt_meta["last_end"]) get the correct timestamp
                    # instead of falling back to 0.0 and appending CTA at the start of the clip.
                    if srt_part.exists() and srt_part.stat().st_size > 0:
                        _srt_meta = _read_srt_meta(str(srt_part))
                    _job_log(
                        effective_channel, job_id,
                        f"subtitle_resume_cache_hit part_no={idx} "
                        f"srt_exists={srt_part.exists()} "
                        f"ass_exists={ass_part.exists()} "
                        f"last_sub_end={_srt_meta.get('last_end')!r}",
                        kind="debug",
                    )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="subtitle_part_sync",
                        level="INFO",
                        message=f"Subtitle resume cache hit for part {idx}: {_srt_meta.get('subtitle_count', 0)} entries",
                        step="subtitle.slice",
                        context={
                            "part_no": idx,
                            "part_start": seg["start"],
                            "part_end": seg["end"],
                            "part_srt_path": str(srt_part),
                            "resume_cache_hit_srt": True,
                            "resume_cache_hit_ass": not needs_ass,
                            "subtitle_count": _srt_meta.get("subtitle_count", 0),
                            "last_sub_end": _srt_meta.get("last_end"),
                        },
                    )
                _part_manifest.srt_path = str(srt_part)
                write_manifest(work_dir, _part_manifest)
                # OQ-1.2 — subtitle intelligence: semantic resegmentation for readability.
                # Targets segment-level SRT only; word-level SRT is skipped internally.
                # Fires only on fresh slices — resume cache hits are left unchanged.
                if _srt_source_is_fresh and srt_part.exists() and not getattr(payload, "highlight_per_word", False):
                    try:
                        _intel_out = resegment_srt_for_readability(str(srt_part))
                        if _intel_out > 0:
                            needs_ass = True
                    except Exception as _intel_exc:
                        logger.warning("subtitle_intel_resegment_failed part=%d: %s", idx, _intel_exc)

                _ass_srt_source = srt_part
                if getattr(payload, "subtitle_translate_enabled", False) and srt_part.exists() and srt_part.stat().st_size > 0:
                    _needs_translated = not (payload.resume_from_last and translated_srt_part.exists() and translated_srt_part.stat().st_size > 0)
                    if _needs_translated:
                        _sub_translate_attempts.append(idx)
                        if cancel_registry.is_cancelled(job_id):
                            raise cancel_registry.JobCancelledError()
                        try:
                            _job_log(effective_channel, job_id, f"subtitle_translate_started part_no={idx} target={_sub_target_lang}", kind="debug")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="subtitle_translate_started",
                                level="INFO",
                                message=f"Translating subtitle (part {idx})",
                                step="subtitle.translate",
                                context={"part_no": idx, "target": _sub_target_lang},
                            )
                            _, _block_failures = translate_srt_file(str(srt_part), str(translated_srt_part), target_language=_sub_target_lang)
                            for _bfi in _block_failures:
                                _job_log(effective_channel, job_id, f"subtitle_translate_block_failed part_no={idx} block={_bfi} target={_sub_target_lang}", kind="warning")
                            if _block_failures:
                                _sub_translate_partial.append(idx)
                                _job_log(
                                    effective_channel, job_id,
                                    f"Translation partially failed for {_sub_target_lang} export — "
                                    f"{len(_block_failures)} subtitle block(s) could not be translated. "
                                    f"Original text preserved for those blocks.",
                                    kind="warning",
                                )
                            else:
                                _sub_translate_clean.append(idx)
                            _job_log(effective_channel, job_id, f"subtitle_translate_completed part_no={idx} output={translated_srt_part}")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="subtitle_translate_completed",
                                level="INFO",
                                message=f"Subtitle translated (part {idx})",
                                step="subtitle.translate",
                                context={"part_no": idx, "output": str(translated_srt_part), "block_failures": len(_block_failures)},
                            )
                            needs_ass = True
                        except Exception as _trans_exc:
                            _sub_translate_failed_parts.append(idx)
                            _job_log(effective_channel, job_id, f"subtitle_translate_failed part_no={idx}: {_trans_exc}", kind="warning")
                            _job_log(
                                effective_channel, job_id,
                                f"Translation failed for {_sub_target_lang} export (part {idx}). "
                                f"Subtitles will use original language.",
                                kind="warning",
                            )
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="subtitle_translate_failed",
                                level="WARNING",
                                message=f"Subtitle translation failed (part {idx}): {_trans_exc}",
                                step="subtitle.translate",
                                context={"part_no": idx},
                            )
                    if translated_srt_part.exists() and translated_srt_part.stat().st_size > 0:
                        _ass_srt_source = translated_srt_part
                        if _needs_translated:
                            _srt_source_is_fresh = True  # P1: freshly translated — mutations must run
                _sub_edits = getattr(payload, 'subtitle_edits', None)
                if _srt_source_is_fresh and _sub_edits and _ass_srt_source.exists():
                    try:
                        _apply_subtitle_edits_to_srt(str(_ass_srt_source), _sub_edits)
                    except Exception as _se_exc:
                        logger.warning("subtitle_edits: skipped due to error: %s", _se_exc)
                if _srt_source_is_fresh and _hook_apply_enabled and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
                    try:
                        _hook_apply_meta = apply_market_hook_text_to_srt(
                            str(_ass_srt_source),
                            _hook_applied_text,
                            max_hook_blocks=1,
                            max_hook_seconds=5.0,
                        )
                        _hook_affected = int(_hook_apply_meta.get("affected_count") or 0)
                        if _hook_apply_meta.get("applied"):
                            needs_ass = True
                        _job_log(
                            effective_channel,
                            job_id,
                            "market_viral_hook_apply "
                            f"part_no={idx} market={_mv_market} "
                            f"hook_apply_enabled={_hook_apply_enabled} "
                            f"hook_score={_hook_score} "
                            f"subtitle_blocks_affected={_hook_affected} "
                            f"original_hook_text={_hook_apply_meta.get('original_hook_text', '')!r} "
                            f"applied_hook_text={_hook_apply_meta.get('applied_hook_text', '')!r}",
                        )
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="market_viral_hook_applied",
                            level="INFO",
                            message=f"Market Viral hook applied to {_hook_affected} subtitle block(s) (part {idx})",
                            step="subtitle.market_hook",
                            context={
                                "part_no": idx,
                                "market": _mv_market,
                                "hook_apply_enabled": _hook_apply_enabled,
                                "hook_score": _hook_score,
                                "subtitle_blocks_affected": _hook_affected,
                                "original_hook_text": _hook_apply_meta.get("original_hook_text", ""),
                                "applied_hook_text": _hook_apply_meta.get("applied_hook_text", ""),
                            },
                        )
                    except Exception as _hook_exc:
                        logger.warning("market_viral_hook_apply: skipped due to error: %s", _hook_exc)
                elif _hook_apply_enabled:
                    _job_log(
                        effective_channel,
                        job_id,
                        "market_viral_hook_apply "
                        f"part_no={idx} market={_mv_market} "
                        f"hook_apply_enabled={_hook_apply_enabled} "
                        f"hook_score={_hook_score} "
                        "subtitle_blocks_affected=0 "
                        "original_hook_text='' "
                        f"applied_hook_text={_hook_applied_text!r}",
                        kind="warning",
                    )
                if _srt_source_is_fresh and _mv_cfg and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
                    try:
                        apply_market_line_break_to_srt(str(_ass_srt_source), _mv_cfg)
                        needs_ass = True
                    except Exception:
                        pass
                # P4-2: Hook subtitle impact — opening lines of every output clip
                if _srt_source_is_fresh and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
                    try:
                        _hook_orig_len = _ass_srt_source.stat().st_size
                        _hook_blocks = apply_hook_subtitle_format(str(_ass_srt_source))
                        if _hook_blocks > 0:
                            needs_ass = True
                            _hook_subtitle_formatted = True
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="subtitle_hook_format_applied",
                                level="INFO",
                                message=f"Hook subtitle impact applied: {_hook_blocks} blocks (part {idx})",
                                step="subtitle.hook_format",
                                context={
                                    "part_no": idx,
                                    "original_length": _hook_orig_len,
                                    "new_length": _ass_srt_source.stat().st_size,
                                    "lines_count": _hook_blocks,
                                },
                            )
                    except Exception as _hfmt_exc:
                        logger.warning("apply_hook_subtitle_format: skipped part %d due to error: %s", idx, _hfmt_exc)
                # Content-type subtitle auto-default — fires only when no explicit style set.
                # Creator's explicit choice (any non-empty subtitle_style) always wins.
                _CONTENT_TYPE_SUB_DEFAULTS: dict[str, str] = {
                    "interview":  "clean",
                    "commentary": "viral",
                    "vlog":       "story",
                    "tutorial":   "clean",
                    "montage":    "gaming",
                }
                # Subtitle hierarchy (UP14): variant > creator explicit > platform bias > content-type default.
                # Variant subtitle takes priority; falls back to creator payload choice.
                _raw_sub_style = (
                    str(seg.get("variant_subtitle_style") or "").strip()
                    or (payload.subtitle_style or "").strip()
                )
                # UP14: platform sub_bias — only used when neither variant nor creator set a style.
                _platform_sub_bias = (
                    _PLATFORM_PROFILES.get(_target_platform, {})
                    .get("sub_bias", {})
                    .get(str(seg.get("content_type_hint") or "vlog"), "")
                ) if not _raw_sub_style else ""
                # UP20: DNA sub_bias — clean_visual identity nudge; below platform in hierarchy.
                _dna_sub_bias_val = (
                    {"interview": "clean", "commentary": "story", "vlog": "story",
                     "tutorial": "clean", "montage": "gaming"}.get(
                        str(seg.get("content_type_hint") or "vlog"), "")
                ) if (not _raw_sub_style and not _platform_sub_bias and _dna_clean_visual) else ""
                # UP20.1 Part D: log when clean_visual DNA was suppressed by a higher layer.
                if _dna_clean_visual and not _dna_sub_bias_val:
                    _sub_suppress_reason = (
                        "variant"  if str(seg.get("variant_subtitle_style") or "").strip() else
                        "creator"  if (payload.subtitle_style or "").strip() else
                        "platform" if _platform_sub_bias else "n/a"
                    )
                    _job_log(
                        effective_channel, job_id,
                        f"dna_sub_suppressed: reason={_sub_suppress_reason} part={idx}",
                        kind="debug",
                    )
                _effective_subtitle_style = (
                    _raw_sub_style
                    or _platform_sub_bias
                    or _dna_sub_bias_val
                    or _CONTENT_TYPE_SUB_DEFAULTS.get(
                        seg.get("content_type_hint", "vlog"), "tiktok_bounce_v1"
                    )
                )

                # S4: Subtitle emphasis — semantic wrap + keyword uppercase + highlight markers
                # Phase 5.5: AI emphasis level override applied here if config.applied=True.
                # _effective_subtitle_style (preset ID for ASS) is NEVER changed by AI.
                # Only emphasis_level_override influences text transforms inside the pass.
                if _srt_source_is_fresh and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
                    try:
                        _emph_blocks = parse_srt_blocks(str(_ass_srt_source))
                        if _emph_blocks:
                            # Phase 5.5: resolve AI emphasis level override (None = disabled/not applied)
                            _ai_emph_override = (
                                _ai_subtitle_emphasis_config.emphasis_style
                                if (
                                    _ai_subtitle_emphasis_config is not None
                                    and _ai_subtitle_emphasis_config.applied
                                )
                                else None
                            )
                            subtitle_emphasis_pass(
                                _emph_blocks,
                                preset_id=_effective_subtitle_style,
                                market=_mv_market,
                                language=_sub_target_lang,
                                emphasis_level_override=_ai_emph_override,
                            )
                            write_srt_blocks(_emph_blocks, str(_ass_srt_source))
                            needs_ass = True
                            _job_log(
                                effective_channel, job_id,
                                f"subtitle_emphasis_applied part={idx} "
                                f"style={_effective_subtitle_style} market={_mv_market} "
                                f"lang={_sub_target_lang} blocks={len(_emph_blocks)}"
                                + (f" ai_emph_override={_ai_emph_override}" if _ai_emph_override else ""),
                                kind="info",
                            )
                        else:
                            _job_log(
                                effective_channel, job_id,
                                f"subtitle_emphasis_skipped part={idx} reason=empty_blocks "
                                f"style={_effective_subtitle_style}",
                                kind="debug",
                            )
                    except Exception:
                        _job_log(
                            effective_channel, job_id,
                            f"subtitle_emphasis_error part={idx} style={_effective_subtitle_style} "
                            f"market={_mv_market} — emphasis pass skipped, render continues",
                            kind="warning",
                        )

                # UP16: Smart CTA ending — optional subtitle end card.
                # Default OFF. Creator must explicitly enable via cta_enabled.
                # Appended AFTER emphasis (CTA text is not formatted) and BEFORE ASS conversion.
                _cta_enabled = bool(getattr(payload, "cta_enabled", False))
                if _cta_enabled and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
                    try:
                        _cta_type    = str(getattr(payload, "cta_type", "auto") or "auto").strip().lower()
                        _ct_hint     = str(seg.get("content_type_hint") or "vlog")
                        _cta_vt      = str(seg.get("variant_type") or "")
                        _cta_text    = _select_cta_text(_ct_hint, _target_platform, _cta_type, _cta_vt)
                        _last_sub_end = float(_srt_meta.get("last_end") or 0)
                        _eff_speed    = float(
                            seg.get("variant_playback_speed")
                            or getattr(payload, "playback_speed", 1.07)
                            or 1.07
                        )
                        _raw_dur  = float(seg.get("duration") or 0)
                        _eff_dur  = max(5.0, _raw_dur / _eff_speed) - 0.5
                        if _cta_text and _append_cta_block_to_srt(
                            str(_ass_srt_source), _cta_text, _last_sub_end, _eff_dur
                        ):
                            needs_ass = True
                            seg["cta_applied"] = True
                            seg["cta_text"]    = _cta_text
                            _emit_render_event(
                                channel_code=effective_channel, job_id=job_id,
                                event="cta_appended", level="INFO",
                                message=f"CTA appended: part {idx} text={_cta_text!r}",
                                step="render.cta",
                                context={
                                    "part_no":        idx,
                                    "cta_text":       _cta_text,
                                    "cta_type":       _cta_type,
                                    "content_type":   _ct_hint,
                                    "target_platform": _target_platform,
                                    "last_sub_end":   _last_sub_end,
                                },
                            )
                            _job_log(
                                effective_channel, job_id,
                                f"cta_appended part_no={idx} text={_cta_text!r} "
                                f"type={_cta_type} platform={_target_platform} ct={_ct_hint}",
                            )
                    except Exception as _cta_exc:
                        logger.warning("cta_append_failed part=%d: %s", idx, _cta_exc)

                if needs_ass:
                    _play_res_y = _aspect_play_res_y(payload.aspect_ratio)
                    _margin_v = getattr(payload, "sub_margin_v", 180)
                    # Part F: light subtitle safety for face-forward content without motion reframe.
                    # When motion_aware_crop=True the crop system already enforces subtitle_safe_bottom_ratio.
                    # When disabled, interview/commentary faces can reach the subtitle zone — add clearance.
                    if not payload.motion_aware_crop and seg.get("content_type_hint") in ("interview", "commentary"):
                        _margin_v += 40
                    _t_sub = time.perf_counter()
                    if _effective_subtitle_style == "pro_karaoke":
                        from app.services.subtitle_engine import _hex_to_ass
                        srt_to_ass_karaoke(
                            str(_ass_srt_source), str(ass_part),
                            scale_y=payload.frame_scale_y,
                            font_size=getattr(payload, "sub_font_size", 46),
                            font_name=getattr(payload, "sub_font", "Bungee"),
                            margin_v=_margin_v,
                            play_res_y=_play_res_y,
                            base_color=_hex_to_ass(getattr(payload, "sub_color", "#FFFFFF")),
                            highlight_color=_hex_to_ass(getattr(payload, "sub_highlight", "#FFFF00")),
                            outline_size=getattr(payload, "sub_outline", 3),
                            x_percent=getattr(payload, "sub_x_percent", 50.0),
                        )
                    else:
                        srt_to_ass_bounce(
                            str(_ass_srt_source),
                            str(ass_part),
                            subtitle_style=_effective_subtitle_style,
                            scale_y=payload.frame_scale_y,
                            highlight_per_word=payload.highlight_per_word,
                            font_name=getattr(payload, "sub_font", "Bungee"),
                            margin_v=_margin_v,
                            play_res_y=_play_res_y,
                            x_percent=getattr(payload, "sub_x_percent", 50.0),
                            font_size=getattr(payload, "sub_font_size", 0),
                        )
                    _subtitle_ass_ms = int((time.perf_counter() - _t_sub) * 1000)
                    logger.info(
                        "subtitle_ass_ms=%d part=%d style=%s content_type=%s",
                        _subtitle_ass_ms, idx, _effective_subtitle_style,
                        seg.get("content_type_hint", ""),
                    )
                    # Debug: per-part subtitle file chain — detect identical SRT or wrong timestamps
                    _dbg_first_line = ""
                    _dbg_first_ts: float = -1.0
                    try:
                        _dbg_blocks = parse_srt_blocks(str(_ass_srt_source))
                        if _dbg_blocks:
                            _dbg_first_line = _dbg_blocks[0]["text"][:80]
                            _dbg_first_ts = round(_dbg_blocks[0]["start"], 3)
                    except Exception:
                        pass
                    # Compute source-time offset for the first subtitle to detect rebase drift
                    _dbg_source_offset = round(_effective_start + _dbg_first_ts - seg["start"], 3) if _dbg_first_ts >= 0 else None
                    _job_log(
                        effective_channel, job_id,
                        f"subtitle_file_chain part={idx} "
                        f"srt={srt_part.name} srt_size={srt_part.stat().st_size if srt_part.exists() else 0} "
                        f"ass={ass_part.name} ass_size={ass_part.stat().st_size if ass_part.exists() else 0} "
                        f"source_fresh={_srt_source_is_fresh} needs_srt={needs_srt} needs_ass={needs_ass} "
                        f"first_ts={_dbg_first_ts}s first_line={_dbg_first_line!r} "
                        f"effective_start={_effective_start:.3f}s rebase_origin={seg['start']:.3f}s "
                        f"source_offset={_dbg_source_offset}s",
                        kind="debug",
                    )
                    _job_log(
                        effective_channel, job_id,
                        f"Part {idx} subtitle: style={_effective_subtitle_style} "
                        f"(payload={payload.subtitle_style or 'auto'}) "
                        f"font_size={getattr(payload, 'sub_font_size', 0)} "
                        f"margin_v={_margin_v} x_pct={getattr(payload, 'sub_x_percent', 50.0):.1f} "
                        f"play_res_y={_play_res_y} aspect={payload.aspect_ratio}",
                        kind="info",
                    )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="subtitle_style_applied",
                        level="INFO",
                        message=f"Subtitle style applied for part {idx}: {_effective_subtitle_style}",
                        step="render.subtitle",
                        context={
                            "part_no": idx,
                            "subtitle_style": _effective_subtitle_style,
                            "subtitle_style_source": "auto" if not _raw_sub_style else "explicit",
                            "content_type_hint": seg.get("content_type_hint", ""),
                            "font_size": getattr(payload, "sub_font_size", 0),
                            "margin_v": _margin_v,
                            "play_res_y": _play_res_y,
                            "aspect_ratio": payload.aspect_ratio,
                        },
                    )
                    _part_manifest.ass_path = str(ass_part)
                    write_manifest(work_dir, _part_manifest)
            else:
                _job_log(effective_channel, job_id, f"Part {idx} subtitle disabled", kind="debug")

            # ── Hook overlay: build per-part text_layers with optional opening banner ──
            # Operates on a copy so the global normalized_text_layers is never mutated.
            # Two variants are built simultaneously:
            #   _part_text_layers         — legacy path (hook end_time = 1.5 × speed, pre-setpts)
            #   _part_text_layers_overlay — overlay path (hook end_time = 1.5 output seconds)
            _hook_overlay_applied_for_part = False
            _part_text_layers = list(normalized_text_layers)
            _part_text_layers_overlay = list(normalized_text_layers)
            if _hook_overlay_enabled and len(_part_text_layers) < MAX_TEXT_LAYERS:
                _hook_srt_path = str(srt_part) if srt_part.exists() and srt_part.stat().st_size > 0 else None
                _hook_text, _hook_source = resolve_hook_overlay_text(
                    _hook_applied_text if _hook_applied_text else None,
                    _hook_srt_path,
                )
                if _hook_text:
                    _hook_overlay_applied_for_part = True
                    # Legacy path: end_time is pre-setpts source-clip seconds; multiply by speed
                    # so the overlay shows for ~1.5 s of perceived output time at any playback rate.
                    _hook_spd = max(0.5, min(1.5, float(payload.playback_speed or 1.07)))
                    _hook_end_t = round(min(2.5, 1.5 * _hook_spd), 3)
                    _part_text_layers = [
                        {
                            "id": f"hook_overlay_{idx}",
                            "text": _hook_text,
                            "font_family": "Bungee",
                            "font_size": 52,
                            "color": "#FFFFFF",
                            "position": "top-center",
                            "x_percent": 50.0,
                            "y_percent": 26.0,
                            "alignment": "center",
                            "bold": False,
                            "outline": {"enabled": True, "thickness": 4},
                            "shadow": {"enabled": False, "offset_x": 0, "offset_y": 0},
                            "background": {"enabled": True, "color": "#000000CC", "padding": 18},
                            "start_time": 0.0,
                            "end_time": _hook_end_t,
                            "order": -1,
                        }
                    ] + _part_text_layers
                    # Overlay path: base_clip.mp4 PTS is already output-timeline, so end_time
                    # is 1.5 output seconds directly — no speed multiplication needed.
                    _part_text_layers_overlay = [
                        {
                            "id": f"hook_overlay_{idx}",
                            "text": _hook_text,
                            "font_family": "Bungee",
                            "font_size": 52,
                            "color": "#FFFFFF",
                            "position": "top-center",
                            "x_percent": 50.0,
                            "y_percent": 26.0,
                            "alignment": "center",
                            "bold": False,
                            "outline": {"enabled": True, "thickness": 4},
                            "shadow": {"enabled": False, "offset_x": 0, "offset_y": 0},
                            "background": {"enabled": True, "color": "#000000CC", "padding": 18},
                            "start_time": 0.0,
                            "end_time": 1.5,
                            "order": -1,
                        }
                    ] + _part_text_layers_overlay
                    logger.info(
                        "hook_overlay_selected part=%d text=%r source=%s end_t=%.3f",
                        idx, _hook_text, _hook_source, _hook_end_t,
                    )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="hook_overlay_applied",
                        level="INFO",
                        message=f"Hook overlay applied for part {idx}: {_hook_text!r}",
                        step="render.hook_overlay",
                        context={
                            "part_no": idx,
                            "hook_text": _hook_text,
                            "source": _hook_source,
                            "end_time": _hook_end_t,
                            "hook_overlay_duration": _hook_end_t,
                        },
                    )
                    _job_log(effective_channel, job_id,
                        f"hook_overlay_applied part={idx} text={_hook_text!r} source={_hook_source} "
                        f"end_t={_hook_end_t:.3f}s")
                else:
                    logger.info("hook_overlay_skipped_reason part=%d reason=%s", idx, _hook_source)
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="hook_overlay_skipped",
                        level="INFO",
                        message=f"Hook overlay skipped for part {idx}: {_hook_source}",
                        step="render.hook_overlay",
                        context={"part_no": idx, "reason": _hook_source},
                    )

            overlay_title = (payload.title_overlay_text or "").strip() or source["title"]
            upsert_job_part(job_id, idx, part_name, JobPartStage.RENDERING, 70, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Rendering final video")

            # Visual finish params (QUALITY-UP11)
            _vf_ct = seg.get("content_type_hint", "vlog")
            _vf_crf_delta = _crf_delta_for_content_type(_vf_ct)
            _part_video_crf = max(11, min(28, tuned["video_crf"] + _vf_crf_delta))
            _vf_bitrate_profile = (
                "high" if _vf_ct == "montage" else
                "low" if _vf_ct in ("interview", "tutorial") else "standard"
            )
            _vf_subtitle_bump = not payload.motion_aware_crop and _vf_ct in ("interview", "commentary")
            logger.info(
                "visual_finish_applied part=%d content_type=%s crf=%d(delta=%+d) "
                "bitrate_profile=%s subtitle_safety_bump=%s",
                idx, _vf_ct, _part_video_crf, _vf_crf_delta,
                _vf_bitrate_profile, _vf_subtitle_bump,
            )

            # Start a background timer that writes linear progress estimates
            # (70–99%) every _PROGRESS_TICK_SEC seconds while FFmpeg runs.
            # Stopped in `finally` before the authoritative 100% write.
            _encode_stop = threading.Event()
            _encode_timer = threading.Thread(
                target=_render_progress_timer,
                args=(
                    _encode_stop, job_id, idx, part_name, seg,
                    str(final_part),
                    time.monotonic(),
                    max(float(seg.get("duration") or 0), 1.0),
                    effective_channel,
                ),
                daemon=True,
                name=f"progress-timer-{job_id[:8]}-p{idx}",
            )
            _encode_timer.start()
            _t_encode = time.perf_counter()
            _t_render = time.perf_counter()
            # UP28.1: motion path cache key — stable across rerenders of same source+clip range
            _motion_ck = None
            _motion_crop_fallback: list = []  # P1-02: signal from render_part_smart when crop falls back
            if payload.motion_aware_crop and _src_stat_for_motion is not None:
                try:
                    _motion_ck = _render_cache_key(
                        str(source_path),
                        _src_stat_for_motion.st_mtime,
                        _src_stat_for_motion.st_size,
                        round(_effective_start, 3),
                        round(float(seg["end"]), 3),
                        str(payload.aspect_ratio),
                        float(payload.frame_scale_x),
                        float(payload.frame_scale_y),
                        str(getattr(payload, "reframe_mode", "subject")),
                        str(seg.get("content_type_hint", "vlog")),
                    )
                except Exception:
                    _motion_ck = None
            # When FEATURE_OVERLAY_AFTER_BASE_CLIP is set without FEATURE_BASE_CLIP_FIRST,
            # the overlay has no base clip to work with — warn once per part and fall back.
            if _FEATURE_OVERLAY_AFTER_BASE_CLIP and not _FEATURE_BASE_CLIP_FIRST:
                logger.warning(
                    "overlay_flag_ignored job_id=%s part=%d: "
                    "FEATURE_OVERLAY_AFTER_BASE_CLIP=1 requires FEATURE_BASE_CLIP_FIRST=1 "
                    "— using render_part_smart() for final output",
                    job_id, idx,
                )

            # When FEATURE_BASE_CLIP_FIRST is enabled, render a no-overlay base clip
            # as a parallel artifact.  The base clip feeds the overlay composite when
            # FEATURE_OVERLAY_AFTER_BASE_CLIP is also enabled; otherwise it is a
            # parallel validation artifact only and render_part_smart() produces the output.
            if _FEATURE_BASE_CLIP_FIRST:
                _base_clip_out = work_dir / f"part_{idx}" / "base_clip.mp4"
                try:
                    _base_clip_out.parent.mkdir(parents=True, exist_ok=True)
                    _bc_bgm_path = str(getattr(payload, "reup_bgm_path", None) or "").strip()
                    _bc_bgm_ok = (
                        getattr(payload, "reup_bgm_enable", False)
                        and _bc_bgm_path
                        and Path(_bc_bgm_path).is_file()
                    )
                    _bc_meta = render_base_clip(
                        input_path=str(raw_part),
                        output_path=str(_base_clip_out),
                        timeline=_part_timeline,
                        aspect_ratio=payload.aspect_ratio,
                        scale_x=payload.frame_scale_x,
                        scale_y=payload.frame_scale_y,
                        motion_aware_crop=payload.motion_aware_crop,
                        reframe_mode=getattr(payload, "reframe_mode", "subject"),
                        effect_preset=payload.effect_preset,
                        transition_sec=tuned["transition_sec"],
                        video_codec=payload.video_codec,
                        video_crf=_part_video_crf,
                        video_preset=tuned["video_preset"],
                        audio_bitrate=payload.audio_bitrate,
                        retry_count=retry_count,
                        encoder_mode=payload.encoder_mode,
                        output_fps=payload.output_fps,
                        loudnorm_enabled=getattr(payload, "loudnorm_enabled", False),
                        ffmpeg_threads=_ffmpeg_threads,
                        content_type=seg.get("content_type_hint", "vlog"),
                        _motion_cache_key=_motion_ck,
                        reup_bgm_enable=getattr(payload, "reup_bgm_enable", False),
                        reup_bgm_path=getattr(payload, "reup_bgm_path", None),
                        reup_bgm_gain=getattr(payload, "reup_bgm_gain", 0.18),
                        # Phase 5.7: pass AI visual intensity hint to renderer.
                        # Renderer owns mapping; None when AI disabled/invalid/user override.
                        visual_intensity_hint=_vis_intensity_hint,
                    )
                    _part_manifest.base_clip_path = str(_base_clip_out)
                    _part_manifest.base_clip_duration = _bc_meta.get("duration")
                    _part_manifest.base_clip_fps = _bc_meta.get("fps")
                    _part_manifest.base_clip_width = _bc_meta.get("width")
                    _part_manifest.base_clip_height = _bc_meta.get("height")
                    _part_manifest.base_clip_has_audio = _bc_meta.get("has_audio")
                    _part_manifest.base_clip_created_at = _bc_meta.get("created_at")
                    _part_manifest.base_clip_bgm_applied = bool(_bc_bgm_ok)
                    write_manifest(work_dir, _part_manifest)
                    logger.info(
                        "base_clip_rendered part=%d path=%s duration=%.3fs",
                        idx, _base_clip_out, _bc_meta.get("duration", 0.0),
                    )
                except Exception as _bc_err:
                    logger.warning(
                        "base_clip_render_failed part=%d err=%s — render_part_smart continues",
                        idx, _bc_err,
                    )

            # Overlay composite: burn output-timeline subtitles onto the base clip.
            # Only activates when both feature flags are ON and base clip was produced.
            _overlay_composite_succeeded = False
            if (
                _FEATURE_BASE_CLIP_FIRST
                and _FEATURE_OVERLAY_AFTER_BASE_CLIP
                and _part_manifest.base_clip_path is not None
            ):
                _overlay_dir = Path(_part_manifest.base_clip_path).parent
                _overlay_srt = _overlay_dir / "subtitle_output_timeline.srt"
                _overlay_ass = _overlay_dir / "subtitle_output_timeline.ass"
                try:
                    _overlay_ass_path: "str | None" = None
                    if part_subtitle_enabled and full_srt_available and full_srt.exists():
                        _ot_meta = slice_srt_to_output_timeline(
                            source_srt_path=str(full_srt),
                            output_srt_path=str(_overlay_srt),
                            source_start=_part_timeline.source_start,
                            source_end=_part_timeline.source_end,
                            timeline=_part_timeline,
                        )
                        if _ot_meta.get("subtitle_count", 0) > 0:
                            _overlay_play_res_y = _aspect_play_res_y(payload.aspect_ratio)
                            _overlay_margin_v = getattr(payload, "sub_margin_v", 180)
                            if (
                                not payload.motion_aware_crop
                                and seg.get("content_type_hint") in ("interview", "commentary")
                            ):
                                _overlay_margin_v += 40
                            srt_to_ass_bounce(
                                str(_overlay_srt),
                                str(_overlay_ass),
                                subtitle_style=_effective_subtitle_style,
                                scale_y=payload.frame_scale_y,
                                font_name=getattr(payload, "sub_font", "Bungee"),
                                font_size=getattr(payload, "sub_font_size", 0),
                                margin_v=_overlay_margin_v,
                                play_res_y=_overlay_play_res_y,
                                play_res_x=1080,
                                x_percent=getattr(payload, "sub_x_percent", 50.0),
                                highlight_per_word=getattr(payload, "highlight_per_word", True),
                            )
                            _overlay_ass_path = str(_overlay_ass)
                            _part_manifest.overlay_srt_path = str(_overlay_srt)
                            _part_manifest.overlay_ass_path = str(_overlay_ass)

                    _oc_meta = composite_overlays_on_base_clip(
                        base_clip_path=_part_manifest.base_clip_path,
                        output_path=str(final_part),
                        timeline=_part_timeline,
                        subtitle_ass=_overlay_ass_path,
                        text_layers=_part_text_layers_overlay if _part_text_layers_overlay else None,
                        title_text=overlay_title if payload.add_title_overlay else None,
                        video_codec=payload.video_codec,
                        video_crf=_part_video_crf,
                        video_preset=tuned["video_preset"],
                        audio_bitrate=payload.audio_bitrate,
                        retry_count=retry_count,
                        encoder_mode=payload.encoder_mode,
                        ffmpeg_threads=_ffmpeg_threads,
                    )
                    _part_manifest.overlay_rendered_path = str(final_part)
                    _part_manifest.rendered_path = str(final_part)
                    _part_manifest.overlay_text_layers_applied = len(_part_text_layers_overlay or [])
                    write_manifest(work_dir, _part_manifest)
                    logger.info(
                        "overlay_composite_succeeded part=%d path=%s subtitle=%s",
                        idx, final_part, _overlay_ass_path is not None,
                    )
                    _overlay_composite_succeeded = True
                except Exception as _oc_err:
                    logger.warning(
                        "overlay_composite_failed job_id=%s part=%d base_clip=%s err=%s "
                        "— falling back to render_part_smart",
                        job_id, idx, _part_manifest.base_clip_path, _oc_err,
                    )

            try:
                if not _overlay_composite_succeeded:
                    render_part_smart(
                    str(raw_part), str(final_part), str(ass_part) if part_subtitle_enabled else None, overlay_title if payload.add_title_overlay else "",
                    payload.aspect_ratio, payload.frame_scale_x, payload.frame_scale_y,
                    payload.motion_aware_crop,
                    reframe_mode=payload.reframe_mode,
                    add_subtitle=part_subtitle_enabled,
                    add_title_overlay=payload.add_title_overlay,
                    effect_preset=payload.effect_preset,
                    transition_sec=tuned["transition_sec"],
                    video_codec=payload.video_codec,
                    video_crf=_part_video_crf,
                    video_preset=tuned["video_preset"],
                    audio_bitrate=payload.audio_bitrate,
                    retry_count=retry_count,
                    encoder_mode=payload.encoder_mode,
                    output_fps=payload.output_fps,
                    reup_mode=payload.reup_mode,
                    reup_overlay_enable=payload.reup_overlay_enable,
                    reup_overlay_opacity=payload.reup_overlay_opacity,
                    reup_bgm_enable=payload.reup_bgm_enable,
                    reup_bgm_path=payload.reup_bgm_path,
                    reup_bgm_gain=payload.reup_bgm_gain,
                    playback_speed=float(
                        seg.get("variant_playback_speed")
                        or max(0.5, min(1.5, float(payload.playback_speed or 1.07)
                               + _PLATFORM_PROFILES.get(_target_platform, {}).get("speed_delta", 0.0)))
                    ),
                    text_layers=_part_text_layers,
                    loudnorm_enabled=getattr(payload, "loudnorm_enabled", False),
                    ffmpeg_threads=_ffmpeg_threads,
                    content_type=seg.get("content_type_hint", "vlog"),
                    _motion_cache_key=_motion_ck,
                    _fallback_flag=_motion_crop_fallback,
                    # Phase 5.7: pass AI visual intensity hint to renderer.
                    # Renderer owns mapping; None when AI disabled/invalid/user override.
                    visual_intensity_hint=_vis_intensity_hint,
                )
            finally:
                _encode_stop.set()
                _encode_timer.join(timeout=5.0)
            _render_ms = int((time.perf_counter() - _t_render) * 1000)
            logger.info("render_part_ms=%d part=%d codec=%s crop=%s",
                        _render_ms, idx, payload.video_codec, payload.motion_aware_crop)
            _part_manifest.rendered_path = str(final_part)
            write_manifest(work_dir, _part_manifest)
            if _motion_ck:
                _job_log(effective_channel, job_id, f"rerender_fast_path part={idx} motion_cache_key={_motion_ck[:8]} render_ms={_render_ms}")
            if _motion_crop_fallback:
                # P1-02: UP24 recovery hook — motion crop fell back to standard crop.
                # Surface to creator via existing Recovered chip / recovery_notes system.
                _recovery_notes.append("Motion crop unavailable — used standard crop")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="recovery_success",
                    level="WARNING",
                    message=f"Recovery: motion crop failed for part {idx}, standard crop used",
                    step="render.motion_crop",
                    context={
                        "recovery_strategy": "fallback_standard_crop",
                        "part_no": idx,
                        "reason": _motion_crop_fallback[0],
                    },
                )
            # Part G: visual finish observability — auditable per-part quality metadata
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="visual_finish_applied",
                level="INFO",
                message=f"Visual finish: part {idx} content_type={_vf_ct} crf={_part_video_crf}({_vf_crf_delta:+d}) bitrate={_vf_bitrate_profile}",
                step="render.visual_finish",
                context={
                    "part_no": idx,
                    "content_type": _vf_ct,
                    "visual_finish_score": min(100, max(0, 50 + (_part_video_crf - tuned["video_crf"]) * -5)),
                    "clarity_level": "enhanced" if _vf_ct in ("tutorial", "interview") else (
                        "reduced" if _vf_ct == "montage" else "standard"
                    ),
                    "compression_risk": "low" if _vf_ct in ("interview", "tutorial") else (
                        "high" if _vf_ct == "montage" else "medium"
                    ),
                    "subtitle_visibility": "adjusted" if _vf_subtitle_bump else "standard",
                    "crf_applied": _part_video_crf,
                    "crf_delta": _vf_crf_delta,
                    "bitrate_profile": _vf_bitrate_profile,
                },
            )
            _part_subtitle_voice_path = None
            if (
                getattr(payload, "voice_enabled", False)
                and getattr(payload, "voice_source", "manual") == "subtitle"
                and voice_audio_path is None
            ):
                _part_srt = srt_part if srt_part.exists() and srt_part.stat().st_size > 0 else None
                _part_srt_inmem_text: str | None = None
                if _part_srt is None and full_srt_available:
                    try:
                        _part_srt_inmem_text = slice_srt_to_text(str(full_srt), seg["start"], seg["end"])
                        _part_srt = full_srt  # truthy sentinel: text loaded in-memory
                        _job_log(effective_channel, job_id, f"voice.srt_in_memory part_no={idx} (no temp file written)", kind="debug")
                    except Exception:
                        _part_srt = None
                if _part_srt:
                    _part_narration_text = _part_srt_inmem_text if _part_srt_inmem_text is not None else extract_text_from_srt(str(_part_srt))
                    if _part_narration_text.strip():
                        _voice_part_tts_attempts.append(idx)
                        _part_mp3 = str(TEMP_DIR / job_id / "voice" / f"part_{idx:03d}.mp3")
                        if cancel_registry.is_cancelled(job_id):
                            raise cancel_registry.JobCancelledError()
                        try:
                            _job_log(effective_channel, job_id, f"Generating AI narration for part {idx}/{total_parts} from subtitle", kind="debug")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_tts_started",
                                level="INFO",
                                message=f"Generating AI voice from subtitle (part {idx})",
                                step="voice.tts",
                                context={"part_no": idx, "language": payload.voice_language, "source": "subtitle"},
                            )
                            _part_subtitle_voice_path = generate_narration_audio(
                                text=_part_narration_text,
                                language=payload.voice_language,
                                gender=payload.voice_gender,
                                rate=payload.voice_rate,
                                job_id=job_id,
                                voice_id=getattr(payload, "voice_id", None),
                                output_path=_part_mp3,
                                content_type=str(seg.get("content_type_hint") or "vlog"),
                                tts_engine=getattr(payload, "tts_engine", "edge"),
                            )
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_tts_completed",
                                level="INFO",
                                message=f"AI voice from subtitle generated (part {idx})",
                                step="voice.tts",
                                context={"part_no": idx, "audio_path": _part_subtitle_voice_path, "voice_text_length": len(_part_narration_text)},
                            )
                            _part_subtitle_voice_path = _maybe_cleanup_narration_audio(
                                str(_part_subtitle_voice_path),
                                payload,
                                effective_channel=effective_channel,
                                job_id=job_id,
                                part_no=idx,
                                source="subtitle",
                            )
                        except Exception as _part_tts_exc:
                            _part_subtitle_voice_path = None
                            _job_log(effective_channel, job_id, f"voice_part_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                            _job_log(effective_channel, job_id, f"Narration generation failed for part {idx}. Continuing without narration.", kind="warning")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_failed",
                                level="ERROR",
                                message=f"AI voice (subtitle, part {idx}) failed: {_part_tts_exc}",
                                step="voice.tts",
                                exception=_part_tts_exc,
                                traceback_text=traceback.format_exc(),
                                context={"part_no": idx, "error_code": "VOICE001"},
                            )
                    else:
                        _job_log(effective_channel, job_id, f"VOICE_SUBTITLE_EMPTY: part {idx} subtitle text empty; narration skipped", kind="warning")
                else:
                    _job_log(effective_channel, job_id, f"voice_subtitle_source_missing part_no={idx} source=subtitle; narration skipped", kind="warning")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="voice_subtitle_source_missing",
                        level="WARNING",
                        message=f"Subtitle voice source missing for part {idx}; narration skipped",
                        step="voice.tts",
                        context={"part_no": idx, "source": "subtitle"},
                    )
            elif (
                getattr(payload, "voice_enabled", False)
                and getattr(payload, "voice_source", "manual") == "translated_subtitle"
                and voice_audio_path is None
            ):
                _tgt_lang_voice = getattr(payload, "subtitle_target_language", "en")
                if not payload.voice_language.lower().startswith(_tgt_lang_voice.lower()):
                    _job_log(effective_channel, job_id, f"VOICE_LANGUAGE_TARGET_MISMATCH: voice_language={payload.voice_language} target={_tgt_lang_voice}", kind="warning")
                _voice_srt = translated_srt_part if translated_srt_part.exists() and translated_srt_part.stat().st_size > 0 else None
                if _voice_srt is None:
                    _job_log(effective_channel, job_id, f"VOICE_TRANSLATED_SUBTITLE_MISSING: part {idx} translated SRT not found; falling back to original", kind="warning")
                    _voice_srt = srt_part if srt_part.exists() and srt_part.stat().st_size > 0 else None
                _voice_srt_inmem_text: str | None = None
                if _voice_srt is None and full_srt_available:
                    try:
                        _voice_srt_inmem_text = slice_srt_to_text(str(full_srt), seg["start"], seg["end"])
                        _voice_srt = full_srt  # truthy sentinel: text loaded in-memory
                        _job_log(effective_channel, job_id, f"voice.translated_srt_in_memory part_no={idx} (no temp file written)", kind="debug")
                    except Exception:
                        _voice_srt = None
                if _voice_srt:
                    _part_narration_text = _voice_srt_inmem_text if _voice_srt_inmem_text is not None else extract_text_from_srt(str(_voice_srt))
                    if _part_narration_text.strip():
                        _voice_part_tts_attempts.append(idx)
                        _part_mp3 = str(TEMP_DIR / job_id / "voice" / f"part_{idx:03d}.mp3")
                        try:
                            _job_log(effective_channel, job_id, f"voice_translated_subtitle_tts_started part_no={idx}", kind="debug")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_translated_subtitle_tts_started",
                                level="INFO",
                                message=f"Generating AI voice from translated subtitle (part {idx})",
                                step="voice.tts",
                                context={"part_no": idx, "language": payload.voice_language, "target": _tgt_lang_voice},
                            )
                            _part_subtitle_voice_path = generate_narration_audio(
                                text=_part_narration_text,
                                language=payload.voice_language,
                                gender=payload.voice_gender,
                                rate=payload.voice_rate,
                                job_id=job_id,
                                voice_id=getattr(payload, "voice_id", None),
                                output_path=_part_mp3,
                                content_type=str(seg.get("content_type_hint") or "vlog"),
                                tts_engine=getattr(payload, "tts_engine", "edge"),
                            )
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_translated_subtitle_tts_completed",
                                level="INFO",
                                message=f"AI voice from translated subtitle generated (part {idx})",
                                step="voice.tts",
                                context={"part_no": idx, "audio_path": _part_subtitle_voice_path, "voice_text_length": len(_part_narration_text)},
                            )
                            _part_subtitle_voice_path = _maybe_cleanup_narration_audio(
                                str(_part_subtitle_voice_path),
                                payload,
                                effective_channel=effective_channel,
                                job_id=job_id,
                                part_no=idx,
                                source="translated_subtitle",
                            )
                        except Exception as _part_tts_exc:
                            _part_subtitle_voice_path = None
                            _job_log(effective_channel, job_id, f"voice_translated_subtitle_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                            _job_log(effective_channel, job_id, f"Narration generation failed for part {idx}. Continuing without narration.", kind="warning")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_failed",
                                level="ERROR",
                                message=f"AI voice (translated subtitle, part {idx}) failed: {_part_tts_exc}",
                                step="voice.tts",
                                exception=_part_tts_exc,
                                traceback_text=traceback.format_exc(),
                                context={"part_no": idx, "error_code": "VOICE001"},
                            )
                    else:
                        _job_log(effective_channel, job_id, f"VOICE_SUBTITLE_EMPTY: part {idx} translated subtitle text empty; narration skipped", kind="warning")
                else:
                    _job_log(effective_channel, job_id, f"voice_subtitle_source_missing part_no={idx} source=translated_subtitle; narration skipped", kind="warning")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="voice_subtitle_source_missing",
                        level="WARNING",
                        message=f"Translated subtitle voice source missing for part {idx}; narration skipped",
                        step="voice.tts",
                        context={"part_no": idx, "source": "translated_subtitle"},
                    )
            _final_voice_path = voice_audio_path or _part_subtitle_voice_path
            if _final_voice_path:
                _part_manifest.narration_path = str(_final_voice_path)
                write_manifest(work_dir, _part_manifest)
                mixed_part = final_part.with_name(final_part.stem + ".voice_tmp.mp4")
                try:
                    _job_log(effective_channel, job_id, f"Mixing AI narration into part {idx}/{total_parts}", kind="debug")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="voice_mix_started",
                        level="INFO",
                        message="Mixing narration audio",
                        step="voice.mix",
                        context={"part_no": idx, "mix_mode": payload.voice_mix_mode},
                    )
                    mix_narration_audio(
                        video_path=str(final_part),
                        narration_audio_path=str(_final_voice_path),
                        mix_mode=payload.voice_mix_mode,
                        output_path=str(mixed_part),
                        playback_speed=_get_effective_playback_speed(payload, _target_platform),
                    )
                    os.replace(str(mixed_part), str(final_part))
                    _job_log(effective_channel, job_id, f"voice_mix_completed part_no={idx}/{total_parts}")
                    _voice_mix_ok.append(idx)
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="voice_mix_completed",
                        level="INFO",
                        message="Voice narration completed",
                        step="voice.mix",
                        context={"part_no": idx, "output_file": str(final_part)},
                    )
                except Exception as mix_exc:
                    _safe_unlink(mixed_part)
                    _job_log(effective_channel, job_id, f"voice_mix_failed part_no={idx}: {mix_exc}", kind="error")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="voice_failed",
                        level="ERROR",
                        message=f"voice_mix_failed part_no={idx}: {mix_exc}",
                        step="voice.mix",
                        context={"part_no": idx, "output_file": str(final_part), "error_code": "VOICE001"},
                        exception=mix_exc,
                        traceback_text=traceback.format_exc(),
                    )

            # P4-4: Micro pacing — compress mid-clip silences (all output clips)
            _micro_pacing_applied = False
            _micro_pacing_trim_sec = 0.0
            if cancel_registry.is_cancelled(job_id):
                raise cancel_registry.JobCancelledError()
            if final_part.exists() and final_part.stat().st_size > 0:
                _paced_part = work_dir / f"{source['slug']}_part_{idx:03d}_paced.mp4"
                _t_mp = time.perf_counter()
                try:
                    _seg_content_type = seg.get("content_type_hint", "vlog")
                    _pacing = apply_micro_pacing(
                        str(final_part), str(_paced_part),
                        content_type=_seg_content_type,
                    )
                    _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
                    if _pacing["applied"] and _paced_part.exists() and _paced_part.stat().st_size > 0:
                        os.replace(str(_paced_part), str(final_part))
                        _micro_pacing_applied = True
                        _micro_pacing_trim_sec = max(0.0, float(_pacing.get("total_trim_ms") or 0) / 1000.0)
                        _job_log(
                            effective_channel, job_id,
                            f"Part {idx} micro pacing: {_pacing['segments_trimmed']} segments, "
                            f"{_pacing['total_trim_ms']}ms trimmed, "
                            f"content_type={_seg_content_type}",
                        )
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="micro_pacing_applied",
                            level="INFO",
                            message=(
                                f"Micro pacing applied: {_pacing['segments_trimmed']} segments, "
                                f"{_pacing['total_trim_ms']}ms removed"
                            ),
                            step="render.micro_pacing",
                            context={
                                "part_no": idx,
                                "segments_trimmed": _pacing["segments_trimmed"],
                                "total_trim_ms": _pacing["total_trim_ms"],
                                "method": _pacing["method"],
                                "content_type": _seg_content_type,
                            },
                        )
                    else:
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="micro_pacing_skipped",
                            level="INFO",
                            message="Micro pacing skipped: no qualifying silence segments",
                            step="render.micro_pacing",
                            context={"part_no": idx},
                        )
                except subprocess.TimeoutExpired:
                    _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
                    _job_log(
                        effective_channel, job_id,
                        f"micro_pacing_timeout part_no={idx} elapsed_ms={_micro_pacing_ms} — skipped, original kept",
                        kind="warning",
                    )
                except Exception as _pace_exc:
                    _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
                    _job_log(
                        effective_channel, job_id,
                        f"micro_pacing_failed part_no={idx}: {_pace_exc}",
                        kind="warning",
                    )
                finally:
                    _safe_unlink(_paced_part)
                logger.info("micro_pacing_ms=%d part=%d applied=%s", _micro_pacing_ms, idx, _micro_pacing_applied)

            # P4 combined opening optimization summary — emitted for every output part
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="p4_output_opening_optimized",
                level="INFO",
                message=(
                    f"P4 opening: part {idx} trim={_trim_offset:.3f}s "
                    f"hook={_hook_subtitle_formatted} pacing={_micro_pacing_applied}"
                ),
                step="render.p4_opening",
                context={
                    "part_no": idx,
                    "original_start": seg["start"],
                    "effective_start": _effective_start,
                    "trim_offset": _trim_offset,
                    "original_duration": seg["end"] - seg["start"],
                    "effective_duration": seg["end"] - _effective_start,
                    "subtitle_count": _srt_count,
                    "hook_subtitle_formatted": _hook_subtitle_formatted,
                    "micro_pacing_applied": _micro_pacing_applied,
                    "micro_pacing_trim_sec": _micro_pacing_trim_sec,
                },
            )

            _encode_ms = int((time.perf_counter() - _t_encode) * 1000)
            _total_part_ms = int((time.perf_counter() - _t_part_start) * 1000)
            _effective_duration = max(0.0, float(seg["end"]) - float(_effective_start))
            _render_speed = _get_effective_playback_speed(payload, _target_platform)
            _remotion_intro_sec = _maybe_prepend_remotion_hook_intro(
                final_part,
                payload,
                effective_channel=effective_channel,
                job_id=job_id,
                part_no=idx,
                content_type=str(seg.get("content_type_hint") or "vlog"),
                hook_text=_hook_applied_text or None,
                source_title=str(source.get("title") or ""),
            )
            # UP27: Creator asset application — safe-skip on any failure
            _maybe_prepend_asset_intro(final_part, payload,
                effective_channel=effective_channel, job_id=job_id, part_no=idx)
            _maybe_append_asset_outro(final_part, payload,
                effective_channel=effective_channel, job_id=job_id, part_no=idx)
            _maybe_apply_asset_logo(final_part, payload,
                effective_channel=effective_channel, job_id=job_id, part_no=idx)
            _expected_final_duration = max(
                0.0,
                (_effective_duration / _render_speed) - _micro_pacing_trim_sec + _remotion_intro_sec,
            )
            _speed_ratio = round(_expected_final_duration * 1000 / max(_encode_ms, 1), 2)
            _job_log(
                effective_channel, job_id,
                f"playback_speed_resolution part={idx} "
                f"payload_speed={float(payload.playback_speed or 1.0):.4f} "
                f"platform_delta={_PLATFORM_PROFILES.get(_target_platform, {}).get('speed_delta', 0.0):.4f} "
                f"effective_speed={_render_speed:.4f} "
                f"target_platform={_target_platform} "
                f"source_duration={_part_timeline.source_duration:.3f}s "
                f"output_duration={_part_timeline.output_duration:.3f}s "
                f"effective_duration={_effective_duration:.3f}s "
                f"expected_duration={_expected_final_duration:.3f}s "
                f"manifest={_manifest_path(work_dir, idx)}",
                kind="debug",
            )
            logger.info(
                "total_part_render_ms=%d part=%d "
                "cut_ms=%d first_frame_ms=%d subtitle_ass_ms=%d "
                "render_ms=%d pacing_ms=%d quality_ms=%d",
                _total_part_ms, idx,
                _cut_ms, _first_frame_scan_ms, _subtitle_ass_ms,
                _render_ms, _micro_pacing_ms, _quality_validation_ms,
            )
            if normalized_text_layers:
                _job_log(
                    effective_channel,
                    job_id,
                    f"Applied {len(normalized_text_layers)} text layer(s) on part {idx}/{total_parts}",
                    kind="debug",
                )
            _job_log(
                effective_channel, job_id,
                f"Part {idx}/{total_parts} done: encode_ms={_encode_ms} "
                f"expected_final_duration={_expected_final_duration:.2f}s speed_ratio={_speed_ratio}x "
                f"(>1 = faster than realtime)",
                kind="info",
            )

            # ── Market Viral scoring — safe, never breaks render ──────────
            try:
                _mv_text = ""
                if srt_part.exists() and srt_part.stat().st_size > 0:
                    _mv_text = extract_text_from_srt(str(srt_part))
                _mv_dur = float(seg.get("duration") or 0) or None
                _mv_result = _mv_score_part(_mv_text, _mv_dur, _mv_market)
                seg["mv_viral_score"]   = _mv_result.get("viral_score",  0)
                seg["mv_viral_tier"]    = _mv_result.get("viral_tier",   "weak")
                seg["mv_viral_market"]  = _mv_result.get("viral_market", _mv_market)
                seg["mv_viral_reasons"] = _mv_result.get("reasons",      [])
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="market_viral_scored",
                    level="INFO",
                    message=(
                        f"Part {idx} market viral: {seg['mv_viral_score']} "
                        f"{seg['mv_viral_tier']} ({seg['mv_viral_market']})"
                    ),
                    step="render.market_viral",
                    context={
                        "part_no":              idx,
                        "market_viral_score":   seg["mv_viral_score"],
                        "market_viral_tier":    seg["mv_viral_tier"],
                        "market_viral_market":  seg["mv_viral_market"],
                        "market_viral_reasons": seg["mv_viral_reasons"][:2],
                    },
                )
            except Exception:
                pass

            # ── Combined Score computation ─────────────────────────────────
            try:
                _cs_enabled  = bool(getattr(payload, "combined_scoring_enabled", False))
                _cs_adaptive = bool(getattr(payload, "adaptive_scoring_enabled", False))
                _cs_viral    = float(seg.get("viral_score", 0) or 0)
                _cs_mv_raw   = seg.get("mv_viral_score")
                _cs_mv       = float(_cs_mv_raw) if _cs_mv_raw is not None else _cs_viral
                _cs_hook_raw = (seg.get("hook_text_score") or seg.get("hook_timing_score") or
                                seg.get("hook_opening_score") or seg.get("hook_score"))
                _cs_hook     = float(_cs_hook_raw or 0)
                _cs_dur      = float(seg.get("duration") or 0) or None

                _cs_weights = resolve_combined_score_weights(
                    target_market=_mv_market,
                    has_market_score=(_cs_mv_raw is not None),
                    has_hook_score=(_cs_hook_raw is not None and float(_cs_hook_raw) > 0),
                    duration=_cs_dur,
                    adaptive_enabled=_cs_adaptive,
                )
                seg["combined_weights"] = _cs_weights

                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="adaptive_score_weights_resolved",
                    level="INFO",
                    message=f"Part {idx} weights v={_cs_weights['viral_weight']} m={_cs_weights['market_weight']} h={_cs_weights['hook_weight']} reason={_cs_weights['reason']}",
                    step="render.combined_score",
                    context={
                        "part_no":                  idx,
                        "adaptive_scoring_enabled": _cs_adaptive,
                        "target_market":            _mv_market,
                        "duration":                 _cs_dur,
                        "viral_weight":             _cs_weights["viral_weight"],
                        "market_weight":            _cs_weights["market_weight"],
                        "hook_weight":              _cs_weights["hook_weight"],
                        "reason":                   _cs_weights["reason"],
                    },
                )

                _cs_raw = (
                    _cs_viral * _cs_weights["viral_weight"] +
                    _cs_mv    * _cs_weights["market_weight"] +
                    _cs_hook  * _cs_weights["hook_weight"]
                )
                seg["combined_score"] = round(max(0.0, min(100.0, _cs_raw)), 1)
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="combined_score_computed",
                    level="INFO",
                    message=f"Part {idx} combined_score={seg['combined_score']}",
                    step="render.combined_score",
                    context={
                        "part_no":                  idx,
                        "viral_score":              _cs_viral,
                        "market_viral_score":       _cs_mv,
                        "hook_score_component":     _cs_hook,
                        "combined_score":           seg["combined_score"],
                        "combined_scoring_enabled": _cs_enabled,
                        "viral_weight":             _cs_weights["viral_weight"],
                        "market_weight":            _cs_weights["market_weight"],
                        "hook_weight":              _cs_weights["hook_weight"],
                    },
                )
            except Exception:
                pass

            # ── Post-render output validation ─────────────────────────────
            _expect_audio: bool | None = None
            if getattr(payload, "voice_enabled", False):
                _expect_audio = True
            elif (getattr(payload, "reup_bgm_enable", False)
                  and bool(str(getattr(payload, "reup_bgm_path", None) or "").strip())):
                _expect_audio = True
            _qa = _validate_render_output(
                final_part,
                expected_duration=_expected_final_duration if _expected_final_duration > 0 else None,
                expect_audio=_expect_audio,
            )
            _actual_final_duration = float((_qa.get("metadata") or {}).get("duration") or 0.0)
            _job_log(
                effective_channel,
                job_id,
                f"Part {idx} duration validation: expected_final_duration={_expected_final_duration:.3f}s "
                f"actual_final_duration={_actual_final_duration:.3f}s "
                f"effective_start={float(_effective_start):.3f}s segment_end={float(seg['end']):.3f}s "
                f"playback_speed={_render_speed:.4f}",
                kind="debug",
            )
            if not _qa["ok"]:
                _qa_code = str(_qa.get("code") or "RN001")
                _job_log(effective_channel, job_id,
                         f"Part {idx} output_validation_failed: {_qa['error']} | "
                         f"code={_qa_code} output={final_part} meta={_qa['metadata']}", kind="error")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_validation_failed",
                    level="ERROR",
                    message=f"Part {idx} output validation failed: {_qa['error']}",
                    step="render.output.validate",
                    error_code=_qa_code,
                    context={
                        "part_no": idx,
                        "output_file": str(final_part),
                        "validation_code": _qa_code,
                        **_qa["metadata"],
                    },
                )
                raise RuntimeError(f"output_validation_failed[{_qa_code}]: {_qa['error']}")
            if _qa["warnings"]:
                _job_log(effective_channel, job_id,
                         f"Part {idx} output_validation_warning: {'; '.join(_qa['warnings'])} | "
                         f"meta={_qa['metadata']}", kind="warning")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_validation_warning",
                    level="WARNING",
                    message=f"Part {idx} output validation passed with warnings: {'; '.join(_qa['warnings'])}",
                    step="render.output.validate",
                    context={"part_no": idx, "output_file": str(final_part), **_qa["metadata"]},
                )
            else:
                _job_log(effective_channel, job_id,
                         f"Part {idx} output_validation_passed: "
                         f"dur={_qa['metadata']['duration']:.2f}s "
                         f"size={_qa['metadata']['size_bytes']} "
                         f"has_video={_qa['metadata']['has_video']} "
                         f"has_audio={_qa['metadata']['has_audio']}")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_validation_passed",
                    level="INFO",
                    message=f"Part {idx} output validation passed",
                    step="render.output.validate",
                    context={"part_no": idx, "output_file": str(final_part), **_qa["metadata"]},
                )

            # ── Output quality validator: perceptual checks + score penalty ──────
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="output_quality_validation_started",
                level="INFO",
                message=f"Part {idx} quality validation started",
                step="render.output.quality",
                context={"part_no": idx, "output_file": str(final_part)},
            )
            _t_qq = time.perf_counter()
            _qq = _assess_output_quality(
                final_part,
                output_dir,
                expect_subtitle=part_subtitle_enabled,
                subtitle_file=ass_part if part_subtitle_enabled else None,
                expect_hook=_hook_overlay_enabled,
                hook_applied=_hook_overlay_applied_for_part,
            )
            _quality_validation_ms = int((time.perf_counter() - _t_qq) * 1000)
            logger.info("quality_validation_ms=%d part=%d penalty=%d",
                        _quality_validation_ms, idx, int(_qq["score_penalty"]))
            _quality_penalty = int(_qq["score_penalty"])
            seg["quality_penalty"] = _quality_penalty
            if _qq["warnings"] or not _qq["passed"]:
                _qq_level = "ERROR" if not _qq["passed"] else "WARNING"
                _qq_evt = "output_quality_validation_failed" if not _qq["passed"] else "output_quality_validation_warning"
                for _qw in _qq["warnings"]:
                    _job_log(effective_channel, job_id, f"Part {idx} quality_warning: {_qw}", kind="warning")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event=_qq_evt,
                    level=_qq_level,
                    message=f"Part {idx} quality validation: {len(_qq['warnings'])} warning(s)",
                    step="render.output.quality",
                    context={
                        "part_no": idx,
                        "output_file": str(final_part),
                        "warnings": _qq["warnings"],
                        "hard_failures": _qq["hard_failures"],
                        "checks": _qq["checks"],
                        "score_penalty": _quality_penalty,
                    },
                )
            else:
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_quality_validation_passed",
                    level="INFO",
                    message=f"Part {idx} quality validation passed",
                    step="render.output.quality",
                    context={"part_no": idx, "output_file": str(final_part), "checks": _qq["checks"]},
                )
            if _quality_penalty > 0:
                _job_log(
                    effective_channel, job_id,
                    f"Part {idx} quality_score_penalty: -{_quality_penalty} checks={_qq['checks']}",
                    kind="warning",
                )
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_quality_score_penalty_applied",
                    level="WARNING",
                    message=f"Part {idx} quality penalty applied: -{_quality_penalty} points",
                    step="render.output.quality",
                    context={
                        "part_no": idx,
                        "score_penalty": _quality_penalty,
                        "checks": _qq["checks"],
                        "warnings": _qq["warnings"],
                    },
                )
            if _quality_penalty > 20:
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="render.quality_penalty_high",
                    level="WARNING",
                    message=f"Part {idx} quality penalty high: -{_quality_penalty} points",
                    step="render.output.quality",
                    context={
                        "part_no": idx,
                        "warnings": _qq["warnings"],
                        "score_penalty": _quality_penalty,
                    },
                )

            # ── UP15: Smart cover frame extraction ───────────────────────────
            try:
                _clip_dur = max(1.0, float(seg.get("duration") or 0))
                # S3.3: look up advisory hint from AI plan (RC6: +1 candidate max).
                # idx starts from 1; AI plan clip_cover_hints uses 0-based keys.
                _cover_hint_ratio: float | None = None
                try:
                    if _ai_edit_plan is not None:
                        _plan_hint = (_ai_edit_plan.clip_cover_hints or {}).get(idx - 1) or {}
                        _raw_ratio = _plan_hint.get("preferred_offset_ratio")
                        if _raw_ratio is not None:
                            _cover_hint_ratio = float(_raw_ratio)
                except Exception:
                    pass
                _cover_offset, _cover_reason = _select_cover_frame_time(
                    clip_duration=_clip_dur,
                    hook_score=float(seg.get("hook_score") or 0),
                    srt_meta=_srt_meta,
                    target_platform=_target_platform,
                    variant_type=str(seg.get("variant_type") or ""),
                    cover_hint_ratio=_cover_hint_ratio,
                )
                # S4.3: Thumbnail Quality Intelligence (S4_THUMBNAIL_QUALITY_ENABLED=1)
                # Samples ±1.5s around heuristic offset; picks sharpest/best-exposed frame.
                _cover_quality_reasons: list = []
                _cover_bytes = None
                if os.getenv("S4_THUMBNAIL_QUALITY_ENABLED") == "1":
                    try:
                        from app.services.thumbnail_quality import select_best_thumbnail
                        _t_thumb = time.perf_counter()
                        _cover_bytes, _cover_offset, _cover_quality_reasons = select_best_thumbnail(
                            str(final_part), _cover_offset, _clip_dur, width=640
                        )
                        _thumb_ms = int((time.perf_counter() - _t_thumb) * 1000)
                        logger.debug("s4_thumbnail_select_ms part=%d ms=%d offset=%.3f", idx, _thumb_ms, _cover_offset)
                    except Exception as _s43_exc:
                        logger.debug("s4_thumbnail_quality_failed part=%d: %s", idx, _s43_exc)
                if not _cover_bytes:
                    _cover_bytes = extract_thumbnail_frame(str(final_part), _cover_offset, width=640)
                if _cover_bytes:
                    _cover_stem = (
                        f"{_output_stem}_{_variant_type}_cover" if _variant_type
                        else f"{_output_stem}_part_{idx:03d}_cover"
                    )
                    _cover_path = output_dir / f"{_cover_stem}.jpg"
                    _cover_path.write_bytes(_cover_bytes)
                    seg["cover_file"] = str(_cover_path)
                    seg["cover_frame_offset"] = _cover_offset
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="cover_frame_selected",
                        level="INFO",
                        message=f"Smart cover: part {idx} offset={_cover_offset:.3f}s",
                        step="render.cover",
                        context={
                            "part_no":        idx,
                            "cover_file":     str(_cover_path),
                            "frame_offset":   _cover_offset,
                            "cover_reason":   _cover_reason,
                            "target_platform": _target_platform,
                            "variant_type":   str(seg.get("variant_type") or ""),
                            "thumbnail_quality_reason": _cover_quality_reasons,
                        },
                    )
                    _job_log(
                        effective_channel, job_id,
                        f"cover_frame_selected part_no={idx} offset={_cover_offset:.3f}s "
                        f"platform={_target_platform} reason={_cover_reason!r}",
                    )
            except Exception as _cov_exc:
                logger.warning("cover_frame_extraction_failed part=%d: %s", idx, _cov_exc)
            upsert_job_part(job_id, idx, part_name, JobPartStage.DONE, 100, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Completed")
            row = [job_id, effective_channel, source["title"], idx, seg["start"], seg["end"], seg["duration"], seg["viral_score"], seg["priority_rank"], str(final_part)]
            if payload.cleanup_temp_files:
                _safe_unlink(raw_part)
                _safe_unlink(srt_part)
                _safe_unlink(ass_part)
            return {"idx": idx, "output": str(final_part), "row": row, "skipped": False}

        cpu_total = os.cpu_count() or 2
        gpu_ready = nvenc_available()

        # Distinguish which options add TRUE CPU parallelism cost outside the ffmpeg vf chain.
        # - add_subtitle / text_layers: run INSIDE ffmpeg's filter pipeline; they slow each
        #   job but do not prevent N jobs from running in parallel (no extra process spawned).
        # - motion_aware_crop: runs OpenCV optical-flow as a blocking CPU pre-pass BEFORE
        #   ffmpeg; this competes directly with parallel workers on CPU.
        # - reup_mode: BGM audio subprocess; moderate overhead on CPU.
        if gpu_ready:
            # GPU handles encode; CPU cost per worker is low.
            # Only penalise the pre-pass operations that stay on CPU.
            cpu_extra = sum([
                bool(payload.motion_aware_crop),
                bool(payload.reup_mode),
            ])
            heavy_penalty = min(cpu_extra, 2)
            base = max(2, cpu_total // 3)
            hard_ceiling = 6
        else:
            # CPU-only: libx264/libx265 uses -threads 0 (all cores per worker).
            # Count all heavy opts but cap penalty at 2 (not 3) so higher core counts
            # can still unlock a second parallel worker.
            all_heavy = sum([
                bool(payload.motion_aware_crop),
                bool(payload.add_subtitle),
                bool(payload.reup_mode),
                bool(payload.text_layers),
            ])
            heavy_penalty = min(all_heavy, 2)
            base = max(1, cpu_total // 4)
            hard_ceiling = 4

        hw_cap = max(1, min(base - heavy_penalty, hard_ceiling))

        # max_parallel_parts == 0 means "adaptive / let backend decide"
        # max_parallel_parts >= 1 means user ceiling — honour it but never exceed hw_cap
        user_req = int(payload.max_parallel_parts or 0)
        if user_req >= 1:
            max_workers = max(1, min(user_req, hw_cap))
        else:
            max_workers = hw_cap

        from app.services.render_engine import _resolve_codec
        _effective_codec = _resolve_codec(payload.video_codec, encoder_mode=payload.encoder_mode)
        _job_log(
            effective_channel, job_id,
            f"Using max_workers={max_workers} "
            f"(cpu={cpu_total}, gpu={gpu_ready}, heavy_penalty={heavy_penalty}, "
            f"base={base}, hw_cap={hw_cap}, user_req={user_req}) | "
            f"codec={_effective_codec} preset={tuned['video_preset']} crf={tuned['video_crf']}",
        )
        # Acquire JOB_SEMAPHORE before entering the FFmpeg-encode section.
        # Blocks until a slot opens when MAX_RENDER_JOBS pipelines are already active.
        # Reduces per-job part parallelism proportionally under contention so that
        # two simultaneous jobs share CPU rather than fighting at 100%.
        JOB_SEMAPHORE.acquire()
        with _render_active_lock:
            _render_active_count[0] += 1
            _render_slot = _render_active_count[0]
        try:
            if _render_slot > 1:
                max_workers = max(1, max_workers // _render_slot)
                _job_log(
                    effective_channel, job_id,
                    f"Throttling to {max_workers} worker(s) — {_render_slot} concurrent render(s) active",
                    kind="info",
                )
            _ffmpeg_threads = resolve_ffmpeg_threads(max_workers)
            _job_log(effective_channel, job_id, f"ffmpeg_threads={_ffmpeg_threads} cpu_total={os.cpu_count() or 4} max_workers={max_workers}")
            completed_parts = 0
            failed_parts = []
            _set_stage(JobStage.RENDERING_PARALLEL if max_workers > 1 else JobStage.RENDERING, 30, f"Rendering parts 0/{total_parts}")
            _t_render_loop = time.perf_counter()
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.ffmpeg.start",
                level="INFO",
                message="Running ffmpeg render",
                step="render.ffmpeg",
                context={"total_parts": total_parts, "workers": max_workers},
            )
            if normalized_text_layers:
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="render.text_layers.apply",
                    level="INFO",
                    message="Applying text overlay layers during render",
                    step="render.text_layers",
                    context={"layer_count": len(normalized_text_layers), "total_parts": total_parts},
                )

            if max_workers == 1:
                for idx, seg in enumerate(scored, start=1):
                    if cancel_registry.is_cancelled(job_id):
                        raise cancel_registry.JobCancelledError()
                    try:
                        result = _process_one_part(idx, seg)
                        if result["output"]:
                            outputs.append(result["output"])
                        if result["row"]:
                            rows.append(result["row"])
                    except Exception as part_err:
                        failure_detail = _render_part_failure_detail(idx, part_err)
                        failed_parts.append(failure_detail)
                        upsert_job_part(
                            job_id,
                            idx,
                            f"{source['slug']}_part_{idx:03d}.mp4",
                            JobPartStage.FAILED,
                            _failed_part_progress(job_id, idx),
                            seg["start"],
                            seg["end"],
                            seg["duration"],
                            seg.get("viral_score", 0),
                            seg.get("motion_score", 0),
                            seg.get("hook_score", 0),
                            "",
                            f"Failed: {part_err}",
                        )
                        _job_log(
                            effective_channel,
                            job_id,
                            f"Part {idx}/{total_parts} failed: "
                            f"phase={failure_detail['phase']} code={failure_detail['code']} error={part_err}",
                            kind="error",
                        )
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="part_degraded",
                            level="WARNING",
                            message=f"Clip {idx} failed — {len(outputs)}/{total_parts} clips completed so far",
                            step="render.part",
                            context={
                                "part_no": idx,
                                "total_parts": total_parts,
                                "completed_so_far": len(outputs),
                                "failed_so_far": len(failed_parts),
                                "error_code": failure_detail["code"],
                                "phase": failure_detail["phase"],
                            },
                        )
                    completed_parts += 1
                    progress = 30 + int((completed_parts / total_parts) * 60)
                    _set_stage(JobStage.RENDERING, progress, f"Processed {completed_parts}/{total_parts} parts")
            else:
                future_map = {}
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    for idx, seg in enumerate(scored, start=1):
                        if cancel_registry.is_cancelled(job_id):
                            break  # stop submitting; running futures will self-cancel
                        future_map[executor.submit(_process_one_part, idx, seg)] = idx

                    for future in as_completed(future_map):
                        idx = future_map[future]
                        seg = scored[idx - 1]
                        try:
                            result = future.result()
                            if result["output"]:
                                outputs.append(result["output"])
                            if result["row"]:
                                rows.append(result["row"])
                        except cancel_registry.JobCancelledError:
                            raise  # propagate immediately; executor.__exit__ waits for running futures
                        except Exception as part_err:
                            failure_detail = _render_part_failure_detail(idx, part_err)
                            failed_parts.append(failure_detail)
                            upsert_job_part(
                                job_id,
                                idx,
                                f"{source['slug']}_part_{idx:03d}.mp4",
                                JobPartStage.FAILED,
                                _failed_part_progress(job_id, idx),
                                seg["start"],
                                seg["end"],
                                seg["duration"],
                                seg.get("viral_score", 0),
                                seg.get("motion_score", 0),
                                seg.get("hook_score", 0),
                                "",
                                f"Failed: {part_err}",
                            )
                            _job_log(
                                effective_channel,
                                job_id,
                                f"Part {idx}/{total_parts} failed: "
                                f"phase={failure_detail['phase']} code={failure_detail['code']} error={part_err}",
                                kind="error",
                            )
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="part_degraded",
                                level="WARNING",
                                message=f"Clip {idx} failed — {len(outputs)}/{total_parts} clips completed so far",
                                step="render.part",
                                context={
                                    "part_no": idx,
                                    "total_parts": total_parts,
                                    "completed_so_far": len(outputs),
                                    "failed_so_far": len(failed_parts),
                                    "error_code": failure_detail["code"],
                                    "phase": failure_detail["phase"],
                                },
                            )
                        completed_parts += 1
                        progress = 30 + int((completed_parts / total_parts) * 60)
                        _set_stage(JobStage.RENDERING_PARALLEL, progress, f"Processed {completed_parts}/{total_parts} parts")
                # Catch cancel that completed all futures before propagating (e.g. last part cancelled)
                if cancel_registry.is_cancelled(job_id):
                    raise cancel_registry.JobCancelledError()

            _render_loop_ms = int((time.perf_counter() - _t_render_loop) * 1000)
            _job_log(
                effective_channel, job_id,
                f"Render loop done: {len(outputs)}/{total_parts} parts in {_render_loop_ms}ms "
                f"({_render_loop_ms // 1000}s) with {max_workers} worker(s)",
            )
        finally:
            with _render_active_lock:
                _render_active_count[0] -= 1
            JOB_SEMAPHORE.release()

        if failed_parts and not outputs:
            raise RuntimeError(f"All parts failed ({len(failed_parts)}/{total_parts})")
        if failed_parts:
            _job_log(effective_channel, job_id, f"Partial success: {len(outputs)} done, {len(failed_parts)} failed")

        rows.sort(key=lambda x: int(x[3]))
        outputs = sorted(outputs)
        _set_stage(JobStage.WRITING_REPORT, 95, "Writing render report")
        report_path = output_dir / "render_report.xlsx"
        append_rows(report_path, ["job_id", "channel_code", "video_title", "part_no", "start", "end", "duration", "viral_score", "priority_rank", "output_file"], rows)
        _job_log(effective_channel, job_id, f"Report written: {report_path}")
        if not getattr(payload, "voice_enabled", False):
            _voice_summary = "not used"
        elif _voice_tts_failed:
            _voice_summary = "failed"
        elif _voice_mix_ok:
            _voice_summary = "applied"
        elif _voice_part_tts_attempts and not _voice_mix_ok:
            _voice_summary = "failed"
        else:
            _voice_summary = "not used"
        if not getattr(payload, "subtitle_translate_enabled", False) or not _sub_translate_attempts:
            _subtitle_translate_summary = "not used"
        elif _sub_translate_clean and not _sub_translate_partial and not _sub_translate_failed_parts:
            _subtitle_translate_summary = "applied"
        elif _sub_translate_failed_parts and not _sub_translate_clean and not _sub_translate_partial:
            _subtitle_translate_summary = "failed"
        else:
            _subtitle_translate_summary = "partial"
        _job_log(effective_channel, job_id, f"Voice: {_voice_summary}")
        _job_log(effective_channel, job_id, f"Subtitle translation: {_subtitle_translate_summary}")
        _mv_parts = [
            {
                "part_no":              _i + 1,
                "market_viral_score":   _s.get("mv_viral_score",  0),
                "market_viral_tier":    _s.get("mv_viral_tier",   ""),
                "market_viral_market":  _s.get("mv_viral_market", _mv_market),
                "market_viral_reasons": _s.get("mv_viral_reasons", []),
            }
            for _i, _s in enumerate(scored)
            if "mv_viral_score" in _s
        ]

        # ── P5-1 Output Ranking ───────────────────────────────────────────────
        _failed_idx_set = {int(f.get("part_no", 0)) for f in failed_parts}
        _rank_entries: list[dict] = []
        for _r_idx, _r_seg in enumerate(scored, start=1):
            if _r_idx in _failed_idx_set:
                continue
            _r_vt = str(_r_seg.get("variant_type") or "")
            _r_output = str(
                output_dir / (f"{_output_stem}_{_r_vt}.mp4" if _r_vt else f"{_output_stem}_part_{_r_idx:03d}.mp4")
            )
            _rank_entry = _compute_output_ranking_entry(
                _r_idx,
                _r_seg,
                _r_output,
                payload_hook_score=_hook_score,
            )
            if _r_vt:
                _rank_entry["variant_type"]  = _r_vt
                _rank_entry["variant_label"] = str(_r_seg.get("variant_label") or _r_vt.replace("_", " ").title())
            # UP15: cover frame — propagate from segment dict (set during _process_one_part)
            _r_cover_file   = str(_r_seg.get("cover_file") or "")
            _r_cover_offset = float(_r_seg.get("cover_frame_offset") or 0)
            if _r_cover_file:
                _rank_entry["cover_file"]         = _r_cover_file
                _rank_entry["cover_frame_offset"] = round(_r_cover_offset, 3)
            # UP16: CTA — propagate cta_applied / cta_text from segment dict
            if _r_seg.get("cta_applied"):
                _rank_entry["cta_applied"] = True
                _rank_entry["cta_text"]    = str(_r_seg.get("cta_text") or "")
            # Apply quality penalty from per-part validator
            _rank_raw_score = float(_rank_entry["output_score"])
            _rank_q_penalty = int(_r_seg.get("quality_penalty", 0))
            _rank_final_score = round(max(0.0, min(100.0, _rank_raw_score - _rank_q_penalty)), 1)
            _rank_entry["raw_score"] = _rank_raw_score
            _rank_entry["quality_penalty"] = _rank_q_penalty
            _rank_entry["final_score"] = _rank_final_score
            _rank_entry["output_score"] = _rank_final_score
            _rank_entry["output_rank_score"] = _rank_final_score
            _rank_entries.append(_rank_entry)
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="output_rank_computed",
                level="INFO",
                message=f"Part {_r_idx} output_score={_rank_entry['output_score']}",
                step="render.output_rank",
                context={
                    "part_no": _r_idx,
                    "output_score": _rank_entry["output_score"],
                    "output_rank_score": _rank_entry["output_rank_score"],
                    "ranking_reason": _rank_entry["ranking_reason"],
                    "ranking_components": _rank_entry["ranking_components"],
                },
            )
        _rank_entries.sort(key=lambda x: x["output_score"], reverse=True)
        if len(_rank_entries) >= 2:
            _conf_margin = _rank_entries[0]["output_score"] - _rank_entries[1]["output_score"]
        else:
            _conf_margin = 50.0
        _confidence_tier = (
            "strong" if _conf_margin >= 8 else
            "worth_testing" if _conf_margin >= 4 else
            "experimental"
        )
        if _rank_entries:
            _rank_entries[0]["confidence_tier"] = _confidence_tier
            _rank_entries[0]["score_margin"] = round(_conf_margin, 1)
        logger.info(
            "ranking_truth_audit job=%s confidence=%s margin=%.1f dominant=%s suppressed=%s",
            job_id, _confidence_tier, _conf_margin,
            _rank_entries[0].get("dominant_signal", "") if _rank_entries else "",
            _rank_entries[0].get("suppressed_signals", []) if _rank_entries else [],
        )
        for _ri, _re in enumerate(_rank_entries, start=1):
            _re["output_rank"]    = _ri
            _re["is_best_clip"]   = (_ri == 1)
            _re["is_best_output"] = (_ri == 1)
            _seg = scored[_re["part_no"] - 1]
            _seg["output_rank"] = _re["output_rank"]
            _seg["output_score"] = _re["output_score"]
            _seg["is_best_clip"] = _re["is_best_clip"]
            _seg["ranking_reason"] = _re["ranking_reason"]
        _rank_entries_ordered = sorted(_rank_entries, key=lambda x: x["part_no"])
        _best_rank_entry = _rank_entries[0] if _rank_entries else None
        _partial_warning = (
            f"{len(failed_parts)} of {total_parts} selected part(s) failed; "
            "ranking includes successful outputs only."
            if failed_parts else ""
        )
        if _partial_warning:
            for _re in _rank_entries_ordered:
                _re["partial_failure_warning"] = _partial_warning
            if _best_rank_entry:
                _best_rank_entry["partial_failure_warning"] = _partial_warning
        if cancel_registry.is_cancelled(job_id):
            raise cancel_registry.JobCancelledError()
        _rank_entries_ordered = attach_ai_visibility_summaries(_rank_entries_ordered)
        _best_rank_entry = next(
            (_entry for _entry in _rank_entries_ordered if bool(_entry.get("is_best_clip"))),
            None,
        )
        if _best_rank_entry:
            _job_log(
                effective_channel,
                job_id,
                f"Output ranking: ranked={len(_rank_entries)} "
                f"best_part_no={_best_rank_entry['part_no']} "
                f"best_output_score={_best_rank_entry['output_score']} "
                f"reason={_best_rank_entry['ranking_reason']}",
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="output_ranking_completed",
                level="INFO",
                message=(
                    f"Output ranking: best=part_{_best_rank_entry['part_no']:03d} "
                    f"score={_best_rank_entry['output_score']} total={len(_rank_entries)}"
                ),
                step="render.output_rank",
                context={
                    "total_outputs":   len(_rank_entries),
                    "failed_outputs":  len(failed_parts),
                    "warning":         _partial_warning,
                    "best_part_no":    _best_rank_entry["part_no"],
                    "best_score":      _best_rank_entry["output_score"],
                    "best_reason":     _best_rank_entry["ranking_reason"],
                    "ranking_summary": [
                        {
                            "part_no": e["part_no"],
                            "rank": e["output_rank"],
                            "score": e["output_score"],
                            "reason": e["ranking_reason"],
                        }
                        for e in _rank_entries[:5]
                    ],
                },
            )

        # ── P5-2 Auto Best Export ─────────────────────────────────────────────
        _best_exports_list: list[dict] = []
        if getattr(payload, "auto_best_export_enabled", False):
            if _rank_entries:
                _abe_count = max(1, min(10, int(getattr(payload, "auto_best_export_count", 3) or 3)))
                _abe_top   = _rank_entries[:_abe_count]  # already sorted desc by score
                _best_dir  = output_dir / "best"
                try:
                    _best_dir.mkdir(parents=True, exist_ok=True)
                    for _abe in _abe_top:
                        _abe_src = Path(_abe["output_file"])
                        _abe_dst = _best_dir / f"{_output_stem}_rank_{_abe['output_rank']:02d}.mp4"
                        try:
                            shutil.copy2(str(_abe_src), str(_abe_dst))
                            _best_exports_list.append({
                                "rank":              _abe["output_rank"],
                                "part_no":           _abe["part_no"],
                                "source_file":       str(_abe_src),
                                "best_file":         str(_abe_dst),
                                "output_score":      _abe["output_score"],
                                "output_rank_score": _abe["output_rank_score"],
                                "ranking_reason":    _abe["ranking_reason"],
                            })
                        except Exception as _abe_copy_err:
                            _job_log(
                                effective_channel, job_id,
                                f"best_export copy failed part_{_abe['part_no']:03d}: {_abe_copy_err}",
                                kind="warning",
                            )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="best_export_completed",
                        level="INFO",
                        message=f"Best export: {len(_best_exports_list)}/{len(_abe_top)} files → {_best_dir}",
                        step="render.best_export",
                        context={
                            "count":          len(_best_exports_list),
                            "best_dir":       str(_best_dir),
                            "exported_files": [e["best_file"] for e in _best_exports_list],
                        },
                    )
                except Exception as _abe_err:
                    _job_log(
                        effective_channel, job_id,
                        f"best_export_failed: {_abe_err}",
                        kind="warning",
                    )
            else:
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="best_export_skipped",
                    level="INFO",
                    message="Best export skipped: no ranked outputs available",
                    step="render.best_export",
                    context={"reason": "no_ranked_outputs"},
                )

        _is_partial_success = bool(failed_parts)
        _final_status = "completed_with_errors" if _is_partial_success else "completed"
        _final_message = (
            f"Render complete: {len(outputs)}/{total_parts} clips · {len(failed_parts)} failed"
            if _is_partial_success else "Render completed"
        )
        if _recovery_notes:
            _final_message += " [" + "; ".join(_recovery_notes) + "]"

        # ── Phase 30: AI Output Ranking — best-effort, never blocks render ──
        _ai_output_ranking: dict = {"available": False, "mode": "recommendation_only"}
        try:
            from app.ai.output.output_ranker import rank_variant_outputs as _rank_ai_outputs
            _ai_rank_inputs = [
                {
                    "output_id": str(_re.get("part_no") or i),
                    "path": str(_re.get("output_file") or ""),
                    "variant_id": str(_re.get("variant_id") or ""),
                    "output_rank_score": float(_re.get("output_rank_score") or _re.get("output_score") or 0.0),
                    "failed": False,
                    "warnings": [],
                }
                for i, _re in enumerate(_rank_entries_ordered)
            ] + [
                {
                    "output_id": str(_fp.get("part_no") or f"failed_{i}"),
                    "path": "",
                    "variant_id": "",
                    "output_rank_score": 0.0,
                    "failed": True,
                    "warnings": [str(_fp.get("error") or "render_failed")],
                }
                for i, _fp in enumerate(failed_parts)
            ]
            _ai_rank_result = _rank_ai_outputs(
                _ai_rank_inputs,
                edit_plan=_ai_edit_plan,
                context={"job_id": job_id},
            )
            _ai_output_ranking = _ai_rank_result.to_dict()
            if _ai_edit_plan is not None:
                _ai_edit_plan.output_ranking = _ai_output_ranking
            logger.info(
                "ai_output_ranking_created job_id=%s best=%s outputs=%d",
                job_id,
                _ai_output_ranking.get("best_output_id") or "none",
                len(_ai_output_ranking.get("outputs") or []),
            )
        except Exception as _rank_err:
            logger.warning("ai_output_ranking_skipped job_id=%s: %s", job_id, _rank_err)
            _ai_output_ranking = {
                "available": False,
                "mode": "recommendation_only",
                "warnings": [f"ranking_error:{type(_rank_err).__name__}"],
            }

        # ── Phase 45: AI Render Quality Evaluation — evaluation-only, never blocks render ──
        _ai_render_quality: dict = {"available": False, "evaluation_mode": "evaluation_only"}
        try:
            from app.ai.quality.quality_evaluator import evaluate_render_quality as _eval_quality
            _quality_eval = _eval_quality(
                outputs,
                edit_plan=_ai_edit_plan,
                context={"job_id": job_id},
            )
            _ai_render_quality = _quality_eval.to_dict()
            if _ai_edit_plan is not None:
                _ai_edit_plan.render_quality_evaluation = _ai_render_quality
            logger.info(
                "ai_render_quality_evaluated job_id=%s best=%s outputs=%d",
                job_id,
                _ai_render_quality.get("best_quality_output_id") or "none",
                len(_ai_render_quality.get("output_scores") or []),
            )
        except Exception as _quality_err:
            logger.warning("ai_render_quality_evaluation_skipped job_id=%s: %s", job_id, _quality_err)
            _ai_render_quality = {
                "available": False,
                "evaluation_mode": "evaluation_only",
                "warnings": [f"quality_evaluation_error:{type(_quality_err).__name__}"],
            }

        # Phase 49A — Build stable UI-safe AI UX metadata contract
        _ai_ux_metadata: dict = {"available": False}
        try:
            from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata as _build_ai_ux
            _ai_ux_metadata = _build_ai_ux(_ai_edit_plan, output_ranking=_ai_output_ranking)
        except Exception as _ux_err:
            logger.debug("ai_ux_metadata_skipped job_id=%s: %s", job_id, _ux_err)

        _result_payload = {
            "outputs": outputs,
            "render_preset": _preset_name,
            "render_preset_id": _preset_id,
            "render_preset_label": _preset_label,
            "segments": scored,
            "market_viral_parts": _mv_parts,
            "output_ranking": _rank_entries_ordered,
            "output_ranking_warning": _partial_warning,
            "best_clip": _best_rank_entry,
            "best_exports": _best_exports_list,
            "voice_summary": _voice_summary,
            "subtitle_translate_summary": _subtitle_translate_summary,
            "failed_parts": [int(f["part_no"]) for f in failed_parts],
            "failed_parts_detail": failed_parts,
            "selected_segments_count": total_parts,
            "successful_outputs_count": len(outputs),
            "failed_outputs_count": len(failed_parts),
            "is_partial_success": _is_partial_success,
            "ai_director": _ai_edit_plan.to_dict() if _ai_edit_plan is not None else {"enabled": False},
            "ai_render_influence": _ai_influence_report,
            "ai_beat_execution": _ai_beat_report,
            "story": _ai_edit_plan.story if _ai_edit_plan is not None else {},
            "preset_evolution": _ai_edit_plan.preset_evolution if _ai_edit_plan is not None else {},
            "creator_style": _ai_edit_plan.creator_style if _ai_edit_plan is not None else {},
            "ai_output_ranking": _ai_output_ranking,
            "ai_render_quality_evaluation": _ai_render_quality,
            "ai_ux": _ai_ux_metadata,
            "recovery_notes": _recovery_notes,
        }
        upsert_job(
            job_id,
            "render",
            effective_channel,
            _final_status,
            payload.model_dump(),
            _result_payload,
            stage=JobStage.DONE,
            progress_percent=100,
            message=_final_message,
        )
        # ── AI Memory write (Phase 3) — after job finalized, never blocks render ──
        if getattr(payload, "ai_director_enabled", False) or _ai_edit_plan is not None:
            try:
                from app.ai.rag.memory_writer import write_render_memory as _write_mem
                _write_mem(
                    _result_payload,
                    context={
                        "market": getattr(payload, "viral_market", None),
                        "mode": getattr(payload, "ai_mode", "viral_tiktok"),
                        "duration": source.get("duration", 0.0),
                    },
                )
            except Exception:
                pass

        _job_log(
            effective_channel,
            job_id,
            f"Render final summary: status={_final_status} "
            f"successful_outputs={len(outputs)} failed_outputs={len(failed_parts)} "
            f"selected_segments={total_parts}",
            kind="warning" if _is_partial_success else "info",
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.ffmpeg.success",
            level="WARNING" if _is_partial_success else "INFO",
            message="FFmpeg render completed with errors" if _is_partial_success else "FFmpeg render completed",
            step="render.ffmpeg",
            context={"outputs": len(outputs), "failed_outputs": len(failed_parts), "total_parts": total_parts},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.complete_with_errors" if _is_partial_success else "render.complete",
            level="WARNING" if _is_partial_success else "INFO",
            message=_final_message,
            step="render.complete",
            duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            context={
                "outputs": len(outputs),
                "failed_outputs": len(failed_parts),
                "total_parts": total_parts,
                "is_partial_success": _is_partial_success,
                "voice_summary": _voice_summary,
                "subtitle_translate_summary": _subtitle_translate_summary,
            },
        )
    except Exception as e:
        fail_message = f"Failed at step '{current_stage}': {e}"
        tb = traceback.format_exc()
        _job_log(effective_channel, job_id, f"[ERROR_STEP] {current_stage}")
        _job_log(effective_channel, job_id, f"Render failed: {e}")
        _job_log(effective_channel, job_id, tb)
        if current_stage == JobStage.SCENE_DETECTION:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.scene.detect.error",
                level="ERROR",
                message=f"Scene detection failed: {e}",
                step="render.scene.detect",
                exception=e,
                traceback_text=tb,
            )
        if current_stage == JobStage.DOWNLOADING:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.download.error",
                level="ERROR",
                message=f"Source download failed: {e}",
                step="render.download",
                exception=e,
                traceback_text=tb,
            )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.error",
            level="ERROR",
            message=fail_message,
            step=current_stage,
            exception=e,
            traceback_text=tb,
            duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            context={"current_stage": current_stage, "source_mode": payload.source_mode, "youtube_url": (payload.youtube_url or ""), "source_video_path": (payload.source_video_path or "")},
        )
        if current_stage in {JobStage.STARTING, JobStage.DOWNLOADING}:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.error",
                level="ERROR",
                message=f"Source preparation failed: {e}",
                step="render.prepare_source.error",
                exception=e,
                traceback_text=tb,
                context={"current_stage": current_stage, "source_mode": payload.source_mode, "youtube_url": (payload.youtube_url or ""), "source_video_path": (payload.source_video_path or "")},
            )
        upsert_job(
            job_id,
            "render",
            effective_channel,
            "failed",
            payload.model_dump(),
            {"error": str(e), "failed_step": current_stage},
            stage=JobStage.FAILED,
            progress_percent=max(0, min(99, int(current_progress))),
            message=fail_message,
        )
        return
    finally:
        if payload.cleanup_temp_files:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
                _job_log(effective_channel, job_id, "Temporary files cleaned")
            except Exception as cleanup_err:
                _job_log(effective_channel, job_id, f"Temp cleanup warning: {cleanup_err}")
        # Cleanup preview session only on success — failed/cancelled renders should
        # keep the session alive so the user can retry without re-preparing the source.
        _session_render_succeeded = _final_status in ("completed", "completed_with_errors")
        if edit_session_id and _session_render_succeeded:
            try:
                cleanup_session_fn(edit_session_id)
            except Exception:
                pass
        _JOB_LOG_DIRS.pop(job_id, None)
        close_thread_conn()  # release render thread's cached DB connection

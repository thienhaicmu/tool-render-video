"""
pipeline_helpers.py — Pure utility helpers for the render pipeline.

Extracted from render_pipeline.py (Phase A-1). No behavior change.
All functions are stateless and do not depend on pipeline execution state.
"""

import logging
import re
from pathlib import Path

from app.services.subtitle_engine import parse_srt_blocks, write_srt_blocks

logger = logging.getLogger("app.render")

# ---------------------------------------------------------------------------
# Module-level constants (previously in render_pipeline.py)
# ---------------------------------------------------------------------------

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

# UP16 — CTA / Series Intelligence: deterministic end-card text library.
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

# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# AI segment mapping
# ---------------------------------------------------------------------------

def _map_ai_segments_to_scored(ai_clips: list, heuristic_scored: list) -> list:
    """
    Map AIClipPlan list onto heuristic scored[] dicts via time-overlap matching.
    Preserves all heuristic score fields (viral_score, motion_score, hook_score).
    AI's start/end boundaries override heuristic boundaries when overlap >= 30%.
    AI clips with no matching heuristic segment synthesize a minimal scored dict.
    """
    result = []
    used: set = set()
    for clip in ai_clips:
        best_idx, best_ratio = None, 0.0
        for i, seg in enumerate(heuristic_scored):
            if i in used:
                continue
            s, e = float(seg.get("start", 0)), float(seg.get("end", 0))
            overlap = max(0.0, min(e, clip.end) - max(s, clip.start))
            min_dur = min(e - s, clip.end - clip.start)
            ratio = overlap / min_dur if min_dur > 0 else 0.0
            if ratio > best_ratio:
                best_ratio, best_idx = ratio, i
        if best_idx is not None and best_ratio >= 0.30:
            seg = dict(heuristic_scored[best_idx])
            seg["start"] = clip.start
            seg["end"] = clip.end
            seg["duration"] = round(clip.end - clip.start, 3)
            seg["ai_content_selected"] = True
            seg["ai_select_reason"] = clip.reason
            seg["ai_select_score"] = clip.score
            used.add(best_idx)
            result.append(seg)
        else:
            result.append({
                "start": clip.start,
                "end": clip.end,
                "duration": round(clip.end - clip.start, 3),
                "viral_score": max(0, min(100, int(clip.score))),
                "motion_score": 0,
                "hook_score": 0,
                "ai_content_selected": True,
                "ai_select_reason": clip.reason,
                "ai_select_score": clip.score,
            })
    return result


# ---------------------------------------------------------------------------
# Cover frame selection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CTA helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Playback speed
# ---------------------------------------------------------------------------

def _get_effective_playback_speed(payload, target_platform: str) -> float:
    """Single source of truth for the playback speed used by both the renderer and the validator.

    Combines the creator-selected base speed with the platform speed delta so that
    expected_duration in output validation matches the actual render output duration.
    """
    platform_delta = _PLATFORM_PROFILES.get(target_platform, {}).get("speed_delta", 0.0)
    return max(0.5, min(1.5, float(payload.playback_speed or 1.0) + platform_delta))


# ---------------------------------------------------------------------------
# SRT metadata reader
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Multi-variant segment selection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ASS subtitle resolution helper
# ---------------------------------------------------------------------------

def _aspect_play_res_y(aspect_ratio: str) -> int:
    ar = (aspect_ratio or "").strip()
    val = _PLAY_RES_Y_MAP.get(ar)
    if val is None:
        logger.warning("_aspect_play_res_y: unrecognised aspect_ratio=%r, defaulting to 1440", ar)
        return 1440
    return val


# ---------------------------------------------------------------------------
# SRT edit patcher
# ---------------------------------------------------------------------------

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

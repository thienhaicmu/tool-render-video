import re
import logging
from pathlib import Path
from app.features.render.engine.subtitle.generator.srt import _parse_srt_blocks, format_srt_timestamp
from app.features.render.engine.subtitle.processing.readability import _HOOK_EMPHASIS_WORDS

logger = logging.getLogger(__name__)


def resolve_hook_overlay_text(
    hook_applied_text: str | None,
    srt_path: str | None,
    max_words: int = 10,
) -> tuple[str, str]:
    """Resolve hook overlay text for the opening visual overlay.

    Priority:
    1. hook_applied_text — explicit user-supplied hook string.
    2. First meaningful subtitle block from srt_path (â‰¥2 words).
    3. Return ("", reason) when nothing suitable is found.

    Returns (text, source_reason).
    Cleans: collapses whitespace, strips ASS tags, truncates to max_words,
    converts all-caps (>3 words) to title-case.
    """
    def _clean(raw: str) -> str:
        t = re.sub(r"\s+", " ", str(raw or "").replace("\n", " ").strip())
        t = re.sub(r"\{[^}]*\}", "", t).strip()  # strip ASS override tags
        words = t.split()
        if len(words) > max_words:
            t = " ".join(words[:max_words]).strip()
            words = t.split()
        if len(words) > 3 and t == t.upper():
            t = t.title()
        return t.strip()

    explicit = str(hook_applied_text or "").strip()
    if explicit:
        cleaned = _clean(explicit)
        if cleaned:
            return cleaned, "explicit"

    if srt_path:
        try:
            blocks = _parse_srt_blocks(srt_path)
            for b in blocks:
                text = str(b.get("text") or "").strip()
                if text and len(text.split()) >= 2:
                    cleaned = _clean(text)
                    if cleaned:
                        return cleaned, "subtitle_first_block"
        except Exception:
            pass

    return "", "no_suitable_text"


def apply_market_line_break_to_srt(srt_path: str, market_payload: dict) -> str:
    """Re-wrap SRT subtitle lines to the market/tone word-count ceiling.

    Called after subtitle text is finalized, before the SRT is consumed further.
    Safe no-op when market_payload is falsy or any error occurs.
    """
    if not market_payload:
        return srt_path
    try:
        from app.features.render.engine.subtitle.processing.market_policy import (
            get_market_subtitle_policy,
            break_text_by_words,
            highlight_keywords_in_text,
            select_subtitle_keywords,
        )
        market       = str(market_payload.get("target_market") or "US").upper()
        tone         = str(market_payload.get("subtitle_tone")  or "clean").lower()
        do_highlight = bool(market_payload.get("keyword_highlight", False))
        policy   = get_market_subtitle_policy(market, tone)
        max_w    = int(policy["max_words_per_line"])
        keywords = policy["highlight_keywords"] if do_highlight else []
        blocks = _parse_srt_blocks(srt_path)
        if not blocks:
            return srt_path
        avg_words = sum(len(str(b["text"]).split()) for b in blocks) / max(1, len(blocks))
        word_level_like = len(blocks) >= 6 and avg_words <= 1.5
        total_lines = 0
        highlighted_terms: list[str] = []
        timing_adjusted = 0
        with Path(srt_path).open("w", encoding="utf-8") as f:
            for idx, b in enumerate(blocks, start=1):
                text = break_text_by_words(b["text"], max_w)
                total_lines += max(1, len(text.splitlines()))
                if do_highlight and not word_level_like:
                    highlighted_terms.extend(select_subtitle_keywords(text, keywords, market, 2))
                    text = highlight_keywords_in_text(text, keywords, market)
                start = b["start"]
                end = b["end"]
                if not word_level_like:
                    start = max(0.0, start - 0.10)
                    extend = 0.20 if (b["end"] - b["start"]) < 1.2 else 0.12
                    end = b["end"] + extend
                    end_cap = None
                    if idx < len(blocks):
                        next_start = max(0.0, blocks[idx]["start"] - 0.10)
                        end_cap = next_start - 0.02
                        end = min(end, end_cap)
                    if end <= start + 0.08:
                        if end_cap is not None and end_cap > start:
                            end = end_cap
                        elif end_cap is not None:
                            start = max(0.0, end_cap - 0.08)
                            end = max(start, end_cap)
                        else:
                            end = max(start + 0.08, b["end"])
                    if abs(start - b["start"]) > 0.001 or abs(end - b["end"]) > 0.001:
                        timing_adjusted += 1
                f.write(
                    f"{idx}\n"
                    f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n"
                    f"{text}\n\n"
                )
        logger.info(
            "subtitle_v2_market_format: path=%s market=%s tone=%s blocks=%d lines=%d "
            "highlight_words=%s timing_adjusted=%d word_level_like=%s",
            srt_path,
            policy["market"],
            tone,
            len(blocks),
            total_lines,
            sorted({w.lower() for w in highlighted_terms})[:12],
            timing_adjusted,
            word_level_like,
        )
    except Exception:
        logger.exception("subtitle_v2_market_format_failed path=%s", srt_path)
    return srt_path


# ---------------------------------------------------------------------------
# P4-2 — Hook subtitle impact formatting
# ---------------------------------------------------------------------------

def apply_market_hook_text_to_srt(
    srt_path: str,
    hook_text: str,
    max_hook_blocks: int = 1,
    max_hook_seconds: float = 5.0,
) -> dict:
    """Replace the opening subtitle hook zone with user-selected hook text.

    This only changes text in the first subtitle block by default. Timestamps,
    ordering, and non-hook blocks are preserved. Safe no-op on missing subtitles,
    blank hook text, parse errors, or write errors.
    """
    result = {
        "applied": False,
        "affected_count": 0,
        "original_hook_text": "",
        "applied_hook_text": str(hook_text or "").strip(),
    }
    if not result["applied_hook_text"]:
        return result
    try:
        max_blocks = max(1, min(2, int(max_hook_blocks or 1)))
    except Exception:
        max_blocks = 1
    try:
        max_seconds = max(3.0, min(5.0, float(max_hook_seconds or 5.0)))
    except Exception:
        max_seconds = 5.0

    try:
        blocks = _parse_srt_blocks(srt_path)
        if not blocks:
            return result

        target_indexes = []
        for i, b in enumerate(blocks):
            if len(target_indexes) >= max_blocks:
                break
            if not str(b.get("text") or "").strip():
                continue
            if float(b.get("start") or 0.0) <= max_seconds:
                target_indexes.append(i)

        if not target_indexes:
            first_text_idx = next(
                (i for i, b in enumerate(blocks) if str(b.get("text") or "").strip()),
                None,
            )
            if first_text_idx is not None:
                target_indexes.append(first_text_idx)

        if not target_indexes:
            return result

        target_set = set(target_indexes)
        result["original_hook_text"] = " ".join(
            str(blocks[i].get("text") or "").strip()
            for i in target_indexes
            if str(blocks[i].get("text") or "").strip()
        ).strip()

        with Path(srt_path).open("w", encoding="utf-8") as f:
            for idx, b in enumerate(blocks, start=1):
                text = result["applied_hook_text"] if (idx - 1) in target_set else b["text"]
                f.write(
                    f"{idx}\n"
                    f"{format_srt_timestamp(b['start'])} --> {format_srt_timestamp(b['end'])}\n"
                    f"{text}\n\n"
                )

        result["applied"] = True
        result["affected_count"] = len(target_indexes)
        return result
    except Exception:
        return result


def format_hook_subtitle(text: str) -> str:
    """Format one subtitle block for hook/first-clip visual impact.

    - Normalises whitespace and collapses newlines to one line
    - Returns original unchanged when text < 20 chars
    - For short segments (â‰¤ 4 words): uppercases detected emphasis words in place
    - For longer segments: splits into max 2 lines and uppercases the leading phrase
    """
    text = re.sub(r"\s+", " ", text.replace("\n", " ").strip())
    if len(text) < 20:
        return text

    words = text.split()
    total = len(words)

    def _is_emphasis(w: str) -> bool:
        return re.sub(r"[^\w]", "", w).lower() in _HOOK_EMPHASIS_WORDS

    if total <= 4:
        return " ".join(w.upper() if _is_emphasis(w) else w for w in words)

    # Find emphasis anchor in first 6 words to set the split point for line 1
    split_at = min(4, total - 2)  # default: ~4 words on line 1, â‰¥2 on line 2
    for i in range(min(6, total - 1)):
        if _is_emphasis(words[i]):
            split_at = i + 1

    # Clamp: line 1 = 2–6 words, line 2 always has â‰¥ 1 word
    split_at = max(2, min(split_at, 6, total - 1))

    line1 = " ".join(words[:split_at]).upper()
    line2 = " ".join(words[split_at:])
    return f"{line1}\n{line2}"


def apply_hook_subtitle_format(srt_path: str, max_hook_blocks: int = 2) -> int:
    """Apply hook-impact formatting to the opening blocks of an SRT file (in-place).

    Only the first `max_hook_blocks` entries receive impact formatting; the rest
    are written back unchanged.  Returns the number of formatted blocks on success,
    0 on empty file or error.
    Safe no-op on any exception — original file is left untouched if writing fails.
    """
    try:
        blocks = _parse_srt_blocks(srt_path)
        if not blocks:
            return 0
        formatted = 0
        with Path(srt_path).open("w", encoding="utf-8") as f:
            for i, b in enumerate(blocks, start=1):
                if i <= max_hook_blocks:
                    text = format_hook_subtitle(b["text"])
                    formatted += 1
                else:
                    text = b["text"]
                f.write(
                    f"{i}\n"
                    f"{format_srt_timestamp(b['start'])} --> {format_srt_timestamp(b['end'])}\n"
                    f"{text}\n\n"
                )
        return formatted
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Phase 17 — AI subtitle execution metadata integration
# ---------------------------------------------------------------------------

def apply_subtitle_execution_hints(
    blocks: list[dict],
    subtitle_execution: dict | None,
) -> dict:
    """Safely consume AI subtitle execution metadata hints.

    Reads global_hint fields (emphasis_strength, emotion_style, density_mode,
    keyword_focus) from the execution plan and returns a compact hints dict that
    downstream render steps may use.

    Never mutates subtitle timing or text. Never raises. Returns fallback dict
    when metadata is absent or malformed.
    """
    fallback = {
        "applied": False,
        "emphasis_strength": 0.0,
        "emotion_style": "neutral",
        "density_mode": "normal",
        "keyword_focus": [],
        "warnings": [],
    }
    try:
        if not isinstance(subtitle_execution, dict):
            return fallback
        if not subtitle_execution.get("available", False):
            return {**fallback, "warnings": list(subtitle_execution.get("warnings", []))}

        global_hint = subtitle_execution.get("global_hint")
        if not isinstance(global_hint, dict):
            return fallback

        emphasis_strength = float(global_hint.get("emphasis_strength", 0.0))
        emphasis_strength = max(0.0, min(1.0, emphasis_strength))

        emotion_style = str(global_hint.get("emotion_style") or "neutral")
        _VALID_EMOTION = {"neutral", "hype", "dramatic", "calm", "emotional", "punch"}
        if emotion_style not in _VALID_EMOTION:
            emotion_style = "neutral"

        density_mode = str(global_hint.get("density_mode") or "normal")
        _VALID_DENSITY = {"compact", "normal", "expressive"}
        if density_mode not in _VALID_DENSITY:
            density_mode = "normal"

        keyword_focus = [
            str(k) for k in (global_hint.get("keyword_focus") or [])
            if isinstance(k, str)
        ][:10]

        logger.info(
            "subtitle_execution_hints_applied emphasis=%.3f emotion=%s density=%s keywords=%d",
            emphasis_strength, emotion_style, density_mode, len(keyword_focus),
        )

        return {
            "applied": True,
            "emphasis_strength": emphasis_strength,
            "emotion_style": emotion_style,
            "density_mode": density_mode,
            "keyword_focus": keyword_focus,
            "warnings": [],
        }
    except Exception as exc:
        logger.debug("subtitle_execution_hints_failed: %s", exc)
        return {**fallback, "warnings": [f"hints_error:{type(exc).__name__}"]}


import os
import re
import logging
from pathlib import Path
from app.services.subtitles.styles import (
    normalize_subtitle_style_id, get_subtitle_preset, _HL_OPEN, _HL_CLOSE,
)
from app.services.subtitles.srt_core import _parse_srt_blocks, format_srt_timestamp

logger = logging.getLogger(__name__)

_WIDE_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&Wm")
_NARROW_CHARS = frozenset("fijlrt!|,.'\":;-")


def _approx_visual_width(text: str) -> float:
    """Estimate rendered character-width in em units for line-break decisions.

    Uppercase and wide glyphs are counted as 1.3, narrow glyphs as 0.6, rest 1.0.
    This avoids purely word-count-based breaks that under-count wide uppercase text.
    """
    total = 0.0
    for ch in text:
        if ch in _WIDE_CHARS:
            total += 1.3
        elif ch in _NARROW_CHARS:
            total += 0.6
        elif ch == " ":
            total += 0.45
        else:
            total += 1.0
    return total


def _break_by_visual_width(text: str, max_em: float = 18.0, max_lines: int = 2) -> str:
    """Insert newlines to keep subtitle lines within max_em visual width.

    When max_lines=2 (default), splits at the visual midpoint to produce
    balanced two-line captions instead of greedy word-count wrapping.
    Returns text unchanged when it already fits or already has a newline.
    """
    if "\n" in text:
        # Already line-broken: enforce max_lines cap only
        parts = text.split("\n")
        if len(parts) <= max_lines:
            return text
        return "\n".join(parts[:max_lines])

    total_w = _approx_visual_width(text)
    if total_w <= max_em:
        return text

    words = text.split()
    if len(words) <= 1:
        return text

    if max_lines == 2:
        # Find split point closest to visual midpoint
        half = total_w / 2.0
        cum = 0.0
        best_idx = 1
        best_dist = float("inf")
        for i, word in enumerate(words):
            cum += _approx_visual_width(word + " ")
            dist = abs(cum - half)
            if dist < best_dist:
                best_dist = dist
                best_idx = i + 1
        return " ".join(words[:best_idx]) + "\n" + " ".join(words[best_idx:])

    # General greedy wrap for max_lines > 2
    lines: list[str] = []
    current: list[str] = []
    current_w = 0.0
    for word in words:
        ww = _approx_visual_width(word + " ")
        if current and current_w + ww > max_em and len(lines) < max_lines - 1:
            lines.append(" ".join(current))
            current = [word]
            current_w = ww
        else:
            current.append(word)
            current_w += ww
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Hook emphasis vocabulary — shared by text_transforms and emphasis engine
# ---------------------------------------------------------------------------

_HOOK_EMPHASIS_WORDS = frozenset({
    "never", "crazy", "craziest", "crazier", "shocking", "shocked",
    "wait", "look", "watch", "insane", "insanely", "unbelievable",
    "incredible", "impossible", "secret", "truth", "stop", "listen",
    "serious", "seriously", "honest", "honestly", "real", "actually",
    "worst", "best", "only", "first", "last", "ever", "always",
    "believe", "imagine", "realize", "understand", "see", "need", "want",
    "love", "hate", "find", "know", "show", "get", "take", "make",
    "try", "change", "win", "lose", "fail", "break", "run", "fight",
})


# ---------------------------------------------------------------------------
# S4 — Subtitle Emphasis Engine
# ---------------------------------------------------------------------------

def _is_cjk(text: str) -> bool:
    """Return True when text contains CJK/Japanese/Korean characters."""
    for ch in text:
        cp = ord(ch)
        if (
            0x3040 <= cp <= 0x309F    # Hiragana
            or 0x30A0 <= cp <= 0x30FF  # Katakana
            or 0x4E00 <= cp <= 0x9FFF  # CJK Unified Ideographs (BMP)
            or 0x3400 <= cp <= 0x4DBF  # CJK Extension A
            or 0xAC00 <= cp <= 0xD7AF  # Hangul syllables
            or 0x1100 <= cp <= 0x11FF  # Hangul Jamo
        ):
            return True
    return False


def _emphasis_level(preset_id: str) -> str:
    """Return emphasis intensity for preset_id: strong | medium | subtle | minimal | word_only."""
    _MAP = {
        "tiktok_bounce_v1": "strong",
        "viral_bold":       "strong",
        "bold_cap":         "strong",
        "story_clean_01":   "medium",
        "clean_pro":        "subtle",
        "boxed_caption":    "minimal",
        "pro_karaoke":      "word_only",
        # QUALITY-UP6 personality presets
        "viral":            "strong",
        "clean":            "subtle",
        "story":            "medium",
        "gaming":           "strong",
    }
    return _MAP.get(normalize_subtitle_style_id(preset_id), "medium")


_EMPH_CONTRAST = frozenset({
    "only", "never", "always", "first", "last", "best", "worst",
    "free", "new", "top", "no", "zero", "none",
})
_EMPH_EMOTIONAL = frozenset({
    "crazy", "insane", "unbelievable", "incredible", "impossible",
    "shocking", "amazing", "secret", "hidden", "truth",
    "real", "honest", "actually",
})
_EMPH_URGENCY = frozenset({
    "now", "today", "fast", "quick", "limited", "stop", "wait",
    "urgent", "breaking", "instantly",
})

_NUMBER_RE = re.compile(
    r"\$[\d,]+(?:\.\d+)?[kKmMbB]?"  # $1,000  $5k  $2.5M
    r"|[\d,]+(?:\.\d+)?%"            # 100%  3.5%
    r"|\d+[xX]"                      # 10x  3X
    r"|#\d+"                         # #1  #5
    r"|\d+[kKmMbB]"                  # 500k  1M
)


def _should_emphasize(token: str, level: str) -> bool:
    """Return True when this word/token deserves a highlight marker."""
    clean = re.sub(r"[^\w$#%.,]", "", token).rstrip(".,")
    if _NUMBER_RE.fullmatch(clean):
        return True
    lw = clean.lower().rstrip(".,!?;:")
    if level == "strong":
        return (
            lw in _EMPH_CONTRAST or lw in _EMPH_EMOTIONAL
            or lw in _EMPH_URGENCY or lw in _HOOK_EMPHASIS_WORDS
        )
    if level == "medium":
        return lw in _EMPH_CONTRAST or lw in _EMPH_EMOTIONAL or lw in _HOOK_EMPHASIS_WORDS
    return False  # subtle → numbers only (handled above); minimal/word_only → never reaches here


def _uppercase_emphasis_words(text: str) -> str:
    """Uppercase emphasis-class words in text (for strong level, Latin script only)."""
    out = []
    for part in re.split(r"(\s+)", text):
        if not part.strip():
            out.append(part)
            continue
        clean = re.sub(r"[^\w$#%.,]", "", part).rstrip(".,")
        lw = clean.lower().rstrip(".,!?;:")
        if (
            lw in _HOOK_EMPHASIS_WORDS
            or lw in _EMPH_CONTRAST
            or lw in _EMPH_URGENCY
            or _NUMBER_RE.fullmatch(clean)
        ):
            out.append(part.upper())
        else:
            out.append(part)
    return "".join(out)


def _insert_emphasis_markers(text: str, market: str, level: str) -> str:
    """Wrap emphasis tokens with _HL_OPEN/_HL_CLOSE markers for later ASS resolution.

    Skips any token that already contains a marker — prevents double-wrapping
    when apply_market_line_break_to_srt() has already marked keywords.
    """
    mkt = str(market or "US").upper()[:2]
    out = []
    for part in re.split(r"(\s+)", text):
        if not part.strip():
            out.append(part)
            continue
        if _HL_OPEN in part or _HL_CLOSE in part:
            out.append(part)
            continue
        if _should_emphasize(part, level):
            out.append(f"{_HL_OPEN}{mkt}:{part}{_HL_CLOSE}")
        else:
            out.append(part)
    return "".join(out)


def _semantic_wrap_block(text: str, max_em: float) -> str:
    """Midpoint line-wrap with orphan/widow avoidance.

    Avoids:
    - Orphan: a single word stranded alone on line 2 → skip split entirely
    - Widow: a very short trailing word (≤ 3 chars) on line 2 → shift split right
    """
    if "\n" in text or _approx_visual_width(text) <= max_em:
        return text

    words = text.split()
    n = len(words)
    if n <= 1:
        return text

    total_w = _approx_visual_width(text)
    half = total_w / 2.0
    cum = 0.0
    best_idx = 1
    best_dist = float("inf")
    for i, word in enumerate(words):
        cum += _approx_visual_width(word + " ")
        dist = abs(cum - half)
        if dist < best_dist:
            best_dist = dist
            best_idx = i + 1

    # Orphan avoidance: exactly 1 word on line 2 — return unsplit
    if n - best_idx == 1:
        return text

    # Widow avoidance: last word of line 2 is very short → shift split right by 1
    last_clean = re.sub(r"\W", "", words[-1])
    if len(last_clean) <= 3 and (n - best_idx) >= 2 and best_idx + 1 < n:
        candidate = best_idx + 1
        # Only shift if the new line 2 still has at least 2 words
        if n - candidate >= 2:
            best_idx = candidate

    return " ".join(words[:best_idx]) + "\n" + " ".join(words[best_idx:])


def subtitle_emphasis_pass(
    blocks: list[dict],
    preset_id: str = "tiktok_bounce_v1",
    market: str = "US",
    language: str = "en",
) -> list[dict]:
    """Unified emphasis pass: semantic wrap + keyword uppercase + highlight markers.

    Operates on a list of blocks (dicts with 'start', 'end', 'text' keys).
    Modifies 'text' in-place and returns the same list.

    Per-block pipeline (segment-level only — word-level SRT skips all transforms):
      1. CJK script detection — skips uppercase and markers for CJK text
      2. Semantic line wrap with orphan/widow avoidance
      3. Uppercase transform on emphasis-class words (strong level, Latin only)
      4. Emphasis highlight markers (_HL_OPEN/_HL_CLOSE, resolved by _ass_escape_text)

    Emphasis intensity per preset:
      tiktok_bounce_v1 / viral_bold / bold_cap → strong  (numbers, contrast, urgency, hook words)
      story_clean_01                           → medium  (numbers, contrast, emotional, hook words)
      clean_pro                                → subtle  (numbers only)
      boxed_caption                            → minimal (no emphasis transforms)
      pro_karaoke                              → word_only (no transforms — karaoke handles timing)
    """
    if not blocks:
        return blocks

    preset = get_subtitle_preset(preset_id)
    level = _emphasis_level(preset_id)
    mkt = str(market or "US").upper()

    # Word-level SRT detection — skip all text transforms for per-word transcription
    avg_words = sum(len(str(b.get("text") or "").split()) for b in blocks) / max(1, len(blocks))
    is_word_level = len(blocks) >= 6 and avg_words <= 1.5

    affected = 0
    for b in blocks:
        raw = str(b.get("text") or "").strip()
        if not raw:
            continue

        original = raw
        cjk = _is_cjk(raw)

        # Step 1: semantic line wrap
        if not is_word_level:
            raw = _semantic_wrap_block(raw, preset.wrap_max_em)

        # Step 2: uppercase emphasis-class words (strong level, Latin only)
        if not is_word_level and not cjk and level == "strong":
            raw = _uppercase_emphasis_words(raw)

        # Step 3: emphasis highlight markers (not word-level, not minimal/word_only, not CJK)
        if not is_word_level and level not in ("minimal", "word_only") and not cjk:
            raw = _insert_emphasis_markers(raw, mkt, level)

        if raw != original:
            b["text"] = raw
            affected += 1

    logger.info(
        "subtitle_emphasis_applied preset=%s market=%s level=%s blocks=%d "
        "word_level=%s affected=%d",
        preset_id, mkt, level, len(blocks), is_word_level, affected,
    )
    return blocks


# ---------------------------------------------------------------------------
# OQ-1.2 — Subtitle Intelligence: readability resegmentation
# ---------------------------------------------------------------------------

# Reading-speed targets (env-overridable for tuning without code changes).
_INTEL_MAX_WPS: float = float(os.environ.get("SUBTITLE_MAX_WPS", "3.8"))
_INTEL_MAX_WORDS: int = int(os.environ.get("SUBTITLE_MAX_WORDS", "7"))
_INTEL_MIN_DISPLAY_SEC: float = 0.7
_INTEL_GAP_FILL_SEC: float = 0.04

# Punctuation that marks a natural speech pause inside a subtitle block.
_PUNCT_PAUSE_RE = re.compile(r"[,;:—–]$")

# Words that naturally begin a new clause — strong split candidates.
_CLAUSE_STARTERS = frozenset({
    "and", "but", "or", "so", "yet", "nor",
    "because", "although", "though", "since", "until", "unless",
    "when", "where", "while", "if", "that", "which", "who",
    "however", "therefore", "then", "also", "plus",
    # Vietnamese common connectives
    "nhưng", "và", "mà", "rồi", "thì", "nên", "vì",
})


def _find_phrase_split(words: list[str], max_words: int) -> int:
    """Return split index for *words* → two phrase-balanced chunks.

    Priority:
      1. After a word ending in pause-punctuation (, ; : — –), scanning up to
         max_words positions.
      2. Before a clause-starting conjunction nearest the midpoint.
      3. Visual-weight midpoint fallback.

    Always returns 1 ≤ i < len(words).
    """
    n = len(words)
    if n < 2:
        return 1
    mid = n // 2
    search_end = min(n - 1, max(max_words, mid + 2))

    # P1: punctuation pause (start from 0 so "wait," at position 0 is caught)
    for i in range(0, search_end):
        if _PUNCT_PAUSE_RE.search(words[i]):
            return i + 1

    # P2: clause starter nearest midpoint
    best_clause: int | None = None
    best_dist = n
    for i in range(1, min(search_end + 1, n)):
        token = words[i].lower().rstrip(".,!?;:\"'")
        if token in _CLAUSE_STARTERS:
            dist = abs(i - mid)
            if dist < best_dist:
                best_dist = dist
                best_clause = i
    if best_clause is not None:
        return best_clause

    # P3: visual-weight midpoint
    total_w = _approx_visual_width(" ".join(words))
    half = total_w / 2.0
    cum = 0.0
    best_idx = mid
    best_v_dist = float("inf")
    for i, word in enumerate(words[:-1], start=1):
        cum += _approx_visual_width(word + " ")
        v_dist = abs(cum - half)
        if v_dist < best_v_dist:
            best_v_dist = v_dist
            best_idx = i
    return max(1, min(best_idx, n - 1))


def _split_block_semantic(
    text: str,
    start: float,
    end: float,
    max_words: int,
    min_display_sec: float,
) -> list[dict]:
    """Recursively split one SRT block into ≤max_words chunks, redistributing timing."""
    words = text.split()
    n = len(words)
    if n <= max_words:
        return [{"start": start, "end": end, "text": text}]

    split_at = _find_phrase_split(words, max_words)
    left_words = words[:split_at]
    right_words = words[split_at:]

    duration = max(0.001, end - start)
    left_frac = len(left_words) / n
    left_dur = max(min_display_sec, duration * left_frac)
    mid_t = min(end - min_display_sec, start + left_dur)
    mid_t = max(start + min_display_sec, mid_t)

    left_blocks = _split_block_semantic(
        " ".join(left_words), start, mid_t, max_words, min_display_sec,
    )
    right_blocks = _split_block_semantic(
        " ".join(right_words), mid_t, end, max_words, min_display_sec,
    )
    return left_blocks + right_blocks


def resegment_srt_for_readability(
    srt_path: str,
    *,
    max_words: int = _INTEL_MAX_WORDS,
    max_wps: float = _INTEL_MAX_WPS,
    min_display_sec: float = _INTEL_MIN_DISPLAY_SEC,
    gap_fill_sec: float = _INTEL_GAP_FILL_SEC,
) -> int:
    """Re-segment a clip SRT for CapCut-style reading comfort.

    Targets segment-level SRT only (avg words/block > 1.5). Word-level SRT
    (highlight_per_word=True path) is returned immediately — timing there is
    managed by the bounce/karaoke renderer.

    Operations (in order):
      1. Density check: blocks with >max_wps words/sec OR >max_words are split
      2. Semantic split at phrase boundaries (punctuation > conjunction > midpoint)
      3. Timing redistribution proportional to word count
      4. Minimum display enforcement (≥min_display_sec per block)
      5. Gap-fill: sub-gap-fill-sec gaps between consecutive blocks are closed
      6. Clamp: ensure no block extends past its successor's start

    In-place — overwrites srt_path on success.
    Returns number of output blocks (0 on error or skip).
    Safe no-op on any exception.
    """
    try:
        blocks = _parse_srt_blocks(srt_path)
    except Exception:
        return 0
    if not blocks:
        return 0

    avg_words = sum(len(b["text"].split()) for b in blocks) / len(blocks)
    if avg_words <= 1.5:
        return len(blocks)

    out: list[dict] = []
    for b in blocks:
        text = str(b["text"]).strip()
        if not text:
            continue
        start = float(b["start"])
        end = float(b["end"])
        n = len(text.split())
        duration = max(0.001, end - start)
        wps = n / duration

        if n > max_words or wps > max_wps:
            out.extend(_split_block_semantic(text, start, end, max_words, min_display_sec))
        else:
            if duration < min_display_sec:
                end = start + min_display_sec
            out.append({"start": start, "end": end, "text": text})

    if not out:
        return 0

    # Gap-fill pass
    for i in range(len(out) - 1):
        gap = out[i + 1]["start"] - out[i]["end"]
        if 0 < gap <= gap_fill_sec:
            out[i]["end"] = out[i + 1]["start"]

    # Clamp pass — no block may extend past its successor's start
    for i in range(len(out) - 1):
        if out[i]["end"] > out[i + 1]["start"]:
            out[i]["end"] = out[i + 1]["start"]
        if out[i]["end"] <= out[i]["start"]:
            out[i]["end"] = out[i]["start"] + 0.1

    try:
        with Path(srt_path).open("w", encoding="utf-8") as f:
            for idx, b in enumerate(out, start=1):
                f.write(
                    f"{idx}\n"
                    f"{format_srt_timestamp(b['start'])} --> "
                    f"{format_srt_timestamp(b['end'])}\n"
                    f"{b['text']}\n\n"
                )
        logger.info(
            "subtitle_intel_resegment: blocks_in=%d blocks_out=%d avg_words_in=%.1f path=%s",
            len(blocks), len(out), avg_words, Path(srt_path).name,
        )
    except Exception:
        return 0

    return len(out)

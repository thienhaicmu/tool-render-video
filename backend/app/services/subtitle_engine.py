import subprocess
import os
import re
import logging
from pathlib import Path
import time
import whisper

logger = logging.getLogger(__name__)
from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

_MODEL_CACHE = {}
WORD_MIN_GAP_SEC = 0.02
WORD_MIN_DURATION_SEC = 0.12
WORD_MERGE_SHORTER_THAN_SEC = 0.11

# Whisper model cache — redirect to project dir so models stay on D: not C:
_WHISPER_CACHE_DIR: Path = Path(__file__).resolve().parents[3] / "data" / "whisper_cache"
_WHISPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_whisper_model(model_name: str = "base"):
    model = _MODEL_CACHE.get(model_name)
    if model is None:
        model = whisper.load_model(model_name, download_root=str(_WHISPER_CACHE_DIR))
        _MODEL_CACHE[model_name] = model
    return model


def format_srt_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt_timestamp(ts: str) -> float:
    # Format: HH:MM:SS,mmm
    p = ts.strip().replace(".", ",").split(":")
    if len(p) != 3:
        return 0.0
    h = int(p[0])
    m = int(p[1])
    s_ms = p[2].split(",")
    s = int(s_ms[0])
    ms = int(s_ms[1]) if len(s_ms) > 1 else 0
    return (h * 3600) + (m * 60) + s + (ms / 1000.0)


def _parse_srt_blocks(srt_path: str):
    content = Path(srt_path).read_text(encoding="utf-8")
    blocks = []
    for block in content.split("\n\n"):
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        if len(lines) < 3:
            continue
        time_line = lines[1]
        if " --> " not in time_line:
            continue
        start_s, end_s = time_line.split(" --> ", 1)
        start = parse_srt_timestamp(start_s)
        end = parse_srt_timestamp(end_s)
        text = " ".join(lines[2:]).strip()
        if text and end > start:
            blocks.append({"start": start, "end": end, "text": text})
    return blocks


def slice_srt_by_time(
    source_srt_path: str,
    output_srt_path: str,
    start_sec: float,
    end_sec: float,
    rebase_to_zero: bool = True,
    playback_speed: float = 1.0,
) -> dict:
    src_blocks = _parse_srt_blocks(source_srt_path)
    start_sec = max(0.0, float(start_sec))
    end_sec = max(start_sec, float(end_sec))
    try:
        speed = max(0.5, min(1.5, float(playback_speed or 1.0)))
    except Exception:
        speed = 1.0
    selected = []

    for b in src_blocks:
        ov_start = max(start_sec, b["start"])
        ov_end = min(end_sec, b["end"])
        if ov_end <= ov_start:
            continue
        if rebase_to_zero:
            out_start = (ov_start - start_sec) / speed
            out_end = (ov_end - start_sec) / speed
        else:
            out_start = ov_start / speed
            out_end = ov_end / speed
        if out_end <= out_start:
            continue
        selected.append({"start": out_start, "end": out_end, "text": b["text"]})

    with Path(output_srt_path).open("w", encoding="utf-8") as f:
        for idx, seg in enumerate(selected, start=1):
            f.write(
                f"{idx}\n"
                f"{format_srt_timestamp(seg['start'])} --> {format_srt_timestamp(seg['end'])}\n"
                f"{seg['text']}\n\n"
            )
    return {
        "subtitle_count": len(selected),
        "first_start": selected[0]["start"] if selected else None,
        "first_end": selected[0]["end"] if selected else None,
        "last_start": selected[-1]["start"] if selected else None,
        "last_end": selected[-1]["end"] if selected else None,
    }


def slice_srt_to_text(source_srt_path: str, start_sec: float, end_sec: float) -> str:
    """Slice a SRT by time range and return plain text — no temp file written."""
    src_blocks = _parse_srt_blocks(source_srt_path)
    start_sec = max(0.0, float(start_sec))
    end_sec = max(start_sec, float(end_sec))
    texts = [
        b["text"] for b in src_blocks
        if min(end_sec, b["end"]) > max(start_sec, b["start"])
    ]
    return " ".join(texts).strip()


def _run_with_retry(command: list[str], retries: int = 2, wait_sec: float = 0.8):
    attempt = 0
    while True:
        attempt += 1
        try:
            return subprocess.run(command, check=True)
        except Exception:
            if attempt > retries:
                raise
            time.sleep(wait_sec * attempt)


def _transcribe_with_retry(model, audio_path: str, retries: int = 2, wait_sec: float = 0.8, **kwargs):
    attempt = 0
    while True:
        attempt += 1
        try:
            return model.transcribe(audio_path, fp16=False, **kwargs)
        except Exception:
            if attempt > retries:
                raise
            time.sleep(wait_sec * attempt)


def _ensure_ffmpeg_in_path_for_whisper():
    ffmpeg_bin = get_ffmpeg_bin()
    ffmpeg_dir = str(Path(ffmpeg_bin).parent)
    current = os.environ.get("PATH", "")
    if ffmpeg_dir and ffmpeg_dir not in current:
        os.environ["PATH"] = f"{ffmpeg_dir};{current}" if current else ffmpeg_dir


def has_audio_stream(video_path: str) -> bool:
    """Return True when ffprobe can see at least one audio stream."""
    try:
        cmd = [
            get_ffprobe_bin(),
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return bool((result.stdout or "").strip())
    except Exception:
        return False


def transcribe_to_srt(
    video_path: str,
    srt_path: str,
    model_name: str = "base",
    retry_count: int = 2,
    highlight_per_word: bool = False,
):
    """Transcribe audio to SRT.

    When highlight_per_word=True, uses Whisper word_timestamps to produce
    one SRT entry per word — required for word-by-word pop animation.
    Falls back to segment-level if word timestamps are unavailable.
    """
    audio_path = str(Path(srt_path).with_suffix(".wav"))
    _ensure_ffmpeg_in_path_for_whisper()
    _run_with_retry([
        get_ffmpeg_bin(), "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path
    ], retries=retry_count)

    try:
        model = get_whisper_model(model_name)

        if highlight_per_word:
            try:
                result = _transcribe_with_retry(model, audio_path, retries=retry_count, word_timestamps=True)
                _write_word_level_srt(result, srt_path)
                return result
            except Exception:
                # Fallback to segment-level on failure
                pass

        result = _transcribe_with_retry(model, audio_path, retries=retry_count)
        _write_segment_level_srt(result, srt_path)
        return result
    finally:
        # Always remove extracted WAV — avoids orphan if Whisper fails mid-job
        Path(audio_path).unlink(missing_ok=True)


def _write_word_level_srt(result: dict, srt_path: str):
    """Write one SRT entry per word using Whisper word timestamps."""

    def _normalize_words(words: list[dict], seg_start: float, seg_end: float) -> list[dict]:
        items = []
        prev_end = None
        for w in words:
            text = str(w.get("word", "")).strip()
            if not text:
                continue
            start = float(w.get("start", seg_start))
            end = float(w.get("end", seg_end))
            if prev_end is not None and start < (prev_end + WORD_MIN_GAP_SEC):
                start = prev_end + WORD_MIN_GAP_SEC
            if end < (start + WORD_MIN_DURATION_SEC):
                end = start + WORD_MIN_DURATION_SEC
            items.append({"text": text, "start": start, "end": end})
            prev_end = end

        # Merge ultra-short word events to avoid stacked flashes/overlap feeling.
        merged = []
        i = 0
        while i < len(items):
            cur = items[i]
            cur_dur = float(cur["end"] - cur["start"])
            if cur_dur < WORD_MERGE_SHORTER_THAN_SEC and i + 1 < len(items):
                nxt = items[i + 1]
                merged.append({
                    "text": f"{cur['text']} {nxt['text']}".strip(),
                    "start": cur["start"],
                    "end": max(cur["end"], nxt["end"]),
                })
                i += 2
                continue
            merged.append(cur)
            i += 1
        return merged

    idx = 1
    with open(srt_path, "w", encoding="utf-8") as f:
        for seg in result.get("segments", []):
            words = seg.get("words", [])
            if words:
                normalized = _normalize_words(words, float(seg["start"]), float(seg["end"]))
                for w in normalized:
                    f.write(
                        f"{idx}\n"
                        f"{format_srt_timestamp(float(w['start']))} --> {format_srt_timestamp(float(w['end']))}\n"
                        f"{w['text']}\n\n"
                    )
                    idx += 1
            else:
                # No word timestamps for this segment — fall back to full segment text
                text = seg.get("text", "").strip()
                if text:
                    f.write(
                        f"{idx}\n"
                        f"{format_srt_timestamp(seg['start'])} --> {format_srt_timestamp(seg['end'])}\n"
                        f"{text}\n\n"
                    )
                    idx += 1


def _write_segment_level_srt(result: dict, srt_path: str):
    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(result.get("segments", []), start=1):
            start_ts = format_srt_timestamp(seg["start"])
            end_ts = format_srt_timestamp(seg["end"])
            text = seg["text"].strip()
            if text:
                f.write(f"{idx}\n{start_ts} --> {end_ts}\n{text}\n\n")


# ---------------------------------------------------------------------------
# ASS style definitions
# ---------------------------------------------------------------------------

def _resolve_ass_style(
    subtitle_style: str = "tiktok_bounce_v1",
    scale_y: int = 106,
    highlight_per_word: bool = True,
    font_name: str = "Bungee",
    margin_v: int = 180,
):
    """Return (style_line, line_fx) for the requested subtitle style.

    line_fx is prepended to each Dialogue text field (ASS override tags).
    For word-by-word mode, line_fx includes a pop-in bounce animation.
    """
    style = (subtitle_style or "tiktok_bounce_v1").lower()

    # --- Bounce pop-in tag: scale from 118% → 100% over 220ms ---
    BOUNCE_FX = r"{\fscx118\fscy118\t(0,220,\fscx100\fscy100)}"

    safe_font = (font_name or "Bungee").replace(",", " ").strip() or "Bungee"

    if style == "viral_clean_montserrat":
        line_fx = BOUNCE_FX if highlight_per_word else ""
        return (
            f"Style: Default,{safe_font},34,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,100,{scale_y},0,0,1,3,1,2,30,30,{margin_v},1",
            line_fx,
        )
    if style == "viral_soft_poppins":
        line_fx = BOUNCE_FX if highlight_per_word else ""
        return (
            f"Style: Default,{safe_font},32,&H00F0F0F0,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,100,{scale_y},0,0,1,3,1,2,30,30,{margin_v},1",
            line_fx,
        )
    if style == "viral_pop_anton":
        line_fx = BOUNCE_FX if highlight_per_word else r"{\bord3\fscx100\fscy108}"
        return (
            f"Style: Default,{safe_font},40,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,100,{scale_y},0,0,1,3,1,2,30,30,{margin_v},1",
            line_fx,
        )
    if style == "viral_compact_barlow":
        line_fx = BOUNCE_FX if highlight_per_word else ""
        return (
            f"Style: Default,{safe_font},36,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,100,{scale_y},0,0,1,3,1,2,30,30,{margin_v},1",
            line_fx,
        )
    if style == "clean_bold_01":
        return (
            f"Style: Default,{safe_font},34,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,{scale_y},0,0,1,3,1,2,30,30,{margin_v},1",
            BOUNCE_FX if highlight_per_word else "",
        )
    if style == "story_clean_01":
        return (
            f"Style: Default,{safe_font},32,&H00F6F6F6,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,100,{scale_y},0,0,1,3,0,2,40,40,{margin_v},1",
            BOUNCE_FX if highlight_per_word else "",
        )

    # Default / tiktok_bounce_v1 — Bungee font, word-by-word bounce
    if highlight_per_word:
        return (
            f"Style: Default,{safe_font},38,&H00FFFFFF,&H0000FFFF,&H00000000,&H90000000,0,0,0,0,100,{scale_y},0,0,1,3,1,2,30,30,{margin_v},1",
            BOUNCE_FX,
        )
    # Segment mode
    return (
        f"Style: Default,{safe_font},34,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,100,{scale_y},0,0,1,3,1,2,30,30,{margin_v},1",
        "",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp format H:MM:SS.cc"""
    cs = int(round(seconds * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ---------------------------------------------------------------------------
# SRT → ASS conversion
# ---------------------------------------------------------------------------

def srt_to_ass_bounce(
    srt_path: str,
    ass_path: str,
    subtitle_style: str = "tiktok_bounce_v1",
    scale_y: int = 106,
    highlight_per_word: bool = True,
    font_name: str = "Bungee",
    margin_v: int = 180,
    play_res_y: int = 1440,
    x_percent: float = 50.0,
):
    ass_style, line_fx = _resolve_ass_style(
        subtitle_style,
        scale_y,
        highlight_per_word,
        font_name=font_name,
        margin_v=margin_v,
    )
    # Inject \pos(x,y) when subtitle is not centered (>0.5% off 50%).
    # Uses PlayRes coordinates — libass scales to actual video size.
    # Default x_percent=50 → no tag → backward-compatible with existing renders.
    _pos_tag = ""
    if abs(x_percent - 50.0) > 0.5:
        _px = round(1080 * x_percent / 100)
        _py = play_res_y - margin_v
        _pos_tag = "{\\pos(" + str(_px) + "," + str(_py) + ")}"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{ass_style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    out = [header]
    for block in Path(srt_path).read_text(encoding="utf-8").split("\n\n"):
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        if len(lines) < 3:
            continue
        time_line = lines[1]
        if " --> " not in time_line:
            continue
        start_s, end_s = time_line.split(" --> ", 1)
        start_ass = _ass_time(parse_srt_timestamp(start_s))
        end_ass   = _ass_time(parse_srt_timestamp(end_s))
        text = " ".join(lines[2:]).replace("{", "(").replace("}", ")")
        out.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{_pos_tag}{line_fx}{text}\n")
    Path(ass_path).write_text("".join(out), encoding="utf-8")
    logger.info("srt_to_ass_bounce: style=%s play_res_y=%d margin_v=%d -> %s", subtitle_style, play_res_y, margin_v, ass_path)
    return ass_path


# ---------------------------------------------------------------------------
# Pro Karaoke subtitle (srt_to_ass_karaoke)
# ---------------------------------------------------------------------------

def _hex_to_ass(hex_color: str, alpha: int = 0) -> str:
    """Convert CSS #RRGGBB to ASS &HAABBGGRR colour string."""
    h = hex_color.lstrip("#")
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        r, g, b = 255, 255, 255
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def srt_to_ass_karaoke(
    srt_path: str,
    ass_path: str,
    words_per_group: int = 4,
    scale_y: int = 106,
    font_size: int = 46,
    font_name: str = "Bungee",
    margin_v: int = 180,
    play_res_y: int = 1440,
    highlight_color: str = "&H0000FFFF",   # yellow (ASS BGR: 00FFFF = yellow)
    base_color: str = "&H00FFFFFF",         # white
    outline_color: str = "&H00000000",      # black outline
    back_color: str = "&H90000000",         # semi-transparent shadow
    outline_size: int = 3,
    shadow_size: int = 1,
    x_percent: float = 50.0,
):
    """Pro karaoke-style subtitle.

    Hiển thị nhóm từ cùng lúc, từ đang nói được highlight màu vàng.
    Style giống MrBeast / viral TikTok.

    Yêu cầu: srt_path là word-level SRT (mỗi entry = 1 từ).
    """
    blocks = _parse_srt_blocks(srt_path)
    if not blocks:
        return srt_to_ass_bounce(srt_path, ass_path, scale_y=scale_y, margin_v=margin_v, play_res_y=play_res_y)

    # Group words into chunks
    groups: list[list[dict]] = []
    for i in range(0, len(blocks), words_per_group):
        chunk = blocks[i:i + words_per_group]
        if chunk:
            groups.append(chunk)

    # ASS style — 2 colours: primary (base) + secondary (highlight during karaoke)
    style_line = (
        f"Style: Default,{font_name},{font_size},"
        f"{base_color},{highlight_color},"
        f"{outline_color},{back_color},"
        f"0,0,0,0,100,{scale_y},0,0,1,{outline_size},{shadow_size},"
        f"2,30,30,{margin_v},1"
    )

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_line}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Inject \pos(x,y) when subtitle is not centered. Default 50 → no tag.
    _pos_tag = ""
    if abs(x_percent - 50.0) > 0.5:
        _px = round(1080 * x_percent / 100)
        _py = play_res_y - margin_v
        _pos_tag = "{\\pos(" + str(_px) + "," + str(_py) + ")}"

    out = [header]
    for group in groups:
        g_start = group[0]["start"]
        g_end = group[-1]["end"]

        # Build karaoke text: {\kN}word  (N = duration in centiseconds)
        parts = []
        for w in group:
            dur_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            word = w["text"].replace("{", "(").replace("}", ")")
            parts.append(f"{{\\k{dur_cs}}}{word}")

        text = " ".join(parts)
        out.append(
            f"Dialogue: 0,{_ass_time(g_start)},{_ass_time(g_end)},"
            f"Default,,0,0,0,,{_pos_tag}{text}\n"
        )

    Path(ass_path).write_text("".join(out), encoding="utf-8")
    logger.info("srt_to_ass_karaoke: play_res_y=%d margin_v=%d words_per_group=%d -> %s", play_res_y, margin_v, words_per_group, ass_path)
    return ass_path


# ---------------------------------------------------------------------------
# Subtitle burn-in
# ---------------------------------------------------------------------------

def _safe_filter_path(p: str) -> str:
    """Escape a file path for use inside an ffmpeg filter option value."""
    return p.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def burn_subtitle_onto_video(
    input_path: str,
    ass_path: str,
    output_path: str,
    fonts_dir: str | None = None,
    retry_count: int = 2,
):
    """Burn an ASS subtitle file onto a video using ffmpeg.

    Raises FileNotFoundError if ass_path does not exist (instead of silently
    dropping the subtitle and producing a video without captions).
    """
    ass_file = Path(ass_path)
    if not ass_file.exists():
        raise FileNotFoundError(f"ASS subtitle file not found: {ass_path}")

    safe_ass = _safe_filter_path(str(ass_file.resolve()))
    if fonts_dir and Path(fonts_dir).is_dir():
        safe_fonts = _safe_filter_path(str(Path(fonts_dir).resolve()))
        vf = f"ass='{safe_ass}':fontsdir='{safe_fonts}'"
    else:
        vf = f"ass='{safe_ass}'"

    cmd = [
        get_ffmpeg_bin(), "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:a", "copy",
        output_path,
    ]
    _run_with_retry(cmd, retries=retry_count)


def apply_market_line_break_to_srt(srt_path: str, market_payload: dict) -> str:
    """Re-wrap SRT subtitle lines to the market/tone word-count ceiling.

    Called after subtitle text is finalized, before the SRT is consumed further.
    Safe no-op when market_payload is falsy or any error occurs.
    """
    if not market_payload:
        return srt_path
    try:
        from app.services.market_subtitle_policy import (
            get_market_subtitle_policy,
            break_text_by_words,
            highlight_keywords_in_text,
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
        with Path(srt_path).open("w", encoding="utf-8") as f:
            for idx, b in enumerate(blocks, start=1):
                text = break_text_by_words(b["text"], max_w)
                if do_highlight:
                    text = highlight_keywords_in_text(text, keywords, market)
                f.write(
                    f"{idx}\n"
                    f"{format_srt_timestamp(b['start'])} --> {format_srt_timestamp(b['end'])}\n"
                    f"{text}\n\n"
                )
    except Exception:
        pass
    return srt_path


# ---------------------------------------------------------------------------
# P4-2 — Hook subtitle impact formatting
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


def format_hook_subtitle(text: str) -> str:
    """Format one subtitle block for hook/first-clip visual impact.

    - Normalises whitespace and collapses newlines to one line
    - Returns original unchanged when text < 20 chars
    - For short segments (≤ 4 words): uppercases detected emphasis words in place
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
    split_at = min(4, total - 2)  # default: ~4 words on line 1, ≥2 on line 2
    for i in range(min(6, total - 1)):
        if _is_emphasis(words[i]):
            split_at = i + 1

    # Clamp: line 1 = 2–6 words, line 2 always has ≥ 1 word
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

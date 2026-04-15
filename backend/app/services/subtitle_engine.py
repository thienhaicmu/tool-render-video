import subprocess
import os
from pathlib import Path
import time
import whisper
from app.services.bin_paths import get_ffmpeg_bin

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
):
    src_blocks = _parse_srt_blocks(source_srt_path)
    start_sec = max(0.0, float(start_sec))
    end_sec = max(start_sec, float(end_sec))
    selected = []

    for b in src_blocks:
        ov_start = max(start_sec, b["start"])
        ov_end = min(end_sec, b["end"])
        if ov_end <= ov_start:
            continue
        if rebase_to_zero:
            out_start = ov_start - start_sec
            out_end = ov_end - start_sec
        else:
            out_start = ov_start
            out_end = ov_end
        selected.append({"start": out_start, "end": out_end, "text": b["text"]})

    with Path(output_srt_path).open("w", encoding="utf-8") as f:
        for idx, seg in enumerate(selected, start=1):
            f.write(
                f"{idx}\n"
                f"{format_srt_timestamp(seg['start'])} --> {format_srt_timestamp(seg['end'])}\n"
                f"{seg['text']}\n\n"
            )
    return output_srt_path


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

    model = get_whisper_model(model_name)

    if highlight_per_word:
        try:
            result = _transcribe_with_retry(model, audio_path, retries=retry_count, word_timestamps=True)
            _write_word_level_srt(result, srt_path)
            try:
                Path(audio_path).unlink(missing_ok=True)
            except Exception:
                pass
            return result
        except Exception:
            # Fallback to segment-level on failure
            pass

    result = _transcribe_with_retry(model, audio_path, retries=retry_count)
    _write_segment_level_srt(result, srt_path)
    try:
        Path(audio_path).unlink(missing_ok=True)
    except Exception:
        pass
    return result


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
    margin_v: int = 170,
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
            f"Style: Default,{safe_font},34,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,{scale_y},0,0,1,3,1,2,30,30,165,1",
            BOUNCE_FX if highlight_per_word else "",
        )
    if style == "story_clean_01":
        return (
            f"Style: Default,{safe_font},32,&H00F6F6F6,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,100,{scale_y},0,0,1,2,0,2,40,40,165,1",
            BOUNCE_FX if highlight_per_word else "",
        )

    # Default / tiktok_bounce_v1 — Bungee font, word-by-word bounce
    if highlight_per_word:
        return (
            f"Style: Default,{safe_font},38,&H00FFFFFF,&H0000FFFF,&H00000000,&H90000000,0,0,0,0,100,{scale_y},0,0,1,3,1,2,30,30,175,1",
            BOUNCE_FX,
        )
    # Segment mode
    return (
        f"Style: Default,{safe_font},34,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,0,0,0,0,100,{scale_y},0,0,1,3,1,2,30,30,165,1",
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
    margin_v: int = 170,
):
    ass_style, line_fx = _resolve_ass_style(
        subtitle_style,
        scale_y,
        highlight_per_word,
        font_name=font_name,
        margin_v=margin_v,
    )
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1440
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_line}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""".format(style_line=ass_style)
    out = [header]
    for block in Path(srt_path).read_text(encoding="utf-8").split("\n\n"):
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        if len(lines) < 3:
            continue
        times = lines[1].replace(",", ".").split(" --> ")
        text = " ".join(lines[2:]).replace("{", "(").replace("}", ")")
        out.append(f"Dialogue: 0,{times[0]},{times[1]},Default,,0,0,0,,{line_fx}{text}\n")
    Path(ass_path).write_text("".join(out), encoding="utf-8")
    return ass_path


# ---------------------------------------------------------------------------
# Pro Karaoke subtitle
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
    margin_v: int = 170,
    highlight_color: str = "&H0000FFFF",   # yellow (ASS BGR: 00FFFF = yellow)
    base_color: str = "&H00FFFFFF",         # white
    outline_color: str = "&H00000000",      # black outline
    back_color: str = "&H90000000",         # semi-transparent shadow
    outline_size: int = 3,
    shadow_size: int = 1,
):
    """Pro karaoke-style subtitle.

    Hiển thị nhóm từ cùng lúc, từ đang nói được highlight màu vàng.
    Style giống MrBeast / viral TikTok.

    Yêu cầu: srt_path là word-level SRT (mỗi entry = 1 từ).
    """
    blocks = _parse_srt_blocks(srt_path)
    if not blocks:
        return srt_to_ass_bounce(srt_path, ass_path, scale_y=scale_y)

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
PlayResY: 1440
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_line}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

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
            f"Default,,0,0,0,,{text}\n"
        )

    Path(ass_path).write_text("".join(out), encoding="utf-8")
    return ass_path

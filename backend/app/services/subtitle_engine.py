import subprocess
import os
import re
import logging
from pathlib import Path
import time
import threading
from dataclasses import dataclass
import whisper

logger = logging.getLogger(__name__)
from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

_MODEL_CACHE = {}
_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_TRANSCRIBE_LOCKS = {}
WORD_MIN_GAP_SEC = 0.02
WORD_MIN_DURATION_SEC = 0.12
WORD_MERGE_SHORTER_THAN_SEC = 0.11
_HL_OPEN = "\ue100"
_HL_CLOSE = "\ue101"

# Whisper model cache — redirect to project dir so models stay on D: not C:
_WHISPER_CACHE_DIR: Path = Path(__file__).resolve().parents[3] / "data" / "whisper_cache"
_WHISPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Replaced by preset-table auto_scale / heavy_scale fields — see ASSPreset below.


def _compute_subtitle_scale(play_res_x: int = 1080, play_res_y: int = 1440) -> dict:
    base = min(max(1, int(play_res_x)), max(1, int(play_res_y)))
    return {
        "font_size": max(24, int(base * 0.05)),
        "outline":   max(1, round(base * 0.003)),
        "shadow":    max(1, round(base * 0.004)),
    }


def _compute_margin_v(play_res_x: int = 1080, play_res_y: int = 1440) -> int:
    ratio = play_res_y / max(1, int(play_res_x))
    if ratio >= 1.6:
        return int(play_res_y * 0.18)
    if ratio >= 1.2:
        return int(play_res_y * 0.24)
    return int(play_res_y * 0.30)


def get_whisper_model(model_name: str = "base"):
    with _MODEL_CACHE_LOCK:
        model = _MODEL_CACHE.get(model_name)
        if model is None:
            model = whisper.load_model(model_name, download_root=str(_WHISPER_CACHE_DIR))
            _MODEL_CACHE[model_name] = model
        return model


def _get_transcribe_lock(model_name: str):
    with _MODEL_CACHE_LOCK:
        lock = _MODEL_TRANSCRIBE_LOCKS.get(model_name)
        if lock is None:
            lock = threading.Lock()
            _MODEL_TRANSCRIBE_LOCKS[model_name] = lock
        return lock


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


def parse_srt_blocks(srt_path: str) -> list[dict]:
    """Parse SRT file into a list of {start, end, text} dicts for round-trip editing.

    Unlike the internal _parse_srt_blocks, multi-line text within a block is joined
    with \\n so that write_srt_blocks() faithfully preserves line breaks.
    """
    content = Path(srt_path).read_text(encoding="utf-8")
    blocks: list[dict] = []
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
        text = "\n".join(lines[2:]).strip()
        if text and end > start:
            blocks.append({"start": start, "end": end, "text": text})
    return blocks


def write_srt_blocks(blocks: list[dict], srt_path: str) -> None:
    """Write parsed SRT blocks back to a file in standard SRT format.

    Preserves timing, block order, and multi-line text (\\n within text is kept).
    """
    with Path(srt_path).open("w", encoding="utf-8") as f:
        for idx, b in enumerate(blocks, start=1):
            f.write(
                f"{idx}\n"
                f"{format_srt_timestamp(b['start'])} --> {format_srt_timestamp(b['end'])}\n"
                f"{b['text']}\n\n"
            )


def slice_srt_by_time(
    source_srt_path: str,
    output_srt_path: str,
    start_sec: float,
    end_sec: float,
    rebase_to_zero: bool = True,
    playback_speed: float = 1.0,
    apply_playback_speed: bool = True,
) -> dict:
    src_blocks = _parse_srt_blocks(source_srt_path)
    start_sec = max(0.0, float(start_sec))
    end_sec = max(start_sec, float(end_sec))
    try:
        speed = max(0.5, min(1.5, float(playback_speed or 1.0)))
    except Exception:
        speed = 1.0
    time_scale = speed if apply_playback_speed else 1.0
    selected = []

    for b in src_blocks:
        ov_start = max(start_sec, b["start"])
        ov_end = min(end_sec, b["end"])
        if ov_end <= ov_start:
            continue
        if rebase_to_zero:
            out_start = (ov_start - start_sec) / time_scale
            out_end = (ov_end - start_sec) / time_scale
        else:
            out_start = ov_start / time_scale
            out_end = ov_end / time_scale
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
        "playback_speed": speed,
        "apply_playback_speed": bool(apply_playback_speed),
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
            return subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            if attempt > retries:
                stderr_tail = (exc.stderr or "")[-1000:].strip()
                raise RuntimeError(
                    f"FFmpeg failed (exit={exc.returncode})"
                    + (f": {stderr_tail}" if stderr_tail else "")
                ) from exc
            time.sleep(wait_sec * attempt)
        except Exception:
            if attempt > retries:
                raise
            time.sleep(wait_sec * attempt)


def _transcribe_with_retry(model, audio_path: str, retries: int = 2, wait_sec: float = 0.8, transcribe_lock=None, **kwargs):
    attempt = 0
    while True:
        attempt += 1
        try:
            if transcribe_lock is None:
                return model.transcribe(audio_path, fp16=False, **kwargs)
            with transcribe_lock:
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
    """Return True when the file has at least one audio stream (uses cached probe).

    Delegates to render_engine._has_audio_stream() which wraps the shared cached
    probe_video_metadata() call — zero subprocess cost on repeat calls to the same
    unmodified file.  Deferred import avoids pulling render_engine into the module
    namespace at import time.
    """
    from app.services.render_engine import _has_audio_stream
    return _has_audio_stream(video_path)


def extract_audio_for_transcription(video_path: str, wav_path: str, retry_count: int = 2) -> None:
    """Extract 16 kHz mono WAV from *video_path* for speech transcription engines.

    Used by both the default Whisper path and the faster-whisper adapter so that
    audio extraction logic lives in one place.  The caller is responsible for
    deleting *wav_path* after transcription completes.
    """
    _ensure_ffmpeg_in_path_for_whisper()
    _run_with_retry(
        [
            get_ffmpeg_bin(), "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav_path,
        ],
        retries=retry_count,
    )


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
        transcribe_lock = _get_transcribe_lock(model_name)

        if highlight_per_word:
            try:
                result = _transcribe_with_retry(model, audio_path, retries=retry_count, transcribe_lock=transcribe_lock, word_timestamps=True)
                _write_word_level_srt(result, srt_path)
                return result
            except Exception as exc:
                logger.warning(
                    "word_level_transcription_failed model=%s audio=%s error=%s fallback=segment_level",
                    model_name,
                    Path(audio_path).name,
                    exc,
                )

        result = _transcribe_with_retry(model, audio_path, retries=retry_count, transcribe_lock=transcribe_lock)
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
# ASS Preset architecture
# ---------------------------------------------------------------------------

# Legacy constant — preserved for backward-compatible imports. Internal code uses _get_motion_fx().
BOUNCE_FX = r"{\fscx122\fscy122\t(0,200,\fscx100\fscy100)}"

# OQ-1.4: Per-preset pop-in motion profiles.
# Energetic presets: higher scale, faster settle.
# Editorial presets: softer micro-pop (108-106%), longer settle (160ms).
# bounce_fx=False presets never reach this — caller guards on preset.bounce_fx.
_PRESET_MOTION_FX: dict[str, str] = {
    # Energetic — Anton at large sizes reads best with snap-fast settle
    "viral":            r"{\fscx115\fscy115\t(0,140,\fscx100\fscy100)}",
    "gaming":           r"{\fscx115\fscy115\t(0,140,\fscx100\fscy100)}",
    # Classic TikTok — punchy but softer than pre-OQ-1.4 (was 122%/200ms)
    "tiktok_bounce_v1": r"{\fscx112\fscy112\t(0,150,\fscx100\fscy100)}",
    "viral_bold":       r"{\fscx112\fscy112\t(0,150,\fscx100\fscy100)}",
    "bold_cap":         r"{\fscx112\fscy112\t(0,150,\fscx100\fscy100)}",
    # Editorial / story — soft micro-pop: gentle entry, longer settle
    "story_clean_01":   r"{\fscx108\fscy108\t(0,160,\fscx100\fscy100)}",
    "clean_pro":        r"{\fscx106\fscy106\t(0,160,\fscx100\fscy100)}",
}
_MOTION_FX_DEFAULT = r"{\fscx112\fscy112\t(0,150,\fscx100\fscy100)}"


def _get_motion_fx(preset_id: str) -> str:
    """Return the ASS pop-in animation tag for preset_id."""
    return _PRESET_MOTION_FX.get(preset_id, _MOTION_FX_DEFAULT)


@dataclass(frozen=True)
class ASSPreset:
    """Immutable descriptor for one ASS subtitle style."""
    id: str
    font_default: str
    base_font_size: int
    primary_color: str      # &HAABBGGRR — text fill
    secondary_color: str    # &HAABBGGRR — karaoke highlight sweep
    outline_color: str      # &HAABBGGRR — outline / box border
    back_color: str         # &HAABBGGRR — drop shadow / box fill
    bold: int               # -1 = bold, 0 = normal
    border_style: int       # 1 = outline+shadow, 3 = opaque box (boxed_caption)
    outline_default: int    # Default outline px (box padding when BorderStyle=3)
    shadow_default: int     # Default shadow depth px
    alignment: int          # ASS numpad alignment (2 = bottom-center)
    margin_l: int
    margin_r: int
    wrap_max_em: float      # Visual-width limit for _break_by_visual_width
    bounce_fx: bool         # Whether pop-in animation fires on this preset
    auto_scale: bool        # Font/outline/shadow scale with resolution when font_size=0
    heavy_scale: bool       # Use heavier viral_bold formula vs standard _compute_subtitle_scale
    margin_v_ratio: float   # 0.0 = use margin arg; >0 = override as ratio of play_res_y
    spacing: float = 0.0   # ASS Spacing field — letter-spacing in pixels


# Canonical preset table — one entry per supported style ID.
_PRESETS: dict[str, ASSPreset] = {
    "tiktok_bounce_v1": ASSPreset(
        id="tiktok_bounce_v1", font_default="Bungee", base_font_size=38,
        primary_color="&H00FFFFFF", secondary_color="&H0000FFFF",
        outline_color="&H00000000", back_color="&H90000000",
        bold=0, border_style=1, outline_default=4, shadow_default=2,
        alignment=2, margin_l=30, margin_r=30, wrap_max_em=16.0,
        bounce_fx=True, auto_scale=False, heavy_scale=False, margin_v_ratio=0.0,
        spacing=0.3,
    ),
    "bold_cap": ASSPreset(
        id="bold_cap", font_default="Bungee", base_font_size=48,
        primary_color="&H00FFFFFF", secondary_color="&H0000FFFF",
        outline_color="&H00000000", back_color="&H90000000",
        bold=-1, border_style=1, outline_default=4, shadow_default=2,
        alignment=2, margin_l=30, margin_r=30, wrap_max_em=16.0,
        bounce_fx=True, auto_scale=True, heavy_scale=True, margin_v_ratio=0.20,
        spacing=0.3,
    ),
    "story_clean_01": ASSPreset(
        id="story_clean_01", font_default="Montserrat", base_font_size=32,
        primary_color="&H00F6F6F6", secondary_color="&H0000FFFF",
        outline_color="&H00000000", back_color="&H80000000",
        bold=0, border_style=1, outline_default=3, shadow_default=1,
        alignment=2, margin_l=40, margin_r=40, wrap_max_em=16.0,
        bounce_fx=True, auto_scale=False, heavy_scale=False, margin_v_ratio=0.0,
        spacing=0.5,
    ),
    "viral_bold": ASSPreset(
        id="viral_bold", font_default="Bungee", base_font_size=46,
        primary_color="&H00FFFFFF", secondary_color="&H0015CCFA",
        outline_color="&H00000000", back_color="&HAA000000",
        bold=-1, border_style=1, outline_default=4, shadow_default=2,
        alignment=2, margin_l=30, margin_r=30, wrap_max_em=16.0,
        bounce_fx=True, auto_scale=True, heavy_scale=True, margin_v_ratio=0.20,
        spacing=0.4,
    ),
    "clean_pro": ASSPreset(
        id="clean_pro", font_default="Inter", base_font_size=38,
        primary_color="&H00FFFFFF", secondary_color="&H0000FFFF",
        outline_color="&H00000000", back_color="&H80000000",
        bold=-1, border_style=1, outline_default=3, shadow_default=1,
        alignment=2, margin_l=40, margin_r=40, wrap_max_em=16.0,
        bounce_fx=True, auto_scale=True, heavy_scale=False, margin_v_ratio=0.0,
        spacing=0.6,
    ),
    "boxed_caption": ASSPreset(
        id="boxed_caption", font_default="Bungee", base_font_size=32,
        primary_color="&H00FFFFFF", secondary_color="&H0000FFFF",
        outline_color="&H00000000", back_color="&HC0000000",
        bold=0, border_style=3, outline_default=10, shadow_default=0,
        alignment=2, margin_l=20, margin_r=20, wrap_max_em=16.0,
        bounce_fx=False, auto_scale=True, heavy_scale=False, margin_v_ratio=0.0,
        spacing=0.4,
    ),

    # ── Creator personality presets (QUALITY-UP6) ────────────────────────────
    # Four content-type-native styles. Each has a distinct visual identity
    # while using the bundled Bungee font for render safety.

    # viral: TikTok/Reels-native. Bold, thick outline, short punchy lines.
    # Good for: commentary, reaction, hook-heavy shorts.
    "viral": ASSPreset(
        id="viral", font_default="Anton", base_font_size=50,
        primary_color="&H00FFFFFF", secondary_color="&H0000E5FF",
        outline_color="&H00000000", back_color="&H00000000",
        bold=-1, border_style=1, outline_default=5, shadow_default=2,
        alignment=2, margin_l=20, margin_r=20, wrap_max_em=13.0,
        bounce_fx=True, auto_scale=True, heavy_scale=True, margin_v_ratio=0.22,
        spacing=0.5,
    ),

    # clean: minimal, premium readability. Thin outline, no bounce, wide margins.
    # Good for: education, tutorial, podcast clips.
    "clean": ASSPreset(
        id="clean", font_default="Inter", base_font_size=34,
        primary_color="&H00FFFFFF", secondary_color="&H0080CCFF",
        outline_color="&H00000000", back_color="&H40000000",
        bold=0, border_style=1, outline_default=2, shadow_default=1,
        alignment=2, margin_l=60, margin_r=60, wrap_max_em=18.0,
        bounce_fx=False, auto_scale=True, heavy_scale=False, margin_v_ratio=0.0,
        spacing=1.0,
    ),

    # story: cinematic, soft. Off-white text, minimal outline, serene pacing.
    # Good for: vlog, storytelling, emotional content.
    "story": ASSPreset(
        id="story", font_default="Montserrat", base_font_size=33,
        primary_color="&H00EBEBEB", secondary_color="&H0066CCFF",
        outline_color="&H00000000", back_color="&H20000000",
        bold=0, border_style=1, outline_default=2, shadow_default=1,
        alignment=2, margin_l=55, margin_r=55, wrap_max_em=19.0,
        bounce_fx=False, auto_scale=True, heavy_scale=False, margin_v_ratio=0.0,
        spacing=1.0,
    ),

    # gaming: caption-box style for fast-motion readability. Bold, box-backed.
    # Good for: gaming, sports, montage clips.
    "gaming": ASSPreset(
        id="gaming", font_default="Anton", base_font_size=44,
        primary_color="&H00FFFFFF", secondary_color="&H0000FFFF",
        outline_color="&H00000000", back_color="&HB0000000",
        bold=-1, border_style=3, outline_default=12, shadow_default=0,
        alignment=2, margin_l=20, margin_r=20, wrap_max_em=13.0,
        bounce_fx=True, auto_scale=True, heavy_scale=True, margin_v_ratio=0.20,
        spacing=0.3,
    ),
}

# Legacy alias table — maps removed/renamed style IDs to canonical preset IDs.
# Backward-compatible: old saved job configs and API calls continue to work.
_STYLE_ALIASES: dict[str, str] = {
    "viral_clean_montserrat": "tiktok_bounce_v1",
    "viral_soft_poppins":     "tiktok_bounce_v1",
    "viral_pop_anton":        "tiktok_bounce_v1",
    "viral_compact_barlow":   "tiktok_bounce_v1",
    "clean_bold_01":          "clean_pro",
}

_DEFAULT_PRESET_ID = "tiktok_bounce_v1"


def normalize_subtitle_style_id(style_id: str) -> str:
    """Normalize a style ID: lowercase → resolve alias → fall back to default."""
    sid = (style_id or _DEFAULT_PRESET_ID).lower().strip()
    sid = _STYLE_ALIASES.get(sid, sid)
    return sid if sid in _PRESETS else _DEFAULT_PRESET_ID


def get_subtitle_preset(style_id: str) -> ASSPreset:
    """Return the ASSPreset for style_id after alias resolution."""
    return _PRESETS[normalize_subtitle_style_id(style_id)]


def build_ass_style_line(
    preset: ASSPreset,
    play_res_x: int,
    play_res_y: int,
    scale_y: int,
    font_name: str,
    margin_v: int,
    font_size: int = 0,
    outline_size: int = 0,
    shadow_size: int = 0,
    highlight_per_word: bool = True,
) -> tuple[str, str]:
    """Build an ASS Style line and per-dialogue line_fx tag from a preset.

    Returns (style_line, line_fx).
    line_fx is the override tag prepended to each Dialogue Text field.

    Resolution of font/outline/shadow:
      auto_scale=True  + font_size=0  → computed from play_res (heavy or standard formula)
      auto_scale=False or font_size>0 → explicit value, else preset default
    """
    safe_font = (font_name or preset.font_default).replace(",", " ").strip() or preset.font_default

    # --- Resolve font / outline / shadow ---
    eff_back = preset.back_color
    if preset.auto_scale and font_size == 0:
        if preset.heavy_scale:
            # Heavy formula: viral_bold / bold_cap — larger font, heavier outline
            _base = min(max(1, int(play_res_x)), max(1, int(play_res_y)))
            eff_font_size = max(24, int(_base * 0.055))
            eff_outline   = max(1, round(_base * 0.0035))
            eff_shadow    = max(1, round(_base * 0.002))
        else:
            _sc = _compute_subtitle_scale(play_res_x, play_res_y)
            eff_font_size = _sc["font_size"]
            eff_outline   = _sc["outline"]
            eff_shadow    = _sc["shadow"]
    else:
        eff_font_size = max(12, min(120, font_size)) if font_size > 0 else preset.base_font_size
        eff_outline   = outline_size if outline_size > 0 else preset.outline_default
        eff_shadow    = shadow_size  if shadow_size  > 0 else preset.shadow_default
        # tiktok_bounce_v1 segment mode: slightly lighter values for multi-word blocks
        if not highlight_per_word and preset.id == "tiktok_bounce_v1":
            eff_font_size = max(12, eff_font_size - 4)
            eff_outline   = max(1, eff_outline - 1)
            eff_shadow    = max(1, eff_shadow - 1)
            eff_back = "&H80000000"

    # --- Build style line ---
    # ASS v4+ field order (23 fields):
    # Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour,
    # Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle,
    # BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
    style_line = (
        f"Style: Default,{safe_font},{eff_font_size},"
        f"{preset.primary_color},{preset.secondary_color},"
        f"{preset.outline_color},{eff_back},"
        f"{preset.bold},0,0,0,"
        f"100,{scale_y},{preset.spacing:.1f},0,"
        f"{preset.border_style},{eff_outline},{eff_shadow},"
        f"{preset.alignment},{preset.margin_l},{preset.margin_r},{margin_v},1"
    )
    line_fx = _get_motion_fx(preset.id) if (preset.bounce_fx and highlight_per_word) else ""
    return style_line, line_fx


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


def _ass_escape_text(text: str) -> str:
    """Escape a plain-text string for safe embedding in an ASS Dialogue Text field.

    ASS treats `{...}` as override-tag blocks and `\\N` / `\\n` as hard newlines.
    Literal braces must be replaced; literal backslashes must be escaped first.
    Python `\\n` newlines are converted to ASS soft-wrap (`\\N`).
    """
    text = text.replace("\\", "\\\\ ")   # escape existing backslashes
    text = text.replace("{", "(").replace("}", ")")   # braces → parens (ASS override guard)
    text = text.replace("\n", r"\N")     # Python newline → ASS hard-newline
    text = re.sub(
        f"{_HL_OPEN}([A-Z]{{2}}):(.*?){_HL_CLOSE}",
        lambda m: f"{_ass_highlight_tags(m.group(1))[0]}{m.group(2)}{_ass_highlight_tags(m.group(1))[1]}",
        text,
    )
    text = text.replace(_HL_OPEN, "").replace(_HL_CLOSE, "")
    return text


def _ass_highlight_tags(market: str) -> tuple[str, str]:
    """Return market-specific inline ASS tags for selected subtitle keywords."""
    m = str(market or "US").upper()
    if m == "EU":
        return r"{\b1\c&H00FFFF&}", r"{\b0\c&HFFFFFF&}"
    if m == "JP":
        return r"{\b1\fscx104\fscy104\c&H66FFCC&}", r"{\b0\fscx100\fscy100\c&HFFFFFF&}"
    return r"{\b1\fscx112\fscy112\c&H00FFFF&}", r"{\b0\fscx100\fscy100\c&HFFFFFF&}"


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
    play_res_x: int = 1080,
    x_percent: float = 50.0,
    text_overlay_margin_v: int | None = None,
    font_size: int = 0,
):
    """Convert an SRT file to an ASS subtitle file using the given bounce/viral style.

    font_size: explicit Fontsize to embed in the ASS Style.
               0 (default) uses the per-style built-in size so existing renders
               are unchanged when this param is omitted.
               Clamped to [12, 120] when non-zero.
    """
    preset = get_subtitle_preset(subtitle_style)

    # When text overlays occupy the bottom zone, push subtitles above them.
    effective_margin_v = text_overlay_margin_v if text_overlay_margin_v is not None else margin_v

    # Auto-upgrade bottom margin for vertical formats to avoid TikTok/Reels UI overlap.
    if text_overlay_margin_v is None and effective_margin_v <= 180 and play_res_y > 1200:
        effective_margin_v = _compute_margin_v(play_res_x, play_res_y)

    # Preset-specific margin override — some presets (viral_bold, bold_cap) push captions
    # higher than the safe-zone default to clear platform UI chrome.
    if preset.margin_v_ratio > 0 and text_overlay_margin_v is None:
        effective_margin_v = int(play_res_y * preset.margin_v_ratio)

    ass_style, line_fx = build_ass_style_line(
        preset,
        play_res_x=play_res_x,
        play_res_y=play_res_y,
        scale_y=scale_y,
        font_name=font_name,
        margin_v=effective_margin_v,
        font_size=font_size,
        highlight_per_word=highlight_per_word,
    )

    # Position mode: centred default uses Alignment=2 + MarginV (no \pos tag).
    # Any explicit x offset injects a \pos(x,y) that overrides both axes.
    _pos_tag = ""
    position_mode = "margin"
    if abs(x_percent - 50.0) > 0.5:
        _px = round(1080 * x_percent / 100)
        _py = play_res_y - effective_margin_v
        _pos_tag = "{\\pos(" + str(_px) + "," + str(_py) + ")}"
        position_mode = "pos"

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
        raw_text = "\n".join(lines[2:])
        text = _ass_escape_text(_break_by_visual_width(raw_text, max_em=preset.wrap_max_em))
        out.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{_pos_tag}{line_fx}{text}\n")
    Path(ass_path).write_text("".join(out), encoding="utf-8")

    logger.info(
        "subtitle_style_resolved preset=%s font_size=%s auto_scale=%s heavy_scale=%s "
        "margin_v=%d play_res_x=%d play_res_y=%d x_percent=%.1f position_mode=%s -> %s",
        preset.id,
        font_size if font_size > 0 else "preset_default",
        preset.auto_scale,
        preset.heavy_scale,
        effective_margin_v,
        play_res_x,
        play_res_y,
        x_percent,
        position_mode,
        ass_path,
    )
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
    play_res_x: int = 1080,
    highlight_color: str = "&H0000FFFF",   # yellow (ASS BGR: 00FFFF = yellow)
    base_color: str = "&H00FFFFFF",         # white
    outline_color: str = "&H00000000",      # black outline
    back_color: str = "&H90000000",         # semi-transparent shadow
    outline_size: int = 3,
    shadow_size: int = 1,
    x_percent: float = 50.0,
    text_overlay_margin_v: int | None = None,
):
    """Pro karaoke-style subtitle.

    Hiển thị nhóm từ cùng lúc, từ đang nói được highlight màu vàng.
    Style giống MrBeast / viral TikTok.

    Yêu cầu: srt_path là word-level SRT (mỗi entry = 1 từ).
    """
    effective_margin_v = text_overlay_margin_v if text_overlay_margin_v is not None else margin_v

    # Auto-upgrade bottom margin for vertical formats (9:16, 3:4) to avoid TikTok/Reels UI overlap.
    if text_overlay_margin_v is None and effective_margin_v <= 180 and play_res_y > 1200:
        effective_margin_v = _compute_margin_v(play_res_x, play_res_y)

    blocks = _parse_srt_blocks(srt_path)
    if not blocks:
        return srt_to_ass_bounce(srt_path, ass_path, scale_y=scale_y, margin_v=effective_margin_v, play_res_y=play_res_y)

    # Guard: segment-level SRT produces meaningless \k tags — fallback to bounce
    if len(blocks) > 1:
        avg_words = sum(len(b["text"].split()) for b in blocks) / len(blocks)
        if avg_words > 1.5:
            logger.warning(
                "srt_to_ass_karaoke: segment-level SRT detected (avg %.1f words/block) "
                "— \\k tags would be meaningless; falling back to bounce. "
                "Set highlight_per_word=True for word-level transcription.",
                avg_words,
            )
            return srt_to_ass_bounce(srt_path, ass_path, scale_y=scale_y, margin_v=effective_margin_v, play_res_y=play_res_y)

    # Group words into chunks
    groups: list[list[dict]] = []
    for i in range(0, len(blocks), words_per_group):
        chunk = blocks[i:i + words_per_group]
        if chunk:
            groups.append(chunk)

    # Resolution-aware effective values — scale default 1080p values to actual resolution
    _scale = _compute_subtitle_scale(play_res_x, play_res_y)
    _eff_font_size = font_size if font_size != 46 else _scale["font_size"]
    _eff_outline   = outline_size if outline_size != 3 else _scale["outline"]
    _eff_shadow    = shadow_size  if shadow_size  != 1 else _scale["shadow"]

    # ASS style — 2 colours: primary (base) + secondary (highlight during karaoke)
    style_line = (
        f"Style: Default,{font_name},{_eff_font_size},"
        f"{base_color},{highlight_color},"
        f"{outline_color},{back_color},"
        f"0,0,0,0,100,{scale_y},0,0,1,{_eff_outline},{_eff_shadow},"
        f"2,30,30,{effective_margin_v},1"
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
        _py = play_res_y - effective_margin_v
        _pos_tag = "{\\pos(" + str(_px) + "," + str(_py) + ")}"

    out = [header]
    for group in groups:
        g_start = group[0]["start"]
        g_end = group[-1]["end"]

        # Build karaoke text: {\kN}word  (N = duration in centiseconds)
        parts = []
        for w in group:
            dur_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            # Use _ass_escape_text to guard braces/backslashes; karaoke {\k} tags
            # are inserted around the escaped word so they survive as ASS overrides.
            word = _ass_escape_text(w["text"])
            parts.append(f"{{\\k{dur_cs}}}{word}")

        text = " ".join(parts)
        out.append(
            f"Dialogue: 0,{_ass_time(g_start)},{_ass_time(g_end)},"
            f"Default,,0,0,0,,{_pos_tag}{text}\n"
        )

    Path(ass_path).write_text("".join(out), encoding="utf-8")
    logger.info(
        "subtitle_style_resolved style=karaoke font_size=%d outline=%d shadow=%d "
        "margin_v=%d play_res_x=%d play_res_y=%d words_per_group=%d -> %s",
        _eff_font_size, _eff_outline, _eff_shadow,
        effective_margin_v, play_res_x, play_res_y, words_per_group, ass_path,
    )
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


def resolve_hook_overlay_text(
    hook_applied_text: str | None,
    srt_path: str | None,
    max_words: int = 10,
) -> tuple[str, str]:
    """Resolve hook overlay text for the opening visual overlay.

    Priority:
    1. hook_applied_text — explicit user-supplied hook string.
    2. First meaningful subtitle block from srt_path (≥2 words).
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
        from app.services.market_subtitle_policy import (
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
# Subtitle preview renderer  (used by POST /api/subtitle/preview)
# ---------------------------------------------------------------------------

# Half-resolution preview frames — same aspect ratio, smaller PNG for fast transfer.
_PREVIEW_ASPECT_RES: dict[str, tuple[int, int]] = {
    "9:16": (540, 960),
    "3:4":  (540, 720),
    "4:5":  (540, 675),
    "1:1":  (540, 540),
    "16:9": (960, 540),
}

# Bundled fonts directory next to the backend package
_PREVIEW_FONTS_DIR: Path = Path(__file__).resolve().parents[2] / "fonts"


def render_subtitle_preview(
    subtitle_style: str = "tiktok_bounce_v1",
    font_name: str = "Bungee",
    font_size: int = 0,
    aspect_ratio: str = "9:16",
    margin_v: int | None = None,
    sample_text: str = "This is a preview subtitle",
) -> bytes:
    """Render one PNG frame with the subtitle style applied.

    Uses the same ASSPreset pipeline as the real render so outline, shadow,
    border_style, bold, and color all match actual libass output.
    Returns raw PNG bytes. Raises RuntimeError on FFmpeg failure.
    """
    import tempfile as _tempfile

    play_res_x, play_res_y = _PREVIEW_ASPECT_RES.get(aspect_ratio, (540, 960))
    canonical = normalize_subtitle_style_id(subtitle_style)
    eff_margin_v = int(margin_v) if margin_v is not None else _compute_margin_v(play_res_x, play_res_y)
    clean_text = sample_text.replace("\n", " ").strip() or "Preview subtitle"

    with _tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        srt_path = tmp / "prev.srt"
        ass_path = tmp / "prev.ass"
        img_path = tmp / "prev.png"

        # Single SRT block at t=0 — visible in the first extracted frame.
        srt_path.write_text(
            f"1\n00:00:00,000 --> 00:00:02,000\n{clean_text}\n\n",
            encoding="utf-8",
        )

        # Generate ASS through the same preset pipeline as real renders.
        # highlight_per_word=False omits motion tags so the static frame
        # shows the settled appearance (correct font, outline, shadow, box).
        srt_to_ass_bounce(
            srt_path=str(srt_path),
            ass_path=str(ass_path),
            subtitle_style=canonical,
            font_name=font_name,
            margin_v=eff_margin_v,
            play_res_x=play_res_x,
            play_res_y=play_res_y,
            font_size=font_size,
            highlight_per_word=False,
        )

        safe_ass = _safe_filter_path(str(ass_path.resolve()))
        if _PREVIEW_FONTS_DIR.is_dir():
            safe_fonts = _safe_filter_path(str(_PREVIEW_FONTS_DIR.resolve()))
            vf = f"ass='{safe_ass}':fontsdir='{safe_fonts}'"
        else:
            vf = f"ass='{safe_ass}'"

        # Dark background (0x111827 ≈ slate-900) — mimics a video frame.
        # r=1 → one frame at PTS=0, subtitle at t=0 is visible.
        cmd = [
            get_ffmpeg_bin(), "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x111827:s={play_res_x}x{play_res_y}:r=1",
            "-vf", vf,
            "-frames:v", "1",
            str(img_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=15)
            if proc.returncode != 0:
                stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
                logger.warning(
                    "subtitle_preview_ffmpeg_error style=%s code=%d stderr=%s",
                    subtitle_style, proc.returncode, stderr[:500],
                )
                raise RuntimeError(
                    f"FFmpeg preview failed (code {proc.returncode}): {stderr[:120]}"
                )
            return img_path.read_bytes()
        except subprocess.TimeoutExpired:
            logger.warning("subtitle_preview_timeout style=%s", subtitle_style)
            raise RuntimeError("FFmpeg subtitle preview timed out")


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

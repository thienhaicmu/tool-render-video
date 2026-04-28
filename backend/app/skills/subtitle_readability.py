"""Subtitle Readability skill adapter — overlay styled subtitles onto video."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("app.skills.subtitle_readability")

_FONT_SIZE_MAP = {"small": 28, "medium": 36, "large": 46}
_OUTLINE_MAP   = {"light": 1, "medium": 2, "strong": 4}
_STYLE_MAP = {
    "clean":        {"fontname": "Arial",      "bold": 0},
    "bold social":  {"fontname": "Montserrat", "bold": 1},
    "karaoke":      {"fontname": "Bungee",     "bold": 0},
    "pro karaoke":  {"fontname": "Bungee",     "bold": 1},
}


class SubtitleReadabilityAdapter:
    skill_id = "subtitle_readability"
    label    = "Subtitle Readability"
    description = "Apply a subtitle style preset to improve on-screen text readability."
    status  = "available"
    default_options = {
        "style_preset":     "pro karaoke",
        "font_size":        "medium",
        "position":         "bottom",
        "outline_strength": "medium",
    }
    config_schema = {
        "style_preset": {
            "type": "select", "label": "Style Preset",
            "options": [
                {"value": "clean",       "label": "Clean"},
                {"value": "bold social", "label": "Bold Social"},
                {"value": "karaoke",     "label": "Karaoke"},
                {"value": "pro karaoke", "label": "Pro Karaoke"},
            ],
        },
        "font_size": {
            "type": "select", "label": "Font Size",
            "options": [
                {"value": "small",  "label": "Small"},
                {"value": "medium", "label": "Medium"},
                {"value": "large",  "label": "Large"},
            ],
        },
        "position": {
            "type": "select", "label": "Position",
            "options": [
                {"value": "bottom", "label": "Bottom"},
                {"value": "middle", "label": "Middle"},
                {"value": "top",    "label": "Top"},
            ],
        },
        "outline_strength": {
            "type": "select", "label": "Outline Strength",
            "options": [
                {"value": "light",  "label": "Light"},
                {"value": "medium", "label": "Medium"},
                {"value": "strong", "label": "Strong"},
            ],
        },
    }

    def check(self) -> bool:
        try:
            from app.services.bin_paths import get_ffmpeg_bin
            return bool(get_ffmpeg_bin())
        except Exception:
            return False

    def run(self, input_path: str, output_dir: str, options: dict, context: dict) -> dict:
        from app.services.bin_paths import get_ffmpeg_bin

        inp     = Path(input_path)
        out_dir = Path(output_dir) / "skill_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{inp.stem}_subtitles{inp.suffix}"

        style_key = options.get("style_preset", "pro karaoke")
        style     = _STYLE_MAP.get(style_key, _STYLE_MAP["pro karaoke"])
        font_size = _FONT_SIZE_MAP.get(options.get("font_size", "medium"), 36)
        outline   = _OUTLINE_MAP.get(options.get("outline_strength", "medium"), 2)
        ffmpeg    = get_ffmpeg_bin()

        # ── Try to obtain SRT transcript ──────────────────────────────────────
        srt_path = out_dir / f"{inp.stem}.srt"
        has_srt  = _generate_srt(inp, srt_path)

        if not has_srt:
            # No transcript — stream-copy with a metadata tag, never crash
            cmd = [ffmpeg, "-y", "-i", str(inp), "-c", "copy",
                   "-metadata", f"comment=subtitle_style={style_key}", str(out)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if r.returncode != 0 or not out.exists() or out.stat().st_size == 0:
                raise RuntimeError(
                    f"Metadata copy failed: {(r.stderr or '')[-400:]}"
                )
            return {"output_path": str(out), "applied": True,
                    "style": style_key, "has_transcript": False}

        # ── Encoding safety: ensure UTF-8 without BOM ─────────────────────────
        srt_path, encoding = _ensure_utf8(srt_path)
        logger.info("subtitle_encoding path=%s detected=%s", srt_path, encoding)

        # ── Path safety: POSIX + escaped colon for FFmpeg filter ──────────────
        escaped = _srt_filter_path(srt_path)
        logger.info("subtitle_path raw=%s escaped=%s", srt_path, escaped)

        # ── Probe video dimensions for optional original_size ─────────────────
        w, h = _probe_dimensions(str(inp))

        fontname    = style["fontname"]
        bold        = style["bold"]
        force_style = (
            f"Fontsize={font_size},Outline={outline},"
            f"Fontname={fontname},Bold={bold},"
            "PrimaryColour=&HFFFFFF,OutlineColour=&H000000"
        )

        # ── Attempt 1: include original_size when dimensions are valid ─────────
        vf1 = _build_subtitle_vf(escaped, force_style, w, h, include_size=True)
        logger.info("subtitle filter_string attempt1: %s", vf1)
        cmd1 = [ffmpeg, "-y", "-i", str(inp), "-vf", vf1, "-c:a", "copy", str(out)]
        ok1, stderr1 = _run_ffmpeg_safe(cmd1)

        if ok1 and out.exists() and out.stat().st_size > 0:
            logger.info("subtitle_readability applied style=%s output=%s", style_key, out)
            return {"output_path": str(out), "applied": True,
                    "style": style_key, "has_transcript": True}

        logger.warning(
            "subtitle attempt1 failed — retrying without original_size. "
            "stderr_tail=%s", stderr1[-500:]
        )
        out.unlink(missing_ok=True)

        # ── Attempt 2: drop original_size ─────────────────────────────────────
        vf2 = _build_subtitle_vf(escaped, force_style, None, None, include_size=False)
        logger.info("subtitle filter_string attempt2: %s", vf2)
        cmd2 = [ffmpeg, "-y", "-i", str(inp), "-vf", vf2, "-c:a", "copy", str(out)]
        ok2, stderr2 = _run_ffmpeg_safe(cmd2)

        if ok2 and out.exists() and out.stat().st_size > 0:
            logger.info(
                "subtitle_readability applied (no original_size) style=%s output=%s",
                style_key, out,
            )
            return {"output_path": str(out), "applied": True,
                    "style": style_key, "has_transcript": True}

        logger.error(
            "subtitle both attempts failed — skipping step. stderr_tail=%s",
            stderr2[-500:]
        )

        # ── Graceful fallback: skip this step, DO NOT crash the job ──────────
        return {
            "output_path": input_path,   # pass-through original
            "applied":     False,
            "skipped":     True,
            "skip_reason": "FFmpeg subtitle overlay failed after retry",
            "style":       style_key,
            "has_transcript": True,
        }


# ── Filter path helpers ────────────────────────────────────────────────────────

def _srt_filter_path(srt_path: Path) -> str:
    """
    Return an FFmpeg-safe subtitle path for the subtitles filter.
    Steps:
      1. Resolve to absolute, convert backslashes → forward slashes
      2. Escape the drive colon  (D:/… → D\\:/…)
      3. Escape any single quotes in the path itself
    The caller wraps the result in single quotes: subtitles='<result>'
    """
    posix = str(srt_path.resolve()).replace("\\", "/")
    # Escape drive-letter colon so FFmpeg doesn't treat it as option separator
    if len(posix) >= 2 and posix[1] == ":":
        posix = posix[0] + "\\:" + posix[2:]
    # Escape literal single quotes inside the path
    posix = posix.replace("'", "\\'")
    return posix


def _build_subtitle_vf(
    escaped: str,
    force_style: str,
    w: int | None,
    h: int | None,
    *,
    include_size: bool,
) -> str:
    """Build the FFmpeg -vf filter string step by step."""
    # 1. subtitles filter with single-quoted path
    parts = [f"subtitles='{escaped}'"]
    # 2. force_style option
    parts.append(f"force_style='{force_style}'")
    # 3. original_size only when valid integers are provided
    if include_size and isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
        parts.append(f"original_size={w}x{h}")
    return ":".join(parts)


# ── Encoding helpers ──────────────────────────────────────────────────────────

def _ensure_utf8(srt_path: Path) -> tuple[Path, str]:
    """
    Guarantee the SRT file on disk is UTF-8 without BOM.
    Returns (path, detected_encoding_label).
    """
    raw = srt_path.read_bytes()

    # Strip UTF-8 BOM
    if raw.startswith(b"\xef\xbb\xbf"):
        srt_path.write_bytes(raw[3:])
        return srt_path, "utf-8-bom"

    # Try common encodings in order of likelihood
    for enc in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            if enc != "utf-8":
                srt_path.write_text(text, encoding="utf-8")
                logger.info("subtitle_reencoded %s→utf-8 path=%s", enc, srt_path)
            return srt_path, enc
        except (UnicodeDecodeError, LookupError):
            continue

    # Last resort: replace undecodable bytes
    text = raw.decode("utf-8", errors="replace")
    srt_path.write_text(text, encoding="utf-8")
    logger.warning("subtitle_encoding fallback replace path=%s", srt_path)
    return srt_path, "utf-8-replace"


# ── Video dimension probe ─────────────────────────────────────────────────────

def _probe_dimensions(video_path: str) -> tuple[int | None, int | None]:
    """Return (width, height) of the first video stream, or (None, None) on any failure."""
    try:
        from app.services.bin_paths import get_ffprobe_bin
        cmd = [
            get_ffprobe_bin(),
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-select_streams", "v:0",
            str(video_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            streams = json.loads(r.stdout).get("streams", [])
            if streams:
                w = streams[0].get("width")
                h = streams[0].get("height")
                if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
                    return w, h
    except Exception:
        pass
    return None, None


# ── FFmpeg safe runner ────────────────────────────────────────────────────────

def _run_ffmpeg_safe(cmd: list) -> tuple[bool, str]:
    """Run FFmpeg without raising. Returns (success, stderr_text)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return r.returncode == 0, r.stderr or ""
    except Exception as exc:
        return False, str(exc)


# ── SRT generation ────────────────────────────────────────────────────────────

def _generate_srt(video_path: Path, srt_path: Path) -> bool:
    """Try to transcribe with Whisper and write an SRT. Returns True on success."""
    if srt_path.exists() and srt_path.stat().st_size > 0:
        return True
    try:
        import whisper  # type: ignore
        model  = whisper.load_model("tiny")
        result = model.transcribe(str(video_path), fp16=False, verbose=False)
        _write_srt(result.get("segments", []), srt_path)
        return srt_path.exists() and srt_path.stat().st_size > 0
    except Exception:
        return False


def _write_srt(segments: list, path: Path) -> None:
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _fmt_ts(float(seg.get("start", 0)))
        end   = _fmt_ts(float(seg.get("end",   0)))
        text  = str(seg.get("text", "")).strip()
        if text:
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt_ts(sec: float) -> str:
    h  = int(sec // 3600)
    m  = int((sec % 3600) // 60)
    s  = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


ADAPTER = SubtitleReadabilityAdapter()

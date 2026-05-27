import logging
import re
import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin
from app.services.subtitles.styles import (
    _HL_OPEN, _HL_CLOSE,
    _compute_margin_v, _compute_subtitle_scale,
    get_subtitle_preset, normalize_subtitle_style_id, build_ass_style_line,
)
from app.services.subtitles.srt_core import (
    parse_srt_timestamp, _parse_srt_blocks, _run_with_retry,
)
from app.services.subtitles.readability import _break_by_visual_width

logger = logging.getLogger(__name__)


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
    show_context: bool = True,
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

    # Context style — smaller font above the active line, static white text
    _ctx_font_size  = max(20, round(_eff_font_size * 0.65))
    _ctx_outline    = max(1, round(_eff_outline * 0.75))
    _ctx_shadow     = max(0, round(_eff_shadow  * 0.75))
    _ctx_margin_v   = effective_margin_v + round(_eff_font_size * 1.55)
    context_style_line = (
        f"Style: Context,{font_name},{_ctx_font_size},"
        f"{base_color},{base_color},"
        f"{outline_color},{back_color},"
        f"0,0,0,0,100,{scale_y},0,0,1,{_ctx_outline},{_ctx_shadow},"
        f"2,30,30,{_ctx_margin_v},1"
    )

    _ctx_styles = f"\n{context_style_line}" if show_context else ""

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_line}{_ctx_styles}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Inject \pos(x,y) when subtitle is not centered. Default 50 → no tag.
    _pos_tag = ""
    _ctx_pos_tag = ""
    if abs(x_percent - 50.0) > 0.5:
        _px = round(1080 * x_percent / 100)
        _py = play_res_y - effective_margin_v
        _pos_tag = "{\\pos(" + str(_px) + "," + str(_py) + ")}"
        _ctx_py = play_res_y - _ctx_margin_v
        _ctx_pos_tag = "{\\pos(" + str(_px) + "," + str(_ctx_py) + ")}"

    out = [header]
    prev_plain_text: str | None = None
    for group in groups:
        g_start = group[0]["start"]
        g_end = group[-1]["end"]

        # Context line: show previous group's plain text above the active line
        if show_context and prev_plain_text:
            out.append(
                f"Dialogue: 0,{_ass_time(g_start)},{_ass_time(g_end)},"
                f"Context,,0,0,0,,{_ctx_pos_tag}{prev_plain_text}\n"
            )

        # Build karaoke text: {\kN}word  (N = duration in centiseconds)
        plain_parts = []
        parts = []
        for w in group:
            dur_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            # Use _ass_escape_text to guard braces/backslashes; karaoke {\k} tags
            # are inserted around the escaped word so they survive as ASS overrides.
            word = _ass_escape_text(w["text"])
            parts.append(f"{{\\k{dur_cs}}}{word}")
            plain_parts.append(w["text"])

        text = " ".join(parts)
        prev_plain_text = _ass_escape_text(" ".join(plain_parts))
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


# Half-resolution preview frames — same aspect ratio, smaller PNG for fast transfer.
_PREVIEW_ASPECT_RES: dict[str, tuple[int, int]] = {
    "9:16": (540, 960),
    "3:4":  (540, 720),
    "4:5":  (540, 675),
    "1:1":  (540, 540),
    "16:9": (960, 540),
}

# Bundled fonts directory next to the backend package
_PREVIEW_FONTS_DIR: Path = Path(__file__).resolve().parents[3] / "fonts"


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

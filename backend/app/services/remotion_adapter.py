from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin, _summarize_ffmpeg_stderr


_DIMENSIONS_BY_ASPECT = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "3:4": (1080, 1440),
}

_FALLBACK_HEADLINES = (
    "STOP SCROLLING",
    "WATCH THIS",
    "DON'T MISS THIS",
    "AI HIGHLIGHT",
)

# Content-type → intro preset default.
# Creator's explicit intro_preset payload field always wins.
_CONTENT_TYPE_INTRO_DEFAULTS: dict[str, str] = {
    "commentary": "viral_pop",
    "vlog":       "story_cinematic",
    "story":      "story_cinematic",
    "tutorial":   "clean_creator",
    "interview":  "clean_creator",
    "montage":    "gaming_energy",
    "gaming":     "gaming_energy",
}

# Per-preset timing config.
_INTRO_PRESET_DURATIONS: dict[str, float] = {
    "viral_pop":       1.0,
    "clean_creator":   1.2,
    "story_cinematic": 1.5,
    "gaming_energy":   1.0,
}


def resolve_intro_preset(content_type: str, override: str | None = None) -> str:
    """Return the intro preset ID. Creator override always wins."""
    if override and str(override).strip():
        return str(override).strip()
    return _CONTENT_TYPE_INTRO_DEFAULTS.get(str(content_type or "").strip(), "viral_pop")


def _dimensions_for_aspect(aspect_ratio: str) -> tuple[int, int]:
    return _DIMENSIONS_BY_ASPECT.get((aspect_ratio or "").strip(), _DIMENSIONS_BY_ASPECT["3:4"])


def _escape_drawtext(text: str) -> str:
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _build_intro_headline(
    hook_text: str | None,
    headline_text: str | None,
    source_title: str | None,
    output_path: str,
    max_words: int = 5,
) -> str:
    """Fallback chain: AI hook → headline_text → source title → generic fallback.
    Clamps to max_words for tight intro typography."""
    for raw in [hook_text, headline_text, source_title]:
        candidate = str(raw or "").strip()
        if not candidate:
            continue
        words = candidate.split()
        if len(words) <= max_words:
            return candidate.upper()
        return " ".join(words[:max_words]).upper() + "..."
    idx = sum(ord(ch) for ch in str(output_path)) % len(_FALLBACK_HEADLINES)
    return _FALLBACK_HEADLINES[idx]


# ── Preset VF builders ────────────────────────────────────────────────────────
# Each returns a complete FFmpeg -vf string for the intro clip.
# All use lavfi `color` source + drawbox/drawtext/fade filters only.

def _vf_viral_pop(text: str, w: int, h: int, font_size: int, duration: float) -> str:
    """TikTok/Reels-native: white flash punch-in, cyan+pink accents, large text."""
    fade_out = max(0.1, duration - 0.18)
    acc_h = max(3, int(h * 0.006))
    acc_h2 = max(4, int(h * 0.007))
    return ",".join([
        # Flash punch (kinetic pop feel at t=0–0.08)
        f"drawbox=x=0:y=0:w=iw:h=ih:color=0xFFFFFF@0.12:t=fill:enable='between(t\\,0\\,0.08)'",
        # Cyan top accent line
        f"drawbox=x={int(w*0.08)}:y={int(h*0.295)}:w={int(w*0.84)}:h={acc_h}:color=0x00E5FF@0.85:t=fill",
        # Hot-pink bottom accent line (TikTok red)
        f"drawbox=x={int(w*0.12)}:y={int(h*0.700)}:w={int(w*0.76)}:h={acc_h2}:color=0xFF2D55@0.82:t=fill",
        # Ghost oversized text (kinetic layering at t=0–0.12)
        (
            f"drawtext=text='{text}':fontcolor=0xFFFFFF@0.15:fontsize={int(font_size*1.18)}:"
            f"borderw=9:bordercolor=0xFF2D55@0.30:x=(w-text_w)/2:y=(h-text_h)/2:"
            f"enable='between(t\\,0\\,0.12)'"
        ),
        # Main text — large, dominant
        (
            f"drawtext=text='{text}':fontcolor=white:fontsize={int(font_size*1.12)}:"
            f"borderw=6:bordercolor=0x000000@0.95:shadowcolor=0x000000@0.65:shadowx=0:shadowy=10:"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        ),
        "fade=t=in:st=0:d=0.08",
        f"fade=t=out:st={fade_out:.3f}:d=0.18",
    ])


def _vf_clean_creator(text: str, w: int, h: int, font_size: int, duration: float) -> str:
    """Minimal/premium: slow fade, thin divider, editorial typography above center."""
    fade_out = max(0.2, duration - 0.25)
    div_h = max(2, int(h * 0.003))
    return ",".join([
        # Single thin horizontal divider (editorial feel)
        f"drawbox=x={int(w*0.20)}:y={int(h*0.555)}:w={int(w*0.60)}:h={div_h}:color=0xFFFFFF@0.22:t=fill",
        # Smaller text, slightly above center — premium
        (
            f"drawtext=text='{text}':fontcolor=white:fontsize={int(font_size*0.88)}:"
            f"borderw=2:bordercolor=0x000000@0.80:shadowcolor=0x000000@0.40:shadowx=0:shadowy=4:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-{int(h*0.04)}"
        ),
        "fade=t=in:st=0:d=0.30",
        f"fade=t=out:st={fade_out:.3f}:d=0.25",
    ])


def _vf_story_cinematic(text: str, w: int, h: int, font_size: int, duration: float) -> str:
    """Cinematic/emotional: slow fade, barely-there accent, off-white text below center."""
    fade_out = max(0.2, duration - 0.30)
    soft_h = max(1, int(h * 0.002))
    return ",".join([
        # Film-like soft accent (almost invisible)
        f"drawbox=x={int(w*0.25)}:y={int(h*0.635)}:w={int(w*0.50)}:h={soft_h}:color=0xEBEBEB@0.18:t=fill",
        # Off-white text, minimal 1px border, positioned below center (cinematic)
        (
            f"drawtext=text='{text}':fontcolor=0xEBEBEB:fontsize={int(font_size*0.85)}:"
            f"borderw=1:bordercolor=0x000000@0.60:shadowcolor=0x000000@0.55:shadowx=0:shadowy=6:"
            f"x=(w-text_w)/2:y=(h-text_h)/2+{int(h*0.06)}"
        ),
        "fade=t=in:st=0:d=0.25",
        f"fade=t=out:st={fade_out:.3f}:d=0.30",
    ])


def _vf_gaming_energy(text: str, w: int, h: int, font_size: int, duration: float) -> str:
    """High-energy: electric flash, full-width orange bars, oversized impact text."""
    fade_out = max(0.1, duration - 0.15)
    acc_h = max(5, int(h * 0.009))
    return ",".join([
        # Electric blue flash at t=0–0.06
        f"drawbox=x=0:y=0:w=iw:h=ih:color=0x00AAFF@0.18:t=fill:enable='between(t\\,0\\,0.06)'",
        # Full-width orange accent bars (top + bottom)
        f"drawbox=x=0:y={int(h*0.195)}:w=iw:h={acc_h}:color=0xFF6600@0.90:t=fill",
        f"drawbox=x=0:y={int(h*0.800)}:w=iw:h={acc_h}:color=0xFF6600@0.90:t=fill",
        # Offset ghost text (micro-shake illusion at t=0–0.10)
        (
            f"drawtext=text='{text}':fontcolor=0xFFFFFF@0.12:fontsize={int(font_size*1.22)}:"
            f"borderw=8:bordercolor=0x000000@0.80:x=(w-text_w)/2+2:y=(h-text_h)/2+2:"
            f"enable='between(t\\,0\\,0.10)'"
        ),
        # Main text — large, impact
        (
            f"drawtext=text='{text}':fontcolor=white:fontsize={int(font_size*1.20)}:"
            f"borderw=7:bordercolor=0x000000@0.98:shadowcolor=0x000000@0.70:shadowx=0:shadowy=8:"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        ),
        "fade=t=in:st=0:d=0.06",
        f"fade=t=out:st={fade_out:.3f}:d=0.15",
    ])


_PRESET_VF_BUILDERS = {
    "viral_pop":       _vf_viral_pop,
    "clean_creator":   _vf_clean_creator,
    "story_cinematic": _vf_story_cinematic,
    "gaming_energy":   _vf_gaming_energy,
}

_PRESET_BG_COLORS: dict[str, str] = {
    "viral_pop":       "0x07080D",
    "clean_creator":   "0x0A0E1A",
    "story_cinematic": "0x0D0A07",
    "gaming_energy":   "0x070A0D",
}

_PRESET_MAX_WORDS: dict[str, int] = {
    "viral_pop":       4,
    "clean_creator":   6,
    "story_cinematic": 5,
    "gaming_energy":   4,
}


def generate_hook_intro(
    output_path: str,
    *,
    aspect_ratio: str,
    duration_sec: float,
    headline_text: str | None = None,
    preset_id: str = "viral_pop",
    hook_text: str | None = None,
    source_title: str | None = None,
) -> str | None:
    """Generate a hook intro clip using the specified visual preset.

    Headline fallback chain: hook_text → headline_text → source_title → generic.
    Returns the output path on success, None on any failure.
    """
    out = Path(output_path)
    duration = max(0.5, min(2.0, float(duration_sec or 1.0)))
    width, height = _dimensions_for_aspect(aspect_ratio)

    max_words = _PRESET_MAX_WORDS.get(preset_id, 5)
    bg_color = _PRESET_BG_COLORS.get(preset_id, "0x07080D")
    raw_headline = _build_intro_headline(hook_text, headline_text, source_title, output_path, max_words)
    text = _escape_drawtext(raw_headline)

    font_size = max(44, min(int(height * 0.072), int(width * 0.115)))
    vf_builder = _PRESET_VF_BUILDERS.get(preset_id) or _PRESET_VF_BUILDERS["viral_pop"]
    vf = vf_builder(text, width, height, font_size, duration)

    cmd = [
        get_ffmpeg_bin(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c={bg_color}:s={width}x{height}:r=30:d={duration:.3f}",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r=48000:cl=stereo:d={duration:.3f}",
        "-vf",
        vf,
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(out),
    ]
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0 or not out.exists() or out.stat().st_size <= 0:
            return None
        return str(out)
    except Exception:
        return None


def prepend_intro_clip(
    clip_path: str,
    intro_path: str,
    output_path: str,
    *,
    timeout_sec: int = 60,
) -> str | None:
    """Prepend intro to an existing rendered clip via FFmpeg concat filter.

    Returns None on any failure so the caller can preserve the original clip.
    """
    clip = Path(clip_path)
    intro = Path(intro_path)
    out = Path(output_path)
    if not clip.exists() or not intro.exists():
        return None
    filter_complex = (
        "[0:v]setsar=1,fps=30,format=yuv420p[v0];"
        "[1:v]setsar=1,fps=30,format=yuv420p[v1];"
        "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a0];"
        "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a1];"
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    cmd = [
        get_ffmpeg_bin(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(intro),
        "-i",
        str(clip),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        if proc.returncode != 0 or not out.exists() or out.stat().st_size <= 0:
            _summarize_ffmpeg_stderr(proc.stderr or "")
            return None
        return str(out)
    except Exception:
        return None

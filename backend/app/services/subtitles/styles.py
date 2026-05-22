"""Subtitle style presets, constants, and resolution helpers.

This module owns:
- _HL_OPEN / _HL_CLOSE PUA Unicode highlight delimiters (shared with readability + ass_core)
- ASSPreset dataclass (immutable style descriptor)
- _PRESETS canonical preset table
- _STYLE_ALIASES backward-compat alias table
- Resolution-dependent compute helpers (_compute_subtitle_scale, _compute_margin_v)
- build_ass_style_line() — ASS Style line + per-word line_fx tag

No file I/O. No subprocess. No threading. No optional dependencies.
"""
from dataclasses import dataclass


_HL_OPEN = ""
_HL_CLOSE = ""


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

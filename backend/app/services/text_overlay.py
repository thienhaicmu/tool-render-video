from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


MAX_TEXT_LAYERS = 8
VALID_POSITIONS = {
    "top-left",
    "top-center",
    "top-right",
    "center",
    "bottom-left",
    "bottom-center",
    "bottom-right",
}
VALID_ALIGNMENTS = {"left", "center", "right"}
VALID_FONTS = {
    "Bungee",
    "Anton",
    "Bebas Neue",
    "Oswald",
    "Impact",
    "Arial Black",
    "Segoe UI Black",
    "Archivo Black",
    "Teko",
    "Luckiest Guy",
    "Montserrat",
    "Roboto",
    "Arial",
    "Segoe UI",
}
HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

POSITION_TO_XY = {
    "top-left": (5.0, 5.0),
    "top-center": (50.0, 5.0),
    "top-right": (95.0, 5.0),
    "center": (50.0, 50.0),
    "bottom-left": (5.0, 90.0),
    "bottom-center": (50.0, 90.0),
    "bottom-right": (95.0, 90.0),
}

# Corner/edge positions get a narrower wrap budget (62%) because they're anchored
# to one side; centre-aligned positions use 88% of the 1080px reference width.
_EDGE_POSITIONS = {"top-left", "top-right", "bottom-left", "bottom-right"}

_WIDE_CHARS = frozenset("WMmwQ")
_NARROW_CHARS = frozenset("iIl1|!fjrt.,:;")


def safe_filter_path(path: str) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _safe_text(text: str) -> str:
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("\n", r"\n")
    )


def _ensure_hex_color(value: str, fallback: str) -> str:
    color = str(value or "").strip()
    if HEX_COLOR_RE.match(color):
        return color
    return fallback


def _hex_to_ffmpeg_color(value: str, default_alpha: float = 1.0) -> str:
    color = _ensure_hex_color(value, "#FFFFFF")
    if len(color) == 9:
        rgb = color[1:7]
        alpha = int(color[7:9], 16) / 255.0
    else:
        rgb = color[1:]
        alpha = float(default_alpha)
    alpha = max(0.0, min(1.0, alpha))
    if alpha >= 0.999:
        return f"0x{rgb}"
    return f"0x{rgb}@{alpha:.2f}"


def _custom_fonts_dir() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "fonts",
        here.parents[3] / "fonts",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _fontfile_for_family(font_family: str, bold: bool = False) -> str | None:
    ff = str(font_family or "").strip()

    # 1. Bundled fonts dir
    custom = _custom_fonts_dir()
    if custom:
        regular_map = {
            "Bungee":        "Bungee-Regular.ttf",
            "Anton":         "Anton-Regular.ttf",
            "Bebas Neue":    "BebasNeue-Regular.ttf",
            "Oswald":        "Oswald-Regular.ttf",
            "Archivo Black": "ArchivoBlack-Regular.ttf",
            "Teko":          "Teko-Regular.ttf",
            "Luckiest Guy":  "LuckiestGuy-Regular.ttf",
            "Montserrat":    "Montserrat-Regular.ttf",
            "Roboto":        "Roboto-Regular.ttf",
        }
        bold_map = {
            "Oswald":     "Oswald-Bold.ttf",
            "Teko":       "Teko-Bold.ttf",
            "Montserrat": "Montserrat-Bold.ttf",
            "Roboto":     "Roboto-Bold.ttf",
        }
        file_name = (bold_map.get(ff, "") or regular_map.get(ff, "")) if bold else regular_map.get(ff, "")
        if file_name:
            p = custom / file_name
            if p.exists():
                return str(p)
        ff_lower = ff.lower().replace(" ", "")
        # Bold: prefer a file whose stem contains both family name and "bold"
        if bold:
            for f in custom.glob("*.ttf"):
                stem = f.stem.lower().replace(" ", "")
                if ff_lower in stem and "bold" in stem:
                    return str(f)
        # Fall through to any matching file (regular variant used as last resort for bold)
        for f in custom.glob("*.ttf"):
            if ff_lower in f.stem.lower().replace(" ", ""):
                return str(f)

    # 2. Windows system fonts
    windir = Path(str(Path.home().drive) + "\\Windows") if Path.home().drive else Path("C:\\Windows")
    fonts_dir = windir / "Fonts"
    if fonts_dir.exists():
        win_regular_map = {
            "Arial":          "arial.ttf",
            "Arial Black":    "ariblk.ttf",
            "Segoe UI":       "segoeui.ttf",
            "Segoe UI Black": "seguibl.ttf",
            "Impact":         "impact.ttf",
        }
        win_bold_map = {
            "Arial":    "arialbd.ttf",
            "Segoe UI": "segoeuib.ttf",
        }
        fname = (win_bold_map.get(ff, "") or win_regular_map.get(ff, "")) if bold else win_regular_map.get(ff, "")
        if fname:
            p = fonts_dir / fname
            if p.exists():
                return str(p)
        ff_lower = ff.lower().replace(" ", "")
        if bold:
            for f in fonts_dir.glob("*.ttf"):
                stem = f.stem.lower().replace(" ", "")
                if ff_lower in stem and "bold" in stem:
                    return str(f)
        for f in fonts_dir.glob("*.ttf"):
            if ff_lower in f.stem.lower().replace(" ", ""):
                return str(f)

    logger.warning("text_overlay: font '%s' (bold=%s) not found on disk; ffmpeg will use system font lookup", ff, bold)
    return None


def _char_width(ch: str, font_size: int) -> float:
    if ch == " ":
        return font_size * 0.28
    if ch in _NARROW_CHARS:
        return font_size * 0.36
    if ch in _WIDE_CHARS:
        return font_size * 0.82
    if ch.isupper():
        return font_size * 0.65
    return font_size * 0.55


def _approx_line_width(line: str, font_size: int) -> float:
    return sum(_char_width(c, font_size) for c in line)


def _wrap_text_for_drawtext(text: str, font_size: int, max_width_px: float) -> str:
    """Word-wrap text to fit max_width_px using visual-width estimation.

    Preserves user-entered newlines. Returns text with \\n as the line
    separator (ffmpeg drawtext format). Hard-capped at 4 lines.
    """
    raw_lines = str(text or "").split("\n")
    result_lines: list[str] = []

    for raw_line in raw_lines:
        raw_line = raw_line.strip()
        if not raw_line:
            result_lines.append("")
            continue
        if _approx_line_width(raw_line, font_size) <= max_width_px:
            result_lines.append(raw_line)
            continue
        words = raw_line.split(" ")
        current = ""
        for word in words:
            candidate = (current + " " + word) if current else word
            if _approx_line_width(candidate, font_size) <= max_width_px:
                current = candidate
            else:
                if current:
                    result_lines.append(current)
                current = word
        if current:
            result_lines.append(current)

    return "\n".join(result_lines[:4])


def normalize_text_layers(text_layers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    layers = text_layers or []
    if not isinstance(layers, list):
        raise ValueError("text_layers must be a list")
    if len(layers) > MAX_TEXT_LAYERS:
        raise ValueError(f"text_layers exceeds maximum {MAX_TEXT_LAYERS}")

    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(layers):
        if not isinstance(raw, dict):
            raise ValueError(f"text_layers[{idx}] must be an object")

        text = str(raw.get("text") or "").strip()
        if not text:
            raise ValueError(f"text_layers[{idx}].text cannot be empty")

        font_family = str(raw.get("font_family") or "Bungee").strip()
        if font_family not in VALID_FONTS:
            raise ValueError(f"text_layers[{idx}].font_family is invalid")

        try:
            font_size = int(raw.get("font_size") or 42)
        except Exception:
            raise ValueError(f"text_layers[{idx}].font_size must be number")
        if font_size < 12 or font_size > 300:
            raise ValueError(f"text_layers[{idx}].font_size out of range (12-300)")

        color = _ensure_hex_color(str(raw.get("color") or "#FFFFFF"), "#FFFFFF")
        position = str(raw.get("position") or "bottom-center").strip().lower()
        if position not in VALID_POSITIONS:
            raise ValueError(f"text_layers[{idx}].position is invalid")
        alignment = str(raw.get("alignment") or "center").strip().lower()
        if alignment not in VALID_ALIGNMENTS:
            raise ValueError(f"text_layers[{idx}].alignment is invalid")

        default_x, default_y = POSITION_TO_XY.get(position, (50.0, 90.0))
        raw_x = raw.get("x_percent", default_x)
        raw_y = raw.get("y_percent", default_y)
        try:
            x_percent = float(raw_x)
            y_percent = float(raw_y)
        except Exception:
            raise ValueError(f"text_layers[{idx}].x_percent/y_percent must be number")
        if x_percent < 0 or x_percent > 100:
            raise ValueError(f"text_layers[{idx}].x_percent out of range (0-100)")
        if y_percent < 0 or y_percent > 100:
            raise ValueError(f"text_layers[{idx}].y_percent out of range (0-100)")

        outline_raw = raw.get("outline") if isinstance(raw.get("outline"), dict) else {}
        outline_enabled = bool(outline_raw.get("enabled", False))
        outline_thickness = int(outline_raw.get("thickness", 2) or 0)
        outline_thickness = max(0, min(8, outline_thickness))

        shadow_raw = raw.get("shadow") if isinstance(raw.get("shadow"), dict) else {}
        shadow_enabled = bool(shadow_raw.get("enabled", False))
        shadow_x = int(shadow_raw.get("offset_x", 2) or 0)
        shadow_y = int(shadow_raw.get("offset_y", 2) or 0)
        shadow_x = max(-20, min(20, shadow_x))
        shadow_y = max(-20, min(20, shadow_y))

        bg_raw = raw.get("background") if isinstance(raw.get("background"), dict) else {}
        bg_enabled = bool(bg_raw.get("enabled", False))
        bg_color = _ensure_hex_color(str(bg_raw.get("color") or "#00000099"), "#00000099")
        bg_padding = int(bg_raw.get("padding", 10) or 0)
        bg_padding = max(0, min(64, bg_padding))

        try:
            start_time = float(raw.get("start_time", 0) or 0)
        except Exception:
            raise ValueError(f"text_layers[{idx}].start_time must be number")
        try:
            end_time = float(raw.get("end_time", 0) or 0)
        except Exception:
            raise ValueError(f"text_layers[{idx}].end_time must be number")
        if start_time < 0:
            raise ValueError(f"text_layers[{idx}].start_time must be >= 0")
        if end_time < 0:
            raise ValueError(f"text_layers[{idx}].end_time must be >= 0")
        if end_time > 0 and end_time <= start_time:
            raise ValueError(f"text_layers[{idx}].end_time must be greater than start_time")

        order_raw = raw.get("order", idx)
        if order_raw is None:
            order = idx
        else:
            order = int(order_raw)

        normalized.append(
            {
                "id": str(raw.get("id") or f"layer_{idx+1}"),
                "text": text,
                "font_family": font_family,
                "font_size": font_size,
                "color": color,
                "position": position,
                "x_percent": round(x_percent, 3),
                "y_percent": round(y_percent, 3),
                "alignment": alignment,
                "bold": bool(raw.get("bold", False)),
                "outline": {"enabled": outline_enabled, "thickness": outline_thickness},
                "shadow": {"enabled": shadow_enabled, "offset_x": shadow_x, "offset_y": shadow_y},
                "background": {"enabled": bg_enabled, "color": bg_color, "padding": bg_padding},
                "start_time": round(start_time, 3),
                "end_time": round(end_time, 3),
                "order": order,
            }
        )

    normalized.sort(key=lambda x: int(x.get("order", 0)))
    return normalized


def append_text_layer_filters(
    vf_parts: list[str],
    text_layers: list[dict[str, Any]] | None,
    subtitle_zone_height_px: int = 0,
) -> None:
    """Append drawtext filters for each validated text layer.

    subtitle_zone_height_px: when >0, layers in the bottom zone (y_percent >= 72)
    are pushed up so their rendered bottom edge stays above the subtitle safe area.
    This prevents text overlays from colliding with burned-in ASS subtitles.
    """
    layers = normalize_text_layers(text_layers)
    if not layers:
        return
    for layer in layers:
        x_percent = max(0.0, min(100.0, float(layer.get("x_percent", 50) or 50)))
        y_percent = max(0.0, min(100.0, float(layer.get("y_percent", 90) or 90)))

        # Safe-zone: keep text away from the outermost 3% of each edge so
        # platform cropping (YouTube, TikTok) doesn't cut off the text.
        x_percent = max(3.0, min(97.0, x_percent))
        y_percent = max(3.0, min(97.0, y_percent))

        # Subtitle-safe: nudge bottom-zone layers upward when subtitle zone is active.
        if subtitle_zone_height_px > 0 and y_percent >= 72.0:
            # Build y as a runtime expression: clamp bottom of text box above subtitle zone.
            x_expr = f"(w-text_w)*{x_percent:.3f}/100"
            y_expr = (
                f"min((h-text_h)*{y_percent:.3f}/100,"
                f"h-text_h-{int(subtitle_zone_height_px)})"
            )
        else:
            x_expr = f"(w-text_w)*{x_percent:.3f}/100"
            y_expr = f"(h-text_h)*{y_percent:.3f}/100"

        # ── Wrapping ─────────────────────────────────────────────────────
        position = str(layer.get("position", "bottom-center"))
        max_width_percent = 62.0 if position in _EDGE_POSITIONS else 88.0
        font_size = int(layer.get("font_size", 42))
        max_width_px = 1080.0 * max_width_percent / 100.0
        wrapped_text = _wrap_text_for_drawtext(str(layer.get("text") or ""), font_size, max_width_px)
        line_count = len(wrapped_text.split("\n"))
        text = _safe_text(wrapped_text)

        draw = [
            "drawtext",
            f"text='{text}'",
            f"fontsize={font_size}",
            f"fontcolor={_hex_to_ffmpeg_color(str(layer.get('color') or '#FFFFFF'))}",
            f"x={x_expr}",
            f"y={y_expr}",
            "line_spacing=8",
        ]

        # ── Font resolution ───────────────────────────────────────────────
        is_bold = bool(layer.get("bold"))
        family = str(layer.get("font_family") or "Bungee")
        fontfile = _fontfile_for_family(family, bold=is_bold)
        bold_via_fontfile = False

        if fontfile:
            bold_via_fontfile = is_bold and "bold" in Path(fontfile).stem.lower()
            draw.append(f"fontfile='{safe_filter_path(fontfile)}'")
            if is_bold and not bold_via_fontfile:
                logger.debug(
                    "text_overlay: bold requested for '%s' — no bold fontfile found; using outline fallback",
                    family,
                )
        else:
            safe_family = family.replace("'", "")
            if is_bold:
                draw.append(f"font='{safe_family}:style=Bold'")
            else:
                draw.append(f"font='{safe_family}'")

        logger.info(
            "text_overlay: id=%s order=%s font=%s size=%d file=%s bold=%s "
            "max_w=%.0f%% lines=%d x=%.1f%% y=%.1f%%",
            layer.get("id", "?"),
            layer.get("order", "?"),
            family,
            font_size,
            Path(fontfile).name if fontfile else "(system)",
            is_bold,
            max_width_percent,
            line_count,
            x_percent,
            y_percent,
        )

        # ── Outline / border ──────────────────────────────────────────────
        outline = layer.get("outline") if isinstance(layer.get("outline"), dict) else {}
        borderw = int(outline.get("thickness", 2) or 0) if bool(outline.get("enabled")) else 0
        # Fake-bold via outline only when no bold fontfile was resolved
        if is_bold and not bold_via_fontfile:
            borderw = max(borderw, 2)
        if borderw > 0:
            draw.append(f"borderw={borderw}")
            draw.append("bordercolor=0x000000")

        shadow = layer.get("shadow") if isinstance(layer.get("shadow"), dict) else {}
        if bool(shadow.get("enabled")):
            draw.append(f"shadowx={int(shadow.get('offset_x', 2) or 0)}")
            draw.append(f"shadowy={int(shadow.get('offset_y', 2) or 0)}")
            draw.append("shadowcolor=0x000000")

        bg = layer.get("background") if isinstance(layer.get("background"), dict) else {}
        if bool(bg.get("enabled")):
            draw.append("box=1")
            draw.append(f"boxcolor={_hex_to_ffmpeg_color(str(bg.get('color') or '#00000099'), default_alpha=0.55)}")
            draw.append(f"boxborderw={int(bg.get('padding', 8) or 0)}")
        else:
            draw.append("box=0")

        start_t = max(0.0, float(layer.get("start_time", 0) or 0))
        end_t = max(0.0, float(layer.get("end_time", 0) or 0))
        if end_t > 0:
            draw.append(f"enable='gte(t\\,{start_t:.3f})*lt(t\\,{end_t:.3f})'")
        elif start_t > 0:
            draw.append(f"enable='gte(t\\,{start_t:.3f})'")

        vf_parts.append(draw[0] + "=" + ":".join(draw[1:]))

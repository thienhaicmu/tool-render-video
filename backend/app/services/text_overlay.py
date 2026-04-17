from __future__ import annotations

import re
from pathlib import Path
from typing import Any


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


def _fontfile_for_family(font_family: str) -> str | None:
    ff = str(font_family or "").strip()
    custom = _custom_fonts_dir()
    if custom:
        mapping = {
            "Bungee": "Bungee-Regular.ttf",
        }
        file_name = mapping.get(ff, "")
        if file_name:
            p = custom / file_name
            if p.exists():
                return str(p)

    windir = Path(str(Path.home().drive) + "\\Windows") if Path.home().drive else Path("C:\\Windows")
    fonts_dir = windir / "Fonts"
    if fonts_dir.exists():
        win_map = {
            "Arial": "arial.ttf",
            "Arial Black": "ariblk.ttf",
            "Segoe UI": "segoeui.ttf",
            "Segoe UI Black": "seguibl.ttf",
            "Impact": "impact.ttf",
            "Roboto": "arial.ttf",
            "Montserrat": "arial.ttf",
            "Bebas Neue": "arial.ttf",
            "Anton": "arial.ttf",
            "Oswald": "arial.ttf",
            "Archivo Black": "arial.ttf",
            "Teko": "arial.ttf",
            "Luckiest Guy": "arial.ttf",
        }
        f = win_map.get(ff, "")
        if f:
            p = fonts_dir / f
            if p.exists():
                return str(p)
    return None


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


def append_text_layer_filters(vf_parts: list[str], text_layers: list[dict[str, Any]] | None) -> None:
    layers = normalize_text_layers(text_layers)
    if not layers:
        return
    for layer in layers:
        x_percent = max(0.0, min(100.0, float(layer.get("x_percent", 50) or 50)))
        y_percent = max(0.0, min(100.0, float(layer.get("y_percent", 90) or 90)))
        x_expr = f"(w-text_w)*{x_percent:.3f}/100"
        y_expr = f"(h-text_h)*{y_percent:.3f}/100"

        text = _safe_text(str(layer.get("text") or ""))
        draw = [
            "drawtext",
            f"text='{text}'",
            f"fontsize={int(layer.get('font_size', 42))}",
            f"fontcolor={_hex_to_ffmpeg_color(str(layer.get('color') or '#FFFFFF'))}",
            f"x={x_expr}",
            f"y={y_expr}",
            "line_spacing=8",
        ]

        fontfile = _fontfile_for_family(str(layer.get("font_family") or "Bungee"))
        if fontfile:
            draw.append(f"fontfile='{safe_filter_path(fontfile)}'")
        else:
            family = str(layer.get("font_family") or "Arial").replace("'", "")
            draw.append(f"font='{family}'")
            if bool(layer.get("bold")):
                draw[-1] = f"font='{family}:style=Bold'"

        outline = layer.get("outline") if isinstance(layer.get("outline"), dict) else {}
        borderw = int(outline.get("thickness", 2) or 0) if bool(outline.get("enabled")) else 0
        if bool(layer.get("bold")):
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

"""ass_capcut.py — CapCut/Opus-grade word-by-word subtitle generator.

PHASE 0 PROTOTYPE — not yet wired into the render pipeline. Used to
render preview frames so the new look can be chosen before integration.

Why a new engine: the legacy karaoke path uses ASS ``{\\k}`` colour-sweep
tags (the word "fills" with colour over its duration) — a dated karaoke
look. CapCut/Opus instead switch the active word *instantly* to an accent
colour with a scale-pop, dim the not-yet-spoken words, and optionally put
the active word on a filled box. This module emits one Dialogue per
active-word window with per-word inline overrides to produce that look.

Supported looks (per CapCutStyle flags):
  - active word accent colour + scale-pop
  - filled box behind the active word (single-word mode, BorderStyle=3)
  - group karaoke (3–5 words; active bright, others dimmed)
  - keyword / number colour emphasis

Pure text generation: no I/O beyond reading the word-level SRT and writing
the ASS file. No subprocess, no optional deps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.features.render.engine.subtitle.generator.ass import _ass_time, _ass_escape_text
from app.features.render.engine.subtitle.generator.srt import _parse_srt_blocks
from app.features.render.engine.subtitle.processing.styles import (
    _compute_subtitle_scale,
    _compute_margin_v,
)

# Numbers, ALL-CAPS words (≥2 chars), or currency/percent tokens read as
# "keywords" worth a colour accent even when they are not the active word.
_KEYWORD_RE = re.compile(r"(\d|[%$€£])")
_ALLCAPS_RE = re.compile(r"^[A-Z]{2,}$")


@dataclass(frozen=True)
class CapCutStyle:
    """Immutable descriptor for a CapCut-style caption look (ASS colours)."""
    id: str
    font: str
    base_color: str        # &HAABBGGRR — spoken / default word fill
    accent_color: str      # active word fill (or box fill in box mode)
    box_text_color: str    # active word text when on a box
    outline_color: str
    keyword_color: str     # "" disables keyword emphasis
    words_per_group: int
    box: bool              # active word sits on a filled BorderStyle=3 box
    pop: bool              # scale-pop on the active word (overshoot/settle)
    dim_future: bool       # not-yet-spoken words are alpha-dimmed
    font_scale: float = 0.052   # font size as a ratio of play_res_y
    smooth: bool = False   # Premiere-style: gentle grow (no overshoot) + fade
    reveal: bool = False   # words stay hidden until spoken, then fade in


# Curated preset table — small and opinionated (vs the 15 legacy presets).
CAPCUT_PRESETS: dict[str, CapCutStyle] = {
    # Opus-style: 4-word groups, active word yellow + pop, future dimmed.
    "opus_pop": CapCutStyle(
        id="opus_pop", font="Anton",
        base_color="&H00FFFFFF", accent_color="&H0000E5FF",
        box_text_color="&H00000000", outline_color="&H00000000",
        keyword_color="&H0000E5FF",
        words_per_group=4, box=False, pop=True, dim_future=True,
    ),
    # CapCut box: one word at a time on a bright yellow box, black text.
    "capcut_box": CapCutStyle(
        id="capcut_box", font="Anton",
        base_color="&H00FFFFFF", accent_color="&H0000E5FF",
        box_text_color="&H00000000", outline_color="&H00000000",
        keyword_color="",
        words_per_group=1, box=True, pop=True, dim_future=False,
        font_scale=0.060,
    ),
    # Green punch: 3-word groups, active green + pop, keyword accent.
    "punch_green": CapCutStyle(
        id="punch_green", font="Anton",
        base_color="&H00FFFFFF", accent_color="&H0080FF00",
        box_text_color="&H00000000", outline_color="&H00000000",
        keyword_color="&H0000E5FF",
        words_per_group=3, box=False, pop=True, dim_future=True,
    ),
    # Karaoke highlight: 5-word groups, active bright white, others dimmed,
    # no pop — high-retention "read-along" feel.
    "karaoke_clean": CapCutStyle(
        id="karaoke_clean", font="Montserrat",
        base_color="&H00FFFFFF", accent_color="&H0000E5FF",
        box_text_color="&H00000000", outline_color="&H00000000",
        keyword_color="",
        words_per_group=5, box=False, pop=False, dim_future=True,
    ),
    # Premiere Pro "smooth animated captions": clean Inter, words fade in
    # word-by-word with a gentle grow (no overshoot), elegant/cinematic.
    "smooth_premiere": CapCutStyle(
        id="smooth_premiere", font="Inter",
        base_color="&H00FFFFFF", accent_color="&H00FFFFFF",
        box_text_color="&H00000000", outline_color="&H00000000",
        keyword_color="",
        words_per_group=4, box=False, pop=False, dim_future=False,
        smooth=True, reveal=True, font_scale=0.046,
    ),
}
_DEFAULT_STYLE_ID = "opus_pop"

# Legacy subtitle_style IDs → new CapCut preset. Lets old stored jobs and
# existing API callers keep working: a request for an old style routes to
# the closest new look instead of breaking. Anything unmapped falls back to
# the default (opus_pop).
_LEGACY_TO_CAPCUT: dict[str, str] = {
    # energetic / viral → opus_pop
    "tiktok_bounce_v1": "opus_pop", "viral": "opus_pop", "viral_bold": "opus_pop",
    "color_pop": "opus_pop", "slay_soft": "opus_pop", "neon_glow": "opus_pop",
    # box / heavy → capcut_box
    "bold_cap": "capcut_box", "boxed_caption": "capcut_box", "dark_card": "capcut_box",
    "bold_stroke": "capcut_box",
    # high-energy / sport → punch_green
    "gaming": "punch_green", "fire_bold": "punch_green",
    # clean / editorial → smooth_premiere
    "clean": "smooth_premiere", "clean_pro": "smooth_premiere",
    "story": "smooth_premiere", "story_clean_01": "smooth_premiere",
    # read-along karaoke → karaoke_clean
    "pro_karaoke": "karaoke_clean", "karaoke": "karaoke_clean",
}


def resolve_capcut_style(style_id: str) -> str:
    """Resolve any subtitle_style (new ID, legacy ID, or unknown) to a
    CapCut preset ID. Never raises; unknown → default."""
    sid = (style_id or "").lower().strip()
    if sid in CAPCUT_PRESETS:
        return sid
    return _LEGACY_TO_CAPCUT.get(sid, _DEFAULT_STYLE_ID)


def get_capcut_style(style_id: str) -> CapCutStyle:
    return CAPCUT_PRESETS[resolve_capcut_style(style_id)]


def _is_keyword(word: str) -> bool:
    w = word.strip(".,!?;:\"'")
    return bool(_KEYWORD_RE.search(w) or _ALLCAPS_RE.match(w))


# D2: AI-chosen emphasis words get the keyword accent too (colour + pop).
_EMPH_STRIP = ".,!?;:\"'()[]…—-"


def _norm_emph(word: str) -> str:
    return (word or "").strip().strip(_EMPH_STRIP).lower()


def _emphasis_set(emphasis) -> "set[str]":
    """Normalise an emphasis word/phrase list into comparable tokens (lowercased,
    punctuation-stripped, phrases split into words). Never raises."""
    out: "set[str]" = set()
    if not emphasis:
        return out
    try:
        for item in emphasis:
            for tok in str(item or "").split():
                n = _norm_emph(tok)
                if n:
                    out.add(n)
    except Exception:
        return set()
    return out


def _word_override(state: str, style: CapCutStyle, is_keyword: bool) -> str:
    """Inline ASS override block for one word in a given state.

    state ∈ {"spoken", "active", "future"}. Every block resets \\c, \\alpha
    and \\fscx/\\fscy so styling never bleeds into the next word.
    """
    if state == "active":
        color = style.box_text_color if style.box else style.accent_color
        if style.smooth:
            # Gentle grow (no overshoot) + optional fade-in reveal.
            grow = r"\fscx94\fscy94\t(0,220,\fscx100\fscy100)"
            fade = r"\alpha&HFF&\t(0,200,\alpha&H00&)" if style.reveal else r"\alpha&H00&"
            return r"{" + fade + r"\c" + color + grow + "}"
        pop = r"\fscx118\fscy118\t(0,140,\fscx100\fscy100)" if style.pop else r"\fscx100\fscy100"
        return r"{\alpha&H00&\c" + color + pop + "}"

    # spoken / future share the reset; choose colour + alpha.
    color = style.base_color
    if is_keyword and style.keyword_color:
        color = style.keyword_color
    if state == "future":
        alpha = r"\alpha&HFF&" if style.reveal else (r"\alpha&H88&" if style.dim_future else r"\alpha&H00&")
    else:  # spoken — always fully visible
        alpha = r"\alpha&H00&"
    return r"{" + alpha + r"\c" + color + r"\fscx100\fscy100}"


def _style_lines(style: CapCutStyle, font_name: str, font_size: int,
                 outline: int, shadow: int, scale_y: int, margin_v: int) -> str:
    """Build the [V4+ Styles] body. Box mode uses BorderStyle=3 (opaque box)."""
    if style.box:
        # Opaque box (BorderStyle=3): libass fills the box with OutlineColour
        # (\3c) and pads it by the Outline value. PrimaryColour is the text.
        # → box = accent, text = box_text_color, BackColour transparent.
        return (
            f"Style: Default,{font_name},{font_size},"
            f"{style.box_text_color},{style.box_text_color},"
            f"{style.accent_color},&H00000000,"
            f"-1,0,0,0,100,{scale_y},0.5,0,3,{max(8, outline * 3)},0,"
            f"2,40,40,{margin_v},1"
        )
    return (
        f"Style: Default,{font_name},{font_size},"
        f"{style.base_color},{style.accent_color},"
        f"{style.outline_color},&H64000000,"
        f"-1,0,0,0,100,{scale_y},0.4,0,1,{outline},{shadow},"
        f"2,30,30,{margin_v},1"
    )


def srt_to_ass_capcut(
    srt_path: str,
    ass_path: str,
    *,
    style: CapCutStyle | str = _DEFAULT_STYLE_ID,
    font_name: str = "",
    play_res_x: int = 1080,
    play_res_y: int = 1440,
    margin_v: int | None = None,
    font_size: int = 0,
    emphasis: "set[str] | list[str] | None" = None,
) -> str:
    """Generate a CapCut-style ASS file from a WORD-LEVEL SRT.

    Each SRT entry must be a single word with its own timing. Returns the
    ass_path. Falls back to a single static line if the SRT is empty.
    """
    st = style if isinstance(style, CapCutStyle) else get_capcut_style(style)
    font = (font_name or st.font).strip() or st.font

    sc = _compute_subtitle_scale(play_res_x, play_res_y)
    eff_font = font_size if font_size > 0 else max(72, int(play_res_y * st.font_scale))
    eff_outline = sc["outline"]
    eff_shadow = sc["shadow"]
    eff_margin = margin_v if margin_v is not None else _compute_margin_v(play_res_x, play_res_y)
    scale_y = 100

    words = _parse_srt_blocks(srt_path)
    _emph = _emphasis_set(emphasis)   # D2: AI-chosen emphasis words → accent
    style_body = _style_lines(st, font, eff_font, eff_outline, eff_shadow, scale_y, eff_margin)
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\nPlayResY: {play_res_y}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style_body}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    out = [header]
    n = max(1, st.words_per_group)
    for gi in range(0, len(words), n):
        group = words[gi:gi + n]
        for i, active in enumerate(group):
            a_start = active["start"]
            a_end = active["end"]
            parts = []
            for j, w in enumerate(group):
                state = "active" if j == i else ("spoken" if j < i else "future")
                _kw = _is_keyword(w["text"]) or (bool(_emph) and _norm_emph(w["text"]) in _emph)
                tag = _word_override(state, st, _kw)
                parts.append(tag + _ass_escape_text(w["text"]))
            line = " ".join(parts)
            out.append(
                f"Dialogue: 0,{_ass_time(a_start)},{_ass_time(a_end)},Default,,0,0,0,,{line}\n"
            )

    Path(ass_path).write_text("".join(out), encoding="utf-8")
    return ass_path

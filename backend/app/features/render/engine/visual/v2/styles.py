"""
styles.py — CHARACTER STYLE registry (GĐ2 Visual Foundation).

Story Mode will offer SEVERAL character art styles, picked by the user on the UI
(per project / per render). Every style implements the SAME contract:

    render(look, emotion, pose, facing) -> svg inner content (1024×1536 frame)

so the identity (look_spec.CharacterLook), the emotion/pose vocabulary and the
compositor stay style-agnostic — switching style re-skins the whole video without
touching the plan. ``STYLES`` carries the UI metadata (id, display name, blurb).

Defensive: unknown style falls back to DEFAULT_STYLE; renderers never raise.
"""
from __future__ import annotations

from typing import Callable, Optional

DEFAULT_STYLE = "anime"


def _render_anime(look, emotion: str, pose: str, facing: str) -> str:
    from app.features.render.engine.visual.v2.anime_char import anime_char_inner
    return anime_char_inner(look, emotion, pose, facing)


def _render_chibi_soft(look, emotion: str, pose: str, facing: str) -> str:
    from app.features.render.engine.visual.v2.chibi_soft import chibi_soft_inner
    return chibi_soft_inner(look, emotion, pose, facing)


def _render_vector_hero(look, emotion: str, pose: str, facing: str) -> str:
    from app.features.render.engine.visual.v2.vector_hero import vector_hero_inner
    return vector_hero_inner(look, emotion, pose, facing)


def _render_jp_theme(style_id: str):
    def _render(look, emotion: str, pose: str, facing: str) -> str:
        from app.features.render.engine.visual.v2.anime_char import anime_char_inner
        return anime_char_inner(look, emotion, pose, facing, style_id=style_id)
    return _render


# style_id → {name (UI label), desc (UI blurb), render}. Procedural styles are the
# built-in $0 fallbacks; INSTALLED LOTTIE PACKS (designer-made animated characters,
# hướng A) are appended dynamically as "lottie:{pack_id}" — see list_styles().
STYLES: "dict[str, dict]" = {
    "jp_anime_clean_v1": {
        "name": "Japanese Anime Clean",
        "desc": "Nét sạch, màu rõ và cel-shading cân bằng cho nội dung Nhật.",
        "render": _render_jp_theme("jp_anime_clean_v1"),
    },
    "jp_anime_cinematic_v1": {
        "name": "Japanese Anime Cinematic",
        "desc": "Tương phản sâu, rim light và bóng điện ảnh cho drama/cao trào.",
        "render": _render_jp_theme("jp_anime_cinematic_v1"),
    },
    "jp_anime_soft_drama_v1": {
        "name": "Japanese Anime Soft Drama",
        "desc": "Màu ấm, pastel và ánh sáng mềm cho gia đình/tình cảm.",
        "render": _render_jp_theme("jp_anime_soft_drama_v1"),
    },
    "anime": {
        "name": "Anime",
        "desc": "Tỉ lệ thật 1:6.5, cel-shading + line-art — hợp drama/wuxia/kinh dị.",
        "render": _render_anime,
    },
    "chibi_soft": {
        "name": "Chibi mềm",
        "desc": "Đầu to tròn, nét dày, má hồng — dễ thương, hợp truyện nhẹ nhàng/hài.",
        "render": _render_chibi_soft,
    },
    "hero": {
        "name": "Vector Hero",
        "desc": "Semi-chibi nét dày + gradient + phục trang ornament (procedural).",
        "render": _render_vector_hero,
    },
}

_LOTTIE_PREFIX = "lottie:"


def list_styles() -> "list[dict]":
    """UI metadata: [{id, name, desc, animated}] — built-in styles first, then every
    installed Lottie pack. Never raises."""
    out = [{"id": sid, "name": s["name"], "desc": s["desc"], "animated": False}
           for sid, s in STYLES.items()]
    try:
        from app.features.render.engine.visual.v2 import lottie_pack
        for p in lottie_pack.list_packs():
            out.append({"id": f"{_LOTTIE_PREFIX}{p['id']}", "name": p["name"],
                        "desc": p["desc"], "animated": True})
    except Exception:
        pass
    return out


def render_character(style: "Optional[str]", look, emotion: str = "neutral",
                     pose: str = "stand", facing: str = "front") -> str:
    """Render ``look`` in ``style`` (unknown/empty → DEFAULT_STYLE). A Lottie-pack
    style renders its recolored MASTER frame as an embedded <image> (same SVG-inner
    contract as the procedural styles). Never raises."""
    try:
        sid = (style or "").strip().lower()
        if sid.startswith(_LOTTIE_PREFIX):
            from app.features.render.engine.visual.v2 import lottie_pack
            inner = lottie_pack.char_image_inner(sid[len(_LOTTIE_PREFIX):], look,
                                                 emotion, pose, facing)
            if inner:
                return inner
            sid = DEFAULT_STYLE                      # pack missing/renderer absent → fallback
        s = STYLES.get(sid) or STYLES[DEFAULT_STYLE]
        fn: Callable = s["render"]
        return fn(look, emotion, pose, facing) or ""
    except Exception:
        return ""


__all__ = ["STYLES", "DEFAULT_STYLE", "list_styles", "render_character"]

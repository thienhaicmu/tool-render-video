"""Map human-facing Story art-style labels to V3 catalog style ids."""
from __future__ import annotations


_STYLE_ALIASES = {
    "cinematic": "jp_anime_cinematic_v1",
    "cinematic anime": "jp_anime_cinematic_v1",
    "cinematic ink wash": "jp_anime_cinematic_v1",
    "cinematic ink-wash": "jp_anime_cinematic_v1",
    "clean anime": "jp_anime_clean_v1",
    "anime clean": "jp_anime_clean_v1",
    "soft drama": "jp_anime_soft_drama_v1",
    "soft anime": "jp_anime_soft_drama_v1",
    "anime drama": "jp_anime_soft_drama_v1",
}


def normalize_v3_style(style: str = "") -> str:
    """Return a stable V3 style id for a Planner/UI style label."""
    value = " ".join(str(style or "").strip().lower().replace("_", " ").split())
    return _STYLE_ALIASES.get(value, value)


__all__ = ["normalize_v3_style"]

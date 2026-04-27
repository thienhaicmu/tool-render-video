"""
market_subtitle_policy.py — Market-aware subtitle rendering policy helper.

Returns per-market configuration for subtitle line length, keyword emphasis,
and tone hints. Designed to be imported by the render pipeline when needed.

Usage:
    from app.services.market_subtitle_policy import get_market_subtitle_policy

    policy = get_market_subtitle_policy("US", subtitle_tone="bold")
    # → {
    #     "market": "US",
    #     "max_words_per_line": 4,
    #     "highlight_keywords": ["money", "results", ...],
    #     "avoid_words": ["maybe", "somewhat", ...],
    #     "style_hint": "bold-impact",
    #     "tone_hint": "aggressive",
    # }
"""
from __future__ import annotations

from typing import Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# Market policies
# Each market has independent keyword sets — no cross-market reuse.
# ─────────────────────────────────────────────────────────────────────────────

_POLICIES: Dict[str, Dict] = {

    # ── US ────────────────────────────────────────────────────────────────────
    # Direct, aggressive, high-energy. Short punchy lines.
    # Subtitle tone variants shift word-count ceiling and style hint only.
    "US": {
        "base_max_words": 4,        # default for "clean" tone
        "tone_overrides": {
            "bold":    {"max_words_per_line": 3, "style_hint": "bold-impact"},
            "karaoke": {"max_words_per_line": 5, "style_hint": "karaoke-word"},
            "clean":   {"max_words_per_line": 4, "style_hint": "clean-punch"},
        },
        "highlight_keywords": [
            "money", "results", "growth", "earn", "profit",
            "scale", "fast", "win", "free", "now",
            "secret", "hack", "proven", "instant",
        ],
        "avoid_words": [
            "maybe", "perhaps", "somewhat", "kind of",
            "sort of", "i guess", "not sure", "possibly",
        ],
        "tone_hint": "aggressive",
    },

    # ── EU ────────────────────────────────────────────────────────────────────
    # Informative, trust-based. Longer, readable lines. No hype language.
    "EU": {
        "base_max_words": 6,
        "tone_overrides": {
            "bold":    {"max_words_per_line": 5, "style_hint": "structured-bold"},
            "karaoke": {"max_words_per_line": 8, "style_hint": "karaoke-phrase"},
            "clean":   {"max_words_per_line": 6, "style_hint": "clean-readable"},
        },
        "highlight_keywords": [
            "research", "evidence", "study", "expert",
            "guide", "transparent", "honest", "safe",
            "quality", "verified", "trusted", "explained",
        ],
        "avoid_words": [
            "guaranteed", "overnight", "instantly", "skyrocket",
            "crazy", "insane", "massive", "explosive",
        ],
        "tone_hint": "informative",
    },

    # ── JP ────────────────────────────────────────────────────────────────────
    # Subtle, emotional, soft. Very short lines. Curiosity-driven.
    "JP": {
        "base_max_words": 3,
        "tone_overrides": {
            "bold":    {"max_words_per_line": 3, "style_hint": "soft-bold"},
            "karaoke": {"max_words_per_line": 4, "style_hint": "karaoke-mora"},
            "clean":   {"max_words_per_line": 2, "style_hint": "minimal-clean"},
        },
        "highlight_keywords": [
            "actually", "turns out", "convenient", "recommend",
            "daily", "simple", "gentle", "discover",
            "feeling", "surprise", "wonder", "kind",
        ],
        "avoid_words": [
            "dominate", "crush", "destroy", "aggressive",
            "earn money", "get rich", "explosive", "urgent",
        ],
        "tone_hint": "subtle",
    },
}

_VALID_MARKETS = frozenset(_POLICIES.keys())
_VALID_TONES   = frozenset({"clean", "bold", "karaoke"})


def get_market_subtitle_policy(market: str, subtitle_tone: str = "clean") -> Dict:
    """
    Return a subtitle rendering policy for the given market and tone.

    Args:
        market:        Target market — "US", "EU", or "JP".
                       Unknown values fall back to "US".
        subtitle_tone: Subtitle style — "clean" | "bold" | "karaoke".
                       Unknown values fall back to "clean".

    Returns:
        {
            "market":             str,
            "max_words_per_line": int,
            "highlight_keywords": list[str],
            "avoid_words":        list[str],
            "style_hint":         str,
            "tone_hint":          str,
        }
    """
    m = str(market or "").strip().upper()
    if m not in _VALID_MARKETS:
        m = "US"

    t = str(subtitle_tone or "").strip().lower()
    if t not in _VALID_TONES:
        t = "clean"

    cfg     = _POLICIES[m]
    override = cfg["tone_overrides"].get(t, cfg["tone_overrides"]["clean"])

    return {
        "market":             m,
        "max_words_per_line": override["max_words_per_line"],
        "highlight_keywords": list(cfg["highlight_keywords"]),
        "avoid_words":        list(cfg["avoid_words"]),
        "style_hint":         override["style_hint"],
        "tone_hint":          cfg["tone_hint"],
    }

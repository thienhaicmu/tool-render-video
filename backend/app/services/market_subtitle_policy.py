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

import re
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
_HL_OPEN = "\ue100"
_HL_CLOSE = "\ue101"
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "so", "to", "of", "in", "on", "for",
    "with", "is", "are", "was", "were", "be", "been", "it", "this", "that",
    "i", "you", "we", "they", "he", "she", "my", "your", "our", "their",
    "just", "like", "really", "very", "there", "here", "now", "then",
})


def _split_phrases(words: list[str], max_words: int) -> list[list[str]]:
    phrases: list[list[str]] = []
    cur: list[str] = []
    conjunctions = {"and", "but", "so"}
    for w in words:
        clean = re.sub(r"[^\w']", "", w).lower()
        cur.append(w)
        if bool(re.search(r"[,.!?;:]$", w)) or (clean in conjunctions and len(cur) >= 2) or len(cur) >= max_words:
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    return phrases


def _shape_two_lines(words: list[str], max_words: int) -> list[str]:
    if len(words) <= max_words:
        return [" ".join(words)]
    total = len(words)
    target = max(2, round(total * 0.42))
    candidates: set[int] = set()
    conjunctions = {"and", "but", "so"}
    for idx, word in enumerate(words[:-1], start=1):
        clean = re.sub(r"[^\w']", "", word).lower()
        if re.search(r"[,.!?;:]$", word):
            candidates.add(idx)
        if clean in conjunctions and idx > 1:
            candidates.add(idx - 1)
        if idx % max_words == 0:
            candidates.add(idx)
    valid = [c for c in candidates if 1 <= c < total and c <= (total - c)]
    if valid:
        split = min(
            valid,
            key=lambda c: (
                re.sub(r"[^\w']", "", words[c - 1]).lower() in conjunctions,
                abs(c - target),
                c,
            ),
        )
    else:
        split = min(target, max_words, total - 1)
        if total - split < split:
            split = max(1, split - 1)
    left, right = words[:split], words[split:]
    return [" ".join(left), " ".join(right)] if right else [" ".join(left)]


def break_text_by_words(text: str, max_words: int) -> str:
    try:
        words = str(text or "").split()
        if not words or max_words < 1:
            return str(text or "")
        return "\n".join(_shape_two_lines(words, max(2, int(max_words))))
    except Exception:
        return text


def select_subtitle_keywords(text: str, keywords: list, market: str = "US", max_terms: int = 2) -> list[str]:
    try:
        if str(market or "").upper() == "EU":
            max_terms = min(max_terms, 1)
        words = re.findall(r"\b[\w']+\b", str(text or ""), flags=re.UNICODE)
        low_text = str(text or "").lower()
        picked: list[str] = []
        for kw in keywords or []:
            if len(picked) >= max_terms:
                break
            if str(kw).lower() in low_text:
                picked.append(str(kw))
        if len(picked) < max_terms:
            candidates = [
                w for w in words
                if len(w) >= 5 and w.lower() not in _STOPWORDS and not w.isdigit()
            ]
            candidates.sort(key=lambda w: (len(w), words.index(w)), reverse=True)
            for w in candidates:
                if len(picked) >= max_terms:
                    break
                if not any(w.lower() == p.lower() for p in picked):
                    picked.append(w)
        return picked[:max_terms]
    except Exception:
        return []


def highlight_keywords_in_text(text: str, keywords: list, market: str = "US") -> str:
    """Uppercase whole-word keyword matches in subtitle text.

    JP is skipped — UPPERCASE is not meaningful for CJK characters.
    Multi-word keywords work as long as no line-break falls inside the phrase.
    """
    try:
        if not text or not keywords:
            return text
        selected = select_subtitle_keywords(text, keywords, market, 2)
        if not selected:
            return text
        result = text
        marker_market = str(market or "US").upper()
        for kw in selected:
            pattern = r'\b' + re.escape(kw) + r'\b'
            result = re.sub(
                pattern,
                lambda m: f"{_HL_OPEN}{marker_market}:{m.group(0)}{_HL_CLOSE}",
                result,
                count=1,
                flags=re.IGNORECASE,
            )
        return result
    except Exception:
        return text


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

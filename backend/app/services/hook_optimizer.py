"""
hook_optimizer.py — Rule-based hook quality analyzer.

Analyzes a short subtitle text snippet (first 3-5 seconds) and returns
scoring, issue detection, and market-appropriate suggestions.

Does NOT rewrite original content — returns suggestions only.

Usage:
    from app.services.hook_optimizer import analyze_hook

    result = analyze_hook("So today we are going to look at...", market="US")
    # {
    #   "hook_score":        15,
    #   "strength":          "weak",
    #   "issues":            ["No strong action verb", "No clear benefit", "Too long (14 words)"],
    #   "suggestions":       ["Stop doing this if you want results...", ...],
    #   "improved_examples": [...],
    # }
"""
from __future__ import annotations

import re
from typing import Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# Signal word sets
# ─────────────────────────────────────────────────────────────────────────────

_STRONG_VERBS: frozenset = frozenset({
    "stop", "start", "make", "avoid", "discover", "learn", "find",
    "get", "try", "use", "build", "create", "do", "take", "need",
    "watch", "listen", "think", "know", "see", "grab", "check",
    "change", "fix", "beat", "win", "unlock", "master",
})

_BENEFIT_WORDS: frozenset = frozenset({
    "money", "results", "improve", "faster", "better", "save", "earn",
    "profit", "grow", "success", "win", "free", "proven", "easy",
    "effective", "powerful", "simple", "quick", "best", "boost",
    "transform", "achieve", "gain", "impact", "value", "worth",
})

# Passive-voice detector: "is/are/was/were + past participle"
_PASSIVE_RE = re.compile(
    r'\b(is|are|was|were|been|being)\s+(done|made|used|shown|given|told|said|known|seen|found|created|built)\b',
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# Market hook templates
# ─────────────────────────────────────────────────────────────────────────────

_SUGGESTIONS: Dict[str, List[str]] = {
    "US": [
        'Stop doing this if you want real results...',
        'This one thing will make you money...',
        'Avoid this mistake before it\'s too late...',
        'Start doing this to grow faster than ever...',
    ],
    "EU": [
        'Here\'s a practical way to improve right now...',
        'Based on real results, this actually works...',
        'Research shows this is the most effective approach...',
        'The honest truth about what actually delivers results...',
    ],
    "JP": [
        '実はこれだけで変わります',          # 実はこれだけで変わります
        '知らないと損するかも',                       # 知らないと損するかも
        'これを見てから決めてください',  # これを見てから決めてください
        'ちょっと待って、これ大事です',  # ちょっと待って、これ大事です
    ],
}

_VALID_MARKETS = frozenset(_SUGGESTIONS.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def analyze_hook(text: str, market: str = "US") -> dict:
    """Analyze hook quality of a subtitle text snippet.

    Args:
        text:   The first few seconds of subtitle text (3-5 sec worth).
        market: Target market — "US", "EU", or "JP". Unknown values → "US".

    Returns:
        {
            "hook_score":        int   (0-100),
            "strength":          str   ("weak" | "medium" | "strong"),
            "issues":            list[str],
            "suggestions":       list[str],  (2 market-specific templates)
            "improved_examples": list[str],  (all 4 templates for market)
        }
    """
    m = str(market or "US").strip().upper()
    if m not in _VALID_MARKETS:
        m = "US"

    templates = _SUGGESTIONS[m]

    # Empty input — safe fallback
    if not str(text or "").strip():
        return {
            "hook_score":        0,
            "strength":          "weak",
            "issues":            ["No hook text provided"],
            "suggestions":       templates[:2],
            "improved_examples": templates,
        }

    clean      = str(text).strip()
    words      = clean.split()
    word_count = len(words)
    lower      = clean.lower()

    issues: List[str] = []

    # ── Signal detection ──────────────────────────────────────────────────────

    has_strong_verb = any(
        re.search(r'\b' + re.escape(v) + r'\b', lower) for v in _STRONG_VERBS
    )
    has_benefit = any(
        re.search(r'\b' + re.escape(b) + r'\b', lower) for b in _BENEFIT_WORDS
    )
    has_passive = bool(_PASSIVE_RE.search(clean))

    # ── Scoring ───────────────────────────────────────────────────────────────
    # Start at 40 (neutral). Positive signals push toward 100, negative toward 0.

    score = 40

    if has_strong_verb:
        score += 25
    else:
        issues.append("No strong action verb (stop, start, discover, etc.)")

    if has_benefit:
        score += 20
    else:
        issues.append("No clear benefit or result mentioned")

    if word_count <= 8:
        score += 15          # punchy bonus
    elif word_count > 12:
        score -= 20
        issues.append(f"Too long ({word_count} words — aim for ≤12)")

    if has_passive:
        score -= 15
        issues.append("Passive voice detected — prefer active tone")

    score = max(0, min(100, score))

    if score >= 70:
        strength = "strong"
    elif score >= 40:
        strength = "medium"
    else:
        strength = "weak"

    return {
        "hook_score":        score,
        "strength":          strength,
        "issues":            issues,
        "suggestions":       templates[:2],
        "improved_examples": templates,
    }

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

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "this", "that", "i", "you",
    "we", "they", "he", "she", "my", "your", "our", "their", "so", "just",
    "like", "what", "when", "then", "now",
})

_PATTERNS: Dict[str, dict] = {
    "US": {
        "names": ["shock_bold_claim", "you_wont_believe", "result_first"],
        "templates": [
            "You won't believe {core}",
            "This went sideways fast: {core}",
            "The result starts here: {core}",
            "Nobody expected {core}",
            "Watch what happens when {core}",
        ],
        "regex": [r"you won't believe", r"went sideways", r"result starts", r"nobody expected", r"watch what happens"],
    },
    "EU": {
        "names": ["trust_info", "structured_phrasing", "lower_hype"],
        "templates": [
            "Here is what happened: {core}",
            "The key detail is {core}",
            "A clear look at {core}",
            "Why this moment matters: {core}",
            "What this shows about {core}",
        ],
        "regex": [r"here is what happened", r"key detail", r"clear look", r"why this moment matters", r"what this shows"],
    },
    "JP": {
        "names": ["curiosity", "soft_tension", "storytelling"],
        "templates": [
            "At first, it looks simple: {core}",
            "Then this small moment changes things",
            "The quiet detail is {core}",
            "There is more to this moment than it seems",
            "This starts like a normal story, then {core}",
        ],
        "regex": [r"at first", r"small moment changes", r"quiet detail", r"more to this moment", r"normal story"],
    },
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text or "").lower())


def _context_core(text: str) -> tuple[str, str]:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    words = _words(clean)
    content = [w for w in words if len(w) > 2 and w not in _STOPWORDS]
    core_words = content[:6] or [w for w in words if len(w) > 1][:6]
    core = " ".join(core_words) or "this moment"
    if len(core) > 52:
        core = core[:49].strip() + "..."
    return clean, core


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def score_hook_variant(hook: str, source_text: str, market: str = "US") -> dict:
    m = str(market or "US").strip().upper()
    if m not in _PATTERNS:
        m = "US"
    clean = re.sub(r"\s+", " ", str(hook or "")).strip()
    lower = clean.lower()
    hook_words = _words(clean)
    source_words = {w for w in _words(source_text) if w not in _STOPWORDS}
    hook_content = [w for w in hook_words if w not in _STOPWORDS]
    overlap = sum(1 for w in hook_content if w in source_words)
    alignment = (overlap / len(hook_content)) if hook_content else 0.0
    wc = len(hook_words)
    cfg = _PATTERNS[m]

    curiosity = _clamp_score((18 if "?" in clean else 0) + (62 if re.search(r"\b(why|what|how|watch|believe|expected|moment|detail|then|first)\b", lower) else 28) + (16 if alignment >= 0.25 else 0))
    emotion = _clamp_score((70 if re.search(r"\b(won't believe|sideways|nobody|expected|changes|matters|normal story|quiet|small moment)\b", lower) else 38) + (15 if m == "US" and re.search(r"\b(fast|believe|nobody|watch)\b", lower) else 0) + (12 if m != "US" and re.search(r"\b(clear|detail|quiet|moment)\b", lower) else 0))
    clarity = _clamp_score((86 if alignment >= 0.45 else 72 if alignment >= 0.25 else 58 if alignment > 0 else 28) - (14 if wc > 14 else 0))
    pattern = _clamp_score(92 if any(re.search(p, lower) for p in cfg["regex"]) else 48)
    market_fit = _clamp_score(pattern * 0.72 + (22 if any(re.search(p, lower) for p in cfg["regex"]) else 8))
    length = 58 if wc < 4 else 96 if wc <= 10 else 78 if wc <= 14 else max(35, 78 - (wc - 14) * 7)
    unsupported = [w for w in ("money", "profit", "earn", "million", "secret", "guaranteed") if w in lower and w not in source_words]
    penalty = (18 if alignment == 0 else 8 if alignment < 0.2 else 0) + len(unsupported) * 12
    if m != "US" and re.search(r"\b(won't believe|nobody expected|shocking|insane)\b", lower):
        penalty += 10

    score = _clamp_score(curiosity * 0.20 + emotion * 0.16 + clarity * 0.22 + pattern * 0.16 + market_fit * 0.16 + length * 0.10 - penalty)
    issues = []
    if alignment < 0.2:
        issues.append("Low content alignment")
    if unsupported:
        issues.append("Unsupported claim: " + ", ".join(unsupported))
    if wc > 14:
        issues.append(f"Too long ({wc} words)")
    if not issues and score >= 70:
        issues.append("Aligned hook candidate")
    return {
        "hook": clean,
        "hook_score": score,
        "hook_text_score": score,
        "strength": "strong" if score >= 72 else "medium" if score >= 48 else "weak",
        "curiosity_score": curiosity,
        "emotion_score": emotion,
        "clarity_score": clarity,
        "pattern_score": pattern,
        "market_fit_score": market_fit,
        "length_score": _clamp_score(length),
        "alignment_score": _clamp_score(alignment * 100),
        "issues": issues,
    }


def optimize_hook_variants(text: str, market: str = "US") -> dict:
    m = str(market or "US").strip().upper()
    if m not in _PATTERNS:
        m = "US"
    clean, core = _context_core(text)
    if not clean:
        return {"best_hook": "", "all_variants": [], "scores": [], "market": m, "patterns": _PATTERNS[m]["names"]}
    variants = []
    seen = set()
    for tmpl in _PATTERNS[m]["templates"]:
        hook = re.sub(r"\s+([:,.?!])", r"\1", tmpl.format(core=core)).strip()
        key = hook.lower()
        if hook and key not in seen:
            seen.add(key)
            variants.append(hook)
    scores = sorted((score_hook_variant(v, clean, m) for v in variants[:5]), key=lambda x: x["hook_score"], reverse=True)
    return {
        "best_hook": scores[0]["hook"] if scores else "",
        "all_variants": [s["hook"] for s in scores],
        "scores": scores,
        "market": m,
        "patterns": _PATTERNS[m]["names"],
        "source_excerpt": clean,
        "formula": "0.20 curiosity + 0.16 emotion + 0.22 clarity + 0.16 pattern + 0.16 market_fit + 0.10 length - penalties",
    }


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
    optimized = optimize_hook_variants(text, market)
    m = optimized["market"]
    templates = _SUGGESTIONS[m]

    # Empty input — safe fallback
    if not str(text or "").strip():
        return {
            "hook_score":        0,
            "strength":          "weak",
            "issues":            ["No hook text provided"],
            "suggestions":       templates[:2],
            "improved_examples": templates,
            "best_hook":         "",
            "all_variants":      [],
            "scores":            [],
        }

    best = optimized["scores"][0] if optimized["scores"] else score_hook_variant(str(text or ""), str(text or ""), m)
    return {
        "hook_score":        best["hook_score"],
        "hook_text_score":   best["hook_score"],
        "strength":          best["strength"],
        "issues":            best["issues"],
        "suggestions":       optimized["all_variants"][:2],
        "improved_examples": optimized["all_variants"],
        "best_hook":         optimized["best_hook"],
        "all_variants":      optimized["all_variants"],
        "scores":            optimized["scores"],
        "formula":           optimized["formula"],
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

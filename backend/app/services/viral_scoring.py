"""
viral_scoring.py — Market-aware viral scoring engine for video parts.

Scores text content for viral potential in US, EU, or JP markets.
Each market has distinct hook patterns, keyword sets, scoring weights,
and tone profiles.  The SAME input text produces different scores,
different tiers, and different reasons in each market.

Usage:
    from backend.app.services.viral_scoring import score_part_for_market

    result = score_part_for_market(
        "Stop doing this if you want to make money",
        duration=65,
        market="US",
    )
    # → {"viral_score": 71, "viral_tier": "hot", "viral_market": "US",
    #     "reasons": ["[hook] strong match ...", "[keywords] money(1)", ...]}

Example outputs for "Stop doing this if you want to make money" (no duration):
    US → viral_score≈71  tier="hot"    (strong hook + money keyword)
    EU → viral_score≈24  tier="normal" (aggressive tone penalized, no credibility)
    JP → viral_score≈21  tier="weak"   (direct/financial language rejected)

Scoring components:
    score_hook()        — hook pattern match rate
    score_keywords()    — market-relevant keyword density
    score_duration()    — duration fit for market content norms
    score_tone()        — tonal alignment; each market boosts / penalizes differently
    score_readability() — text length fit for market attention style

Tier boundaries:
    hot    ≥ 65
    warm   ≥ 45
    normal ≥ 22
    weak   <  22
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Market Configuration
# ─────────────────────────────────────────────────────────────────────────────

MARKET_CONFIG: Dict[str, Dict] = {

    # ─────────────────────────────────────────────────────────────────────────
    # US — direct, aggressive, high-energy, result-driven
    #
    # Hook style   : commanding imperatives, shock openers, number claims
    # Keywords     : money/income, growth/scale, transformation, urgency, proof
    # Tone rewards : power words, urgency language, emotional intensity
    # Tone penalizes: passive / hedged language ("maybe", "kind of")
    # Duration     : 55-85 s sweet spot (punchy, action-packed)
    # Readability  : 8-18 words (short and impactful)
    # ─────────────────────────────────────────────────────────────────────────
    "US": {
        "hook_patterns": [
            r"\bstop\b",
            r"\bnever\s+again\b",
            r"\byou won't believe\b",
            r"\bsecret\b",
            r"\b(hack|hacks|cheat code)\b",
            r"\bwhy (most|everyone|nobody)\b",
            r"\bdo this (now|today|immediately|right now)\b",
            r"\b(change|transform) your\b",
            r"\bthis is why\b",
            r"\bwhat (no one|nobody) tells you\b",
            r"\b(warning|alert)\b",
            r"\bdon't (do|make|buy|use|ignore|miss)\b",
            r"\b(instantly|immediately|overnight)\b",
            r"\b\d+\s*(reasons|ways|tips|tricks|steps|mistakes|things)\b",
            r"\bhow (i|we) (made|earned|built|grew|lost|gained)\b",
            r"\bif you want to\b",
            r"\bstop wasting\b",
            r"\bthe (number one|#1|top)\b",
        ],
        "keyword_sets": {
            "money": [
                "money", "income", "earn", "profit", "rich", "wealthy",
                "revenue", "cash", "salary", "make money", "financial freedom",
            ],
            "growth": [
                "grow", "growth", "scale", "expand", "boost", "double",
                "triple", "skyrocket", "10x", "increase", "explode",
            ],
            "transformation": [
                "transform", "change", "results", "success", "achieve",
                "win", "goal", "before and after", "level up", "breakthrough",
            ],
            "urgency": [
                "now", "today", "immediately", "fast", "quick", "instant",
                "limited", "deadline", "hurry", "don't wait", "last chance",
            ],
            "proof": [
                "million", "thousand", "percent", "100k", "10k",
                "followers", "views", "subscribers", "downloads",
            ],
        },
        "scoring_weights": {
            "hook":        0.30,
            "keywords":    0.25,
            "duration":    0.15,
            "tone":        0.15,
            "readability": 0.15,
        },
        "tone_profile": {
            "power_words": [
                "crush", "dominate", "destroy", "shatter", "massive",
                "insane", "crazy", "huge", "epic", "viral", "unstoppable",
                "blazing", "explosive", "unreal",
            ],
            "urgency_words": [
                "stop", "start", "act now", "don't wait", "limited",
                "before it's too late", "right now", "immediately",
                "today only", "hurry",
            ],
            "emotion_words": [
                "shocked", "amazed", "unbelievable", "incredible",
                "jaw-dropping", "obsessed", "mind-blowing", "blown away",
                "can't believe",
            ],
            # US penalizes weakness / hedging:
            "passive_penalty": [
                "maybe", "perhaps", "might be", "could be",
                "somewhat", "kind of", "sort of", "i guess", "not sure",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────────────────
    # EU — trust-based, informative, credibility-first
    #
    # Hook style   : explanatory questions, data-backed openers, guide framing
    # Keywords     : research/evidence, explanation/clarity, usefulness, transparency
    # Tone rewards : trust signals, clarity language, factual references
    # Tone penalizes: hype words, aggressive urgency, overblown claims
    # Duration     : 70-120 s sweet spot (room for explanation)
    # Readability  : 15-35 words (complete sentences, informative depth)
    # ─────────────────────────────────────────────────────────────────────────
    "EU": {
        "hook_patterns": [
            r"\bwhat (you should|everyone should|most people) (know|understand|consider)\b",
            r"\bthe (real|actual|true|honest) (reason|truth|story|answer|explanation)\b",
            r"\bbased on (data|research|studies|science|evidence|facts|statistics)\b",
            r"\bthis explains (why|how|what)\b",
            r"\bhere'?s?\s+(why|how|what)\b",
            r"\bwhy (experts|scientists|researchers|doctors|specialists) (say|recommend|warn|advise)\b",
            r"\b(study|research|report|analysis|survey) (shows|reveals|finds|confirms|indicates)\b",
            r"\bguide (to|for)\b",
            r"\b(explained|breakdown|overview)\b",
            r"\bin (simple|plain|clear|easy) (words|terms|language|steps)\b",
            r"\bdid you know\b",
            r"\bhave you ever wondered\b",
            r"\blet'?s? (look at|examine|compare|understand)\b",
            r"\bthe (complete|full|honest) (guide|truth|picture)\b",
        ],
        "keyword_sets": {
            "credibility": [
                "research", "study", "expert", "scientist", "evidence",
                "data", "analysis", "proven", "fact", "report", "source",
                "verified", "peer-reviewed", "statistics", "cited",
            ],
            "explanation": [
                "explained", "reason", "because", "therefore", "since",
                "due to", "as a result", "means that", "that is why",
                "in other words", "to clarify", "which means",
            ],
            "usefulness": [
                "useful", "helpful", "practical", "guide", "advice",
                "recommendation", "improve", "benefit", "effective",
                "worthwhile", "valuable", "tip",
            ],
            "transparency": [
                "honest", "truth", "transparent", "openly", "clearly",
                "actually", "reality", "genuine", "authentic", "fair",
                "unbiased", "objective", "straightforward",
            ],
            "knowledge": [
                "understand", "learn", "know", "aware", "informed",
                "education", "insight", "knowledge", "discovery", "finding",
                "lesson",
            ],
        },
        "scoring_weights": {
            "hook":        0.22,
            "keywords":    0.24,
            "duration":    0.14,
            "tone":        0.20,
            "readability": 0.20,
        },
        "tone_profile": {
            "trust_words": [
                "proven", "research", "expert", "fact", "clear",
                "honest", "transparent", "understand", "explain",
                "verify", "confirm", "reliable", "accurate", "evidence",
            ],
            "clarity_words": [
                "simple", "clear", "easy to", "step by step", "guide",
                "overview", "summary", "breakdown", "explained",
                "straightforward", "in short", "let me explain",
            ],
            # EU actively penalizes US-style hype and aggressive urgency:
            "hype_penalty": [
                "insane", "crazy", "unbelievable", "mind-blowing",
                "explode", "crush", "dominate", "shatter", "jaw-dropping",
                "epic", "viral", "stop doing", "warning", "make money fast",
                "get rich", "overnight", "instantly", "you won't believe",
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────────────────
    # JP — subtle, emotional, curiosity-driven, daily-life storytelling
    #
    # Hook style   : soft curiosity ("actually", "turns out"), personal experience
    #                ("i tried"), Japanese-language soft openers (実は, やってみた)
    # Keywords     : convenience/easy, daily-life, gentle recommendation, emotion
    # Tone rewards : soft, relatable, curious language
    # Tone penalizes: financial urgency, aggressive commands, Western-style hype
    # Duration     : 30-70 s sweet spot (short and snappy)
    # Readability  : 5-15 words (minimal, concise)
    # ─────────────────────────────────────────────────────────────────────────
    "JP": {
        "hook_patterns": [
            # Japanese soft-curiosity openers
            r"実は",
            r"知らないと損",
            r"これだけで",
            r"やってみた",
            r"試してみた",
            r"意外と",
            r"なぜか",
            r"気づいたら",
            r"なんと",
            r"〜してみた",
            # English soft-curiosity patterns common in JP-market content
            r"\bactually\b",
            r"\bturns out\b",
            r"\bi (tried|tested|discovered|realized|found out)\b",
            r"\bdidn't (know|expect|realize|think)\b",
            r"\b(so easy|so simple|so quick|incredibly easy|super easy)\b",
            r"\b(life hack|daily tip|simple way|easy way)\b",
            r"\btry this\b",
            r"\byou might not know\b",
            r"\bwithout (knowing|realizing)\b",
            r"\bjust (one|a simple|this one)\b",
        ],
        "keyword_sets": {
            "convenience": [
                "easy", "simple", "quick", "effortless", "convenient",
                "handy", "smooth", "just", "only", "one step",
            ],
            "daily_life": [
                "daily", "everyday", "morning", "night", "routine", "home",
                "life", "habit", "meal", "family", "work", "weekend", "cozy",
            ],
            "recommend": [
                "recommend", "try", "suggest", "worth", "good for", "nice",
                "favorite", "love", "enjoy", "helpful", "useful",
            ],
            "emotion": [
                "happy", "smile", "warm", "cozy", "comfortable", "peaceful",
                "gentle", "soft", "kind", "relaxing", "satisfying", "calm",
            ],
            "curiosity": [
                "actually", "turns out", "surprising", "unexpected",
                "discover", "realize", "notice", "found", "didn't know",
                "interesting",
            ],
        },
        "scoring_weights": {
            "hook":        0.24,
            "keywords":    0.22,
            "duration":    0.14,
            "tone":        0.25,
            "readability": 0.15,
        },
        "tone_profile": {
            "soft_words": [
                "actually", "turns out", "gently", "little", "just",
                "easy", "simple", "nice", "warm", "cozy", "daily",
                "try", "soft", "quiet", "calm", "slowly", "naturally",
            ],
            "curiosity_words": [
                "i wonder", "have you tried", "surprising", "unexpected",
                "interesting", "you might", "didn't expect", "noticed",
                "i found",
            ],
            # JP penalizes financial urgency, aggressive commands, Western-style hype.
            # Longer phrases are checked first (via sorted dedup) to avoid double-counting.
            "hype_penalty": [
                "stop", "crush", "destroy", "dominate", "explode",
                "insane", "crazy", "shatter", "make money", "get rich",
                "earn fast", "immediately", "right now", "warning",
                "urgent", "limited time", "act now", "don't miss",
            ],
            "aggression_penalty": [
                "stop doing", "never again", "you won't believe",
                "before it's too late", "don't miss", "act now",
                "fastest way to", "money making",
            ],
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_VALID_MARKETS = frozenset(MARKET_CONFIG.keys())

_TIER_THRESHOLDS = [
    (65, "hot"),
    (45, "warm"),
    (22, "normal"),
    (0,  "weak"),
]


def normalize_market(market: str) -> str:
    """Normalize market code to US/EU/JP; unknown values fall back to US."""
    m = str(market or "").strip().upper()
    return m if m in _VALID_MARKETS else "US"


def get_tier(score: float) -> str:
    """Map a 0-100 viral score to hot | warm | normal | weak."""
    for threshold, label in _TIER_THRESHOLDS:
        if score >= threshold:
            return label
    return "weak"


def _readable_pattern(pattern: str) -> str:
    """Strip regex metacharacters to produce a human-readable hint."""
    s = pattern.replace(r"\b", " ").replace("\\b", " ")
    s = re.sub(r"[\\^$.*+?{}\[\]]", "", s)
    s = s.replace("(", "").replace(")", "").replace("|", "/")
    return " ".join(s.split())[:48] or pattern[:30]


def _is_ascii_pattern(pattern: str) -> bool:
    return all(ord(c) < 128 for c in pattern)


# ─────────────────────────────────────────────────────────────────────────────
# Scoring components
# ─────────────────────────────────────────────────────────────────────────────

def score_hook(text: str, hook_patterns: List[str]) -> Tuple[float, List[str]]:
    """
    Score 0-100: how strongly the text opens with a market-appropriate hook.

    Each market's hook_patterns are tuned to different cultural expectations:
    - US: commanding imperatives, shock openers ("stop", "you won't believe")
    - EU: informative / explanatory openers ("based on data", "here's why")
    - JP: soft curiosity ("actually", "turns out", Japanese soft openers)

    Scoring: 0 matches → 0,  1 → 80,  2 → 90,  3+ → 100
    A single strong hook is already a meaningful signal (hence 80, not 40).
    """
    text_lower = text.lower()
    matched_labels: List[str] = []

    for pattern in hook_patterns:
        target = text_lower if _is_ascii_pattern(pattern) else text
        try:
            if re.search(pattern, target, re.IGNORECASE):
                matched_labels.append(_readable_pattern(pattern))
        except re.error:
            pass

    if not matched_labels:
        return 0.0, []

    n = len(matched_labels)
    score = 80.0 if n == 1 else (90.0 if n == 2 else 100.0)
    return score, matched_labels[:3]


def score_keywords(
    text: str, keyword_sets: Dict[str, List[str]], market: str
) -> Tuple[float, List[str]]:
    """
    Score 0-100: density of market-relevant keywords.

    Each market has completely different keyword categories:
    - US:  money, growth, transformation, urgency, proof
    - EU:  credibility, explanation, usefulness, transparency, knowledge
    - JP:  convenience, daily_life, recommend, emotion, curiosity

    The first matched category is worth different amounts per market
    (US values money/urgency words more aggressively):
      US first match = 60 pts, EU = 55, JP = 50
    Additional categories add 15 pts; density adds up to 20 pts.
    """
    text_lower = text.lower()
    matched_cats: List[str] = []
    total_hits = 0

    for category, keywords in keyword_sets.items():
        hits = sum(1 for kw in keywords if kw.lower() in text_lower)
        if hits:
            matched_cats.append(f"{category}({hits})")
            total_hits += hits

    if not matched_cats:
        return 0.0, []

    first_value: Dict[str, float] = {"US": 60.0, "EU": 55.0, "JP": 50.0}
    base = first_value.get(market, 55.0)
    score = base + (len(matched_cats) - 1) * 15.0 + min(total_hits * 5.0, 20.0)
    return min(round(score, 1), 100.0), matched_cats


def score_duration(
    duration: Optional[float], market: str
) -> Tuple[float, List[str]]:
    """
    Score 0-100: how well the part duration fits each market's preferred length.

    Optimal centres differ by market and content culture:
    - US: 70 s ± 18 s  (55-85 s sweet spot — high-energy, packed)
    - EU: 95 s ± 25 s  (70-120 s — room for explanation and context)
    - JP: 50 s ± 15 s  (30-70 s — short, snappy, daily-life format)

    Uses a Gaussian curve centred at the optimal value.
    Returns 55 (neutral) when duration is not provided.
    """
    if duration is None:
        return 55.0, ["duration not provided — neutral score applied"]

    duration = float(duration)
    params: Dict[str, Tuple[float, float, str]] = {
        "US": (70.0, 18.0, "55-85 s"),
        "EU": (95.0, 25.0, "70-120 s"),
        "JP": (50.0, 15.0, "30-70 s"),
    }
    center, sigma, label = params.get(market, params["US"])
    score = math.exp(-0.5 * ((duration - center) / sigma) ** 2) * 100.0
    return round(score, 1), [f"{duration:.0f}s — {market} optimal range is {label}"]


def score_tone(
    text: str, tone_profile: Dict, market: str
) -> Tuple[float, List[str]]:
    """
    Score 0-100: tonal alignment with market audience expectations.

    Markets reward and penalize completely different tonal qualities:

    US  — rewards power/urgency/emotion words; penalizes passive/hedged language
          (+12 per positive word, -10 per passive word)

    EU  — rewards trust/clarity signals; HEAVILY penalizes hype language
          (+10 per trust/clarity word, -18 per hype phrase)
          EU hype_penalty includes words that US rewards (insane, crush, viral)

    JP  — rewards soft/curiosity tone; STRONGLY penalizes aggressive/financial
          (+10 per soft/curiosity word, -25 per aggressive phrase)
          JP aggression_penalty uses longest-match deduplication to avoid
          double-counting overlapping phrases (e.g. "stop doing" covers "stop")

    Baseline score: 50 (neutral — no signals in either direction).
    Clamped to [0, 100].
    """
    text_lower = text.lower()
    reasons: List[str] = []
    score = 50.0

    if market == "US":
        pos = (
            tone_profile.get("power_words", [])
            + tone_profile.get("urgency_words", [])
            + tone_profile.get("emotion_words", [])
        )
        neg = tone_profile.get("passive_penalty", [])

        pos_found = [w for w in pos if w.lower() in text_lower]
        neg_found = [w for w in neg if w.lower() in text_lower]

        score += len(pos_found) * 12.0
        score -= len(neg_found) * 10.0

        if pos_found:
            reasons.append(
                f"high-energy/urgency tone words matched ({len(pos_found)}): "
                + ", ".join(pos_found[:3])
            )
        if neg_found:
            reasons.append(
                f"passive/weak language detected ({len(neg_found)}): "
                + ", ".join(neg_found[:3])
            )

    elif market == "EU":
        pos = tone_profile.get("trust_words", []) + tone_profile.get("clarity_words", [])
        neg = tone_profile.get("hype_penalty", [])

        pos_found = [w for w in pos if w.lower() in text_lower]
        neg_found = [w for w in neg if w.lower() in text_lower]

        score += len(pos_found) * 10.0
        score -= len(neg_found) * 18.0  # EU strongly penalizes hype

        if pos_found:
            reasons.append(
                f"credibility/clarity tone words matched ({len(pos_found)}): "
                + ", ".join(pos_found[:3])
            )
        if neg_found:
            reasons.append(
                f"hype/aggressive language penalized by EU audience ({len(neg_found)}): "
                + ", ".join(neg_found[:3])
            )

    elif market == "JP":
        pos = tone_profile.get("soft_words", []) + tone_profile.get("curiosity_words", [])
        # Combine both penalty lists and deduplicate longest-first so that
        # "stop doing" is counted as ONE violation (not also counted as "stop").
        raw_neg = (
            tone_profile.get("aggression_penalty", [])
            + tone_profile.get("hype_penalty", [])
        )
        all_neg = sorted(
            {w.lower() for w in raw_neg if w}, key=len, reverse=True
        )

        pos_found = [w for w in pos if w.lower() in text_lower]

        # Greedy longest-match deduplication
        consumed = text_lower
        neg_found: List[str] = []
        for phrase in all_neg:
            if phrase in consumed:
                neg_found.append(phrase)
                consumed = consumed.replace(phrase, "\x00" * len(phrase))

        score += len(pos_found) * 10.0
        score -= len(neg_found) * 25.0  # JP strongly rejects aggressive tone

        if pos_found:
            reasons.append(
                f"soft/relatable tone words matched ({len(pos_found)}): "
                + ", ".join(pos_found[:3])
            )
        if neg_found:
            reasons.append(
                f"direct/aggressive/financial tone rejected by JP audience ({len(neg_found)}): "
                + ", ".join(neg_found[:3])
            )

    if not reasons:
        reasons.append(f"neutral tone — no strong positive or negative signals for {market}")

    return round(max(0.0, min(100.0, score)), 1), reasons


def score_readability(text: str, market: str) -> Tuple[float, List[str]]:
    """
    Score 0-100: text length and structure fit for each market's attention style.

    Markets have very different length preferences:
    - US: 8-18 words (punchy, direct, high-impact — longer content loses attention fast)
    - EU: 15-35 words (informative depth — too short feels thin, very long is tolerated)
    - JP: 5-15 words (minimalist brevity — content above 15 words decays sharply)

    US gets a +10 bonus when the text contains a number (audiences trust specifics).
    """
    words = text.split()
    word_count = len(words)
    has_number = bool(re.search(r"\d+", text))
    reasons: List[str] = []

    if market == "US":
        if 8 <= word_count <= 18:
            score = 85.0
            reasons.append(f"punchy length ({word_count} words) — fits US direct style")
        elif word_count < 8:
            score = 50.0
            reasons.append(
                f"too short ({word_count} words) — US audiences expect an impactful statement"
            )
        else:
            score = max(25.0, 85.0 - (word_count - 18) * 3.0)
            reasons.append(
                f"length ({word_count} words) — US prefers shorter, punchier content"
            )
        if has_number:
            score = min(score + 10.0, 100.0)
            reasons.append("contains a number — US audiences respond well to specific figures")

    elif market == "EU":
        if 15 <= word_count <= 35:
            score = 85.0
            reasons.append(
                f"informative length ({word_count} words) — suits EU explanation style"
            )
        elif word_count < 15:
            score = max(30.0, 30.0 + word_count * 2.0)
            reasons.append(
                f"too brief ({word_count} words) — EU audiences expect more explanation depth"
            )
        else:
            score = max(40.0, 85.0 - (word_count - 35) * 1.5)
            reasons.append(
                f"long ({word_count} words) — EU tolerates depth but clarity suffers above 35"
            )

    elif market == "JP":
        if 5 <= word_count <= 15:
            score = 88.0
            reasons.append(f"concise length ({word_count} words) — ideal for JP brevity")
        elif word_count < 5:
            score = 65.0
            reasons.append(
                f"very short ({word_count} words) — minimal, may need more context"
            )
        else:
            score = max(15.0, 88.0 - (word_count - 15) * 4.0)
            reasons.append(
                f"too long ({word_count} words) — JP audiences strongly prefer shorter content"
            )

    else:
        score = 55.0
        reasons.append(f"word count {word_count}")

    return round(max(0.0, min(100.0, score)), 1), reasons


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def score_part_for_market(
    text: str,
    duration: Optional[float] = None,
    market: str = "US",
) -> Dict:
    """
    Score a video part's text for viral potential in a specific market.

    Args:
        text:     Subtitle / narration text from the video part.
        duration: Duration of the part in seconds (optional).
        market:   Target market — "US", "EU", or "JP".
                  Unknown values silently fall back to "US".

    Returns:
        {
            "viral_score":  int 0-100,
            "viral_tier":   "hot" | "warm" | "normal" | "weak",
            "viral_market": "US" | "EU" | "JP",
            "reasons":      [str, ...]   — ordered by component
        }

    Component weights per market
    ─────────────────────────────────────────────────
    Component      US     EU     JP
    hook           0.30   0.22   0.24   ← US most hook-dependent
    keywords       0.25   0.24   0.22   ← EU/JP rely more on other signals
    duration       0.15   0.14   0.14
    tone           0.15   0.20   0.25   ← JP most tone-sensitive
    readability    0.15   0.20   0.15   ← EU rewards explanatory depth
    ─────────────────────────────────────────────────
    """
    market = normalize_market(market)
    cfg = MARKET_CONFIG[market]
    w = cfg["scoring_weights"]

    text = str(text or "").strip()
    if not text:
        return {
            "viral_score":  0,
            "viral_tier":   "weak",
            "viral_market": market,
            "reasons":      ["no text provided"],
        }

    # ── Component scores ──────────────────────────────────────────────────────
    hook_s,  hook_r  = score_hook(text, cfg["hook_patterns"])
    kw_s,    kw_r    = score_keywords(text, cfg["keyword_sets"], market)
    dur_s,   dur_r   = score_duration(duration, market)
    tone_s,  tone_r  = score_tone(text, cfg["tone_profile"], market)
    read_s,  read_r  = score_readability(text, market)

    # ── Weighted composite ────────────────────────────────────────────────────
    composite = (
        hook_s  * w["hook"]
        + kw_s  * w["keywords"]
        + dur_s * w["duration"]
        + tone_s * w["tone"]
        + read_s * w["readability"]
    )
    viral_score = int(round(max(0.0, min(100.0, composite))))

    # ── Build reasons list ────────────────────────────────────────────────────
    reasons: List[str] = []

    # Hook
    if hook_s >= 60:
        reasons.append(
            f"[hook] strong {market} hook matched — "
            + (", ".join(hook_r) if hook_r else "pattern detected")
        )
    elif hook_s > 0:
        reasons.append(f"[hook] partial hook match ({hook_s:.0f}/100)")
    else:
        reasons.append(f"[hook] no {market}-style hook detected in opening")

    # Keywords
    if kw_s >= 55:
        reasons.append(f"[keywords] strong {market} keyword signal — {', '.join(kw_r)}")
    elif kw_s > 0:
        reasons.append(f"[keywords] {market} keywords found — {', '.join(kw_r)}")
    else:
        reasons.append(f"[keywords] no {market}-relevant keywords detected")

    # Tone (carries its own context-rich reasons)
    for r in tone_r:
        reasons.append(f"[tone] {r}")

    # Readability
    for r in read_r:
        reasons.append(f"[readability] {r}")

    # Duration
    for r in dur_r:
        reasons.append(f"[duration] {r}")

    return {
        "viral_score":  viral_score,
        "viral_tier":   get_tier(viral_score),
        "viral_market": market,
        "reasons":      reasons,
    }

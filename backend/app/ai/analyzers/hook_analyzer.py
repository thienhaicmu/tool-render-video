"""
hook_analyzer.py — Hook quality scorer with optional semantic upgrade.

Rule-based scoring always runs.
Semantic scoring (sentence-transformers) is loaded lazily on first use.
If the library is missing or model load fails, falls back to rule score only.

Public API:
    score_hook_text(text)                                    -> float (0-100)
    score_hook_text_semantic(text)                           -> float | None
    is_semantic_hook_available()                             -> bool
    detect_hook_type(text)                                   -> str
    get_opening_window_text(chunks, candidate_start, ...)    -> str
    score_hook_intelligence(text, goal)                      -> float ([0, +20])
"""
from __future__ import annotations

import math
import os
import re
from typing import Optional

from app.ai.dependencies import has_sentence_transformers

# Set HOOK_INTELLIGENCE_ENABLED=0 to disable the goal-aware bonus entirely.
HOOK_INTELLIGENCE_ENABLED: bool = os.environ.get("HOOK_INTELLIGENCE_ENABLED", "1") == "1"

# ---------------------------------------------------------------------------
# Hook taxonomy — 9 types, EN + VI patterns
# ---------------------------------------------------------------------------

_HOOK_PATTERNS: dict[str, dict[str, list[str]]] = {
    "curiosity": {
        "en": [
            r"\bwait\b",
            r"\blook at this\b",
            r"\bwatch this\b",
            r"\byou have to see\b",
            r"\bguess what\b",
            r"\byou won't believe\b",
        ],
        "vi": [
            r"khoan đã",
            r"hãy xem",
            r"nhìn cái này",
            r"xem đây",
            r"bạn có biết không",
        ],
    },
    "surprise": {
        "en": [
            r"\bthis changed everything\b",
            r"\bi can'?t believe\b",
            r"\bno way\b",
            r"\bunbelievable\b",
            r"\bwhat happened next\b",
            r"\bshocked\b",
        ],
        "vi": [
            r"điều này thay đổi",
            r"không thể tin",
            r"khó tin",
            r"bất ngờ",
            r"chấn động",
        ],
    },
    "warning": {
        "en": [
            r"\bstop doing\b",
            r"\bbefore you\b",
            r"\bnever do\b",
            r"\bdon'?t do this\b",
            r"\bbig mistake\b",
            r"\bwarning\b",
        ],
        "vi": [
            r"đừng làm",
            r"trước khi bạn",
            r"cảnh báo",
            r"sai lầm lớn nhất",
            r"đừng bao giờ",
            r"ngừng làm",
        ],
    },
    "authority": {
        "en": [
            r"\bi tested\b",
            r"\bi tried\b",
            r"\bhere'?s what happened\b",
            r"\bi spent\b",
            r"\bmy results\b",
            r"\bafter \d+\b",
            r"\bproved\b",
        ],
        "vi": [
            r"tôi đã thử",
            r"tôi đã kiểm tra",
            r"kết quả của tôi",
            r"tôi đã dành",
            r"tôi đã chứng minh",
        ],
    },
    "problem": {
        "en": [
            r"\bhere'?s why\b",
            r"\bthe reason\b",
            r"\bthe problem is\b",
            r"\bwhy (most|every|no)\b",
            r"\bthe truth\b",
            r"\bthe real reason\b",
        ],
        "vi": [
            r"đây là lý do",
            r"lý do là",
            r"vấn đề là",
            r"sự thật là",
            r"nguyên nhân là",
        ],
    },
    "story": {
        "en": [
            r"\bit all started\b",
            r"\bone day\b",
            r"\byears ago\b",
            r"\bback then\b",
            r"\bi was.{0,20}when\b",
        ],
        "vi": [
            r"hôm đó",
            r"lúc đó",
            r"ngày đó tôi",
            r"nhiều năm trước",
            r"câu chuyện bắt đầu",
        ],
    },
    "contrarian": {
        "en": [
            r"\bnobody talks about\b",
            r"\beveryone is wrong\b",
            r"\bmost people (don'?t|never)\b",
            r"\bunpopular opinion\b",
            r"\bnobody tells you\b",
            r"\bcontrary\b",
        ],
        "vi": [
            r"ít ai biết",
            r"hầu hết mọi người",
            r"ngược lại",
            r"sai lầm phổ biến",
            r"không ai nói cho bạn",
        ],
    },
    "result_first": {
        "en": [
            r"\bthis got me\b",
            r"\bi went from\b",
            r"\bhow i (made|got|earned|built|grew)\b",
            r"\bbefore.{0,20}after\b",
            r"\bthe results\b",
            r"\bin \d+ days?\b",
        ],
        "vi": [
            r"từ.{0,15}đến",
            r"kết quả là",
            r"tôi đã đạt",
            r"cách tôi kiếm",
            r"trước và sau",
        ],
    },
    "challenge": {
        "en": [
            r"\bi did.{0,20}(days?|weeks?|hours?)\b",
            r"\bwhat if you\b",
            r"\bchallenge\b",
            r"\b\d+ day(s)? (challenge|experiment)\b",
        ],
        "vi": [
            r"thử làm",
            r"thách thức",
            r"\d+ ngày",
            r"liệu bạn có",
            r"thí nghiệm",
        ],
    },
}

# ---------------------------------------------------------------------------
# Goal-to-hook multipliers
# Higher = this hook type is more valuable for this goal
# 1.0 = neutral, <1.0 = suppressed (still positive, never penalises absence)
# ---------------------------------------------------------------------------

_GOAL_MULTIPLIERS: dict[str, dict[str, float]] = {
    "viral": {
        "surprise":    2.0,
        "contrarian":  2.0,
        "curiosity":   1.8,
        "challenge":   1.6,
        "warning":     1.2,
        "result_first":1.0,
        "problem":     0.8,
        "authority":   0.6,
        "story":       0.6,
    },
    "education": {
        "authority":   2.0,
        "problem":     2.0,
        "warning":     1.8,
        "result_first":1.6,
        "curiosity":   1.0,
        "story":       0.8,
        "surprise":    0.7,
        "challenge":   0.7,
        "contrarian":  0.6,
    },
    "podcast": {
        "problem":     1.8,
        "story":       1.8,
        "contrarian":  1.6,
        "curiosity":   1.2,
        "authority":   1.0,
        "warning":     0.8,
        "result_first":0.6,
        "challenge":   0.6,
        "surprise":    0.5,
    },
    "product": {
        "result_first":2.0,
        "warning":     1.8,
        "authority":   1.8,
        "surprise":    1.2,
        "curiosity":   0.8,
        "problem":     0.8,
        "story":       0.7,
        "challenge":   0.6,
        "contrarian":  0.5,
    },
    "storytelling": {
        "story":       2.0,
        "curiosity":   1.8,
        "challenge":   1.6,
        "surprise":    1.2,
        "problem":     0.8,
        "authority":   0.7,
        "result_first":0.6,
        "contrarian":  0.5,
        "warning":     0.5,
    },
}

# ---------------------------------------------------------------------------
# Reference phrases for semantic similarity
# ---------------------------------------------------------------------------

_REFERENCE_HOOKS: list[str] = [
    "nobody tells you this",
    "this changed everything",
    "wait for it",
    "you need to know this",
    "the truth is",
    "most people get this wrong",
    "I was shocked",
    "before you do this",
    "stop doing this",
    "here is why",
]

# ---------------------------------------------------------------------------
# Rule-based signals (kept light — no heavy deps)
# ---------------------------------------------------------------------------

_STRONG_VERBS = frozenset({
    "stop", "start", "make", "avoid", "discover", "learn", "find",
    "get", "try", "build", "create", "watch", "know", "grab", "check",
    "change", "fix", "win", "unlock", "master", "need",
})

_BENEFIT_WORDS = frozenset({
    "money", "results", "improve", "faster", "better", "save", "earn",
    "profit", "grow", "success", "free", "proven", "easy", "effective",
    "powerful", "simple", "quick", "boost", "transform", "achieve",
})

_HOOK_SIGNALS = re.compile(
    r"\b(nobody|truth|secret|shocked|wrong|everybody|most people|"
    r"changed|everything|wait|you need|before you|stop doing|why|"
    r"nobody tells|you won't believe|here is)\b",
    re.IGNORECASE,
)

_PASSIVE_RE = re.compile(
    r"\b(is|are|was|were|been|being)\s+"
    r"(done|made|used|shown|given|told|said|known|seen|found|created|built)\b",
    re.IGNORECASE,
)


def _rule_score(text: str) -> float:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return 0.0

    lower = clean.lower()
    words = re.findall(r"[a-z0-9']+", lower)
    wc = len(words)

    score = 30.0

    if any(re.search(r"\b" + re.escape(v) + r"\b", lower) for v in _STRONG_VERBS):
        score += 20.0
    if any(re.search(r"\b" + re.escape(b) + r"\b", lower) for b in _BENEFIT_WORDS):
        score += 10.0
    if "?" in clean:
        score += 10.0
    if _HOOK_SIGNALS.search(lower):
        score += 25.0
    if wc <= 8:
        score += 15.0
    elif wc > 14:
        score -= 15.0
    if _PASSIVE_RE.search(clean):
        score -= 10.0

    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# Lazy semantic model
# ---------------------------------------------------------------------------

_model = None        # SentenceTransformer instance or False (failed)
_ref_vectors: Optional[list] = None
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _load_model():
    global _model, _ref_vectors
    if _model is not None:
        return _model is not False

    if not has_sentence_transformers():
        _model = False
        return False

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        m = SentenceTransformer(_MODEL_NAME)
        _ref_vectors = m.encode(_REFERENCE_HOOKS, convert_to_numpy=False)
        _model = m
        return True
    except Exception:
        _model = False
        return False


# ---------------------------------------------------------------------------
# Public API — existing (unchanged)
# ---------------------------------------------------------------------------

def is_semantic_hook_available() -> bool:
    return _load_model()


def score_hook_text_semantic(text: str) -> Optional[float]:
    """Return max cosine similarity against reference hooks scaled 0-100, or None."""
    if not _load_model():
        return None
    try:
        vec = _model.encode([str(text or "")], convert_to_numpy=False)[0]
        best = max(_cosine(vec, r) for r in _ref_vectors)
        return max(0.0, min(100.0, best * 100.0))
    except Exception:
        return None


def score_hook_text(text: str) -> float:
    """Score hook quality 0-100.

    Uses 60% rule + 40% semantic if sentence-transformers is available,
    otherwise rule score only.
    """
    rule = _rule_score(text)
    semantic = score_hook_text_semantic(text)
    if semantic is None:
        return rule
    return max(0.0, min(100.0, rule * 0.6 + semantic * 0.4))


# ---------------------------------------------------------------------------
# Public API — S2.1 Goal-Aware Hook Intelligence
# ---------------------------------------------------------------------------

def detect_hook_type(text: str) -> str:
    """Identify the dominant hook type in text. Returns hook name or 'none'.

    Scans both EN and VI pattern sets. The type with the most pattern matches wins.
    """
    if not text:
        return "none"
    lower = text.lower()
    best_type = "none"
    best_count = 0
    for hook_type, langs in _HOOK_PATTERNS.items():
        count = 0
        for lang_patterns in langs.values():
            for pattern in lang_patterns:
                if re.search(pattern, lower, re.IGNORECASE):
                    count += 1
        if count > best_count:
            best_count = count
            best_type = hook_type
    return best_type


def get_opening_window_text(
    chunks: list[dict],
    candidate_start: float,
    window_sec: float = 10.0,
) -> str:
    """Extract and join transcript text from the opening window of a candidate clip.

    Scans chunks whose start time falls within [candidate_start, candidate_start + window_sec].
    This correctly handles long-form content (podcast/tutorial/interview) where the
    candidate may start far into the source video — hook detection always scores
    the opening of THAT candidate, not the head of the source.
    """
    cutoff = candidate_start + window_sec
    opening = [
        c for c in (chunks or [])
        if float(c.get("start") or 0.0) >= candidate_start - 0.5
        and float(c.get("start") or 0.0) < cutoff
    ]
    return " ".join(c.get("text", "") for c in opening).strip()


def score_hook_intelligence(text: str, goal: str = "") -> float:
    """Score goal-aware hook bonus for a candidate's opening window.

    Returns an additive bonus in [0, +20] applied to hook_opening_score.
    Returns 0.0 when:
      - HOOK_INTELLIGENCE_ENABLED is False (env gate)
      - text is empty (graceful degradation when no transcript)
      - no hook type is detected

    Goal-aware multipliers bias the bonus toward hook types that resonate
    with the creator's declared goal without overriding their intent.
    Unknown or absent goals use a neutral multiplier of 1.0.
    """
    if not HOOK_INTELLIGENCE_ENABLED or not text:
        return 0.0

    hook_type = detect_hook_type(text)
    if hook_type == "none":
        return 0.0

    base_bonus = 10.0
    goal_key = str(goal or "").lower().strip()
    multiplier = _GOAL_MULTIPLIERS.get(goal_key, {}).get(hook_type, 1.0)

    return max(0.0, min(20.0, base_bonus * multiplier))

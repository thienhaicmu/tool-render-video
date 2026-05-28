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
# Reference phrases for semantic similarity — EN + VI, all 9 hook types
# ---------------------------------------------------------------------------

_REFERENCE_HOOKS: list[str] = [
    # Curiosity gap
    "nobody tells you this",
    "wait until you see what happens next",
    "you won't believe what I discovered",
    "bạn không biết điều bí mật này",
    "ít ai biết được sự thật này",
    # Warning / urgency
    "stop doing this immediately",
    "before you do this you need to watch this",
    "the biggest mistake most people make",
    "đừng bao giờ làm điều này nếu bạn muốn thành công",
    "cảnh báo quan trọng bạn cần biết ngay",
    # Surprise / contrarian
    "this changed everything for me",
    "I was completely wrong about this",
    "most people get this completely wrong",
    "everything you know about this is wrong",
    "điều này thay đổi tất cả những gì tôi biết",
    "ngược lại với những gì mọi người nghĩ",
    # Authority / proof
    "I tested this for 30 days and here are the results",
    "after years of experience here is what I learned",
    "the results shocked even me",
    "tôi đã thử điều này và kết quả thực sự bất ngờ",
    "sau nhiều năm kinh nghiệm đây là điều tôi học được",
    # Problem / solution
    "here is the real reason this keeps failing",
    "the truth is nobody wants to admit this",
    "sự thật là tại sao hầu hết mọi người không thành công",
    "đây là lý do thực sự khiến bạn thất bại",
    # Story
    "it all started when I made one decision",
    "I was struggling until I discovered this",
    "câu chuyện bắt đầu khi tôi đưa ra quyết định đó",
    "tôi đã thất bại liên tục cho đến khi tìm ra điều này",
    # Result first
    "I went from zero to success using this method",
    "how I achieved this in just 30 days",
    "tôi đã đi từ không có gì đến thành công nhờ điều này",
    "đây là cách tôi đạt được kết quả chỉ trong một tháng",
    # Challenge
    "I did this every single day for a month",
    "what actually happens when you try this for 30 days",
    "tôi đã làm điều này mỗi ngày và kết quả thay đổi cuộc đời tôi",
    # Weak openers (low similarity anchors — help calibrate the scale)
    "so today we are going to talk about something",
    "hello everyone welcome back to my channel today",
]

# ---------------------------------------------------------------------------
# Goal-specific exemplar sets for goal-aware semantic scoring
# ---------------------------------------------------------------------------

_GOAL_EXEMPLARS: dict[str, list[str]] = {
    "viral": [
        "you won't believe what happened next",
        "this is the most shocking thing I have ever seen",
        "nobody is talking about this but everyone needs to know",
        "wait until the very end of this video",
        "điều bất ngờ nhất tôi từng chứng kiến trong cuộc đời",
        "không ai nói cho bạn biết điều này nhưng bạn cần phải biết",
    ],
    "education": [
        "here is the exact step by step process to achieve this",
        "let me explain precisely how this works and why it matters",
        "the most important concept you need to understand about this topic",
        "đây là hướng dẫn từng bước chính xác để đạt được điều này",
        "hãy để tôi giải thích rõ ràng cách hoạt động của điều này",
        "khái niệm quan trọng nhất bạn cần hiểu về chủ đề này",
    ],
    "podcast": [
        "this conversation will completely change how you think about",
        "we need to have an honest discussion about this important topic",
        "my guest today completely transformed my perspective on life",
        "cuộc trò chuyện này sẽ thay đổi hoàn toàn cách bạn nhìn nhận",
        "hôm nay chúng ta cần thảo luận thẳng thắn về vấn đề quan trọng này",
    ],
    "product": [
        "this product completely changed the way I do everything",
        "the before and after results using this for 30 days",
        "I tested every product on the market and this is the winner",
        "sản phẩm này thay đổi hoàn toàn cách tôi làm mọi thứ",
        "kết quả trước và sau khi sử dụng sản phẩm này 30 ngày",
        "tôi đã thử tất cả sản phẩm trên thị trường và đây là cái tốt nhất",
    ],
    "storytelling": [
        "the day my entire life changed forever was unexpected",
        "I never in a million years expected this to happen to me",
        "this is the story of how one moment transformed everything",
        "ngày mà cuộc đời tôi thay đổi mãi mãi là một ngày bình thường",
        "tôi không bao giờ nghĩ điều này sẽ xảy ra với tôi",
        "đây là câu chuyện về cách một khoảnh khắc thay đổi tất cả",
    ],
}

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
_goal_ref_vectors: dict[str, list] = {}   # cached per-goal exemplar embeddings
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


def _ensure_goal_vectors(goal: str) -> bool:
    """Pre-compute and cache embeddings for goal-specific exemplars."""
    if not _load_model() or not goal or goal not in _GOAL_EXEMPLARS:
        return False
    if goal in _goal_ref_vectors:
        return True
    try:
        _goal_ref_vectors[goal] = _model.encode(  # type: ignore[union-attr]
            _GOAL_EXEMPLARS[goal], convert_to_numpy=False
        )
        return True
    except Exception:
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
        vec = _model.encode([str(text or "")], convert_to_numpy=False)[0]  # type: ignore[union-attr]
        best = max(_cosine(vec, r) for r in _ref_vectors)  # type: ignore[union-attr]
        return max(0.0, min(100.0, best * 100.0))
    except Exception:
        return None


def score_hook_semantic_by_goal(text: str, goal: str = "") -> Optional[float]:
    """Similarity score (0-100) against goal-specific exemplars + general hooks.

    Uses goal exemplars when available, blended with general reference hooks.
    Returns None when sentence-transformers is unavailable.
    """
    if not _load_model():
        return None
    try:
        vec = _model.encode([str(text or "")], convert_to_numpy=False)[0]  # type: ignore[union-attr]

        goal_key = str(goal or "").lower().strip()
        if _ensure_goal_vectors(goal_key):
            goal_sim = max(_cosine(vec, r) for r in _goal_ref_vectors[goal_key])
        else:
            goal_sim = 0.0

        general_sim = max(_cosine(vec, r) for r in _ref_vectors)  # type: ignore[union-attr]

        # Weight goal-specific similarity higher when available
        if goal_sim > 0.0:
            best_sim = goal_sim * 0.65 + general_sim * 0.35
        else:
            best_sim = general_sim

        return max(0.0, min(100.0, best_sim * 100.0))
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
    Two signals combined:
      1. Regex path — pattern-matched hook type × goal multiplier (dominant)
      2. Semantic path — goal-aware exemplar similarity (catches regex misses,
         e.g. novel phrasing, Vietnamese hooks not in pattern list)

    Returns 0.0 when HOOK_INTELLIGENCE_ENABLED is False or text is empty.
    Never raises.
    """
    if not HOOK_INTELLIGENCE_ENABLED or not text:
        return 0.0

    goal_key = str(goal or "").lower().strip()
    hook_type = detect_hook_type(text)

    # Regex path
    if hook_type != "none":
        multiplier = _GOAL_MULTIPLIERS.get(goal_key, {}).get(hook_type, 1.0)
        regex_bonus = 10.0 * multiplier  # [0, 20]
    else:
        regex_bonus = 0.0

    # Semantic path — goal-aware (activates only when sentence-transformers installed)
    semantic_sim = score_hook_semantic_by_goal(text, goal_key)
    if semantic_sim is not None and semantic_sim > 55.0:
        # [55, 100] → [0, 15]; lower ceiling than regex to keep regex dominant
        semantic_bonus = (semantic_sim - 55.0) / 45.0 * 15.0
    else:
        semantic_bonus = 0.0

    if hook_type != "none":
        # Regex detected: semantic adds a small boost (up to +4)
        result = regex_bonus + semantic_bonus * 0.27
    else:
        # Regex missed: semantic is the only signal (catches novel/VI hooks)
        result = semantic_bonus

    return max(0.0, min(20.0, result))

"""
hook_analyzer.py — Hook quality scorer with optional semantic upgrade.

Rule-based scoring always runs.
Semantic scoring (sentence-transformers) is loaded lazily on first use.
If the library is missing or model load fails, falls back to rule score only.

Public API:
    score_hook_text(text)          -> float   (0-100, always works)
    score_hook_text_semantic(text) -> float | None
    is_semantic_hook_available()   -> bool
"""
from __future__ import annotations

import math
import re
from typing import Optional

from app.ai.dependencies import has_sentence_transformers

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
# Public API
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

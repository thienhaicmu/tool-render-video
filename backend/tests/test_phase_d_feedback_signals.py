"""Phase D — Creator Feedback Loop QA tests.

Covers:
  - features/render/ai/feedback/signals.py:
      FeedbackSignals.is_empty, to_prompt_hint, build_signals
"""
from __future__ import annotations

from app.features.render.ai.feedback.signals import FeedbackSignals, build_signals


# ── FeedbackSignals.is_empty ──────────────────────────────────────────────────

def test_is_empty_default():
    fs = FeedbackSignals()
    assert fs.is_empty() is True


def test_is_empty_with_liked():
    fs = FeedbackSignals(liked_hook_types=["question"])
    assert fs.is_empty() is False


def test_is_empty_with_avoided():
    fs = FeedbackSignals(avoided_hook_types=["shock"])
    assert fs.is_empty() is False


def test_is_empty_with_duration():
    fs = FeedbackSignals(preferred_duration=(30.0, 60.0))
    assert fs.is_empty() is False


# ── FeedbackSignals.to_prompt_hint ────────────────────────────────────────────

def test_to_prompt_hint_returns_empty_when_too_few_samples():
    fs = FeedbackSignals(
        liked_hook_types=["question"],
        sample_size=2,
    )
    assert fs.to_prompt_hint() == ""


def test_to_prompt_hint_returns_empty_when_no_signal():
    fs = FeedbackSignals(sample_size=10)
    assert fs.to_prompt_hint() == ""


def test_to_prompt_hint_includes_sample_count():
    fs = FeedbackSignals(
        liked_hook_types=["question"],
        sample_size=5,
    )
    hint = fs.to_prompt_hint()
    assert "5" in hint
    assert "question" in hint


def test_to_prompt_hint_includes_avoided_hooks():
    fs = FeedbackSignals(
        liked_hook_types=["story"],
        avoided_hook_types=["shock"],
        sample_size=10,
    )
    hint = fs.to_prompt_hint()
    assert "shock" in hint
    assert "Avoid" in hint


def test_to_prompt_hint_includes_duration_range():
    fs = FeedbackSignals(
        liked_hook_types=["story"],
        preferred_duration=(30.0, 60.0),
        sample_size=5,
    )
    hint = fs.to_prompt_hint()
    assert "30" in hint
    assert "60" in hint


def test_to_prompt_hint_duration_degenerate_equal_bounds():
    fs = FeedbackSignals(
        liked_hook_types=["story"],
        preferred_duration=(45.0, 45.0),
        sample_size=5,
    )
    hint = fs.to_prompt_hint()
    # lo == hi: no range emitted (lo < hi required)
    assert "–" not in hint


def test_to_prompt_hint_caps_liked_at_three():
    fs = FeedbackSignals(
        liked_hook_types=["alpha", "beta", "gamma", "delta", "epsilon"],
        sample_size=10,
    )
    hint = fs.to_prompt_hint()
    # at most 3 hook types mentioned (quoted in output)
    assert "'delta'" not in hint
    assert "'epsilon'" not in hint
    assert "'alpha'" in hint


def test_to_prompt_hint_caps_avoided_at_two():
    fs = FeedbackSignals(
        avoided_hook_types=["shock", "clickbait", "scare"],
        liked_hook_types=["story"],
        sample_size=10,
    )
    hint = fs.to_prompt_hint()
    assert "'scare'" not in hint
    assert "'shock'" in hint


# ── build_signals ─────────────────────────────────────────────────────────────

def test_build_signals_from_full_dict():
    raw = {
        "liked_hook_types": ["question", "story"],
        "avoided_hook_types": ["shock"],
        "preferred_duration": [30.0, 60.0],
        "sample_size": 8,
    }
    fs = build_signals(raw)
    assert fs.liked_hook_types == ["question", "story"]
    assert fs.avoided_hook_types == ["shock"]
    assert fs.preferred_duration == (30.0, 60.0)
    assert fs.sample_size == 8


def test_build_signals_non_dict_returns_empty():
    fs = build_signals("bad input")  # type: ignore[arg-type]
    assert fs.is_empty()


def test_build_signals_none_returns_empty():
    fs = build_signals(None)  # type: ignore[arg-type]
    assert fs.is_empty()


def test_build_signals_bad_duration_ignored():
    raw = {"liked_hook_types": ["x"], "preferred_duration": "bad", "sample_size": 5}
    fs = build_signals(raw)
    assert fs.preferred_duration is None


def test_build_signals_duration_with_negative_lo_ignored():
    raw = {"liked_hook_types": ["x"], "preferred_duration": [-5.0, 30.0], "sample_size": 5}
    fs = build_signals(raw)
    # lo < 0 is invalid
    assert fs.preferred_duration is None


def test_build_signals_strips_non_string_hook_types():
    raw = {
        "liked_hook_types": ["question", 42, None, "story"],
        "sample_size": 5,
    }
    fs = build_signals(raw)
    assert 42 not in fs.liked_hook_types
    assert None not in fs.liked_hook_types
    assert "question" in fs.liked_hook_types
    assert "story" in fs.liked_hook_types


def test_build_signals_bad_sample_size_defaults_zero():
    raw = {"liked_hook_types": ["x"], "sample_size": "bad"}
    fs = build_signals(raw)
    assert fs.sample_size == 0

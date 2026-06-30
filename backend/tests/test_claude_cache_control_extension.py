"""Architecture-review Batch D-3b (2026-06-30) — Anthropic prompt-cache extended
to clips + rewrite call sites.

Pre-D-3b state (verified during investigation):
  - Pass 1 (story) + Pass 3 (recap) already wrap user content with
    ``cache_control: ephemeral`` via the original R7 Stage C wiring.
  - Clips path (``_call_claude_once``) sends plain text — NO cache marker.
  - Rewrite path (``_call_claude_rewrite_once``) sends plain text — NO marker.

D-3b parameterises ``_cached_user_content`` to take a per-call-site gate env
var (default ``CLAUDE_RECAP_CACHE`` for back-compat). Clips + rewrite now
ride their own gates so an operator can disable each independently.

Contract pinned:

  1. Default env vars (CLAUDE_RECAP_CACHE / CLAUDE_CLIPS_CACHE /
     CLAUDE_REWRITE_CACHE all unset or "1") → all three paths carry the
     ephemeral marker.
  2. Setting a single gate to "0" disables ONLY that path; the other two
     keep the marker.
  3. The plain-text fallback (gate="0") preserves the same shape minus
     the cache_control key — no other change.
  4. The default value of ``cache_enabled_env`` is ``CLAUDE_RECAP_CACHE``
     so every pre-D-3b call site (recap, story) keeps the same gate.
"""
from __future__ import annotations

import pytest

from app.features.render.ai.llm.providers.claude import _cached_user_content


@pytest.fixture(autouse=True)
def _clean_cache_envs(monkeypatch):
    """Strip the three gate env vars so each test starts in the
    'all caches enabled by default' state."""
    for key in ("CLAUDE_RECAP_CACHE", "CLAUDE_CLIPS_CACHE", "CLAUDE_REWRITE_CACHE"):
        monkeypatch.delenv(key, raising=False)
    yield


_MARKER = {"type": "ephemeral"}


def _has_marker(block_list) -> bool:
    return any(
        isinstance(b, dict) and b.get("cache_control") == _MARKER for b in block_list
    )


# ---------------------------------------------------------------------------
# Default behaviour — all three gates ON
# ---------------------------------------------------------------------------


def test_recap_default_carries_marker():
    """Existing R7 Stage C wiring preserved: no gate override → marker on."""
    result = _cached_user_content("recap prompt")
    assert _has_marker(result), "recap path lost its marker — back-compat broken"


def test_clips_path_carries_marker_by_default():
    result = _cached_user_content("clips prompt", "CLAUDE_CLIPS_CACHE")
    assert _has_marker(result), "clips path expected to be cached by default"


def test_rewrite_path_carries_marker_by_default():
    result = _cached_user_content("rewrite prompt", "CLAUDE_REWRITE_CACHE")
    assert _has_marker(result), "rewrite path expected to be cached by default"


# ---------------------------------------------------------------------------
# Per-gate kill switch
# ---------------------------------------------------------------------------


def test_clips_kill_switch_strips_marker(monkeypatch):
    monkeypatch.setenv("CLAUDE_CLIPS_CACHE", "0")
    result = _cached_user_content("clips prompt", "CLAUDE_CLIPS_CACHE")
    assert not _has_marker(result)
    assert result == [{"type": "text", "text": "clips prompt"}]


def test_rewrite_kill_switch_strips_marker(monkeypatch):
    monkeypatch.setenv("CLAUDE_REWRITE_CACHE", "0")
    result = _cached_user_content("rewrite prompt", "CLAUDE_REWRITE_CACHE")
    assert not _has_marker(result)


def test_recap_kill_switch_strips_marker(monkeypatch):
    """Existing CLAUDE_RECAP_CACHE=0 behaviour still works for the default
    call site (no gate override → still consults CLAUDE_RECAP_CACHE)."""
    monkeypatch.setenv("CLAUDE_RECAP_CACHE", "0")
    result = _cached_user_content("recap prompt")
    assert not _has_marker(result)


# ---------------------------------------------------------------------------
# Per-gate isolation
# ---------------------------------------------------------------------------


def test_disabling_clips_does_not_affect_recap(monkeypatch):
    monkeypatch.setenv("CLAUDE_CLIPS_CACHE", "0")
    # Recap still on.
    recap = _cached_user_content("recap")
    clips = _cached_user_content("clips", "CLAUDE_CLIPS_CACHE")
    assert _has_marker(recap)
    assert not _has_marker(clips)


def test_disabling_rewrite_does_not_affect_clips_or_recap(monkeypatch):
    monkeypatch.setenv("CLAUDE_REWRITE_CACHE", "0")
    recap = _cached_user_content("recap")
    clips = _cached_user_content("clips", "CLAUDE_CLIPS_CACHE")
    rewrite = _cached_user_content("rewrite", "CLAUDE_REWRITE_CACHE")
    assert _has_marker(recap)
    assert _has_marker(clips)
    assert not _has_marker(rewrite)


def test_all_three_gates_can_be_independently_disabled(monkeypatch):
    monkeypatch.setenv("CLAUDE_RECAP_CACHE", "0")
    monkeypatch.setenv("CLAUDE_CLIPS_CACHE", "0")
    monkeypatch.setenv("CLAUDE_REWRITE_CACHE", "0")
    assert not _has_marker(_cached_user_content("a"))
    assert not _has_marker(_cached_user_content("b", "CLAUDE_CLIPS_CACHE"))
    assert not _has_marker(_cached_user_content("c", "CLAUDE_REWRITE_CACHE"))


# ---------------------------------------------------------------------------
# Shape — payload text is preserved verbatim
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("gate_env", [None, "CLAUDE_CLIPS_CACHE", "CLAUDE_REWRITE_CACHE"])
def test_user_prompt_is_preserved_verbatim(gate_env):
    payload = "Hello, đây là một bài kiểm tra với tiếng Việt + emoji 🎬"
    if gate_env is None:
        result = _cached_user_content(payload)
    else:
        result = _cached_user_content(payload, gate_env)
    assert len(result) == 1
    assert result[0]["text"] == payload
    assert result[0]["type"] == "text"


# ---------------------------------------------------------------------------
# Spot-check call sites use the correct gate
# ---------------------------------------------------------------------------


def test_call_sites_grep():
    """The provider module's two D-3b call sites must reference the new gates
    by name. Defensive grep — catches accidental revert."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "app" / "features" / "render" / "ai" / "llm" / "providers" / "claude.py"
    text = src.read_text(encoding="utf-8")
    assert '_cached_user_content(user_prompt, "CLAUDE_CLIPS_CACHE")' in text, (
        "clips call site missing CLAUDE_CLIPS_CACHE gate"
    )
    assert '_cached_user_content(user_prompt, "CLAUDE_REWRITE_CACHE")' in text, (
        "rewrite call site missing CLAUDE_REWRITE_CACHE gate"
    )

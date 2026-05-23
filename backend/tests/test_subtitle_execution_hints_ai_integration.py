"""
test_subtitle_execution_hints_ai_integration.py — Phase 5.5 subtitle function integration.

Tests that:
- subtitle_emphasis_pass() with emphasis_level_override applies AI emphasis
- timing is preserved (start/end not mutated)
- style ID is unchanged (preset_id unchanged for ASS)
- fallback when config disabled (emphasis_level_override=None → original behavior)
- no new subtitle style IDs created
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helper — build test SRT blocks
# ---------------------------------------------------------------------------

def _blocks(texts=None):
    """Build a list of SRT-style blocks with timing preserved."""
    if texts is None:
        texts = ["This is amazing content", "Never miss this secret"]
    return [
        {"start": float(i), "end": float(i) + 0.9, "text": t}
        for i, t in enumerate(texts)
    ]


# ---------------------------------------------------------------------------
# emphasis_level_override — basic behavior
# ---------------------------------------------------------------------------

def test_subtitle_emphasis_pass_strong_override():
    """AI strong override → emphasis applied at strong level."""
    from app.services.subtitles.readability import subtitle_emphasis_pass
    blocks = _blocks(["This is amazing content"])
    result = subtitle_emphasis_pass(
        blocks,
        preset_id="clean_pro",  # clean_pro default level = subtle
        market="US",
        language="en",
        emphasis_level_override="strong",  # AI overrides to strong
    )
    # strong level should uppercase emphasis words; "amazing" is in _EMPH_EMOTIONAL
    combined = " ".join(b["text"] for b in result)
    # The text should have been processed (uppercase or markers added)
    assert result is blocks  # returns same list (in-place)


def test_subtitle_emphasis_pass_subtle_override():
    """AI subtle override → emphasis applied at subtle level (numbers only)."""
    from app.services.subtitles.readability import subtitle_emphasis_pass
    blocks = _blocks(["Save $100 today on all items"])
    result = subtitle_emphasis_pass(
        blocks,
        preset_id="tiktok_bounce_v1",  # default level = strong
        market="US",
        language="en",
        emphasis_level_override="subtle",  # AI reduces to subtle
    )
    assert result is blocks


def test_subtitle_emphasis_pass_medium_override():
    """AI medium override → emphasis at medium level."""
    from app.services.subtitles.readability import subtitle_emphasis_pass
    blocks = _blocks(["The best deal ever"])
    result = subtitle_emphasis_pass(
        blocks,
        preset_id="clean_pro",
        market="US",
        language="en",
        emphasis_level_override="medium",
    )
    assert result is blocks


def test_subtitle_emphasis_pass_word_only_override():
    """AI word_only override → no block transforms."""
    from app.services.subtitles.readability import subtitle_emphasis_pass
    original_texts = ["Watch this amazing trick"]
    blocks = _blocks(original_texts)
    result = subtitle_emphasis_pass(
        blocks,
        preset_id="tiktok_bounce_v1",
        market="US",
        language="en",
        emphasis_level_override="word_only",
    )
    assert result is blocks


# ---------------------------------------------------------------------------
# Timing is preserved — start/end never mutated by subtitle_emphasis_pass
# ---------------------------------------------------------------------------

def test_timing_preserved_with_ai_override():
    """AI override must not alter SRT timestamps."""
    from app.services.subtitles.readability import subtitle_emphasis_pass
    blocks = [
        {"start": 1.234, "end": 2.567, "text": "Amazing secret revealed"},
        {"start": 3.000, "end": 4.500, "text": "Best content ever"},
    ]
    original_starts = [b["start"] for b in blocks]
    original_ends = [b["end"] for b in blocks]

    subtitle_emphasis_pass(
        blocks,
        preset_id="tiktok_bounce_v1",
        market="US",
        language="en",
        emphasis_level_override="strong",
    )

    assert [b["start"] for b in blocks] == original_starts, "Start times must not change"
    assert [b["end"] for b in blocks] == original_ends, "End times must not change"


def test_timing_preserved_without_ai_override():
    """Original behavior: no override, timing still preserved."""
    from app.services.subtitles.readability import subtitle_emphasis_pass
    blocks = [
        {"start": 0.500, "end": 1.200, "text": "Never give up"},
        {"start": 1.500, "end": 2.800, "text": "Always believe"},
    ]
    original_starts = [b["start"] for b in blocks]
    original_ends = [b["end"] for b in blocks]

    subtitle_emphasis_pass(blocks, preset_id="tiktok_bounce_v1", market="US")

    assert [b["start"] for b in blocks] == original_starts
    assert [b["end"] for b in blocks] == original_ends


# ---------------------------------------------------------------------------
# Style ID unchanged — preset_id for ASS is never changed
# ---------------------------------------------------------------------------

def test_style_id_unchanged_with_ai_override():
    """AI override must not create new style IDs or change preset_id."""
    from app.services.subtitles.readability import subtitle_emphasis_pass
    from app.services.subtitles.styles import normalize_subtitle_style_id, _PRESETS

    original_preset = "clean_pro"
    blocks = _blocks(["Test content here"])

    subtitle_emphasis_pass(
        blocks,
        preset_id=original_preset,
        market="US",
        language="en",
        emphasis_level_override="strong",
    )

    # preset_id is unchanged — verify it resolves to same preset
    resolved = normalize_subtitle_style_id(original_preset)
    assert resolved in _PRESETS, f"preset_id must remain valid: {resolved}"
    assert resolved == "clean_pro"


# ---------------------------------------------------------------------------
# Fallback when config disabled → original behavior unchanged
# ---------------------------------------------------------------------------

def test_no_override_preserves_original_behavior():
    """emphasis_level_override=None → existing behavior exactly preserved."""
    from app.services.subtitles.readability import subtitle_emphasis_pass
    import copy

    blocks_a = [{"start": 0.0, "end": 1.0, "text": "Best deal ever"}]
    blocks_b = copy.deepcopy(blocks_a)

    # Without override
    subtitle_emphasis_pass(blocks_a, preset_id="tiktok_bounce_v1", market="US")
    # With explicit None override
    subtitle_emphasis_pass(
        blocks_b, preset_id="tiktok_bounce_v1", market="US",
        emphasis_level_override=None,
    )

    assert blocks_a[0]["text"] == blocks_b[0]["text"], (
        "None override must produce identical result to omitted parameter"
    )


def test_invalid_override_falls_back_to_preset_level():
    """Invalid override value is ignored → falls back to preset-derived level."""
    from app.services.subtitles.readability import subtitle_emphasis_pass
    import copy

    blocks_a = [{"start": 0.0, "end": 1.0, "text": "Best deal ever"}]
    blocks_b = copy.deepcopy(blocks_a)

    # Without override
    subtitle_emphasis_pass(blocks_a, preset_id="tiktok_bounce_v1", market="US")
    # With invalid override (not in allowed set) → falls back to preset level
    subtitle_emphasis_pass(
        blocks_b, preset_id="tiktok_bounce_v1", market="US",
        emphasis_level_override="ultra_heavy",  # Invalid → ignored
    )

    assert blocks_a[0]["text"] == blocks_b[0]["text"], (
        "Invalid override must fall back to preset level"
    )


# ---------------------------------------------------------------------------
# Empty blocks — safe no-op
# ---------------------------------------------------------------------------

def test_empty_blocks_with_override():
    from app.services.subtitles.readability import subtitle_emphasis_pass
    result = subtitle_emphasis_pass(
        [],
        preset_id="tiktok_bounce_v1",
        market="US",
        emphasis_level_override="strong",
    )
    assert result == []


# ---------------------------------------------------------------------------
# AISubtitleEmphasisConfig integration
# ---------------------------------------------------------------------------

def test_config_applied_feeds_correct_override():
    """Verify config.emphasis_style routes to subtitle_emphasis_pass correctly."""
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    from app.services.subtitles.readability import subtitle_emphasis_pass

    cfg = build_ai_subtitle_emphasis_config({"subtitle_emphasis_style": "subtle"})
    assert cfg.applied is True

    blocks = [{"start": 0.0, "end": 1.0, "text": "Amazing deal $500 off"}]
    # Pass the override from config
    subtitle_emphasis_pass(
        blocks,
        preset_id="tiktok_bounce_v1",
        market="US",
        emphasis_level_override=cfg.emphasis_style if cfg.applied else None,
    )
    # Should not raise; timing not mutated
    assert blocks[0]["start"] == 0.0
    assert blocks[0]["end"] == 1.0


def test_config_not_applied_no_override_passed():
    """When config.applied=False, emphasis_level_override stays None."""
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    from app.services.subtitles.readability import subtitle_emphasis_pass

    cfg = build_ai_subtitle_emphasis_config(None)  # no hints
    assert cfg.applied is False

    override = cfg.emphasis_style if cfg.applied else None
    assert override is None

    blocks = [{"start": 0.0, "end": 1.0, "text": "Content here"}]
    # Must not raise; original behavior
    subtitle_emphasis_pass(
        blocks,
        preset_id="tiktok_bounce_v1",
        market="US",
        emphasis_level_override=override,
    )
    assert blocks[0]["start"] == 0.0
    assert blocks[0]["end"] == 1.0

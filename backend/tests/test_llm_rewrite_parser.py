"""Tests for parse_rewrite_response — v2 segmented parser with plain-text fallback."""
from app.features.render.ai.llm.rewrite_parser import parse_rewrite_response


# ── JSON segmented happy paths ──────────────────────────────────────────────

def test_json_segments_happy_path():
    raw = (
        '{"segments":['
        '{"start":0.0,"end":4.0,"text":"Hôm nay tôi sẽ kể"},'
        '{"start":5.0,"end":9.0,"text":"một câu chuyện hay"}'
        ']}'
    )
    out = parse_rewrite_response(raw, clip_duration_sec=10.0, word_budget=30)
    assert out is not None
    assert len(out) == 2
    assert out[0]["start"] == 0.0 and out[0]["end"] == 4.0
    assert out[0]["text"] == "Hôm nay tôi sẽ kể"
    assert out[1]["start"] == 5.0 and out[1]["end"] == 9.0


def test_json_strips_code_fences():
    raw = '```json\n{"segments":[{"start":0,"end":3,"text":"Hello"}]}\n```'
    out = parse_rewrite_response(raw, 5.0, 10)
    assert out is not None and len(out) == 1
    assert out[0]["text"] == "Hello"


def test_json_handles_prose_wrapped_object():
    raw = 'Here is the result: {"segments":[{"start":0,"end":3,"text":"Foo"}]} done.'
    out = parse_rewrite_response(raw, 5.0, 10)
    assert out is not None and out[0]["text"] == "Foo"


def test_json_filters_invalid_segments():
    # start>=end and missing text — both should be dropped.
    raw = (
        '{"segments":['
        '{"start":0,"end":3,"text":"valid one"},'
        '{"start":5,"end":5,"text":"zero duration"},'
        '{"start":6,"end":8,"text":""}'
        ']}'
    )
    out = parse_rewrite_response(raw, 10.0, 20)
    assert out is not None and len(out) == 1
    assert out[0]["text"] == "valid one"


def test_json_clamps_segments_past_clip_end():
    # end=15 > clip_dur (10) + 0.5 grace → clamp to clip_dur
    raw = '{"segments":[{"start":0,"end":15,"text":"too long"}]}'
    out = parse_rewrite_response(raw, 10.0, 20)
    assert out is not None
    assert out[0]["end"] == 10.0


def test_json_drops_overlapping_later_segment():
    raw = (
        '{"segments":['
        '{"start":0,"end":5,"text":"first"},'
        '{"start":3,"end":7,"text":"overlap with first"}'
        ']}'
    )
    out = parse_rewrite_response(raw, 10.0, 20)
    assert out is not None and len(out) == 1
    assert out[0]["text"] == "first"


def test_json_drops_micro_segment_under_0_3s():
    raw = (
        '{"segments":['
        '{"start":0,"end":3,"text":"valid"},'
        '{"start":4,"end":4.1,"text":"too short"}'
        ']}'
    )
    out = parse_rewrite_response(raw, 10.0, 20)
    assert out is not None and len(out) == 1


def test_json_sorts_segments_by_start():
    raw = (
        '{"segments":['
        '{"start":5,"end":8,"text":"second"},'
        '{"start":0,"end":4,"text":"first"}'
        ']}'
    )
    out = parse_rewrite_response(raw, 10.0, 20)
    assert out is not None and len(out) == 2
    assert out[0]["text"] == "first"
    assert out[1]["text"] == "second"


# ── Plain-text fallback ─────────────────────────────────────────────────────

def test_plain_text_falls_back_to_single_segment():
    # No JSON — parser should produce 1 segment spanning the full clip.
    raw = "Hôm nay tôi sẽ kể bạn nghe một câu chuyện."
    out = parse_rewrite_response(raw, clip_duration_sec=8.0, word_budget=20)
    assert out is not None and len(out) == 1
    assert out[0]["start"] == 0.0
    assert out[0]["end"] == 8.0
    assert out[0]["text"] == "Hôm nay tôi sẽ kể bạn nghe một câu chuyện."


def test_plain_text_collapses_internal_whitespace():
    raw = "Hello    world\n\n\nfoo"
    out = parse_rewrite_response(raw, 5.0, 20)
    assert out is not None and out[0]["text"] == "Hello world foo"


def test_plain_text_rejects_over_2x_budget():
    raw = " ".join(["word"] * 50)
    out = parse_rewrite_response(raw, 5.0, word_budget=10)
    assert out is None


# ── None / empty paths ──────────────────────────────────────────────────────

def test_none_input_returns_none():
    assert parse_rewrite_response(None, 5.0, 10) is None  # type: ignore[arg-type]


def test_empty_string_returns_none():
    assert parse_rewrite_response("", 5.0, 10) is None
    assert parse_rewrite_response("   \n  ", 5.0, 10) is None


def test_empty_json_segments_falls_through_to_plain_text():
    # {"segments": []} is empty — parser should try plain-text fallback on
    # the JSON string itself (which then gets rejected as malformed Vietnamese
    # but actually contains the JSON literal). Verify it doesn't crash.
    raw = '{"segments": []}'
    out = parse_rewrite_response(raw, 5.0, 20)
    # Either None (rejected) or a single segment containing the literal —
    # both are acceptable Sacred #3 outcomes. The key contract is: no crash.
    assert out is None or (isinstance(out, list) and len(out) == 1)

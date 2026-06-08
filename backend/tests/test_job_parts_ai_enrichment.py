"""Tests for the JobPart AI-field enrichment (audit FINDING-C03).

The FE's TS type for JobPart declares four AI-decision optional fields:
``clip_name``, ``ai_title``, ``ai_reason``, ``source``. None of these
live on the ``job_parts`` SQL row — they are emitted by the LLM stage
into ``jobs.result_json.segments[*]`` and were not joined back in
before this audit closure.

These tests pin the join contract performed by
``api_get_job_parts``'s helper ``_enrich_parts_with_segment_ai_fields``:

1. Each part receives the 4 AI fields from the matching segment.
2. Segment-to-part mapping uses explicit ``part_no`` when present,
   else the array position (1-indexed).
3. A non-empty DB value wins over the segment value (Sacred Contract #2
   spirit — never overwrite a stored truth).
4. Malformed / missing result_json silently degrades to un-enriched.
"""
from __future__ import annotations

import json

import pytest

from app.routes.jobs import (
    _PART_AI_FIELDS,
    _enrich_parts_with_segment_ai_fields,
)


# ---------------------------------------------------------------------------
# Happy path — segments[0] joins to part_no=1
# ---------------------------------------------------------------------------

def test_enrich_joins_by_position_when_part_no_absent():
    parts = [
        {"part_no": 1, "status": "done", "output_file": "out1.mp4"},
        {"part_no": 2, "status": "done", "output_file": "out2.mp4"},
    ]
    result = {
        "segments": [
            {"clip_name": "First clip", "ai_title": "T1",
             "ai_reason": "R1", "source": "llm"},
            {"clip_name": "Second clip", "ai_title": "T2",
             "ai_reason": "R2", "source": "render_plan"},
        ],
    }
    out = _enrich_parts_with_segment_ai_fields(parts, json.dumps(result))
    assert out[0]["clip_name"] == "First clip"
    assert out[0]["ai_title"]  == "T1"
    assert out[0]["ai_reason"] == "R1"
    assert out[0]["source"]    == "llm"
    assert out[1]["clip_name"] == "Second clip"
    assert out[1]["source"]    == "render_plan"


def test_enrich_uses_explicit_part_no_when_present():
    """When the segment carries its own part_no, that wins over array index."""
    parts = [
        {"part_no": 1, "output_file": "out1.mp4"},
        {"part_no": 2, "output_file": "out2.mp4"},
    ]
    result = {
        "segments": [
            {"part_no": 2, "clip_name": "Belongs to part 2"},
            {"part_no": 1, "clip_name": "Belongs to part 1"},
        ],
    }
    out = _enrich_parts_with_segment_ai_fields(parts, json.dumps(result))
    out_by = {p["part_no"]: p for p in out}
    assert out_by[1]["clip_name"] == "Belongs to part 1"
    assert out_by[2]["clip_name"] == "Belongs to part 2"


# ---------------------------------------------------------------------------
# Sacred Contract #2 — DB value wins over segment value
# ---------------------------------------------------------------------------

def test_existing_db_value_wins_over_segment():
    parts = [
        {"part_no": 1, "clip_name": "DB-stored name", "output_file": "out1.mp4"},
    ]
    result = {
        "segments": [
            {"clip_name": "Segment name (must NOT win)"},
        ],
    }
    out = _enrich_parts_with_segment_ai_fields(parts, json.dumps(result))
    assert out[0]["clip_name"] == "DB-stored name"


def test_empty_string_db_value_is_overwritten():
    """An empty string is treated as 'no value' so the segment's value
    can fill it. This matches the FE's `?? || fallback` convention.
    """
    parts = [
        {"part_no": 1, "ai_title": "", "output_file": "out1.mp4"},
    ]
    result = {"segments": [{"ai_title": "From segment"}]}
    out = _enrich_parts_with_segment_ai_fields(parts, json.dumps(result))
    assert out[0]["ai_title"] == "From segment"


# ---------------------------------------------------------------------------
# Non-AI columns are never disturbed
# ---------------------------------------------------------------------------

def test_non_ai_fields_are_preserved():
    parts = [
        {"part_no": 1, "status": "done", "viral_score": 85.0,
         "output_file": "out.mp4", "duration": 14.2},
    ]
    result = {"segments": [{"clip_name": "X"}]}
    out = _enrich_parts_with_segment_ai_fields(parts, json.dumps(result))
    assert out[0]["status"]      == "done"
    assert out[0]["viral_score"] == 85.0
    assert out[0]["output_file"] == "out.mp4"
    assert out[0]["duration"]    == 14.2
    assert out[0]["clip_name"]   == "X"


# ---------------------------------------------------------------------------
# Sad paths — must never raise
# ---------------------------------------------------------------------------

def test_no_result_json_returns_parts_unchanged():
    parts = [{"part_no": 1}]
    out = _enrich_parts_with_segment_ai_fields(parts, None)
    assert out == parts


def test_empty_result_json_returns_parts_unchanged():
    parts = [{"part_no": 1}]
    out = _enrich_parts_with_segment_ai_fields(parts, "")
    assert out == parts


def test_malformed_result_json_does_not_raise():
    parts = [{"part_no": 1}]
    out = _enrich_parts_with_segment_ai_fields(parts, "not json{")
    assert out == parts


def test_missing_segments_array_returns_parts_unchanged():
    parts = [{"part_no": 1}]
    out = _enrich_parts_with_segment_ai_fields(parts, json.dumps({"foo": "bar"}))
    assert out == parts


def test_empty_segments_array_returns_parts_unchanged():
    parts = [{"part_no": 1}]
    out = _enrich_parts_with_segment_ai_fields(parts, json.dumps({"segments": []}))
    assert out == parts


def test_segment_for_unknown_part_is_skipped():
    """A segment whose part_no doesn't match any part must not crash."""
    parts = [{"part_no": 1}]
    result = {"segments": [{"part_no": 99, "clip_name": "orphan"}]}
    out = _enrich_parts_with_segment_ai_fields(parts, json.dumps(result))
    assert out[0].get("clip_name") is None


def test_non_dict_segment_entries_are_skipped():
    parts = [{"part_no": 1}, {"part_no": 2}]
    result = {"segments": ["not a dict", {"clip_name": "second"}]}
    # idx=0 skipped, idx=1 → part_no=2 enriched
    out = _enrich_parts_with_segment_ai_fields(parts, json.dumps(result))
    out_by = {p["part_no"]: p for p in out}
    assert out_by[1].get("clip_name") is None
    assert out_by[2]["clip_name"] == "second"


def test_accepts_dict_result_in_place_of_json():
    """The helper can be passed either a JSON string or a parsed dict."""
    parts = [{"part_no": 1}]
    out = _enrich_parts_with_segment_ai_fields(
        parts,
        {"segments": [{"clip_name": "from dict"}]},
    )
    assert out[0]["clip_name"] == "from dict"


# ---------------------------------------------------------------------------
# Contract — only the 4 documented fields are joined
# ---------------------------------------------------------------------------

def test_segment_only_4_documented_fields_join():
    """A segment may carry many other keys (viral_score, hook_score, etc.).
    The enrichment must only copy the 4 audit-pinned AI fields; the rest
    stay in result_json where the AI summary endpoint reads them.
    """
    parts = [{"part_no": 1, "output_file": "out.mp4"}]
    result = {
        "segments": [{
            "clip_name": "Yes-copy",
            "ai_title":  "Yes-copy",
            "ai_reason": "Yes-copy",
            "source":    "llm",
            "viral_score": 85,          # NOT in the merge set
            "hook_score":  90,           # NOT in the merge set
            "ranking_reason": "blah",   # NOT in the merge set
        }],
    }
    out = _enrich_parts_with_segment_ai_fields(parts, json.dumps(result))
    for f in _PART_AI_FIELDS:
        assert f in out[0]
    # Non-listed segment keys MUST NOT bleed into the part.
    assert "viral_score" not in out[0]      # not present (was not on DB row)
    assert "hook_score"  not in out[0]
    assert "ranking_reason" not in out[0]


def test_part_ai_fields_constant_pins_four_documented_keys():
    """A safety pin: any addition to _PART_AI_FIELDS must be coordinated
    with the FE JobPart TS type at frontend/src/types/api.ts:266-269.
    """
    assert _PART_AI_FIELDS == ("clip_name", "ai_title", "ai_reason", "source")

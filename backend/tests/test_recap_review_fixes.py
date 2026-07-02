"""Regression guards for the 2026-07-02 recap review fixes (A/B/C).

Background: review of job d4e53785 (broken episode files) surfaced four
findings beyond the concat bugs fixed the same day:

  Fix A — job_parts.output_file on recap jobs pointed at per-scene temp
          files that are deleted right after episode assembly, so every
          per-part surface (stream / thumbnail / editor) dead-linked.
          _repoint_scene_parts_to_episodes now repoints rows of QA-passing
          episodes at the delivered episode file.

  Fix B — recap scenes with audio_mode="narrate" got the source-dialogue
          ASS subtitles burned IN ADDITION to the R3b narration captions
          whenever add_subtitle=True (two stacked subtitle rows).
          _recap_subtitle_map now enables source-dialogue subs ONLY for
          "original audio" scenes.

  Fix C — a partially-failed synthesize_timed_narration still burned the
          FULL caption set (text with no voice on the failed spans).
          synthesize_timed_narration reports synthesized spans via the
          optional ``synthesized_out`` list and part_voice_mix filters
          _reaction_segments through _filter_voiced_segments.
"""
from __future__ import annotations

import uuid

from app.db.connection import init_db
from app.db.jobs_repo import list_job_parts, upsert_job, upsert_job_part
from app.features.render.engine.pipeline.recap_pipeline import (
    _recap_subtitle_map,
    _repoint_scene_parts_to_episodes,
)
from app.features.render.engine.stages.part_voice_mix import _filter_voiced_segments


# ---------------------------------------------------------------------------
# Fix A — _repoint_scene_parts_to_episodes
# ---------------------------------------------------------------------------


def _make_recap_job_with_parts(n_parts: int) -> str:
    job_id = f"test-repoint-{uuid.uuid4().hex[:12]}"
    init_db()
    upsert_job(job_id, "render", "testch", "running", {}, {})
    for i in range(1, n_parts + 1):
        upsert_job_part(
            job_id, i, f"scene_{i:03d}", "done",
            output_file=f"C:/tmp/scenes/scene_{i:03d}.mp4",
        )
    return job_id


def test_repoint_updates_parts_of_passing_episodes_only():
    job_id = _make_recap_job_with_parts(3)
    scored = [
        {"episode_index": 0},
        {"episode_index": 0},
        {"episode_index": 1},   # episode 1 failed QA — not in outputs
    ]
    outputs = [{"episode_index": 0, "path": "C:/out/ep1.mp4"}]

    repointed = _repoint_scene_parts_to_episodes(job_id, scored, outputs)

    assert repointed == 2
    parts = {int(p["part_no"]): p for p in list_job_parts(job_id)}
    assert parts[1]["output_file"] == "C:/out/ep1.mp4"
    assert parts[2]["output_file"] == "C:/out/ep1.mp4"
    # Failed episode's part keeps its (stale) scene path — pre-existing policy.
    assert parts[3]["output_file"] == "C:/tmp/scenes/scene_003.mp4"
    # Sacred Contract #5: repoint must not touch part status.
    assert all(p["status"] == "done" for p in parts.values())


def test_repoint_never_raises_on_bad_input():
    # Non-existent job / malformed scored entries — best-effort contract.
    assert _repoint_scene_parts_to_episodes("no-such-job", [{}], []) == 0
    assert _repoint_scene_parts_to_episodes("no-such-job", [], [{"episode_index": 0, "path": "x"}]) == 0


# ---------------------------------------------------------------------------
# Fix B — _recap_subtitle_map
# ---------------------------------------------------------------------------


def test_recap_subtitle_map_only_original_scenes_get_source_subs():
    scored = [
        {"audio_mode": "narrate"},
        {"audio_mode": "original"},
        {},                        # missing key defaults to narrate-like
        {"audio_mode": "ORIGINAL"},  # rule is exact-match lowercase wire value
    ]
    assert _recap_subtitle_map(scored) == {1: False, 2: True, 3: False, 4: False}


def test_recap_subtitle_map_empty_scored():
    assert _recap_subtitle_map([]) == {}


# ---------------------------------------------------------------------------
# Fix C — _filter_voiced_segments
# ---------------------------------------------------------------------------


def test_filter_drops_voice_segments_without_synth_overlap():
    segments = [
        {"kind": "voice", "start": 0.0, "end": 5.0, "text": "a"},
        {"kind": "voice", "start": 5.0, "end": 10.0, "text": "b"},
        {"kind": "original", "start": 10.0, "end": 15.0},
    ]
    # Only the first span synthesized successfully.
    kept = _filter_voiced_segments(segments, [(0.0, 5.0)])
    assert kept == [segments[0], segments[2]]


def test_filter_keeps_original_windows_when_all_tts_failed():
    segments = [
        {"kind": "voice", "start": 0.0, "end": 5.0, "text": "a"},
        {"kind": "original", "start": 5.0, "end": 8.0},
    ]
    kept = _filter_voiced_segments(segments, [])
    assert kept == [segments[1]]


def test_filter_overlap_uses_merged_group_spans():
    # timed_narration merges adjacent voice segments into one synth unit;
    # ok_spans then carry the GROUP span. Both originals overlap it → kept.
    segments = [
        {"kind": "voice", "start": 0.0, "end": 4.0, "text": "a"},
        {"kind": "voice", "start": 4.2, "end": 9.0, "text": "b"},
    ]
    kept = _filter_voiced_segments(segments, [(0.0, 9.0)])
    assert kept == segments


def test_filter_passthrough_on_empty_segments():
    assert _filter_voiced_segments(None, [(0.0, 1.0)]) is None
    assert _filter_voiced_segments([], [(0.0, 1.0)]) == []


def test_synthesize_timed_narration_accepts_synthesized_out_kwarg():
    """Signature guard: empty segments → None, and the caller's list stays
    empty instead of raising TypeError on the new kwarg."""
    from app.features.render.engine.audio.timed_narration import synthesize_timed_narration

    spans: list = []
    out = synthesize_timed_narration(
        segments=[],
        clip_duration_sec=10.0,
        voice_language="vi-VN",
        voice_gender="female",
        voice_rate="+0%",
        voice_id=None,
        content_type="vlog",
        tts_engine="edge",
        job_id="test-synth-kwarg",
        part_idx=1,
        synthesized_out=spans,
    )
    assert out is None
    assert spans == []

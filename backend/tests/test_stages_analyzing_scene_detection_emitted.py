"""T2.3 closure regression guard — Audit 2026-06-08 (Batch B B-10-A).

T2.3 (commit 1c8635b) closed B-10-A by making the runtime emit
``JobStage.ANALYZING`` and ``JobStage.SCENE_DETECTION`` — two stages
that Sacred Contract #4 lists in the frozen ordering but that no
pipeline call site wrote pre-T2.3. The enum members existed but the
runtime skipped over them.

This file pins the closure with three complementary checks:

1. **Source-level pin** that the two stage-emit calls actually appear
   in the pipeline modules where T2.3 placed them. A future refactor
   that drops these emits would re-introduce the spec-vs-runtime
   asymmetry.

2. **Adjacency pin** for ANALYZING — it must be emitted BEFORE
   DOWNLOADING (the back-compat label). If a refactor reorders or
   moves ANALYZING after DOWNLOADING, the user-visible progress would
   regress (the FE label-map ordering is anchored at this boundary).

3. **Adjacency pin** for SCENE_DETECTION — it must sit BETWEEN
   TRANSCRIBING_FULL (the Whisper stage in llm_pipeline) and
   SEGMENT_BUILDING (the LLM-selection stage). Sacred Contract #4
   freezes this ordering.

(The STAGE_TO_EVENT coverage of every JobStage value is already
pinned by test_render_pipeline_contract.test_stage_to_event_covers
_every_jobstage. This file adds the COMPLEMENTARY pin that the
emits actually happen at runtime.)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


SOURCE_PREP_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "features" / "render" / "engine"
    / "pipeline" / "pipeline_source_prep.py"
)

LLM_PIPELINE_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "features" / "render" / "engine"
    / "pipeline" / "llm_pipeline.py"
)


# ---------------------------------------------------------------------------
# 1. Source-level pin — both emit calls exist in their target modules.
# ---------------------------------------------------------------------------


def test_analyzing_stage_emitted_in_source_prep():
    """T2.3 placed the ANALYZING transition immediately before the
    DOWNLOADING transition in pipeline_source_prep.py. Both must still
    be present (DOWNLOADING is kept for backward-compatibility with
    stored job records per core/stage.py:10)."""
    source = SOURCE_PREP_PATH.read_text(encoding="utf-8-sig")
    assert "JobStage.ANALYZING" in source, (
        "T2.3 regression — JobStage.ANALYZING is no longer emitted in "
        "pipeline_source_prep.py. Sacred Contract #4 lists ANALYZING in "
        "the frozen ordering between STARTING and DOWNLOADING; the FE "
        "label map relies on the stage being writeable. Restore the "
        "_set_stage(JobStage.ANALYZING, 3, 'Analyzing source video') "
        "call before the DOWNLOADING transition."
    )
    assert "JobStage.DOWNLOADING" in source, (
        "DOWNLOADING was removed — the back-compat label is required "
        "(see core/stage.py:10). If you're trying to retire the label, "
        "audit ALL FE consumers + stored job records first."
    )


def test_scene_detection_stage_emitted_in_llm_pipeline():
    """T2.3 placed the SCENE_DETECTION transition between
    TRANSCRIBING_FULL and SEGMENT_BUILDING in llm_pipeline.py. All
    three must coexist for the Sacred Contract #4 ordering to be
    observable end-to-end."""
    source = LLM_PIPELINE_PATH.read_text(encoding="utf-8-sig")
    assert "JobStage.SCENE_DETECTION" in source, (
        "T2.3 regression — JobStage.SCENE_DETECTION is no longer "
        "emitted in llm_pipeline.py. Sacred Contract #4 lists it "
        "between TRANSCRIBING_FULL and SEGMENT_BUILDING; pre-T2.3 the "
        "enum existed but the runtime never emitted it (Batch B "
        "B-10-A finding). Restore the set_stage_fn(JobStage.SCENE_"
        "DETECTION, 23, 'LLM pipeline: detecting scene boundaries...') "
        "call between TRANSCRIBING_FULL and SEGMENT_BUILDING."
    )
    assert "JobStage.TRANSCRIBING_FULL" in source, (
        "TRANSCRIBING_FULL emission was removed — this is the Whisper "
        "stage that MUST stay before SCENE_DETECTION per Sacred "
        "Contract #4 ordering."
    )
    assert "JobStage.SEGMENT_BUILDING" in source, (
        "SEGMENT_BUILDING emission was removed — this stage MUST stay "
        "after SCENE_DETECTION per Sacred Contract #4 ordering."
    )


# ---------------------------------------------------------------------------
# 2. Adjacency pin — ANALYZING before DOWNLOADING in source_prep.
# ---------------------------------------------------------------------------


def _first_set_stage_call_pos(source: str, stage: str) -> int:
    """Return the source position of the first set_stage / _set_stage /
    set_stage_fn call that emits ``JobStage.<stage>``.

    Multi-line tolerant: matches ``set_stage(JobStage.X`` directly OR
    ``set_stage(\\n   JobStage.X`` (the orchestrator's wrapped form).
    Substring lookups would falsely match docstring / comment hits
    (e.g. the back-compat note at the top of pipeline_source_prep.py
    mentions ``JobStage.DOWNLOADING`` in a docstring).
    """
    pattern = re.compile(
        rf"(_?set_stage(?:_fn)?)\(\s*JobStage\.{stage}\b",
        flags=re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(source)
    return m.start() if m else -1


def test_analyzing_emitted_before_downloading_in_source_prep():
    """T2.3 placed ANALYZING at progress=3 right before DOWNLOADING at
    progress=5. A refactor that swaps the order (or moves ANALYZING
    after the DB-load section) would cause the FE progress bar to
    jump backwards when DOWNLOADING fires later in the actual flow."""
    source = SOURCE_PREP_PATH.read_text(encoding="utf-8-sig")
    pos_analyzing   = _first_set_stage_call_pos(source, "ANALYZING")
    pos_downloading = _first_set_stage_call_pos(source, "DOWNLOADING")
    assert pos_analyzing   != -1, "set_stage(JobStage.ANALYZING, ...) call not found in pipeline_source_prep.py"
    assert pos_downloading != -1, "set_stage(JobStage.DOWNLOADING, ...) call not found in pipeline_source_prep.py"
    assert pos_analyzing < pos_downloading, (
        "T2.3 invariant breached — set_stage(JobStage.ANALYZING, ...) "
        "must come BEFORE set_stage(JobStage.DOWNLOADING, ...) in "
        "pipeline_source_prep.py. Sacred Contract #4's documented "
        "ordering is QUEUED → STARTING → ANALYZING → ... DOWNLOADING "
        "stays for back-compat per core/stage.py:10 but ANALYZING is "
        "the canonical successor and must fire first."
    )


# ---------------------------------------------------------------------------
# 3. Adjacency pin — SCENE_DETECTION between TRANSCRIBING + SEGMENT_BUILDING.
# ---------------------------------------------------------------------------


def test_scene_detection_emitted_between_transcribing_and_segment_building():
    """The Sacred Contract #4 frozen ordering interleaves
    TRANSCRIBING_FULL → SCENE_DETECTION → SEGMENT_BUILDING in
    llm_pipeline.py. The runtime emission order must match that
    spec — verified via the source position of the FIRST occurrence
    of each set_stage_fn(JobStage.<X>, ...) call. A regression would
    flip the order (e.g., emit SCENE_DETECTION after SEGMENT_BUILDING)
    which would scramble the FE progress bar."""
    source = LLM_PIPELINE_PATH.read_text(encoding="utf-8-sig")

    pos_transcribing = _first_set_stage_call_pos(source, "TRANSCRIBING_FULL")
    pos_scene        = _first_set_stage_call_pos(source, "SCENE_DETECTION")
    pos_segment      = _first_set_stage_call_pos(source, "SEGMENT_BUILDING")

    assert pos_transcribing != -1, "set_stage_fn(JobStage.TRANSCRIBING_FULL, ...) call not found in llm_pipeline.py"
    assert pos_scene        != -1, "set_stage_fn(JobStage.SCENE_DETECTION, ...) call not found in llm_pipeline.py"
    assert pos_segment      != -1, "set_stage_fn(JobStage.SEGMENT_BUILDING, ...) call not found in llm_pipeline.py"

    assert pos_transcribing < pos_scene < pos_segment, (
        f"T2.3 invariant breached — Sacred Contract #4 frozen ordering "
        f"is TRANSCRIBING_FULL → SCENE_DETECTION → SEGMENT_BUILDING. "
        f"Source positions observed: "
        f"TRANSCRIBING_FULL @ {pos_transcribing}, "
        f"SCENE_DETECTION @ {pos_scene}, "
        f"SEGMENT_BUILDING @ {pos_segment}. "
        f"Reorder the set_stage_fn(JobStage.SCENE_DETECTION, ...) call "
        f"so it sits between the other two in llm_pipeline.py."
    )


# ---------------------------------------------------------------------------
# 4. Defence-in-depth — the enum members are still in JobStage.
# ---------------------------------------------------------------------------


def test_analyzing_and_scene_detection_enum_members_intact():
    """T2.3 chose approach (b) — EMIT the two dormant enum members —
    over approach (a) which would have DELETED them. If a future
    refactor flips to (a) without auditing FE label maps, this test
    fires. Sacred Contract #4 freezes the enum string values."""
    from app.core.stage import JobStage

    assert JobStage.ANALYZING.value == "analyzing", (
        f"Sacred Contract #4 violation — JobStage.ANALYZING.value "
        f"changed to {JobStage.ANALYZING.value!r}. FE label maps + "
        f"stored job records depend on the string 'analyzing'."
    )
    assert JobStage.SCENE_DETECTION.value == "scene_detection", (
        f"Sacred Contract #4 violation — JobStage.SCENE_DETECTION.value "
        f"changed to {JobStage.SCENE_DETECTION.value!r}. FE label maps "
        f"+ stored job records depend on 'scene_detection'."
    )

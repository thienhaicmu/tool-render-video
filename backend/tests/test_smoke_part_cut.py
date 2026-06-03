"""P2 smoke — part_cut.run_cut_stage signature + CutStageResult shape.

Per Track D D2 audit (followup_7 Finding 1), stages/part_cut.py has
zero direct test consumers. run_cut_stage is the LAYER 6 entry point
for per-part cutting; a kwarg rename or dataclass field rename would
silently strand the caller.

See docs/review/AUDIT_2026-06-02_followup_10.md for closure record.
"""
from __future__ import annotations

import dataclasses
import inspect


CUT_STAGE_PARAMS = {"ctx", "idx", "seg", "raw_part", "part_name", "final_part"}

CUT_RESULT_FIELDS = {
    "trim_offset", "effective_start", "effective_end",
    "force_accurate_cut", "visual_trim",
    "part_timeline", "part_manifest",
    "cut_ms", "first_frame_scan_ms",
}


class TestPartCutSurface:
    """Signature + dataclass conformance for the cut stage."""

    def test_run_cut_stage_signature(self):
        from app.orchestration.stages.part_cut import run_cut_stage
        sig = inspect.signature(run_cut_stage)
        params = set(sig.parameters.keys())
        missing = CUT_STAGE_PARAMS - params
        assert not missing, (
            f"run_cut_stage missing expected params: {missing}. "
            f"Caller in process_one_part binds these by name."
        )

    def test_cut_stage_result_is_dataclass(self):
        from app.orchestration.stages.part_cut import CutStageResult
        assert dataclasses.is_dataclass(CutStageResult)

    def test_cut_stage_result_fields(self):
        from app.orchestration.stages.part_cut import CutStageResult
        actual = {f.name for f in dataclasses.fields(CutStageResult)}
        missing = CUT_RESULT_FIELDS - actual
        assert not missing, (
            f"CutStageResult missing fields: {missing}. "
            f"Caller aliases each field back to its original local name."
        )

    def test_returns_cut_stage_result_annotation(self):
        from app.orchestration.stages.part_cut import run_cut_stage
        sig = inspect.signature(run_cut_stage)
        # `from __future__ import annotations` makes annotations strings.
        assert sig.return_annotation == "CutStageResult", (
            f"run_cut_stage return annotation should be 'CutStageResult', "
            f"got {sig.return_annotation!r}."
        )

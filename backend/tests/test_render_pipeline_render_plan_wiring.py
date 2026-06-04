"""
Sprint 2.3 — pin the RenderPlan wiring contract in the pipeline.

Per Render Edit Protocol, these tests anchor:
- PartRenderContext exposes a `render_plan: Optional[RenderPlan]` field
  with default None (Sacred Contract #2 — additive, defaults to disabled).
- The render orchestrator imports `build_render_plan` and
  `update_render_plan` at module scope so the wiring is reachable on
  the live render path (Sprint 2.3 wire-up, no behavioural consumption
  yet).
- The optional field accepts both None and a real RenderPlan without
  raising TypeError or breaking the existing constructor kwarg surface.

These are sentinel tests — they do not exercise the orchestrator end-
to-end (that's covered by the existing pipeline/guard test suites).
Their job is to fail fast if a future refactor removes the wiring.
"""
from pathlib import Path

from app.domain.render_plan import ClipPlan, RenderPlan
from app.orchestration.stages.part_render_context import PartRenderContext


def _ctx_kwargs() -> dict:
    """Build the minimum required PartRenderContext kwargs.

    Mirrors the constructor surface at render_pipeline.py:704-744 — using
    safe sentinel values for every required field. Mutable lists are
    given as fresh empty lists per call so tests don't share state.
    """
    return {
        "job_id": "job-test-001",
        "effective_channel": "test-channel",
        "total_parts": 1,
        "retry_count": 0,
        "work_dir": Path("/tmp/work"),
        "output_dir": Path("/tmp/out"),
        "source_path": Path("/tmp/source.mp4"),
        "source": {"slug": "test"},
        "output_stem": "out",
        "payload": object(),
        "existing_parts": {},
        "ai_edit_plan": None,
        "vis_intensity_hint": None,
        "target_platform": "youtube_shorts",
        "tuned": {},
        "ffmpeg_threads": 1,
        "cancel_registry": None,
        "src_stat_for_motion": None,
        "full_srt": Path("/tmp/full.srt"),
        "full_srt_available": False,
        "subtitle_enabled_by_idx": {},
        "subtitle_cutoff": 0.0,
        "voice_audio_path": None,
        "mv_market": "",
        "mv_cfg": {},
        "hook_apply_enabled": False,
        "hook_applied_text": "",
        "hook_score": None,
        "hook_overlay_enabled": False,
        "dna_clean_visual": False,
        "ai_subtitle_emphasis_config": None,
        "normalized_text_layers": None,
    }


class TestPartRenderContextRenderPlanField:
    def test_default_is_none(self):
        """Sacred Contract #2: new field defaults to disabled (None)."""
        ctx = PartRenderContext(**_ctx_kwargs())
        assert ctx.render_plan is None

    def test_accepts_explicit_none(self):
        ctx = PartRenderContext(render_plan=None, **_ctx_kwargs())
        assert ctx.render_plan is None

    def test_accepts_real_render_plan(self):
        plan = RenderPlan(clips=[ClipPlan(start=1.0, end=10.0, rank=1, clip_name="hook")])
        ctx = PartRenderContext(render_plan=plan, **_ctx_kwargs())
        assert ctx.render_plan is plan
        assert ctx.render_plan.clips[0].clip_name == "hook"

    def test_existing_fields_still_work_unchanged(self):
        """Adding render_plan must not break the kwargs surface used by
        render_pipeline.py:704-744. Pin a few representative fields."""
        ctx = PartRenderContext(**_ctx_kwargs())
        assert ctx.job_id == "job-test-001"
        assert ctx.total_parts == 1
        assert ctx.recovery_notes == []  # mutable default still works


class TestRenderPipelineImports:
    """Pin that render_pipeline.py exposes the wiring helpers at module
    scope. These imports are how the orchestrator reaches the Sprint 2.1
    DB helper and the Sprint 4.D AI dispatcher — losing them silently
    would unwire the RenderPlan persistence without any runtime error
    until a real render happened.

    Sprint 4.H removed the Sprint 2.2 builder shim
    (`render_plan_builder.build_render_plan`); the corresponding import
    pin was retired with it. The AI emission entry point
    `_llm_select_render_plan` (Sprint 4.D) now stands alone."""

    def test_render_pipeline_imports_update_render_plan(self):
        import app.orchestration.render_pipeline as rp
        assert hasattr(rp, "update_render_plan"), (
            "render_pipeline.py must import update_render_plan from "
            "app.db.jobs_repo"
        )

    def test_render_pipeline_imports_select_render_plan_dispatcher(self):
        """Sprint 4.D entry point — the AI emission branch needs the
        dispatcher resolvable at module scope so a typo / circular
        import would fail at import time rather than at first render."""
        import app.orchestration.render_pipeline as rp
        assert hasattr(rp, "_llm_select_render_plan"), (
            "render_pipeline.py must import select_render_plan from "
            "app.ai.llm as _llm_select_render_plan"
        )

    def test_imports_resolve_to_real_callables(self):
        """Defensive: make sure the names aren't shadowed by something
        non-callable. A typo like `update_render_plan = None` would pass
        the hasattr check above but break the live call."""
        import app.orchestration.render_pipeline as rp
        assert callable(rp.update_render_plan)
        assert callable(rp._llm_select_render_plan)

    def test_shim_imports_retired(self):
        """Sprint 4.H — the Sprint 2.2 builder shim symbols MUST be
        gone. A future refactor that resurrects them would silently
        bring back a fallback path the consume sites (Sprint 4.E/F/G)
        no longer expect."""
        import app.orchestration.render_pipeline as rp
        assert not hasattr(rp, "build_render_plan"), (
            "Sprint 4.H removed the shim — build_render_plan must not "
            "be re-imported"
        )
        assert not hasattr(rp, "LLMSegment"), (
            "Sprint 4.H removed the shim's reconstruct loop — LLMSegment "
            "should no longer be imported here"
        )

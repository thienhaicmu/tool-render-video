"""
Sprint 4.D — pin the LLM_EMIT_RENDER_PLAN feature flag wire-up in
render_pipeline.py.

Per the Render Edit Protocol, these tests anchor:
- The flag constant exists at module scope, defaults to False, and
  reads the LLM_EMIT_RENDER_PLAN env var on module load.
- The select_render_plan dispatcher is imported at module scope so the
  AI-emission branch is reachable on the live render path.
- The new render.plan.ai_emitted / render.plan.ai_fallback events are
  declared in the orchestrator source (Sacred Contract #6: new events
  must keep the canonical _emit_render_event payload shape).
- The shim path remains the default — the legacy
  test_render_pipeline_render_plan_wiring.py sentinels (Sprint 2.3)
  continue to pass under flag-OFF state.

The deeper behavioural verification — "AI plan replaces shim plan when
the flag is ON and the provider returns a RenderPlan" — is left to
integration runs (manual + future end-to-end harness). Unit-testing it
from here would require fabricating every local variable inside
run_render_pipeline. Per the Planner brief we keep blast radius small
by sticking to sentinel pins.
"""
import importlib
from pathlib import Path


# ── Module-level wiring sentinels ────────────────────────────────────────


class TestLlmEmitFlagWiring:
    def test_flag_constant_exists_and_is_bool(self):
        import app.orchestration.render_pipeline as rp
        assert hasattr(rp, "_FEATURE_LLM_EMIT_RENDER_PLAN")
        assert isinstance(rp._FEATURE_LLM_EMIT_RENDER_PLAN, bool)

    def test_flag_defaults_off_when_env_unset(self, monkeypatch):
        """Sacred Contract #2: behavior identical baseline when the
        env var is absent. The constant resolves on module reload."""
        monkeypatch.delenv("LLM_EMIT_RENDER_PLAN", raising=False)
        import app.orchestration.render_pipeline as rp
        rp = importlib.reload(rp)
        assert rp._FEATURE_LLM_EMIT_RENDER_PLAN is False

    def test_flag_on_when_env_set_to_1(self, monkeypatch):
        monkeypatch.setenv("LLM_EMIT_RENDER_PLAN", "1")
        import app.orchestration.render_pipeline as rp
        rp = importlib.reload(rp)
        assert rp._FEATURE_LLM_EMIT_RENDER_PLAN is True

    def test_flag_off_when_env_set_to_anything_else(self, monkeypatch):
        """The flag is a strict '== "1"' compare — anything else
        (case-mismatched "true", "yes", "on", numeric strings other than
        "1") leaves the flag OFF. This pins the contract so a future
        loose-truthy refactor doesn't accidentally turn on the AI
        branch in environments that meant to set the flag to false
        via 'true'."""
        monkeypatch.setenv("LLM_EMIT_RENDER_PLAN", "true")
        import app.orchestration.render_pipeline as rp
        rp = importlib.reload(rp)
        assert rp._FEATURE_LLM_EMIT_RENDER_PLAN is False

    def test_select_render_plan_dispatcher_imported_at_module_scope(self):
        """The AI emission branch reaches the dispatcher through this
        module-level binding. If a future refactor lazy-imports it
        inside the function body the binding still resolves via the
        name `_llm_select_render_plan` — pin both the name and that
        it's callable."""
        import app.orchestration.render_pipeline as rp
        assert hasattr(rp, "_llm_select_render_plan")
        assert callable(rp._llm_select_render_plan)


# ── Source-level pins (new events + comment markers) ─────────────────────


class TestAiEmissionEventDeclarations:
    """Sprint 4.D promises three event names. Pin their declarations in
    the source so a future refactor can't silently drop them — the
    contract with WebSocket consumers depends on them appearing.

    We read the source verbatim rather than mocking _emit_render_event
    inside a real pipeline run because that would require fabricating
    every local variable the run_render_pipeline body holds. The
    string-presence check is enough to prevent the most common
    regressions: typo in event name, accidental removal, or migration
    to a different emitter.
    """

    @staticmethod
    def _read_source() -> str:
        from app.orchestration import render_pipeline as rp
        src = Path(rp.__file__).read_text(encoding="utf-8")
        return src

    def test_render_plan_persisted_event_still_emitted(self):
        """Sprint 2.3 contract — both paths (shim + AI) feed into the
        shared persistence + emission tail."""
        src = self._read_source()
        assert 'event="render.plan.persisted"' in src

    def test_render_plan_ai_emitted_event_present(self):
        """Sprint 4.D — emitted ONLY when the AI path succeeds."""
        src = self._read_source()
        assert 'event="render.plan.ai_emitted"' in src

    def test_render_plan_ai_fallback_event_present(self):
        """Sprint 4.D — emitted when the AI path is taken but returns
        None or raises. Lets operators distinguish 'flag off' from
        'flag on but AI failed' in production logs."""
        src = self._read_source()
        assert 'event="render.plan.ai_fallback"' in src

    def test_ai_path_runs_before_shim_path(self):
        """Ordering pin — the AI branch must precede the shim
        reconstruct in source order so that a successful AI emission
        skips the shim entirely. The Planner brief Section C / Change
        C4 made this the explicit gating contract."""
        src = self._read_source()
        idx_ai = src.find('event="render.plan.ai_emitted"')
        idx_shim = src.find("reconstructed_segments")
        assert idx_ai >= 0 and idx_shim >= 0
        assert idx_ai < idx_shim, (
            "AI emission branch must precede the shim reconstruct block"
        )

    def test_shim_path_gated_by_render_plan_is_none(self):
        """When the AI emission succeeds (returns a non-None
        RenderPlan), the shim reconstruct + builder call must be
        skipped. Pinned by the `if _render_plan is None:` guard."""
        src = self._read_source()
        # The exact gating line — the literal string is stable across
        # whitespace formatters because of the explicit None compare.
        assert "if _render_plan is None:" in src

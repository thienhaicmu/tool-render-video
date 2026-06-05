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

    def test_flag_defaults_on_when_env_unset(self, monkeypatch):
        """Sprint 7.6a (2026-06-05): default flipped OFF → ON. Operators
        who need the pre-flip baseline set LLM_EMIT_RENDER_PLAN=0
        explicitly (the rollback escape hatch — pinned by
        test_flag_off_when_env_set_to_0_explicitly below)."""
        monkeypatch.delenv("LLM_EMIT_RENDER_PLAN", raising=False)
        import app.orchestration.render_pipeline as rp
        rp = importlib.reload(rp)
        assert rp._FEATURE_LLM_EMIT_RENDER_PLAN is True

    def test_flag_on_when_env_set_to_1(self, monkeypatch):
        monkeypatch.setenv("LLM_EMIT_RENDER_PLAN", "1")
        import app.orchestration.render_pipeline as rp
        rp = importlib.reload(rp)
        assert rp._FEATURE_LLM_EMIT_RENDER_PLAN is True

    def test_flag_off_when_env_set_to_0_explicitly(self, monkeypatch):
        """Sprint 7.6a — Sacred Contract #2 escape-hatch pin. After the
        Sprint 7.6a default flip, operators who need the legacy behaviour
        revert by setting LLM_EMIT_RENDER_PLAN=0 explicitly. This is the
        3-second rollback documented in
        docs/review/SPRINT_7_6a_LLM_FLAG_FLIP_2026-06-05.md."""
        monkeypatch.setenv("LLM_EMIT_RENDER_PLAN", "0")
        import app.orchestration.render_pipeline as rp
        rp = importlib.reload(rp)
        assert rp._FEATURE_LLM_EMIT_RENDER_PLAN is False

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
        """Sprint 4.D — the AI emission path persists the plan; the
        event survives the Sprint 4.H shim removal because it now
        fires from the (single) AI branch directly."""
        src = self._read_source()
        assert 'event="render.plan.persisted"' in src

    def test_render_plan_ai_emitted_event_present(self):
        """Sprint 4.D — emitted ONLY when the AI path succeeds."""
        src = self._read_source()
        assert 'event="render.plan.ai_emitted"' in src

    def test_render_plan_ai_fallback_event_present(self):
        """Sprint 4.D — emitted when the AI path is taken but returns
        None or raises. Lets operators distinguish 'flag off' from
        'flag on but AI failed' in production logs. Sprint 4.H removed
        the shim path so this event also marks the boundary where the
        stage resolvers fall back to legacy payload logic."""
        src = self._read_source()
        assert 'event="render.plan.ai_fallback"' in src

    def test_shim_imports_removed(self):
        """Sprint 4.H removal pin — the orchestrator must NOT re-import
        the Sprint 2.2 builder shim. If a future refactor accidentally
        brings them back the consume sites (Sprint 4.E/F/G) would see
        an unexpected always-populated render_plan even when
        LLM_EMIT_RENDER_PLAN is OFF."""
        src = self._read_source()
        assert "from app.ai.llm.parser import LLMSegment" not in src
        assert "from app.orchestration.render_plan_builder" not in src

    def test_shim_reconstruct_loop_removed(self):
        """Sprint 4.H — the `_reconstructed_segments` reconstruct loop
        and the `build_render_plan(...)` shim call were both removed.
        Pin their absence so a future regression doesn't quietly bring
        back a fallback path the consume sites no longer expect."""
        src = self._read_source()
        assert "_reconstructed_segments" not in src
        assert "build_render_plan(" not in src

    def test_persistence_still_guarded_by_render_plan_is_not_none(self):
        """The persistence tail must still run only when an AI plan
        was actually produced (or skip silently when not). Pinned by
        the explicit `if _render_plan is not None:` guard. Sprint
        4.H kept this guard verbatim — the difference is that flag-OFF
        paths now always trip the "not None" check rather than first
        going through a shim that always produced something."""
        src = self._read_source()
        assert "if _render_plan is not None:" in src

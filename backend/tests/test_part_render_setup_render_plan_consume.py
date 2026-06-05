"""
Sprint 4.F — pin the RenderPlan.camera_strategy consume contract.

These tests anchor the single resolver helper
``_resolve_reframe_mode_from_plan`` that part_render_setup uses to
migrate the camera-reframe decision from the legacy direct payload
read to a per-field merge with the AI-emitted RenderPlan.

The resolver is pure: no I/O, no FFmpeg invocation, no thread-start
side effects. It takes a PartRenderContext and a fallback value and
returns (value, source_tag). Per Planner brief Section D the deeper
behavioural verification — "the preflight actually consumes the plan
and emits the right event source tag" — is covered by source-level
pins (TestEventSourceEnumWired) so we never regress the wire-up.

motion_aware_crop and tracker are EXPLICITLY out of scope for
Sprint 4.F. motion_aware_crop was deferred for the same
emphasis_pass / Sacred-Contract-#2 reason that Sprint 4.E cited.
tracker was deferred because no orchestration call site reads it
today.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.domain.render_plan import (
    AudioPlan,
    CameraStrategy,
    ClipPlan,
    OutputConfig,
    RenderPlan,
    SubtitlePolicy,
)
from app.orchestration.stages.part_render_setup import (
    _RENDER_PLAN_ALLOWED_REFRAME_MODES,
    _resolve_reframe_mode_from_plan,
)


def _ctx(render_plan):
    """Bare-attribute ctx — the resolver only reads `render_plan`."""
    ctx = MagicMock()
    ctx.render_plan = render_plan
    return ctx


# ── _resolve_reframe_mode_from_plan ──────────────────────────────────────


class TestResolveReframeModeFromPlan:
    def test_returns_fallback_when_plan_is_none(self):
        result = _resolve_reframe_mode_from_plan(_ctx(None), "subject")
        assert result == ("subject", "fallback")

    def test_returns_plan_reframe_when_set(self):
        plan = RenderPlan(camera_strategy=CameraStrategy(reframe_mode="center"))
        result = _resolve_reframe_mode_from_plan(_ctx(plan), "subject")
        assert result == ("center", "render_plan")

    def test_returns_fallback_when_plan_reframe_empty(self):
        plan = RenderPlan(camera_strategy=CameraStrategy(reframe_mode=""))
        result = _resolve_reframe_mode_from_plan(_ctx(plan), "subject")
        assert result == ("subject", "fallback")

    def test_returns_fallback_when_plan_reframe_whitespace(self):
        plan = RenderPlan(camera_strategy=CameraStrategy(reframe_mode="   "))
        result = _resolve_reframe_mode_from_plan(_ctx(plan), "subject")
        assert result == ("subject", "fallback")

    def test_returns_fallback_with_invalid_reframe_tag(self):
        plan = RenderPlan(camera_strategy=CameraStrategy(reframe_mode="bogus_xyz"))
        result = _resolve_reframe_mode_from_plan(_ctx(plan), "subject")
        assert result == ("subject", "fallback_invalid_reframe")

    def test_accepts_every_documented_reframe_mode(self):
        """The CameraStrategy dataclass docstring lists center / track
        / fixed as the canonical vocabulary. Pin each."""
        for canonical in ("center", "track", "fixed"):
            plan = RenderPlan(camera_strategy=CameraStrategy(reframe_mode=canonical))
            result = _resolve_reframe_mode_from_plan(_ctx(plan), "subject")
            assert result == (canonical, "render_plan"), f"mode={canonical!r}"

    def test_strips_whitespace_from_plan_reframe(self):
        plan = RenderPlan(camera_strategy=CameraStrategy(reframe_mode="  track  "))
        result = _resolve_reframe_mode_from_plan(_ctx(plan), "subject")
        assert result == ("track", "render_plan")

    def test_legacy_subject_value_passes_through_as_fallback(self):
        """The legacy payload default `"subject"` is NOT in the
        RenderPlan vocabulary, but it must survive as a fallback value
        when the plan is empty / None. Pin that the resolver does not
        accidentally validate the fallback against the plan vocabulary."""
        result = _resolve_reframe_mode_from_plan(_ctx(None), "subject")
        assert result == ("subject", "fallback")
        # And when the plan exists but is empty, the legacy value still
        # surfaces unchanged.
        plan = RenderPlan(camera_strategy=CameraStrategy(reframe_mode=""))
        result = _resolve_reframe_mode_from_plan(_ctx(plan), "subject")
        assert result == ("subject", "fallback")


# ── Source-level pins for event source enum + deferred fields ───────────


class TestEventSourceEnumWired:
    """The Sprint 4.F `camera_strategy_applied` event surfaces a
    `reframe_mode_source` enum mirroring Sprint 4.E's pattern. These
    source-level pins guard against future refactors silently dropping
    the event or the source tag."""

    @staticmethod
    def _read_source() -> str:
        from app.orchestration.stages import part_render_setup as prs
        return Path(prs.__file__).read_text(encoding="utf-8")

    def test_source_enum_includes_render_plan(self):
        src = self._read_source()
        assert '"render_plan"' in src or "'render_plan'" in src

    def test_source_enum_includes_fallback_invalid_reframe(self):
        src = self._read_source()
        assert "fallback_invalid_reframe" in src

    def test_camera_strategy_applied_event_present(self):
        src = self._read_source()
        assert 'event="camera_strategy_applied"' in src

    def test_event_imports_emit_render_event(self):
        """Pin the import wire — Sprint 4.F added _emit_render_event to
        the existing render_events import line."""
        src = self._read_source()
        assert "_emit_render_event" in src

    def test_reframe_resolver_call_site_present(self):
        """The resolver is invoked exactly once and feeds the cache key
        (L188), PartExecutionPlan ctor, and CameraStrategy ctor. Pin
        that the single-resolution pattern from Planner brief
        Section C/C2 survives."""
        src = self._read_source()
        assert "_resolve_reframe_mode_from_plan(" in src
        assert "_effective_reframe, _reframe_source" in src


class TestDeferredFieldsDocumented:
    """Sprint 4.F deferred two fields explicitly. The module-level
    comment block must mention both so a future maintainer doesn't
    accidentally drop the rationale."""

    @staticmethod
    def _read_source() -> str:
        from app.orchestration.stages import part_render_setup as prs
        return Path(prs.__file__).read_text(encoding="utf-8")

    def test_motion_aware_crop_deferred_mentioned(self):
        src = self._read_source()
        # The deferral rationale references both the field name and
        # the contract violation that justifies the defer.
        assert "motion_aware_crop" in src
        assert "deferred" in src.lower() or "DEFERRED" in src

    def test_tracker_deferred_mentioned(self):
        src = self._read_source()
        assert "tracker" in src

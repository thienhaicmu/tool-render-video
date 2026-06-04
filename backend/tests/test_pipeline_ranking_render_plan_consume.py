"""
Sprint 4.G — pin the RenderPlan rank consume contract.

These tests anchor the resolver helper ``_resolve_rank_from_plan``
that the orchestrator (render_pipeline.py:P5-1 Output Ranking block)
uses to migrate per-part ranks from the legacy score-descending sort
to a per-field merge with the AI-emitted RenderPlan.

The resolver is pure: no I/O, no DB hit, no event emission. It takes
a RenderPlan, the orchestrator's `scored` list, and the failed-part
set, and returns (mapping_part_no→rank, source_tag).

Sacred Contract #2 baseline guarantee: the resolver checks the
LLM_EMIT_RENDER_PLAN env var explicitly. When the flag is OFF (the
Sprint 4.D default), the resolver ALWAYS returns
(None, "fallback") — so the shim-built ranks from Sprint 2.2's
_build_clips (which always sets rank=1..N via enumerate) cannot
leak into the live ranking decision when the AI emission path is
not active.
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
from app.orchestration.pipeline_ranking import (
    _RENDER_PLAN_RANK_SOURCES,
    _resolve_rank_from_plan,
)


def _plan(*ranks: int) -> RenderPlan:
    """Build a RenderPlan with ClipPlans carrying the given ranks.

    Each clip is given start/end values that make it parse-able by
    other Sprint 4 helpers, but the resolver only inspects `rank`.
    """
    clips = []
    for i, r in enumerate(ranks):
        clips.append(ClipPlan(
            start=float(10 + i * 50),
            end=float(40 + i * 50),
            rank=r,
            score=0.5,
            clip_name=f"clip_{i+1}",
        ))
    return RenderPlan(clips=clips)


def _scored(n: int) -> list[dict]:
    """Build a list of n placeholder scored dicts."""
    return [{"start": 10.0 + i * 50, "end": 40.0 + i * 50, "viral_score": 50.0} for i in range(n)]


@pytest.fixture(autouse=True)
def _enable_llm_emit_flag(monkeypatch):
    """Default-ON the env flag for tests that exercise the consume
    path. Tests that need the OFF path monkeypatch it themselves."""
    monkeypatch.setenv("LLM_EMIT_RENDER_PLAN", "1")


# ── Feature-flag gate (Sacred Contract #2 baseline guarantee) ────────────


class TestFlagGate:
    def test_flag_off_returns_fallback_even_with_valid_plan(self, monkeypatch):
        """The single most important contract in Sprint 4.G: when the
        env flag is OFF, the resolver MUST return (None, "fallback")
        regardless of plan contents. This stops the Sprint 2.2 builder
        shim's always-populated ranks from leaking into the live
        ranking decision."""
        monkeypatch.setenv("LLM_EMIT_RENDER_PLAN", "0")
        result = _resolve_rank_from_plan(_plan(1, 2, 3), _scored(3), failed_idx_set=set())
        assert result == (None, "fallback")

    def test_flag_unset_returns_fallback(self, monkeypatch):
        monkeypatch.delenv("LLM_EMIT_RENDER_PLAN", raising=False)
        result = _resolve_rank_from_plan(_plan(1, 2, 3), _scored(3), failed_idx_set=set())
        assert result == (None, "fallback")

    def test_flag_loose_truthy_does_not_count(self, monkeypatch):
        """Strict `== "1"` compare. Anything else stays OFF, matching
        the Sprint 4.D pipeline-wire flag's contract."""
        for truthy in ("true", "yes", "on", "1.0", "2"):
            monkeypatch.setenv("LLM_EMIT_RENDER_PLAN", truthy)
            result = _resolve_rank_from_plan(_plan(1, 2, 3), _scored(3), failed_idx_set=set())
            assert result == (None, "fallback"), f"flag={truthy!r} should not enable consume"


# ── Resolver behavior when consume gate is open ──────────────────────────


class TestResolverBehavior:
    def test_returns_fallback_when_plan_is_none(self):
        result = _resolve_rank_from_plan(None, _scored(3), failed_idx_set=set())
        assert result == (None, "fallback")

    def test_returns_fallback_no_plan_rank_when_clips_empty(self):
        plan = RenderPlan(clips=[])
        result = _resolve_rank_from_plan(plan, _scored(3), failed_idx_set=set())
        assert result == (None, "fallback_no_plan_rank")

    def test_returns_fallback_no_plan_rank_when_any_clip_rank_zero(self):
        """Partial rank = AI did not decide for everyone → defer."""
        result = _resolve_rank_from_plan(_plan(1, 0, 2), _scored(3), failed_idx_set=set())
        assert result == (None, "fallback_no_plan_rank")

    def test_returns_mapping_when_all_clips_have_sequential_rank(self):
        mapping, tag = _resolve_rank_from_plan(_plan(1, 2, 3), _scored(3), failed_idx_set=set())
        assert tag == "render_plan"
        assert mapping == {1: 1, 2: 2, 3: 3}

    def test_accepts_permuted_ranks(self):
        """AI may rerank: scored[0] gets rank=3, scored[1] gets rank=1,
        scored[2] gets rank=2. Resolver maps by POSITION."""
        mapping, tag = _resolve_rank_from_plan(_plan(3, 1, 2), _scored(3), failed_idx_set=set())
        assert tag == "render_plan"
        assert mapping == {1: 3, 2: 1, 3: 2}

    def test_returns_collision_on_duplicate_ranks(self):
        result = _resolve_rank_from_plan(_plan(1, 1, 2), _scored(3), failed_idx_set=set())
        assert result == (None, "fallback_rank_collision")

    def test_returns_invalid_on_non_sequential_ranks(self):
        """Ranks {1, 3, 5} are unique but not a permutation of 1..N."""
        result = _resolve_rank_from_plan(_plan(1, 3, 5), _scored(3), failed_idx_set=set())
        assert result == (None, "fallback_rank_invalid")

    def test_respects_failed_idx_set(self):
        """Failed parts must be excluded from the mapping. scored=4,
        failed={2} → mapping covers {1, 3, 4}."""
        mapping, tag = _resolve_rank_from_plan(_plan(1, 2, 3), _scored(4), failed_idx_set={2})
        assert tag == "render_plan"
        assert mapping == {1: 1, 3: 2, 4: 3}

    def test_returns_no_plan_rank_when_plan_has_fewer_clips_than_success(self):
        """3 successful parts but only 2 clips in plan → cannot map."""
        result = _resolve_rank_from_plan(_plan(1, 2), _scored(3), failed_idx_set=set())
        assert result == (None, "fallback_no_plan_rank")

    def test_resolver_is_pure_no_side_effects(self):
        """Calling twice with the same inputs yields the same output
        and does not mutate the inputs."""
        plan = _plan(1, 2, 3)
        scored = _scored(3)
        result1 = _resolve_rank_from_plan(plan, scored, failed_idx_set=set())
        result2 = _resolve_rank_from_plan(plan, scored, failed_idx_set=set())
        assert result1 == result2
        # Plan and scored unchanged.
        assert plan.clips[0].rank == 1
        assert scored[0]["viral_score"] == 50.0


# ── Source enum exposure ────────────────────────────────────────────────


class TestRankSourceEnum:
    def test_enum_contains_render_plan_tag(self):
        assert "render_plan" in _RENDER_PLAN_RANK_SOURCES

    def test_enum_contains_every_fallback_tag(self):
        for tag in (
            "fallback",
            "fallback_no_plan_rank",
            "fallback_rank_collision",
            "fallback_rank_invalid",
        ):
            assert tag in _RENDER_PLAN_RANK_SOURCES, f"missing tag: {tag}"


# ── Source-level pins in render_pipeline.py ──────────────────────────────


class TestRenderPipelineWiring:
    """Sprint 4.G surfaces `rank_source` in two existing events plus
    the audit log. Pin the wire-up so future refactors can't silently
    drop the provenance attribution."""

    @staticmethod
    def _read_source() -> str:
        from app.orchestration import render_pipeline as rp
        return Path(rp.__file__).read_text(encoding="utf-8")

    def test_resolver_imported_at_module_scope(self):
        src = self._read_source()
        assert "_resolve_rank_from_plan" in src

    def test_output_rank_computed_event_carries_rank_source(self):
        """The per-part event must surface the rank source so each
        clip's provenance can be attributed in production traces."""
        src = self._read_source()
        # Find the output_rank_computed event block and confirm
        # rank_source appears within ~600 chars (the context dict).
        idx = src.find('event="output_rank_computed"')
        assert idx >= 0, "output_rank_computed event missing"
        ctx_window = src[idx:idx + 1200]
        assert '"rank_source": _rank_source_tag' in ctx_window

    def test_output_ranking_completed_event_carries_rank_source(self):
        src = self._read_source()
        idx = src.find('event="output_ranking_completed"')
        assert idx >= 0, "output_ranking_completed event missing"
        ctx_window = src[idx:idx + 1600]
        assert '"rank_source":' in ctx_window

    def test_consume_branch_present(self):
        """The if-branch that consumes the plan mapping must be in
        source order BEFORE the legacy score-descending sort branch."""
        src = self._read_source()
        idx_consume = src.find("if _plan_rank_map is not None:")
        idx_legacy = src.find('_rank_entries.sort(key=lambda x: x["output_score"], reverse=True)')
        assert idx_consume >= 0 and idx_legacy >= 0
        assert idx_consume < idx_legacy, (
            "consume branch must precede legacy sort branch in source order"
        )

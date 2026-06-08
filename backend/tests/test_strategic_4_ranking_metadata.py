"""Strategic-4 closure regression guard — Audit 2026-06-08 (Batch A V8-D1/V8-D2).

The audit's Phase 8 finding flagged two ranking-transparency gaps:

  - V8-D1: Local ranking recomputes from a fixed weighted formula at
    pipeline_ranking.py:204-211, overriding the AI's overall score.
    The AI's emitted clip.score was mapped into _base only as a
    fallback for missing component scores; the final output_score
    was the locally-recomputed weighted sum.

  - V8-D2: The AI's rank field was consumed only when
    LLM_EMIT_RENDER_PLAN=1 AND the ranks formed a valid 1..N
    permutation. Otherwise the legacy score-descending sort fired.
    The choice between modes was invisible to consumers — no
    result_json key, no operator-readable attribution.

Strategic-4 surfaces both decisions in ``result_json``:

  1. ``ranking_metadata.rank_source`` — the tag returned by
     ``_resolve_rank_from_plan`` (one of: render_plan, fallback,
     fallback_no_plan_rank, fallback_rank_invalid,
     fallback_rank_collision). Pre-Strategic-4 this tag existed in
     per-entry WS events and the orchestrator log line but never
     reached the persisted result.

  2. ``ranking_metadata.ai_rank_consumed`` — boolean shortcut for
     consumers that just need yes/no.

  3. ``ranking_metadata.local_recompute_active`` — symmetric
     boolean.

  4. ``ranking_metadata.formula`` — the local-recompute coefficients
     mirroring pipeline_ranking.py:204-211 (viral 0.35, hook 0.20,
     retention 0.20, speech_density 0.10, market 0.10,
     duration_fit 0.05). Operators reading the result_json after a
     surprising rank decision can see the formula used.

  5. ``ranking_metadata.fallback_reasons_documented`` — list of all
     valid tag values so a consumer-side switch statement covers
     them all and lints loudly when a new tag is added without
     consumer-side handling.

This file pins:
  a. FinalizeContext carries a ``rank_source`` field with default ""
     (backward-compat for callers that don't set it).
  b. The result_json ranking_metadata block is built from
     ctx.rank_source verbatim.
  c. The formula coefficients match the canonical
     pipeline_ranking.py:_compute_output_ranking_entry values.
  d. The render_pipeline orchestrator now passes _rank_source_tag
     into FinalizeContext at the call site.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# 1. FinalizeContext dataclass — rank_source field present with default "".
# ---------------------------------------------------------------------------


def test_finalize_context_has_rank_source_field():
    """The dataclass surface gains a ``rank_source: str`` field with
    default "" so backward-compat tests / shims that construct
    FinalizeContext without the new kwarg keep working."""
    from dataclasses import fields
    from app.features.render.engine.pipeline.pipeline_finalize import FinalizeContext

    rank_field = next((f for f in fields(FinalizeContext) if f.name == "rank_source"), None)
    assert rank_field is not None, (
        "Strategic-4 regression — FinalizeContext.rank_source field "
        "was removed. The orchestrator at render_pipeline.py:1326+ "
        "passes _rank_source_tag through here; without the field the "
        "rank-source attribution disappears from result_json again."
    )
    # Field must be string-typed with default "".
    assert rank_field.default == "", (
        f"FinalizeContext.rank_source default changed to "
        f"{rank_field.default!r}. The empty-string default is the "
        f"backward-compat marker; callers that don't set rank_source "
        f"degrade gracefully to a 'fallback' label rather than raising."
    )


# ---------------------------------------------------------------------------
# 2. result_json.ranking_metadata block — shape + content.
# ---------------------------------------------------------------------------


def _build_minimal_ctx(*, rank_source: str = "render_plan"):
    """Construct a minimally valid FinalizeContext for unit-testing
    the result_json shape. Only the fields the metadata block reads
    matter; everything else gets a safe default."""
    from app.features.render.engine.pipeline.pipeline_finalize import FinalizeContext
    from app.models.render import RenderRequest

    payload = RenderRequest(
        channel_code="t-strategic-4",
        source_mode="local",
        source_video_path="/nonexistent.mp4",
        output_mode="manual",
        output_dir="/nonexistent/out",
    )

    return FinalizeContext(
        job_id="job-s4",
        effective_channel="t-strategic-4",
        payload=payload,
        started_at=datetime.utcnow(),
        output_dir=Path("/nonexistent/out"),
        output_stem="t_s4",
        outputs=[],
        failed_parts=[],
        total_parts=0,
        scored=[],
        recovery_notes=[],
        rank_entries=[],
        rank_entries_ordered=[],
        best_rank_entry=None,
        partial_warning="",
        preset_name="",
        preset_id="",
        preset_label="",
        mv_parts=[],
        voice_summary="not used",
        subtitle_translate_summary="not used",
        ai_influence_report={"enabled": False},
        ai_beat_report={"enabled": False},
        render_plan=None,
        rank_source=rank_source,
    )


def _capture_result_payload(ctx) -> dict:
    """Run the finalize block far enough to capture the result_json
    dict that gets passed to upsert_job. We patch upsert_job to
    capture its result arg and short-circuit the rest of the
    finalize side effects."""
    from app.features.render.engine.pipeline import pipeline_finalize

    captured: dict = {}

    def _fake_upsert_job(job_id, kind, channel, status, payload, result, **kwargs):
        captured["result"] = result
        captured["status"] = status

    # Patch every side-effecting boundary so the dataclass test stays
    # hermetic. ``maybe_snapshot_after_job`` is lazy-imported inside
    # run_render_finalize and wrapped in try/except, so any
    # snapshot-time error after upsert_job runs is swallowed and the
    # captured ``result`` still reflects the persisted shape.
    with patch.object(pipeline_finalize, "upsert_job", side_effect=_fake_upsert_job), \
         patch.object(pipeline_finalize, "_emit_render_event"), \
         patch.object(pipeline_finalize, "_job_log"):
        try:
            pipeline_finalize.run_render_finalize(ctx)
        except Exception:
            # The test only cares about result_json shape, which is
            # built BEFORE any optional side effects that may fail in
            # this minimal-context environment.
            pass

    return captured.get("result", {})


def test_result_json_contains_ranking_metadata_key():
    """``ranking_metadata`` lives at the TOP level of result_json so
    consumers don't have to dig into output_ranking entries to find
    the source attribution."""
    ctx = _build_minimal_ctx(rank_source="render_plan")
    result = _capture_result_payload(ctx)
    assert "ranking_metadata" in result, (
        "Strategic-4 regression — result_json no longer carries the "
        "ranking_metadata top-level key. Consumers (FE, AI Director, "
        "ops) can't attribute the rank choice post-render. Restore "
        "the _ranking_metadata block in pipeline_finalize.py before "
        "the _result_payload dict."
    )


def test_ranking_metadata_render_plan_source_signals_ai_consumed():
    """When the orchestrator passed rank_source='render_plan', the
    metadata MUST surface ai_rank_consumed=True and
    local_recompute_active=False."""
    ctx = _build_minimal_ctx(rank_source="render_plan")
    result = _capture_result_payload(ctx)
    rm = result["ranking_metadata"]

    assert rm["rank_source"] == "render_plan"
    assert rm["ai_rank_consumed"] is True
    assert rm["local_recompute_active"] is False


def test_ranking_metadata_fallback_source_signals_local_recompute():
    """When the orchestrator passed any fallback tag, the metadata
    MUST surface ai_rank_consumed=False and
    local_recompute_active=True. The exact tag is preserved verbatim
    for forensic value."""
    for tag in ["fallback", "fallback_no_plan_rank",
                "fallback_rank_invalid", "fallback_rank_collision"]:
        ctx = _build_minimal_ctx(rank_source=tag)
        result = _capture_result_payload(ctx)
        rm = result["ranking_metadata"]

        assert rm["rank_source"] == tag, f"tag={tag!r} not preserved"
        assert rm["ai_rank_consumed"] is False, f"tag={tag!r} should signal not consumed"
        assert rm["local_recompute_active"] is True, f"tag={tag!r} should signal local recompute"


def test_ranking_metadata_empty_rank_source_defaults_to_fallback_label():
    """A FinalizeContext built without setting rank_source (the
    backward-compat path) must still produce a usable metadata block.
    The empty default maps to the 'fallback' label so consumers see
    a definite tag rather than an empty string."""
    ctx = _build_minimal_ctx(rank_source="")
    result = _capture_result_payload(ctx)
    rm = result["ranking_metadata"]

    assert rm["rank_source"] == "fallback", (
        f"Empty rank_source must map to the canonical 'fallback' "
        f"label in result_json. Got rank_source={rm['rank_source']!r}."
    )
    assert rm["ai_rank_consumed"] is False
    assert rm["local_recompute_active"] is True


# ---------------------------------------------------------------------------
# 3. The formula coefficients must mirror pipeline_ranking.py:204-211.
# ---------------------------------------------------------------------------


def test_ranking_metadata_formula_coefficients_match_canonical():
    """The local-recompute formula in result_json must mirror the
    canonical weights at pipeline_ranking.py:_compute_output_ranking_entry.
    Documentation MUST follow code: when the actual formula coefficients
    change, this metadata block AND this test must update in lockstep."""
    ctx = _build_minimal_ctx(rank_source="fallback")
    result = _capture_result_payload(ctx)
    formula = result["ranking_metadata"]["formula"]

    # These are the canonical coefficients per pipeline_ranking.py:204-211.
    expected = {
        "viral_score":     0.35,
        "hook_score":      0.20,
        "retention_score": 0.20,
        "speech_density":  0.10,
        "market_score":    0.10,
        "duration_fit":    0.05,
    }
    assert formula == expected, (
        f"Strategic-4 regression — result_json.ranking_metadata.formula "
        f"diverged from the canonical weights at "
        f"pipeline_ranking.py:_compute_output_ranking_entry. Expected "
        f"{expected}, got {formula}. If the formula intentionally "
        f"changed, update both this test AND the metadata block in "
        f"pipeline_finalize.py in lockstep."
    )
    # Coefficients must sum to 1.0 (defence-in-depth).
    assert abs(sum(expected.values()) - 1.0) < 1e-9


def test_ranking_metadata_documents_all_fallback_reasons():
    """``fallback_reasons_documented`` is the consumer-side
    discoverability hook — a FE that switch-cases on rank_source can
    iterate this list to ensure complete coverage."""
    ctx = _build_minimal_ctx(rank_source="render_plan")
    result = _capture_result_payload(ctx)
    reasons = result["ranking_metadata"]["fallback_reasons_documented"]

    # The four fallback tags that _resolve_rank_from_plan returns.
    expected = [
        "fallback",
        "fallback_no_plan_rank",
        "fallback_rank_invalid",
        "fallback_rank_collision",
    ]
    assert set(reasons) == set(expected), (
        f"Strategic-4 regression — fallback_reasons_documented diverged "
        f"from _resolve_rank_from_plan's actual return tags. Got "
        f"{reasons}, expected {expected}. Update pipeline_finalize.py's "
        f"_ranking_metadata block AND the resolver in pipeline_ranking.py "
        f"in lockstep."
    )


# ---------------------------------------------------------------------------
# 4. Orchestrator wiring — render_pipeline.py passes _rank_source_tag.
# ---------------------------------------------------------------------------


def test_orchestrator_passes_rank_source_into_finalize_context():
    """Source-level guard pinning the wiring at
    render_pipeline.py:1326-1351. A refactor that drops the
    rank_source kwarg reverts Strategic-4 — the field defaults to ""
    and the metadata block surfaces 'fallback' regardless of the
    actual orchestrator decision."""
    import re

    src = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine"
        / "pipeline" / "render_pipeline.py"
    )
    source = src.read_text(encoding="utf-8-sig")

    # The FinalizeContext construction call MUST include
    # rank_source=_rank_source_tag.
    assert re.search(
        r"FinalizeContext\([\s\S]*?rank_source\s*=\s*_rank_source_tag",
        source,
    ), (
        "Strategic-4 regression — render_pipeline.py no longer passes "
        "rank_source=_rank_source_tag into FinalizeContext. The "
        "metadata block in pipeline_finalize.py uses ctx.rank_source "
        "verbatim; without the kwarg the field defaults to '' and "
        "the rank-source attribution is lost from result_json."
    )

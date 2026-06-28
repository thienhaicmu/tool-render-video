"""Wiring + contract tests for the ai_rewrite v2 branch in run_part_voice_mix.

Verifies the branch:
  - parses srt_part into blocks + formats for LLM input;
  - calls rewrite_subtitle with srt_segmented + clip_duration_sec;
  - feeds returned segments into synthesize_timed_narration;
  - falls back to a single-segment narration of the ORIGINAL text when
    rewrite returns None (Sacred Contract #3);
  - emits voice_ai_rewrite_started / _completed / _fallback events;
  - is skipped when voice_enabled=False or voice_source!='ai_rewrite';
  - passes clip_duration_sec = (seg.end - seg.start).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.features.render.engine.stages import part_voice_mix as PVM
from app.features.render.engine.stages.part_render_context import PartRenderContext


# ── Module-level contract pins ──────────────────────────────────────────────

def test_module_imports_llm_rewrite_dispatcher():
    assert hasattr(PVM, "_llm_rewrite_subtitle")


def test_module_imports_timed_narration_synthesizer():
    assert hasattr(PVM, "synthesize_timed_narration")


def test_voice_source_allowlist_accepts_ai_rewrite():
    from app.models.render import RenderRequest
    r = RenderRequest(
        url="https://example.com/v.mp4",
        source_mode="local",
        local_file_path="C:/tmp/foo.mp4",
        voice_enabled=True,
        voice_source="ai_rewrite",
        voice_language="vi-VN",
        voice_gender="female",
        voice_mix_mode="replace_original",
    )
    assert r.voice_source == "ai_rewrite"


def test_rewrite_tone_default_is_empty_string():
    from app.models.render import RenderRequest
    r = RenderRequest(
        url="https://example.com/v.mp4",
        source_mode="local",
        local_file_path="C:/tmp/foo.mp4",
    )
    assert r.rewrite_tone == ""


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_ctx(tmp_path: Path, payload, full_srt_text: str = "") -> PartRenderContext:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    full_srt = work_dir / "full.srt"
    if full_srt_text:
        full_srt.write_text(full_srt_text, encoding="utf-8")

    class _CancelStub:
        class JobCancelledError(Exception):
            pass

        def is_cancelled(self, job_id):
            return False

    return PartRenderContext(
        job_id="job-test",
        effective_channel="ch-test",
        total_parts=1,
        retry_count=0,
        work_dir=work_dir,
        output_dir=output_dir,
        source_path=tmp_path / "src.mp4",
        source={"path": str(tmp_path / "src.mp4")},
        output_stem="out",
        payload=payload,
        existing_parts={},
        target_platform="tiktok",
        tuned={},
        ffmpeg_threads=1,
        cancel_registry=_CancelStub(),
        src_stat_for_motion=None,
        full_srt=full_srt,
        full_srt_available=bool(full_srt_text),
        subtitle_enabled_by_idx={},
        subtitle_cutoff=0.0,
        voice_audio_path=None,
        mv_market="",
        mv_cfg={},
        hook_apply_enabled=False,
        hook_applied_text="",
        hook_score=None,
        hook_overlay_enabled=False,
        dna_clean_visual=False,
        normalized_text_layers=None,
    )


def _make_payload(**overrides):
    base = dict(
        voice_enabled=True,
        voice_source="ai_rewrite",
        voice_language="vi-VN",
        voice_gender="female",
        voice_rate="+0%",
        voice_mix_mode="replace_original",
        voice_text=None,
        voice_id=None,
        rewrite_tone="",
        ai_provider="gemini",
        gemini_api_key="fake-key",
        openai_api_key="",
        claude_api_key="",
        llm_model=None,
        tts_engine="edge",
        subtitle_translate_enabled=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


_SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 4.0, "text": "Đoạn 1 đã viết lại"},
    {"start": 5.0, "end": 8.0, "text": "Đoạn 2 đã viết lại"},
]


@pytest.fixture
def _branch_test_env(monkeypatch, tmp_path):
    """Mocks the heavy externals + collects LLM / synthesizer calls + events."""
    srt_part = tmp_path / "part_001.srt"
    srt_part.write_text(
        "1\n00:00:00,000 --> 00:00:04,000\nFirst utterance from source\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nSecond utterance from source\n",
        encoding="utf-8",
    )
    captured: dict = {"rewrite_return": _SAMPLE_SEGMENTS}
    events: list = []

    def _spy_rewrite(**kw):
        captured["rewrite_kwargs"] = kw
        return captured["rewrite_return"]

    def _spy_synth(**kw):
        captured["synth_kwargs"] = kw
        out = tmp_path / "voice.mp3"
        out.write_bytes(b"FAKEMP3")
        return str(out)

    def _spy_emit(**kw):
        events.append(kw["event"])

    def _noop_cleanup(path, *a, **kw):
        return path

    monkeypatch.setattr(PVM, "_llm_rewrite_subtitle", _spy_rewrite)
    monkeypatch.setattr(PVM, "synthesize_timed_narration", _spy_synth)
    monkeypatch.setattr(PVM, "_emit_render_event", _spy_emit)
    monkeypatch.setattr(PVM, "_maybe_cleanup_narration_audio", _noop_cleanup)
    monkeypatch.setattr(PVM, "mix_narration_audio", MagicMock(return_value=None))
    monkeypatch.setattr(PVM, "mix_with_bgm", MagicMock(return_value=None))
    monkeypatch.setattr(PVM, "write_manifest", MagicMock(return_value=None))
    monkeypatch.setattr(PVM, "_job_log", lambda *a, **kw: None)
    return captured, events, srt_part


def _invoke_branch(ctx: PartRenderContext, srt_part: Path, seg: dict, idx: int):
    final_part = ctx.work_dir / f"part_{idx:03d}_final.mp4"
    final_part.write_bytes(b"FAKEMP4")
    return PVM.run_part_voice_mix(
        ctx=ctx,
        idx=idx,
        seg=seg,
        srt_part=srt_part,
        translated_srt_part=ctx.work_dir / "translated_missing.srt",
        final_part=final_part,
        part_manifest=MagicMock(),
    )


# ── Branch behavior ─────────────────────────────────────────────────────────

def test_ai_rewrite_feeds_segments_into_synthesizer_when_llm_returns_segments(_branch_test_env, tmp_path):
    captured, events, srt_part = _branch_test_env
    captured["rewrite_return"] = _SAMPLE_SEGMENTS
    ctx = _make_ctx(tmp_path, _make_payload())
    _invoke_branch(ctx, srt_part, {"start": 0.0, "end": 8.0, "content_type_hint": "vlog"}, idx=1)
    assert captured["synth_kwargs"]["segments"] == _SAMPLE_SEGMENTS
    assert "voice_ai_rewrite_started" in events
    assert "voice_ai_rewrite_completed" in events
    assert "voice_tts_started" in events


def test_ai_rewrite_falls_back_to_single_segment_when_llm_returns_none(_branch_test_env, tmp_path):
    captured, events, srt_part = _branch_test_env
    captured["rewrite_return"] = None
    ctx = _make_ctx(tmp_path, _make_payload())
    _invoke_branch(ctx, srt_part, {"start": 0.0, "end": 8.0, "content_type_hint": "vlog"}, idx=1)
    # Fallback path: synthesizer receives ONE segment whose text == extracted SRT plain text.
    segs = captured["synth_kwargs"]["segments"]
    assert len(segs) == 1
    assert segs[0]["start"] == 0.0
    assert segs[0]["end"] == 8.0
    assert "First utterance from source" in segs[0]["text"]
    assert "Second utterance from source" in segs[0]["text"]
    assert "voice_ai_rewrite_fallback" in events


def test_ai_rewrite_clip_duration_from_seg(_branch_test_env, tmp_path):
    captured, _, srt_part = _branch_test_env
    ctx = _make_ctx(tmp_path, _make_payload())
    _invoke_branch(ctx, srt_part, {"start": 10.0, "end": 25.0, "content_type_hint": "vlog"}, idx=1)
    assert captured["rewrite_kwargs"]["clip_duration_sec"] == 15.0
    assert captured["synth_kwargs"]["clip_duration_sec"] == 15.0


def test_ai_rewrite_provider_resolved_from_payload(_branch_test_env, tmp_path):
    captured, _, srt_part = _branch_test_env
    ctx = _make_ctx(tmp_path, _make_payload(ai_provider="claude", claude_api_key="claude-key"))
    _invoke_branch(ctx, srt_part, {"start": 0.0, "end": 8.0, "content_type_hint": "vlog"}, idx=1)
    assert captured["rewrite_kwargs"]["provider"] == "claude"
    assert captured["rewrite_kwargs"]["api_key"] == "claude-key"


def test_ai_rewrite_passes_tone_from_payload(_branch_test_env, tmp_path):
    captured, _, srt_part = _branch_test_env
    ctx = _make_ctx(tmp_path, _make_payload(rewrite_tone="dramatic"))
    _invoke_branch(ctx, srt_part, {"start": 0.0, "end": 8.0, "content_type_hint": "vlog"}, idx=1)
    assert captured["rewrite_kwargs"]["tone"] == "dramatic"


def test_ai_rewrite_passes_srt_segmented_input(_branch_test_env, tmp_path):
    captured, _, srt_part = _branch_test_env
    ctx = _make_ctx(tmp_path, _make_payload())
    _invoke_branch(ctx, srt_part, {"start": 0.0, "end": 8.0, "content_type_hint": "vlog"}, idx=1)
    # srt_segmented should contain the [start - end] formatted lines.
    formatted = captured["rewrite_kwargs"]["srt_segmented"]
    assert "[0.0 - 4.0]" in formatted
    assert "[5.0 - 8.0]" in formatted
    assert "First utterance from source" in formatted


def test_ai_rewrite_appends_to_voice_part_tts_attempts(_branch_test_env, tmp_path):
    _, _, srt_part = _branch_test_env
    ctx = _make_ctx(tmp_path, _make_payload())
    _invoke_branch(ctx, srt_part, {"start": 0.0, "end": 8.0, "content_type_hint": "vlog"}, idx=3)
    assert 3 in ctx.voice_part_tts_attempts


def test_ai_rewrite_skipped_when_voice_disabled(_branch_test_env, tmp_path):
    captured, _, srt_part = _branch_test_env
    captured.pop("rewrite_kwargs", None)
    ctx = _make_ctx(tmp_path, _make_payload(voice_enabled=False))
    _invoke_branch(ctx, srt_part, {"start": 0.0, "end": 8.0, "content_type_hint": "vlog"}, idx=1)
    assert "rewrite_kwargs" not in captured


def test_ai_rewrite_skipped_when_voice_source_is_manual(_branch_test_env, tmp_path):
    captured, _, srt_part = _branch_test_env
    captured.pop("rewrite_kwargs", None)
    ctx = _make_ctx(
        tmp_path,
        _make_payload(voice_source="manual", voice_text="Manual narration text."),
    )
    _invoke_branch(ctx, srt_part, {"start": 0.0, "end": 8.0, "content_type_hint": "vlog"}, idx=1)
    assert "rewrite_kwargs" not in captured

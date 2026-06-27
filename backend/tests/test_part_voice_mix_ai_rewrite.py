"""Wiring + contract tests for the ai_rewrite branch in run_part_voice_mix.

Builds a minimal PartRenderContext, mocks _llm_rewrite_subtitle and
generate_narration_audio, and asserts the branch:
  - calls rewrite_subtitle with correct provider/duration/text;
  - feeds the REWRITTEN text into TTS on success;
  - falls back to the ORIGINAL text when rewrite returns None;
  - emits voice_ai_rewrite_started / _completed / _fallback events;
  - is skipped when voice_enabled=False or voice_source!='ai_rewrite';
  - sets target_duration_sec from (seg.end - seg.start).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.features.render.engine.stages import part_voice_mix as PVM
from app.features.render.engine.stages.part_render_context import PartRenderContext


# ── Sacred #3 contract pin — module imports the dispatcher (not raw provider) ──

def test_module_imports_llm_rewrite_dispatcher():
    """ai_rewrite branch must dispatch through app.features.render.ai.llm.rewrite,
    not through a provider directly (so fallback chain + metrics apply)."""
    assert hasattr(PVM, "_llm_rewrite_subtitle"), (
        "part_voice_mix.py must import rewrite_subtitle as _llm_rewrite_subtitle "
        "from app.features.render.ai.llm.rewrite"
    )


def test_voice_source_allowlist_accepts_ai_rewrite():
    """RenderRequest validator must accept voice_source='ai_rewrite' when
    voice_enabled=True (Sacred #2 — additive extension of allowlist)."""
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
    """Sacred #2 — new field defaults to non-active state."""
    from app.models.render import RenderRequest
    r = RenderRequest(
        url="https://example.com/v.mp4",
        source_mode="local",
        local_file_path="C:/tmp/foo.mp4",
    )
    assert r.rewrite_tone == ""


# ── Branch behavior tests ────────────────────────────────────────────────────

def _make_ctx(tmp_path: Path, payload, full_srt_text: str = "") -> PartRenderContext:
    """Build a minimal PartRenderContext sufficient to enter the ai_rewrite branch."""
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


@pytest.fixture
def _branch_test_env(monkeypatch, tmp_path):
    """Patch heavy externals + collect captured TTS calls + events.

    Returns (captured: dict, events: list, srt_path: Path) — callers
    set captured["rewrite_return"] before invoking the branch.
    """
    srt_part = tmp_path / "part_001.srt"
    srt_part.write_text(
        "1\n00:00:00,000 --> 00:00:08,000\nXin chào, đây là nội dung gốc.\n",
        encoding="utf-8",
    )
    captured: dict = {"rewrite_return": "REWRITTEN narration."}
    events: list = []

    def _spy_rewrite(**kw):
        captured["rewrite_kwargs"] = kw
        return captured["rewrite_return"]

    def _spy_tts(**kw):
        captured["tts_kwargs"] = kw
        out = tmp_path / "voice.mp3"
        out.write_bytes(b"FAKEMP3")
        return str(out)

    def _spy_emit(**kw):
        events.append(kw["event"])

    def _noop_cleanup(path, *a, **kw):
        return path

    monkeypatch.setattr(PVM, "_llm_rewrite_subtitle", _spy_rewrite)
    monkeypatch.setattr(PVM, "generate_narration_audio", _spy_tts)
    monkeypatch.setattr(PVM, "_emit_render_event", _spy_emit)
    monkeypatch.setattr(PVM, "_maybe_cleanup_narration_audio", _noop_cleanup)
    monkeypatch.setattr(PVM, "mix_narration_audio", MagicMock(return_value=None))
    monkeypatch.setattr(PVM, "mix_with_bgm", MagicMock(return_value=None))
    monkeypatch.setattr(PVM, "write_manifest", MagicMock(return_value=None))
    # _job_log shouldn't matter, but stub to keep stderr quiet.
    monkeypatch.setattr(PVM, "_job_log", lambda *a, **kw: None)
    return captured, events, srt_part


def _invoke_branch(ctx: PartRenderContext, srt_part: Path, seg: dict, idx: int):
    """Invoke run_part_voice_mix with the minimal extra plumbing."""
    final_part = ctx.work_dir / f"part_{idx:03d}_final.mp4"
    final_part.write_bytes(b"FAKEMP4")
    # The mixer is mocked — function will short-circuit there.
    return PVM.run_part_voice_mix(
        ctx=ctx,
        idx=idx,
        seg=seg,
        srt_part=srt_part,
        translated_srt_part=ctx.work_dir / "translated_missing.srt",
        final_part=final_part,
        part_manifest=MagicMock(),
    )


def test_ai_rewrite_uses_rewritten_text_when_llm_returns_string(_branch_test_env, tmp_path):
    captured, events, srt_part = _branch_test_env
    captured["rewrite_return"] = "REWRITTEN narration."
    ctx = _make_ctx(tmp_path, _make_payload())
    _invoke_branch(ctx, srt_part, {"start": 0.0, "end": 8.0, "content_type_hint": "vlog"}, idx=1)
    assert captured["tts_kwargs"]["text"] == "REWRITTEN narration."
    assert "voice_ai_rewrite_started" in events
    assert "voice_ai_rewrite_completed" in events
    assert "voice_tts_started" in events


def test_ai_rewrite_falls_back_to_original_when_llm_returns_none(_branch_test_env, tmp_path):
    captured, events, srt_part = _branch_test_env
    captured["rewrite_return"] = None
    ctx = _make_ctx(tmp_path, _make_payload())
    _invoke_branch(ctx, srt_part, {"start": 0.0, "end": 8.0, "content_type_hint": "vlog"}, idx=1)
    # Fallback uses extract_text_from_srt(srt_part) — strips timestamps + block numbers.
    assert captured["tts_kwargs"]["text"] == "Xin chào, đây là nội dung gốc."
    assert "voice_ai_rewrite_fallback" in events


def test_ai_rewrite_target_duration_from_seg(_branch_test_env, tmp_path):
    captured, _, srt_part = _branch_test_env
    ctx = _make_ctx(tmp_path, _make_payload())
    _invoke_branch(ctx, srt_part, {"start": 10.0, "end": 25.0, "content_type_hint": "vlog"}, idx=1)
    assert captured["rewrite_kwargs"]["target_duration_sec"] == 15.0


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

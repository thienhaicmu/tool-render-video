"""test_content_subtitle_style_p1_1.py — P1.1 subtitle-style fix.

Locks the two behaviours P1.1 restored:

  1. Precedence — the user's explicit UI pick (payload.subtitle_style) wins over
     the AI's plan-level suggestion; "auto"/"" hands the choice back to the AI
     (per-scene override, else plan-level). Previously the AI plan style silently
     overrode the user's dropdown choice.
  2. Vocabulary — every subtitle_style the Content Director prompt advertises is
     a REAL CapCut preset id (resolves to itself), so an AI suggestion can no
     longer collapse to the default. Guards against prompt↔resolver drift.

Precedence is verified by spying on the subtitle_style kwarg handed to
render_content_scene (FFmpeg subtitle burn is stubbed — no real render needed).
"""
from __future__ import annotations

import re
import subprocess
import uuid
from pathlib import Path

import pytest


def _ffmpeg_ok() -> bool:
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        return subprocess.run([get_ffmpeg_bin(), "-version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


_NEEDS_FFMPEG = pytest.mark.skipif(not _ffmpeg_ok(), reason="FFmpeg not available")


# ── 2. Vocabulary consistency (no FFmpeg needed) ─────────────────────────────

def test_content_prompt_subtitle_vocab_are_real_capcut_ids():
    """Every subtitle_style id the Content Director prompt advertises must be a
    real CapCut preset id (resolve_capcut_style returns it unchanged)."""
    from app.features.render.ai.llm.content_prompts import build_content_plan_prompt
    from app.features.render.engine.subtitle.generator.ass_capcut import (
        CAPCUT_PRESETS, resolve_capcut_style,
    )

    _sys, user = build_content_plan_prompt("some script", 90.0, "vi-VN", "")
    # The plan-level enum line: "subtitle_style": "a|b|c|..."
    m = re.search(r'"subtitle_style":\s*"([a-z_|]+)"', user)
    assert m, "plan-level subtitle_style enum not found in the prompt"
    ids = [s for s in m.group(1).split("|") if s]
    assert ids, "no subtitle_style ids advertised"
    for sid in ids:
        assert sid in CAPCUT_PRESETS, f"prompt advertises {sid!r} which is not a CapCut preset"
        assert resolve_capcut_style(sid) == sid, f"{sid!r} does not resolve to itself"


# ── 1. Precedence (needs FFmpeg for the concat + QA on stubbed scenes) ───────

def _make_av(path: str, dur: float = 3.0) -> None:
    from app.services.bin_paths import get_ffmpeg_bin
    subprocess.run(
        [get_ffmpeg_bin(), "-y", "-f", "lavfi", "-i", f"testsrc=size=320x568:rate=30:duration={dur}",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dur}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path],
        capture_output=True, check=True, timeout=60,
    )


@pytest.fixture
def _sandbox(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"; output_dir = tmp_path / "out"; temp_dir = tmp_path / "tmp"
    for p in (data_dir, output_dir, temp_dir):
        p.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "app.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    monkeypatch.setattr("app.core.config.DATABASE_PATH", db_path, raising=False)
    monkeypatch.setattr("app.core.config.APP_DATA_DIR", data_dir, raising=False)
    monkeypatch.setattr("app.core.config.TEMP_DIR", temp_dir, raising=False)
    monkeypatch.setattr("app.core.config.LOGS_DIR", data_dir / "logs", raising=False)
    monkeypatch.setattr(
        "app.features.render.engine.pipeline.content_pipeline.TEMP_DIR", temp_dir, raising=False,
    )
    from app.db.connection import init_db, close_thread_conn
    init_db()
    yield {"output_dir": output_dir}
    close_thread_conn()


def _plan_with_style(plan_style: str):
    from app.domain.content_plan import ContentPlan, ContentScene
    return ContentPlan(
        topic="T", tone="documentary", audience="general", language="vi-VN",
        total_target_sec=6.0, subtitle_style=plan_style, bgm_mood="epic",
        scenes=[
            ContentScene(index=0, role="hook", narration="Cau mot.", reading_speed=1.0),
            ContentScene(index=1, role="conclusion", narration="Cau hai.", reading_speed=1.0),
        ],
    )


def _run_capturing_style(_sandbox, monkeypatch, *, user_style: str, plan_style: str):
    """Run run_content with render_content_scene stubbed to record the
    subtitle_style it receives. Returns the list of captured styles."""
    from app.models.schemas import RenderRequest
    import app.features.render.engine.pipeline.content_pipeline as cp
    # CM-6: TTS + scene render moved into scene_stage (render_one_scene).
    import app.features.render.engine.stages.content.scene_stage as scene_stage

    captured: list[str] = []

    def _fake_render_scene(*, subtitle_style, out_path, **kwargs):
        captured.append(subtitle_style)
        _make_av(out_path, dur=3.0)   # real clip so concat + QA gate pass
        return True

    def _fake_synth(*, scene, job_id, out_path, **kwargs):
        _make_av_audio(out_path)
        return (out_path, 2.0)

    def _make_av_audio(path: str):
        from app.services.bin_paths import get_ffmpeg_bin
        subprocess.run(
            [get_ffmpeg_bin(), "-y", "-f", "lavfi",
             "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
             "-t", "2", "-c:a", "libmp3lame", path],
            capture_output=True, check=True, timeout=60,
        )

    monkeypatch.setattr(cp, "select_content_plan", lambda **k: _plan_with_style(plan_style))
    monkeypatch.setattr(scene_stage, "synthesize_scene_narration", _fake_synth)
    monkeypatch.setattr(scene_stage, "render_content_scene", _fake_render_scene)

    payload = RenderRequest(
        channel_code="content-p11", render_format="content", content_script="x",
        content_background_kind="color", content_background_value="#101820",
        output_dir=str(_sandbox["output_dir"] / f"p11-{uuid.uuid4().hex[:8]}"),
        aspect_ratio="9:16", output_fps=30,
        add_subtitle=True, subtitle_style=user_style, voice_enabled=False,
    )
    cp.run_content(job_id=str(uuid.uuid4()), payload=payload, resume_mode=False,
                   load_session_fn=lambda s: None, cleanup_session_fn=lambda s: None)
    return captured


@_NEEDS_FFMPEG
def test_user_pick_overrides_ai_plan_style(_sandbox, monkeypatch):
    """User chose 'capcut_box' → every scene renders with it, NOT the AI plan's
    'opus_pop'."""
    captured = _run_capturing_style(_sandbox, monkeypatch, user_style="capcut_box", plan_style="opus_pop")
    assert captured, "render_content_scene was never called"
    assert all(s == "capcut_box" for s in captured), captured


@_NEEDS_FFMPEG
def test_auto_defers_to_ai_plan_style(_sandbox, monkeypatch):
    """User left it on 'auto' → the AI plan-level style flows through to the render."""
    captured = _run_capturing_style(_sandbox, monkeypatch, user_style="auto", plan_style="karaoke_clean")
    assert captured, "render_content_scene was never called"
    assert all(s == "karaoke_clean" for s in captured), captured

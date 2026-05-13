from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch


def test_render_request_default_remotion_hook_intro_false():
    from app.models.schemas import RenderRequest

    payload = RenderRequest()

    assert payload.remotion_hook_intro is False


def test_generate_hook_intro_returns_path_when_ffmpeg_creates_file(tmp_path):
    from app.services.remotion_adapter import generate_hook_intro

    output = tmp_path / "intro.mp4"
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        output.write_bytes(b"video")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("app.services.remotion_adapter.subprocess.run", side_effect=fake_run):
        result = generate_hook_intro(
            str(output),
            aspect_ratio="9:16",
            duration_sec=1.0,
            headline_text="STOP SCROLLING",
        )

    assert result == str(output)
    cmd = captured["cmd"]
    assert "color=c=black:s=1080x1920:r=30:d=1.000" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "STOP SCROLLING" in vf
    assert "borderw=5" in vf
    assert "shadowcolor=0x000000@0.70" in vf
    assert "drawbox=" in vf
    assert "enable='between(t\\,0\\,0.18)'" in vf


def test_generate_hook_intro_uses_fallback_headline_rotation(tmp_path):
    from app.services.remotion_adapter import _FALLBACK_HEADLINES, generate_hook_intro

    output = tmp_path / "fallback.mp4"
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        output.write_bytes(b"video")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("app.services.remotion_adapter.subprocess.run", side_effect=fake_run):
        result = generate_hook_intro(
            str(output),
            aspect_ratio="1:1",
            duration_sec=1.0,
            headline_text=None,
        )

    assert result == str(output)
    assert "color=c=black:s=1080x1080:r=30:d=1.000" in captured["cmd"]
    vf = captured["cmd"][captured["cmd"].index("-vf") + 1]
    assert any(headline.replace("'", "\\'") in vf for headline in _FALLBACK_HEADLINES)


def test_generate_hook_intro_failure_returns_none(tmp_path):
    from app.services.remotion_adapter import generate_hook_intro

    output = tmp_path / "intro.mp4"
    with patch("app.services.remotion_adapter.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 1, "", "drawtext failed")
        result = generate_hook_intro(str(output), aspect_ratio="3:4", duration_sec=1.0)

    assert result is None
    assert not output.exists()


def test_remotion_disabled_does_not_touch_rendered_clip(tmp_path):
    from app.models.schemas import RenderRequest
    from app.orchestration.render_pipeline import _maybe_prepend_remotion_hook_intro

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"original")
    payload = RenderRequest(remotion_hook_intro=False)

    with patch("app.orchestration.render_pipeline.generate_hook_intro") as generate:
        result = _maybe_prepend_remotion_hook_intro(
            clip,
            payload,
            effective_channel="test",
            job_id="job123",
            part_no=1,
        )

    generate.assert_not_called()
    assert result == 0.0
    assert clip.read_bytes() == b"original"


def test_remotion_intro_generation_failure_preserves_original_clip(tmp_path):
    from app.models.schemas import RenderRequest
    from app.orchestration.render_pipeline import _maybe_prepend_remotion_hook_intro

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"original")
    payload = RenderRequest(remotion_hook_intro=True)

    with patch("app.orchestration.render_pipeline._job_log"), \
         patch("app.orchestration.render_pipeline.generate_hook_intro", return_value=None), \
         patch("app.orchestration.render_pipeline.prepend_intro_clip") as prepend:
        result = _maybe_prepend_remotion_hook_intro(
            clip,
            payload,
            effective_channel="test",
            job_id="job123",
            part_no=1,
        )

    prepend.assert_not_called()
    assert result == 0.0
    assert clip.read_bytes() == b"original"


def test_remotion_concat_failure_preserves_original_clip(tmp_path):
    from app.models.schemas import RenderRequest
    from app.orchestration.render_pipeline import _maybe_prepend_remotion_hook_intro

    clip = tmp_path / "clip.mp4"
    intro = tmp_path / "intro.mp4"
    clip.write_bytes(b"original")
    intro.write_bytes(b"intro")
    payload = RenderRequest(remotion_hook_intro=True)

    with patch("app.orchestration.render_pipeline._job_log"), \
         patch("app.orchestration.render_pipeline.generate_hook_intro", return_value=str(intro)), \
         patch("app.orchestration.render_pipeline.prepend_intro_clip", return_value=None):
        result = _maybe_prepend_remotion_hook_intro(
            clip,
            payload,
            effective_channel="test",
            job_id="job123",
            part_no=1,
        )

    assert result == 0.0
    assert clip.read_bytes() == b"original"


def test_remotion_success_replaces_clip_with_concatenated_output(tmp_path):
    from app.models.schemas import RenderRequest
    from app.orchestration.render_pipeline import _maybe_prepend_remotion_hook_intro

    clip = tmp_path / "clip.mp4"
    intro = tmp_path / "intro.mp4"
    merged = tmp_path / "merged.mp4"
    clip.write_bytes(b"original")
    intro.write_bytes(b"intro")
    merged.write_bytes(b"merged")
    payload = RenderRequest(remotion_hook_intro=True)

    with patch("app.orchestration.render_pipeline._job_log"), \
         patch("app.orchestration.render_pipeline.generate_hook_intro", return_value=str(intro)), \
         patch("app.orchestration.render_pipeline.prepend_intro_clip", return_value=str(merged)):
        result = _maybe_prepend_remotion_hook_intro(
            clip,
            payload,
            effective_channel="test",
            job_id="job123",
            part_no=1,
        )

    assert result == 1.0
    assert clip.read_bytes() == b"merged"
    assert not merged.exists()

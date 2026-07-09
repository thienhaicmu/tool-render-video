"""Story-to-Video P4 — /api/story/narration/preview router tests (offline)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.features.render.engine.audio import tts as tts_mod
from app.features.story.router import NarrationPreviewRequest, narration_preview


def test_preview_422_on_empty_text():
    with pytest.raises(HTTPException) as ei:
        narration_preview(NarrationPreviewRequest(text="  "))
    assert ei.value.status_code == 422


def test_preview_success_writes_audio_and_reports_engine(monkeypatch):
    def fake_gen(**kw):
        Path(kw["output_path"]).write_bytes(b"ID3fake-mp3-bytes")
        return kw["output_path"]
    monkeypatch.setattr(tts_mod, "generate_narration_audio", fake_gen)
    out = narration_preview(NarrationPreviewRequest(text="Hàn Phong bước đi.", language="en"))
    assert out["engine"] == "elevenlabs"      # EN → ElevenLabs
    assert out["url"].endswith(out["token"])
    assert "duration_sec" in out


def test_preview_vietnamese_uses_gemini(monkeypatch):
    monkeypatch.setattr(tts_mod, "generate_narration_audio",
                        lambda **kw: (Path(kw["output_path"]).write_bytes(b"x"), kw["output_path"])[1])
    out = narration_preview(NarrationPreviewRequest(text="Đêm lạnh.", language="vi"))
    assert out["engine"] == "gemini"


def test_preview_502_when_tts_raises(monkeypatch):
    def boom(**kw):
        raise RuntimeError("tts down")
    monkeypatch.setattr(tts_mod, "generate_narration_audio", boom)
    with pytest.raises(HTTPException) as ei:
        narration_preview(NarrationPreviewRequest(text="hi", language="en"))
    assert ei.value.status_code == 502

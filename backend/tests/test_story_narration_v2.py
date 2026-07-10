"""Story Mode v2 — B6 synthesize_timeline: fill render.beat_audio (offline mock)."""
from __future__ import annotations

from pathlib import Path

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, Beat
from app.features.render.engine.audio import story_narration as sn


def _plan():
    p = StoryPlan(language="vi", characters=[CharacterDef(id="han", name="H", voice_gender="male")],
                  timeline=[
                      Beat(id="b1", narration="Đêm lạnh.", speaker_id="", visual_id="v1"),
                      Beat(id="b2", narration="Hàn Phong bước.", speaker_id="han", visual_id="v1"),
                      Beat(id="b3", narration="", hold_sec=1.5, visual_id="v1"),   # silent hold
                  ])
    p.render.voices = {"": ["gemini", "vi-A"], "han": ["gemini", "vi-B"]}
    return p


def _mock(monkeypatch, capture):
    def fake_gen(**kw):
        capture.append(kw)
        Path(kw["output_path"]).write_bytes(b"ID3fake")
        return kw["output_path"]
    monkeypatch.setattr(sn, "generate_narration_audio", fake_gen)
    monkeypatch.setattr(sn, "probe_audio_duration", lambda p: 2.5)


def test_fills_beat_audio(monkeypatch, tmp_path):
    cap = []
    _mock(monkeypatch, cap)
    p = _plan()
    sn.synthesize_timeline(p, job_id="job", audio_dir=str(tmp_path))
    assert p.render.beat_audio["b1"].dur == 2.5 and p.render.beat_audio["b1"].path
    assert p.render.beat_audio["b2"].dur == 2.5
    # silent hold → dur = hold_sec, no path.
    assert p.render.beat_audio["b3"].path == "" and p.render.beat_audio["b3"].dur == 1.5


def test_uses_cast_voice_and_engine(monkeypatch, tmp_path):
    cap = []
    _mock(monkeypatch, cap)
    sn.synthesize_timeline(_plan(), job_id="job", audio_dir=str(tmp_path))
    # b1 narrator → voice vi-A; b2 han → voice vi-B; engine gemini; language locale vi-VN.
    by_text = {c["text"]: c for c in cap}
    assert by_text["Đêm lạnh."]["voice_id"] == "vi-A"
    assert by_text["Hàn Phong bước."]["voice_id"] == "vi-B"
    assert all(c["tts_engine"] == "gemini" and c["language"] == "vi-VN" for c in cap)


def test_tts_failure_empty_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(sn, "generate_narration_audio", lambda **kw: None)  # TTS fails
    monkeypatch.setattr(sn, "probe_audio_duration", lambda p: 0.0)
    p = _plan()
    sn.synthesize_timeline(p, job_id="job", audio_dir=str(tmp_path))
    assert p.render.beat_audio["b1"].path == "" and p.render.beat_audio["b1"].dur == 0.0


def test_never_raises(monkeypatch, tmp_path):
    def boom(**kw):
        raise RuntimeError("tts down")
    monkeypatch.setattr(sn, "generate_narration_audio", boom)
    monkeypatch.setattr(sn, "probe_audio_duration", lambda p: 0.0)
    p = _plan()
    sn.synthesize_timeline(p, job_id="job", audio_dir=str(tmp_path))   # must not raise
    assert p.render.beat_audio["b1"].path == ""

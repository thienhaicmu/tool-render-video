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


def test_on_progress_streams_to_total(monkeypatch, tmp_path):
    # P0: on_progress fires per beat and ends at (total, total) — the monitor moves
    # during narration instead of freezing. Holds for both parallel + serial paths.
    for workers in ("4", "1"):
        monkeypatch.setenv("STORY_TTS_WORKERS", workers)
        _mock(monkeypatch, [])
        p = _plan()                                   # 3 beats (2 spoken + 1 silent hold)
        seen = []
        sn.synthesize_timeline(p, job_id="job", audio_dir=str(tmp_path),
                               on_progress=lambda done, total: seen.append((done, total)))
        assert seen, f"no progress emitted (workers={workers})"
        assert all(t == 3 for _, t in seen)           # total is stable
        assert seen[-1][0] == 3                        # ends fully done
        assert [d for d, _ in seen] == sorted(d for d, _ in seen)  # monotonic
        # every beat still filled regardless of completion order
        assert set(p.render.beat_audio) == {"b1", "b2", "b3"}


def _multiline_plan():
    from app.domain.story_plan_v2 import Line
    p = StoryPlan(language="vi",
                  characters=[CharacterDef(id="han", voice_gender="male"),
                              CharacterDef(id="lan", voice_gender="female")],
                  timeline=[Beat(id="b1", visual_id="v1", lines=[
                      Line("", "Ngày xưa"), Line("han", "Ta là Hàn", "angry"),
                      Line("lan", "Còn ta Lan", "sad")])])
    p.render.voices = {"": ["gemini", "vi-N"], "han": ["gemini", "vi-H"], "lan": ["gemini", "vi-L"]}
    return p


def test_dialogue_mode_synthesizes_each_line_voice(monkeypatch, tmp_path):
    # P2 — dialogue beat with 3 distinct speakers → one TTS call per line in THAT
    # speaker's voice, concatenated into one beat_audio.
    cap = []
    _mock(monkeypatch, cap)
    import app.features.render.engine.audio.timed_narration as tn
    monkeypatch.setattr(tn, "_concat_with_pads",
                        lambda offs, total, out: (Path(out).write_bytes(b"ID3joined") or True))
    p = _multiline_plan()
    sn.synthesize_timeline(p, job_id="job", audio_dir=str(tmp_path), voice_mode="dialogue")
    assert sorted(c["voice_id"] for c in cap) == ["vi-H", "vi-L", "vi-N"]   # per-line voices
    assert p.render.beat_audio["b1"].path.endswith("beat_b1.mp3")          # concatenated beat clip


def test_narrator_mode_joins_lines_into_one_call(monkeypatch, tmp_path):
    # P2 — narrator mode: ONE call, narrator voice, all line texts joined (kể chuyện).
    cap = []
    _mock(monkeypatch, cap)
    p = _multiline_plan()
    sn.synthesize_timeline(p, job_id="job", audio_dir=str(tmp_path), voice_mode="narrator")
    assert len(cap) == 1 and cap[0]["voice_id"] == "vi-N"
    assert "Hàn" in cap[0]["text"] and "Lan" in cap[0]["text"]


def test_parallel_matches_serial_output(monkeypatch, tmp_path):
    # Parallel (workers=4) and serial (workers=1) produce identical beat_audio.
    def run(workers):
        monkeypatch.setenv("STORY_TTS_WORKERS", workers)
        _mock(monkeypatch, [])
        p = _plan()
        sn.synthesize_timeline(p, job_id="job", audio_dir=str(tmp_path))
        return {k: (v.path.endswith(f"beat_{k}.mp3") if v.path else "", round(v.dur, 2))
                for k, v in p.render.beat_audio.items()}
    assert run("4") == run("1")

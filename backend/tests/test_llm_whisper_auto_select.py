"""Pin logic auto-select model Whisper cho full SRT (llm_pipeline).

Bất biến chất lượng: từ khi phụ đề per-part slice từ full SRT, hạ model
chỉ được phép khi job KHÔNG có consumer chất lượng (phụ đề tắt VÀ voice
tắt). Job bật phụ đề/voice phải giữ nguyên model — kể cả large-v3 từ
profile — vì model đó quyết định chữ phụ đề người xem đọc.
"""
from types import SimpleNamespace

from app.features.render.engine.pipeline.llm_pipeline import _llm_whisper_auto_select


def _payload(subs: bool, voice: bool = False):
    return SimpleNamespace(add_subtitle=subs, voice_enabled=voice)


def test_short_video_no_consumers_downgrades_to_tiny(monkeypatch):
    monkeypatch.delenv("LLM_WHISPER_AUTO_SELECT", raising=False)
    assert _llm_whisper_auto_select("base", 117.0, _payload(subs=False)) == "tiny"
    # Model từ profile (large-v3) cũng được hạ khi không consumer — đây là
    # ca lãng phí 210s mà smoke 2026-07 phát hiện.
    assert _llm_whisper_auto_select("large-v3", 117.0, _payload(subs=False)) == "tiny"


def test_subtitles_on_keeps_model(monkeypatch):
    # Vá lỗ rò chất lượng cũ: bản trước hạ base→tiny bất kể phụ đề.
    monkeypatch.delenv("LLM_WHISPER_AUTO_SELECT", raising=False)
    assert _llm_whisper_auto_select("base", 117.0, _payload(subs=True)) == "base"
    assert _llm_whisper_auto_select("large-v3", 117.0, _payload(subs=True)) == "large-v3"


def test_voice_on_keeps_model(monkeypatch):
    monkeypatch.delenv("LLM_WHISPER_AUTO_SELECT", raising=False)
    assert _llm_whisper_auto_select("base", 117.0, _payload(subs=False, voice=True)) == "base"


def test_long_video_keeps_model(monkeypatch):
    monkeypatch.delenv("LLM_WHISPER_AUTO_SELECT", raising=False)
    assert _llm_whisper_auto_select("base", 600.0, _payload(subs=False)) == "base"


def test_kill_switch_disables_auto_select(monkeypatch):
    monkeypatch.setenv("LLM_WHISPER_AUTO_SELECT", "0")
    assert _llm_whisper_auto_select("base", 117.0, _payload(subs=False)) == "base"


def test_zero_duration_keeps_model(monkeypatch):
    monkeypatch.delenv("LLM_WHISPER_AUTO_SELECT", raising=False)
    assert _llm_whisper_auto_select("base", 0.0, _payload(subs=False)) == "base"

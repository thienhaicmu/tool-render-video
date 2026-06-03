"""P2 smoke — pipeline_narration.run_manual_voice_tts signature + skip-path.

Per Track D D2 audit (followup_7), orchestration/pipeline_narration.py
has zero direct test consumers. run_manual_voice_tts is conditional
(only fires when voice_enabled=True AND voice_source='manual'). A
kwarg drift would silently skip narration without raising.

See docs/review/AUDIT_2026-06-02_followup_10.md for closure record.
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock


VOICE_TTS_PARAMS = {
    "payload", "job_id", "effective_channel",
    "current_stage", "current_progress", "recovery_notes",
}


class TestPipelineNarrationSurface:
    """run_manual_voice_tts signature + skip-path conformance."""

    def test_run_manual_voice_tts_signature(self):
        from app.orchestration.pipeline_narration import run_manual_voice_tts
        sig = inspect.signature(run_manual_voice_tts)
        params = set(sig.parameters.keys())
        missing = VOICE_TTS_PARAMS - params
        assert not missing, (
            f"run_manual_voice_tts missing expected params: {missing}."
        )

    def test_run_manual_voice_tts_is_keyword_only(self):
        from app.orchestration.pipeline_narration import run_manual_voice_tts
        sig = inspect.signature(run_manual_voice_tts)
        for name, param in sig.parameters.items():
            assert param.kind == inspect.Parameter.KEYWORD_ONLY

    def test_returns_none_false_when_voice_disabled(self):
        """When voice_enabled=False, returns (None, False) immediately
        without invoking TTS. Guards against the early-return being
        removed in a future refactor."""
        from app.orchestration.pipeline_narration import run_manual_voice_tts

        payload = MagicMock()
        payload.voice_enabled = False
        payload.voice_source = "manual"

        result = run_manual_voice_tts(
            payload=payload, job_id="j", effective_channel="manual",
            current_stage="render", current_progress=10,
            recovery_notes=[],
        )
        assert result == (None, False), (
            f"Expected (None, False) for disabled voice, got {result!r}."
        )

    def test_returns_none_false_when_voice_source_is_subtitle(self):
        """When voice_source != 'manual' (e.g., 'subtitle'), the manual
        path is skipped. Returns (None, False) — the subtitle-source
        voice block in part_voice_mix.py handles that case instead."""
        from app.orchestration.pipeline_narration import run_manual_voice_tts

        payload = MagicMock()
        payload.voice_enabled = True
        payload.voice_source = "subtitle"  # NOT manual

        result = run_manual_voice_tts(
            payload=payload, job_id="j", effective_channel="manual",
            current_stage="render", current_progress=10,
            recovery_notes=[],
        )
        assert result == (None, False)

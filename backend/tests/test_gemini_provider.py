"""Smoke tests for the Gemini LLM provider.

These tests use mocks — they do NOT call the Gemini API.
Live API tests would burn quota and require a real key in CI.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestGeminiProvider:
    def test_returns_none_when_api_key_missing(self):
        from app.ai.llm.gemini_provider import select_segments
        result = select_segments(
            srt_content="1\n00:00:10,000 --> 00:00:40,000\nHello world\n",
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="",
        )
        assert result is None

    def test_returns_none_when_transcript_empty(self):
        from app.ai.llm.gemini_provider import select_segments
        result = select_segments(
            srt_content="",
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="fake-key",
        )
        assert result is None

    def test_parses_valid_gemini_json_response(self):
        from app.ai.llm import gemini_provider
        fake_text = json.dumps({
            "segments": [
                {"start": 10, "end": 40, "score": 0.9, "clip_name": "A",
                 "title": "T", "reason": "R"},
                {"start": 50, "end": 90, "score": 0.8, "clip_name": "B",
                 "title": "T", "reason": "R"},
            ]
        })
        mock_resp = MagicMock()
        mock_resp.text = fake_text
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp

        with patch.object(gemini_provider, "_GENAI_SDK", True), \
             patch.object(gemini_provider, "_genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = gemini_provider.select_segments(
                srt_content="1\n00:00:10,000 --> 00:00:40,000\nhi\n",
                output_count=2, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is not None
        assert len(result) == 2
        assert result[0].clip_name == "A"

    def test_returns_none_when_api_call_raises(self):
        from app.ai.llm import gemini_provider
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("network down")

        with patch.object(gemini_provider, "_GENAI_SDK", True), \
             patch.object(gemini_provider, "_genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = gemini_provider.select_segments(
                srt_content="1\n00:00:10,000 --> 00:00:40,000\nhi\n",
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is None


class TestLLMDispatcher:
    def test_dispatches_to_groq_by_default(self):
        from app.ai import llm
        with patch.object(llm, "logger"):
            with patch("app.ai.analysis.groq.select_segments", return_value=None) as mock_groq:
                llm.select_segments(
                    provider="groq",
                    srt_content="x", output_count=1, min_sec=15, max_sec=60,
                    video_duration=300, api_key="k",
                )
                assert mock_groq.called

    def test_dispatches_to_gemini(self):
        from app.ai import llm
        with patch("app.ai.llm.gemini_provider.select_segments", return_value=None) as mock_gem:
            llm.select_segments(
                provider="gemini",
                srt_content="x", output_count=1, min_sec=15, max_sec=60,
                video_duration=300, api_key="k",
            )
            assert mock_gem.called

    def test_unknown_provider_returns_none(self):
        from app.ai import llm
        result = llm.select_segments(
            provider="totally-fake-provider",
            srt_content="x", output_count=1, min_sec=15, max_sec=60,
            video_duration=300, api_key="k",
        )
        assert result is None

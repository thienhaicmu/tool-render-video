"""Smoke tests for the OpenAI LLM provider (mocked — no API calls)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


class TestOpenAIProvider:
    def test_returns_none_when_api_key_missing(self):
        from app.ai.llm.openai_provider import select_segments
        result = select_segments(
            srt_content="1\n00:00:10,000 --> 00:00:40,000\nHello\n",
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="",
        )
        assert result is None

    def test_returns_none_when_transcript_empty(self):
        from app.ai.llm.openai_provider import select_segments
        result = select_segments(
            srt_content="",
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="sk-fake",
        )
        assert result is None

    def test_parses_valid_openai_json_response(self):
        from app.ai.llm import openai_provider
        fake_text = json.dumps({
            "segments": [
                {"start": 10, "end": 40, "score": 0.9, "clip_name": "A",
                 "title": "T", "reason": "R"},
            ]
        })
        mock_msg = MagicMock(); mock_msg.content = fake_text
        mock_choice = MagicMock(); mock_choice.message = mock_msg
        mock_resp = MagicMock(); mock_resp.choices = [mock_choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp

        with patch.object(openai_provider, "_OPENAI_SDK", True), \
             patch.object(openai_provider, "_openai") as mock_oai:
            mock_oai.OpenAI.return_value = mock_client
            result = openai_provider.select_segments(
                srt_content="1\n00:00:10,000 --> 00:00:40,000\nhi\n",
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="sk-fake",
            )
        assert result is not None
        assert len(result) == 1
        assert result[0].clip_name == "A"

    def test_returns_none_when_api_call_raises(self):
        from app.ai.llm import openai_provider
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("rate limited")

        with patch.object(openai_provider, "_OPENAI_SDK", True), \
             patch.object(openai_provider, "_openai") as mock_oai:
            mock_oai.OpenAI.return_value = mock_client
            result = openai_provider.select_segments(
                srt_content="1\n00:00:10,000 --> 00:00:40,000\nhi\n",
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="sk-fake",
            )
        assert result is None

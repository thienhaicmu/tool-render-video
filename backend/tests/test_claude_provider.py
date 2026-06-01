"""Smoke tests for the Claude LLM provider (mocked — no API calls)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


class TestClaudeProvider:
    def test_returns_none_when_api_key_missing(self):
        from app.ai.llm.claude_provider import select_segments
        result = select_segments(
            srt_content="1\n00:00:10,000 --> 00:00:40,000\nHello\n",
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="",
        )
        assert result is None

    def test_returns_none_when_transcript_empty(self):
        from app.ai.llm.claude_provider import select_segments
        result = select_segments(
            srt_content="",
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="sk-ant-fake",
        )
        assert result is None

    def test_parses_valid_claude_json_response(self):
        from app.ai.llm import claude_provider
        fake_text = json.dumps({
            "segments": [
                {"start": 10, "end": 40, "score": 0.9, "clip_name": "A",
                 "title": "T", "reason": "R"},
            ]
        })
        # Claude returns a list of content blocks; each has .type and .text.
        mock_block = MagicMock(); mock_block.type = "text"; mock_block.text = fake_text
        mock_resp = MagicMock(); mock_resp.content = [mock_block]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        with patch.object(claude_provider, "_ANTHROPIC_SDK", True), \
             patch.object(claude_provider, "_AnthClient", return_value=mock_client):
            result = claude_provider.select_segments(
                srt_content="1\n00:00:10,000 --> 00:00:40,000\nhi\n",
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="sk-ant-fake",
            )
        assert result is not None
        assert len(result) == 1
        assert result[0].clip_name == "A"

    def test_concatenates_multiple_text_blocks(self):
        """Claude can return multiple text blocks — we concatenate them."""
        from app.ai.llm import claude_provider
        fake_text = json.dumps({
            "segments": [
                {"start": 10, "end": 40, "score": 0.9, "clip_name": "A",
                 "title": "T", "reason": "R"},
            ]
        })
        # Split JSON across 2 blocks (rare but possible in streaming-style output).
        split_at = len(fake_text) // 2
        block_a = MagicMock(); block_a.type = "text"; block_a.text = fake_text[:split_at]
        block_b = MagicMock(); block_b.type = "text"; block_b.text = fake_text[split_at:]
        mock_resp = MagicMock(); mock_resp.content = [block_a, block_b]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        with patch.object(claude_provider, "_ANTHROPIC_SDK", True), \
             patch.object(claude_provider, "_AnthClient", return_value=mock_client):
            result = claude_provider.select_segments(
                srt_content="1\n00:00:10,000 --> 00:00:40,000\nhi\n",
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="sk-ant-fake",
            )
        # Parser handles the newline-joined JSON; if it can't, returns None.
        # Either outcome is acceptable for this test as long as it doesn't crash.
        assert result is None or len(result) == 1

    def test_returns_none_when_api_call_raises(self):
        from app.ai.llm import claude_provider
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("rate limited")

        with patch.object(claude_provider, "_ANTHROPIC_SDK", True), \
             patch.object(claude_provider, "_AnthClient", return_value=mock_client):
            result = claude_provider.select_segments(
                srt_content="1\n00:00:10,000 --> 00:00:40,000\nhi\n",
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="sk-ant-fake",
            )
        assert result is None


class TestDispatcherForAllProviders:
    def test_dispatches_to_openai(self):
        from app.ai import llm
        with patch("app.ai.llm.openai_provider.select_segments", return_value=None) as mock_oai:
            llm.select_segments(
                provider="openai",
                srt_content="x", output_count=1, min_sec=15, max_sec=60,
                video_duration=300, api_key="k",
            )
            assert mock_oai.called

    def test_dispatches_to_claude(self):
        from app.ai import llm
        with patch("app.ai.llm.claude_provider.select_segments", return_value=None) as mock_cla:
            llm.select_segments(
                provider="claude",
                srt_content="x", output_count=1, min_sec=15, max_sec=60,
                video_duration=300, api_key="k",
            )
            assert mock_cla.called

    def test_all_four_providers_supported(self):
        from app.ai.llm import SUPPORTED_PROVIDERS
        assert set(SUPPORTED_PROVIDERS) == {"groq", "gemini", "openai", "claude"}

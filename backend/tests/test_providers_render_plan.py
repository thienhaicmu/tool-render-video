"""
Sprint 4.C — pin the dual-mode `select_render_plan` contract on each
provider plus the dispatcher.

These tests are SDK-mocked — no real Gemini / Claude / OpenAI calls
happen. Each provider's `_call_*` helper is replaced via patch so we
exercise the prompt-builder + parser orchestration without burning
quota.

Pinned behaviour:
- empty api_key / empty SRT / missing SDK → returns None (matches the
  legacy select_segments early-exit contract)
- valid native RenderPlan JSON → parsed into a RenderPlan dataclass
  (Sprint 4.A parser end-to-end)
- valid legacy {"segments":[...]} JSON → parsed into a RenderPlan
  (parser absorbs the legacy shape; providers don't care)
- API call raising → returns None (Sacred Contract #3 — never raises)
- dispatcher routes by provider name + falls back to gemini for
  unknown providers + forwards editorial_hint through to the impl
"""
import json
from unittest import mock
from unittest.mock import MagicMock, patch


_SAMPLE_SRT = "1\n00:00:10,000 --> 00:00:40,000\nHello world\n"


def _render_plan_native_json() -> str:
    """A native-shape RenderPlan JSON the parser should accept."""
    return json.dumps({
        "clips": [
            {"start": 10, "end": 40, "score": 0.9, "clip_name": "A",
             "title": "T", "reason": "R", "viral_score": 0.88, "hook_score": 0.9},
            {"start": 50, "end": 90, "score": 0.8, "clip_name": "B",
             "title": "T", "reason": "R", "viral_score": 0.75},
        ],
        "subtitle_policy": {"style": "viral", "market": "vn", "emphasis_pass": False},
        "camera_strategy": {"motion_aware_crop": True, "reframe_mode": "track"},
        "audio_plan": {"voice_enabled": False, "bgm_enabled": False},
        "overlays": [],
    })


# ── Gemini provider ──────────────────────────────────────────────────────


class TestGeminiSelectRenderPlan:
    def test_returns_none_when_api_key_missing(self):
        from app.ai.llm.gemini_provider import select_render_plan
        result = select_render_plan(
            srt_content=_SAMPLE_SRT,
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="",
        )
        assert result is None

    def test_returns_none_when_transcript_empty(self):
        from app.ai.llm.gemini_provider import select_render_plan
        result = select_render_plan(
            srt_content="",
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="fake-key",
        )
        assert result is None

    def test_returns_none_when_sdk_absent(self):
        from app.ai.llm import gemini_provider
        with patch.object(gemini_provider, "_GENAI_SDK", False):
            result = gemini_provider.select_render_plan(
                srt_content=_SAMPLE_SRT,
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is None

    def test_parses_native_render_plan_response(self):
        from app.ai.llm import gemini_provider
        mock_resp = MagicMock()
        mock_resp.text = _render_plan_native_json()
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp

        with patch.object(gemini_provider, "_GENAI_SDK", True), \
             patch.object(gemini_provider, "_genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = gemini_provider.select_render_plan(
                srt_content=_SAMPLE_SRT,
                output_count=2, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is not None
        assert len(result.clips) == 2
        assert result.subtitle_policy.style == "viral"
        assert result.camera_strategy.motion_aware_crop is True

    def test_parses_legacy_segments_response_into_render_plan(self):
        """Sprint 4.A parser absorbs legacy {"segments":[...]} payloads.
        Providers don't need to know which shape the LLM picked."""
        from app.ai.llm import gemini_provider
        legacy = json.dumps({
            "segments": [
                {"start": 10, "end": 40, "score": 0.9, "clip_name": "A"},
            ]
        })
        mock_resp = MagicMock()
        mock_resp.text = legacy
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp

        with patch.object(gemini_provider, "_GENAI_SDK", True), \
             patch.object(gemini_provider, "_genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = gemini_provider.select_render_plan(
                srt_content=_SAMPLE_SRT,
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is not None
        assert len(result.clips) == 1
        assert result.clips[0].clip_name == "A"

    def test_returns_none_when_api_call_raises(self):
        from app.ai.llm import gemini_provider
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("network down")

        with patch.object(gemini_provider, "_GENAI_SDK", True), \
             patch.object(gemini_provider, "_genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = gemini_provider.select_render_plan(
                srt_content=_SAMPLE_SRT,
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is None


# ── Claude provider ──────────────────────────────────────────────────────


class TestClaudeSelectRenderPlan:
    def test_returns_none_when_api_key_missing(self):
        from app.ai.llm.claude_provider import select_render_plan
        result = select_render_plan(
            srt_content=_SAMPLE_SRT,
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="",
        )
        assert result is None

    def test_returns_none_when_transcript_empty(self):
        from app.ai.llm.claude_provider import select_render_plan
        result = select_render_plan(
            srt_content="",
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="fake-key",
        )
        assert result is None

    def test_returns_none_when_sdk_absent(self):
        from app.ai.llm import claude_provider
        with patch.object(claude_provider, "_ANTHROPIC_SDK", False):
            result = claude_provider.select_render_plan(
                srt_content=_SAMPLE_SRT,
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is None

    def test_parses_native_render_plan_response(self):
        from app.ai.llm import claude_provider
        # Claude returns content blocks (block.type == "text", block.text == ...).
        block = MagicMock()
        block.type = "text"
        block.text = _render_plan_native_json()
        mock_resp = MagicMock()
        mock_resp.content = [block]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        with patch.object(claude_provider, "_ANTHROPIC_SDK", True), \
             patch.object(claude_provider, "_AnthClient") as mock_anth:
            mock_anth.return_value = mock_client
            result = claude_provider.select_render_plan(
                srt_content=_SAMPLE_SRT,
                output_count=2, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is not None
        assert len(result.clips) == 2
        assert result.subtitle_policy.style == "viral"

    def test_returns_none_when_api_call_raises(self):
        from app.ai.llm import claude_provider
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("network down")

        with patch.object(claude_provider, "_ANTHROPIC_SDK", True), \
             patch.object(claude_provider, "_AnthClient") as mock_anth:
            mock_anth.return_value = mock_client
            result = claude_provider.select_render_plan(
                srt_content=_SAMPLE_SRT,
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is None


# ── OpenAI provider ──────────────────────────────────────────────────────


class TestOpenAISelectRenderPlan:
    def test_returns_none_when_api_key_missing(self):
        from app.ai.llm.openai_provider import select_render_plan
        result = select_render_plan(
            srt_content=_SAMPLE_SRT,
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="",
        )
        assert result is None

    def test_returns_none_when_transcript_empty(self):
        from app.ai.llm.openai_provider import select_render_plan
        result = select_render_plan(
            srt_content="",
            output_count=1, min_sec=15, max_sec=60, video_duration=300,
            api_key="fake-key",
        )
        assert result is None

    def test_returns_none_when_sdk_absent(self):
        from app.ai.llm import openai_provider
        with patch.object(openai_provider, "_OPENAI_SDK", False):
            result = openai_provider.select_render_plan(
                srt_content=_SAMPLE_SRT,
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is None

    def test_parses_native_render_plan_response(self):
        from app.ai.llm import openai_provider
        # OpenAI Chat Completions response: choices[0].message.content
        choice = MagicMock()
        choice.message.content = _render_plan_native_json()
        mock_resp = MagicMock()
        mock_resp.choices = [choice]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp

        with patch.object(openai_provider, "_OPENAI_SDK", True), \
             patch.object(openai_provider, "_openai") as mock_oai:
            mock_oai.OpenAI.return_value = mock_client
            result = openai_provider.select_render_plan(
                srt_content=_SAMPLE_SRT,
                output_count=2, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is not None
        assert len(result.clips) == 2

    def test_returns_none_when_api_call_raises(self):
        from app.ai.llm import openai_provider
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("network down")

        with patch.object(openai_provider, "_OPENAI_SDK", True), \
             patch.object(openai_provider, "_openai") as mock_oai:
            mock_oai.OpenAI.return_value = mock_client
            result = openai_provider.select_render_plan(
                srt_content=_SAMPLE_SRT,
                output_count=1, min_sec=15, max_sec=60, video_duration=300,
                api_key="fake-key",
            )
        assert result is None


# ── Dispatcher ───────────────────────────────────────────────────────────


class TestDispatcherSelectRenderPlan:
    def test_dispatches_to_gemini_by_default(self):
        from app.ai import llm
        with patch("app.ai.llm.gemini_provider.select_render_plan", return_value=None) as m:
            llm.select_render_plan(
                srt_content="x", output_count=1, min_sec=15, max_sec=60,
                video_duration=300, api_key="k",
            )
            assert m.called

    def test_dispatches_to_gemini_explicit(self):
        from app.ai import llm
        with patch("app.ai.llm.gemini_provider.select_render_plan", return_value=None) as m:
            llm.select_render_plan(
                provider="gemini",
                srt_content="x", output_count=1, min_sec=15, max_sec=60,
                video_duration=300, api_key="k",
            )
            assert m.called

    def test_dispatches_to_claude(self):
        from app.ai import llm
        with patch("app.ai.llm.claude_provider.select_render_plan", return_value=None) as m:
            llm.select_render_plan(
                provider="claude",
                srt_content="x", output_count=1, min_sec=15, max_sec=60,
                video_duration=300, api_key="k",
            )
            assert m.called

    def test_dispatches_to_openai(self):
        from app.ai import llm
        with patch("app.ai.llm.openai_provider.select_render_plan", return_value=None) as m:
            llm.select_render_plan(
                provider="openai",
                srt_content="x", output_count=1, min_sec=15, max_sec=60,
                video_duration=300, api_key="k",
            )
            assert m.called

    def test_unknown_provider_falls_back_to_gemini(self):
        from app.ai import llm
        with patch("app.ai.llm.gemini_provider.select_render_plan", return_value=None) as m:
            result = llm.select_render_plan(
                provider="totally-fake-provider",
                srt_content="x", output_count=1, min_sec=15, max_sec=60,
                video_duration=300, api_key="k",
            )
            assert m.called
            assert result is None

    def test_editorial_hint_forwarded(self):
        """Sprint 3 wired CreatorContext into editorial_hint; the
        dispatcher must forward that string verbatim to the provider
        impl so Sprint 4.D doesn't need a second parameter for it."""
        from app.ai import llm
        with patch("app.ai.llm.gemini_provider.select_render_plan", return_value=None) as m:
            llm.select_render_plan(
                provider="gemini",
                srt_content="x", output_count=1, min_sec=15, max_sec=60,
                video_duration=300, api_key="k",
                editorial_hint="Channel: K1 | Brand voice: authentic",
            )
            assert m.called
            kwargs = m.call_args.kwargs
            assert kwargs.get("editorial_hint") == "Channel: K1 | Brand voice: authentic"

    def test_returns_render_plan_when_provider_succeeds(self):
        """End-to-end pin through the dispatcher: a mocked provider
        that returns a RenderPlan must surface unchanged."""
        from app.ai import llm
        from app.domain.render_plan import RenderPlan, ClipPlan

        sentinel = RenderPlan(clips=[ClipPlan(start=10.0, end=40.0, rank=1, clip_name="A")])
        with patch("app.ai.llm.gemini_provider.select_render_plan", return_value=sentinel):
            result = llm.select_render_plan(
                srt_content="x", output_count=1, min_sec=15, max_sec=60,
                video_duration=300, api_key="k",
            )
        assert result is sentinel

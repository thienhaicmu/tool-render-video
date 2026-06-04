"""
Sprint 3.3 — pin the CreatorContext → editorial_hint integration.

These tests anchor that:
- when no CreatorContext is configured, the editorial hint is
  byte-for-byte identical to pre-Sprint-3 behaviour (Sacred Contract
  #2 spirit — additive, defaults to disabled).
- when a CreatorContext IS configured, its rendered prompt hint is
  appended to the existing hook/video_type hints.
- when CreatorContext is empty, the hint is NOT appended (builder
  normalises empty → None).
- when the builder raises internally (broken DB, bad config, missing
  module), _build_editorial_hint swallows the error and returns the
  payload-only hint — Sacred Contract #3 absolute.
- the prompt-hint string is fed verbatim into prompts.build_segment_
  prompt and does NOT survive a second .format() round (regression
  guard for the pre-flight `{end}` literal bug).
"""
from unittest import mock

import pytest

from app.domain.creator_context import CreatorContext
from app.orchestration.llm_stage import _build_editorial_hint


class _Payload:
    """Bare object exposing only the attributes _build_editorial_hint reads."""

    def __init__(self, hook_strength: str = "", video_type: str = ""):
        self.hook_strength = hook_strength
        self.video_type = video_type


class TestNoCreatorContext:
    def test_empty_payload_yields_empty_hint(self):
        with mock.patch("app.ai.context.creator_context.build_creator_context", return_value=None):
            assert _build_editorial_hint(_Payload()) == ""

    def test_hook_strength_only(self):
        """hook_strength=aggressive picks a non-empty entry from _HOOK_HINTS."""
        with mock.patch("app.ai.context.creator_context.build_creator_context", return_value=None):
            hint = _build_editorial_hint(_Payload(hook_strength="aggressive"))
        assert "bold claim" in hint  # phrase from _HOOK_HINTS["aggressive"]

    def test_video_type_only(self):
        """video_type=storytelling picks a non-empty entry from _VIDEO_TYPE_HINTS."""
        with mock.patch("app.ai.context.creator_context.build_creator_context", return_value=None):
            hint = _build_editorial_hint(_Payload(video_type="storytelling"))
        assert "narrative arc" in hint  # phrase from _VIDEO_TYPE_HINTS["storytelling"]

    def test_builder_returning_none_is_a_noop(self):
        """The Sprint-3 wire must collapse to the payload-only hint when
        no creator context is configured. Pins the additive-only
        contract."""
        with mock.patch(
            "app.ai.context.creator_context.build_creator_context",
            return_value=None,
        ):
            hint_with = _build_editorial_hint(_Payload(video_type="storytelling"))
        with mock.patch(
            "app.ai.context.creator_context.build_creator_context",
            return_value=CreatorContext(),  # explicit empty
        ):
            # Builder normalises empty → None at its layer, so the
            # path through here would not append anything. We also pin
            # the case where the builder mis-returns an empty instead
            # of None (defense in depth) — to_prompt_hint() returns ""
            # which the wire skips.
            hint_with_empty = _build_editorial_hint(_Payload(video_type="storytelling"))
        assert hint_with == hint_with_empty


class TestWithCreatorContext:
    def test_creator_hint_appended_to_payload_hint(self):
        ctx = CreatorContext(channel_name="K1 Cooking", brand_voice="authentic")
        with mock.patch("app.ai.context.creator_context.build_creator_context", return_value=ctx):
            hint = _build_editorial_hint(_Payload(video_type="storytelling"))
        # Both the payload-derived hint AND the creator hint are present.
        assert "narrative arc" in hint
        assert "Channel: K1 Cooking" in hint
        assert "Brand voice: authentic" in hint

    def test_creator_hint_alone_when_payload_is_empty(self):
        ctx = CreatorContext(channel_name="K1", language="vi")
        with mock.patch("app.ai.context.creator_context.build_creator_context", return_value=ctx):
            hint = _build_editorial_hint(_Payload())
        assert "Channel: K1" in hint
        assert "Language: vi" in hint

    def test_creator_hint_is_after_payload_hint(self):
        """Ordering pin: payload-derived editorial guidance comes first
        (it's the legacy contract from before Sprint 3), then the
        creator persona. Order is stable so prompt-engineering tweaks
        downstream see a deterministic input shape."""
        ctx = CreatorContext(channel_name="K1")
        with mock.patch("app.ai.context.creator_context.build_creator_context", return_value=ctx):
            hint = _build_editorial_hint(_Payload(video_type="emotional"))
        idx_payload = hint.find("emotionally")
        idx_creator = hint.find("Channel:")
        assert idx_payload >= 0 and idx_creator >= 0
        assert idx_payload < idx_creator


class TestNeverRaises:
    def test_builder_exception_yields_payload_only_hint(self):
        """Sacred Contract #3 — a raise from the builder must NOT
        propagate. The payload-derived hint stays intact."""
        with mock.patch(
            "app.ai.context.creator_context.build_creator_context",
            side_effect=RuntimeError("boom"),
        ):
            # Should not raise.
            hint = _build_editorial_hint(_Payload(video_type="educational"))
        # Payload hint preserved (the educational entry from _VIDEO_TYPE_HINTS).
        assert hint  # non-empty
        assert "teach" in hint

    def test_import_failure_yields_payload_only_hint(self):
        """If the ai.context module itself fails to import (broken
        deployment, missing dep), the wire must still collapse to the
        payload-only hint."""
        with mock.patch.dict("sys.modules", {"app.ai.context.creator_context": None}):
            hint = _build_editorial_hint(_Payload(video_type="storytelling"))
        assert hint  # payload hint survived
        assert "narrative arc" in hint


class TestPromptSafetyEndToEnd:
    """Defensive guard against the pre-flight `{end}` literal-brace bug:
    if a creator context contains `{...}` text (channel names with
    curly braces, etc.), the hint is fed verbatim into
    prompts.build_segment_prompt → which substitutes it once via
    .format() into `{editorial_section}`. No second .format() pass
    happens, so literal braces in the hint pass through without
    KeyError."""

    def test_curly_braces_in_creator_hint_do_not_crash_prompt_build(self):
        from app.ai.llm.prompts import build_segment_prompt
        ctx = CreatorContext(channel_name="K1 {brand_x}", notes="curly {start} {end} stay literal")
        with mock.patch("app.ai.context.creator_context.build_creator_context", return_value=ctx):
            hint = _build_editorial_hint(_Payload())
        # The hint itself should contain the literal braces.
        assert "{brand_x}" in hint
        assert "{start}" in hint and "{end}" in hint
        # And the downstream prompt builder MUST accept it without
        # KeyError. We hand it the same shape llm_stage does.
        system, user = build_segment_prompt(
            srt_content="00:01,000 --> 00:02,000\nhello",
            output_count=1,
            min_sec=15,
            max_sec=60,
            language="auto",
            editorial_hint=hint,
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        # The literal {brand_x} from the hint survived into the user prompt.
        assert "{brand_x}" in user

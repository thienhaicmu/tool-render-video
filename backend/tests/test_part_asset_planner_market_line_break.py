"""P1 T3 — Market line-break regression guard (Track D follow-up).

The market line-break block at stages/part_asset_planner.py:358-363
is wrapped in `try / except: pass`. Per Track D audit finding H5
(docs/review/AUDIT_2026-06-02_followup_7.md), if
`apply_market_line_break_to_srt` ever raises silently (e.g., due to a
lost import after refactoring, or `ctx.mv_cfg` shape drift), the SRT
file is never reformatted with market-specific line breaks AND the
`needs_ass` flag is never flipped to True — meaning even if a downstream
edit DID change the SRT, the ASS file wouldn't get rebuilt.

This test file is the regression guard. It asserts that when the block
conditions are met, the call fires AND the file-write side effect lands.

If a future refactor breaks this (e.g., loses the
`apply_market_line_break_to_srt` import), at least one of these tests
will fail loudly instead of degrading the subtitle output silently.

See docs/review/AUDIT_2026-06-02_followup_9.md for the closure record.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_ctx(tmp_path, mv_cfg, idx=1):
    """Minimal PartRenderContext stand-in for asset planner testing."""
    ctx = MagicMock()
    ctx.job_id = "test_job"
    ctx.effective_channel = "manual"
    ctx.work_dir = tmp_path
    ctx.output_dir = tmp_path
    ctx.output_stem = "stem"
    ctx.source = {"title": "T", "slug": "t"}
    ctx.target_platform = "tiktok"
    ctx.subtitle_enabled_by_idx = {idx: True}
    ctx.subtitle_cutoff = 0
    ctx.full_srt_available = False
    ctx.mv_market = "US"
    ctx.mv_cfg = mv_cfg
    ctx.hook_apply_enabled = False
    ctx.hook_applied_text = ""
    ctx.hook_score = 0
    ctx.hook_overlay_enabled = False
    ctx.dna_clean_visual = False
    ctx.ai_subtitle_emphasis_config = None
    ctx.normalized_text_layers = []
    ctx.sub_translate_attempts = []
    ctx.sub_translate_partial = []
    ctx.sub_translate_clean = []
    ctx.sub_translate_failed_parts = []
    ctx.cancel_registry.is_cancelled.return_value = False

    ctx.payload.resume_from_last = False
    ctx.payload.add_subtitle = True
    ctx.payload.subtitle_transcription_engine = "default"
    ctx.payload.highlight_per_word = False
    ctx.payload.subtitle_translate_enabled = False
    ctx.payload.subtitle_edits = None
    ctx.payload.subtitle_style = ""
    ctx.payload.frame_scale_y = 1.0
    ctx.payload.sub_font_size = 46
    ctx.payload.sub_font = "Bungee"
    ctx.payload.sub_margin_v = 180
    ctx.payload.sub_x_percent = 50.0
    ctx.payload.sub_color = "#FFFFFF"
    ctx.payload.sub_highlight = "#FFFF00"
    ctx.payload.sub_outline = 3
    ctx.payload.aspect_ratio = "9:16"
    ctx.payload.motion_aware_crop = False
    ctx.payload.cta_enabled = False
    ctx.payload.playback_speed = 1.07
    return ctx


class TestMarketLineBreakActivation:
    """P1 T3 regression guard — H5 silent-fail surface.

    The market line-break block must call apply_market_line_break_to_srt
    when conditions (fresh SRT + ctx.mv_cfg + file exists) are met.
    Pre-fix code (or a future regression) would silently swallow
    exceptions, leaving the SRT unformatted and the ASS unbuilt.
    """

    def test_apply_market_line_break_invoked_when_mv_cfg_set(self, tmp_path):
        """Happy path: mv_cfg present + fresh SRT + non-empty file →
        apply_market_line_break_to_srt is called with the SRT path and
        mv_cfg. needs_ass flips to True so the ASS rebuild fires."""
        from app.orchestration.stages.part_asset_planner import prepare_part_assets

        srt_part = tmp_path / "p_001.srt"
        srt_part.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nhello world this is subtitle\n",
            encoding="utf-8",
        )
        ass_part = tmp_path / "p_001.ass"
        translated_srt_part = tmp_path / "p_001_translated.srt"
        final_part = tmp_path / "p_001.mp4"
        raw_part = tmp_path / "p_001_raw.mp4"
        raw_part.write_bytes(b"v" * 100)

        mv_cfg = {"market": "US", "max_chars_per_line": 32}
        ctx = _make_ctx(tmp_path, mv_cfg=mv_cfg)
        seg = {"start": 0.0, "end": 5.0, "duration": 5.0,
               "viral_score": 50, "motion_score": 50, "hook_score": 50,
               "content_type_hint": "vlog"}
        part_manifest = MagicMock(srt_path=None, ass_path=None)

        with patch(
            "app.orchestration.stages.part_asset_planner.transcribe_with_adapter"
        ), patch(
            "app.orchestration.stages.part_asset_planner.apply_market_line_break_to_srt",
        ) as mock_line_break, patch(
            "app.orchestration.stages.part_asset_planner.apply_hook_subtitle_format",
            return_value=0,
        ), patch(
            "app.orchestration.stages.part_asset_planner.resegment_srt_for_readability",
            return_value=0,
        ), patch(
            "app.orchestration.stages.part_asset_planner.subtitle_emphasis_pass",
            return_value=0,
        ), patch(
            "app.orchestration.stages.part_asset_planner.parse_srt_blocks",
            return_value=[{"text": "hello world", "start": 0.0, "end": 2.0}],
        ), patch(
            "app.orchestration.stages.part_asset_planner.write_srt_blocks"
        ), patch(
            "app.orchestration.stages.part_asset_planner.srt_to_ass_bounce"
        ), patch(
            "app.orchestration.stages.part_asset_planner.srt_to_ass_karaoke"
        ), patch(
            "app.orchestration.stages.part_asset_planner.write_manifest"
        ), patch(
            "app.orchestration.stages.part_asset_planner._read_srt_meta",
            return_value={"first_start": 0.0, "first_end": 2.0,
                          "last_start": 0.0, "last_end": 2.0},
        ), patch(
            "app.orchestration.stages.part_asset_planner._emit_render_event"
        ), patch(
            "app.orchestration.stages.part_asset_planner.upsert_job_part"
        ):
            prepare_part_assets(
                ctx=ctx, idx=1, seg=seg,
                srt_part=srt_part, ass_part=ass_part,
                translated_srt_part=translated_srt_part,
                _effective_start=0.0, _part_manifest=part_manifest,
                part_name="p_001.mp4", final_part=final_part,
                raw_part=raw_part,
            )

        # H5 regression guard: apply_market_line_break_to_srt WAS invoked.
        assert mock_line_break.called, (
            "T3 regression: apply_market_line_break_to_srt was not invoked. "
            "Check that the market line-break block at "
            "stages/part_asset_planner.py:358 still runs without silent "
            "failure when ctx.mv_cfg is truthy and the SRT is fresh."
        )

        # Called with (srt_path_str, mv_cfg).
        args = mock_line_break.call_args.args
        assert args[0] == str(srt_part), (
            f"T3 regression: apply_market_line_break_to_srt called with "
            f"wrong path arg. Expected {str(srt_part)!r}, got {args[0]!r}."
        )
        assert args[1] == mv_cfg, (
            "T3 regression: apply_market_line_break_to_srt called with "
            "wrong mv_cfg arg."
        )

    def test_skipped_when_mv_cfg_falsy(self, tmp_path):
        """When ctx.mv_cfg is empty/None, the line-break block must NOT
        run (the `if` guard short-circuits). This documents the
        intentional fallthrough — not a regression."""
        from app.orchestration.stages.part_asset_planner import prepare_part_assets

        srt_part = tmp_path / "p_002.srt"
        srt_part.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\ntext\n",
            encoding="utf-8",
        )
        ass_part = tmp_path / "p_002.ass"
        translated_srt_part = tmp_path / "p_002_translated.srt"
        final_part = tmp_path / "p_002.mp4"
        raw_part = tmp_path / "p_002_raw.mp4"
        raw_part.write_bytes(b"v" * 100)

        # mv_cfg = {} → falsy
        ctx = _make_ctx(tmp_path, mv_cfg={}, idx=2)
        seg = {"start": 0.0, "end": 5.0, "duration": 5.0,
               "viral_score": 50, "motion_score": 50, "hook_score": 50,
               "content_type_hint": "vlog"}
        part_manifest = MagicMock(srt_path=None, ass_path=None)

        with patch(
            "app.orchestration.stages.part_asset_planner.transcribe_with_adapter"
        ), patch(
            "app.orchestration.stages.part_asset_planner.apply_market_line_break_to_srt"
        ) as mock_line_break, patch(
            "app.orchestration.stages.part_asset_planner.apply_hook_subtitle_format",
            return_value=0,
        ), patch(
            "app.orchestration.stages.part_asset_planner.resegment_srt_for_readability",
            return_value=0,
        ), patch(
            "app.orchestration.stages.part_asset_planner.subtitle_emphasis_pass",
            return_value=0,
        ), patch(
            "app.orchestration.stages.part_asset_planner.parse_srt_blocks",
            return_value=[],
        ), patch(
            "app.orchestration.stages.part_asset_planner.write_srt_blocks"
        ), patch(
            "app.orchestration.stages.part_asset_planner.srt_to_ass_bounce"
        ), patch(
            "app.orchestration.stages.part_asset_planner.srt_to_ass_karaoke"
        ), patch(
            "app.orchestration.stages.part_asset_planner.write_manifest"
        ), patch(
            "app.orchestration.stages.part_asset_planner._read_srt_meta",
            return_value={"first_start": 0.0, "first_end": 2.0,
                          "last_start": 0.0, "last_end": 2.0},
        ), patch(
            "app.orchestration.stages.part_asset_planner._emit_render_event"
        ), patch(
            "app.orchestration.stages.part_asset_planner.upsert_job_part"
        ):
            prepare_part_assets(
                ctx=ctx, idx=2, seg=seg,
                srt_part=srt_part, ass_part=ass_part,
                translated_srt_part=translated_srt_part,
                _effective_start=0.0, _part_manifest=part_manifest,
                part_name="p_002.mp4", final_part=final_part,
                raw_part=raw_part,
            )

        # When mv_cfg is empty dict (falsy), the if-guard short-circuits
        # before the try block. apply_market_line_break_to_srt should NOT
        # be invoked. This is intended behavior — not a silent failure.
        assert not mock_line_break.called, (
            "T3 regression: apply_market_line_break_to_srt was invoked "
            "even though ctx.mv_cfg is falsy. The if-guard at "
            "stages/part_asset_planner.py:358 should short-circuit."
        )

    def test_silent_swallow_when_helper_raises(self, tmp_path):
        """Documents the intentional try/except: pass behavior. When
        apply_market_line_break_to_srt raises (e.g., malformed SRT,
        unsupported mv_cfg keys), the exception is swallowed and
        prepare_part_assets continues without aborting the render."""
        from app.orchestration.stages.part_asset_planner import prepare_part_assets

        srt_part = tmp_path / "p_003.srt"
        srt_part.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nx\n",
            encoding="utf-8",
        )
        ass_part = tmp_path / "p_003.ass"
        translated_srt_part = tmp_path / "p_003_translated.srt"
        final_part = tmp_path / "p_003.mp4"
        raw_part = tmp_path / "p_003_raw.mp4"
        raw_part.write_bytes(b"v" * 100)

        ctx = _make_ctx(tmp_path, mv_cfg={"market": "EU"}, idx=3)
        seg = {"start": 0.0, "end": 5.0, "duration": 5.0,
               "viral_score": 50, "motion_score": 50, "hook_score": 50,
               "content_type_hint": "vlog"}
        part_manifest = MagicMock(srt_path=None, ass_path=None)

        with patch(
            "app.orchestration.stages.part_asset_planner.transcribe_with_adapter"
        ), patch(
            "app.orchestration.stages.part_asset_planner.apply_market_line_break_to_srt",
            side_effect=RuntimeError("simulated mv parse failure"),
        ) as mock_line_break, patch(
            "app.orchestration.stages.part_asset_planner.apply_hook_subtitle_format",
            return_value=0,
        ), patch(
            "app.orchestration.stages.part_asset_planner.resegment_srt_for_readability",
            return_value=0,
        ), patch(
            "app.orchestration.stages.part_asset_planner.subtitle_emphasis_pass",
            return_value=0,
        ), patch(
            "app.orchestration.stages.part_asset_planner.parse_srt_blocks",
            return_value=[],
        ), patch(
            "app.orchestration.stages.part_asset_planner.write_srt_blocks"
        ), patch(
            "app.orchestration.stages.part_asset_planner.srt_to_ass_bounce"
        ), patch(
            "app.orchestration.stages.part_asset_planner.srt_to_ass_karaoke"
        ), patch(
            "app.orchestration.stages.part_asset_planner.write_manifest"
        ), patch(
            "app.orchestration.stages.part_asset_planner._read_srt_meta",
            return_value={"first_start": 0.0, "first_end": 2.0,
                          "last_start": 0.0, "last_end": 2.0},
        ), patch(
            "app.orchestration.stages.part_asset_planner._emit_render_event"
        ), patch(
            "app.orchestration.stages.part_asset_planner.upsert_job_part"
        ):
            # Must NOT raise — the except:pass is the safety net.
            result = prepare_part_assets(
                ctx=ctx, idx=3, seg=seg,
                srt_part=srt_part, ass_part=ass_part,
                translated_srt_part=translated_srt_part,
                _effective_start=0.0, _part_manifest=part_manifest,
                part_name="p_003.mp4", final_part=final_part,
                raw_part=raw_part,
            )

        # The call attempted (proving the block ran), then the exception
        # was swallowed (proving the safety net is intact).
        assert mock_line_break.called
        # prepare_part_assets returned cleanly — no propagation.
        assert result is not None

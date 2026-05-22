# test_subtitle_engine_compat_exports.py — Phase 4G.7 compatibility freeze audit.
#
# Verifies that subtitle_engine.py is a pure re-export shim and that all
# public symbols are importable and share object identity with their respective
# new subtitles/* modules.
#
# Coverage:
# - subtitle_engine imports cleanly
# - subtitle_engine has no function bodies (source inspection)
# - subtitle_engine does not import whisper at module level
# - subtitle_engine does not import render_engine
# - subtitle_engine imports only from app.services.subtitles.*
# - All 7 public symbol groups present (styles, srt_core, output_timeline,
#   ass_core, readability, text_transforms, transcription)
# - Same-object identity: one representative per cluster (7 checks)
# - No subtitles/* module imports subtitle_engine (no upward coupling)
# - transcription.py imports _has_audio_stream from render.ffmpeg_helpers (coupling fix)
# - No real Whisper, no real FFmpeg invocations
from __future__ import annotations

import inspect
import sys
import types
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Inject whisper mock before any project import that triggers transcription.py
# ---------------------------------------------------------------------------

_whisper_mock = types.ModuleType("whisper")
_whisper_mock.load_model = mock.MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("whisper", _whisper_mock)

import app.services.subtitle_engine as se  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Shim structure assertions
# ---------------------------------------------------------------------------

class TestShimStructure:
    def test_subtitle_engine_imports_cleanly(self):
        assert se is not None

    def test_subtitle_engine_has_no_function_bodies(self):
        src = inspect.getsource(se)
        # A pure shim has no `def` lines at module scope
        defs = [line for line in src.splitlines() if line.startswith("def ")]
        assert defs == [], f"Unexpected function bodies: {defs}"

    def test_subtitle_engine_has_no_class_bodies(self):
        src = inspect.getsource(se)
        classes = [line for line in src.splitlines() if line.startswith("class ")]
        assert classes == [], f"Unexpected class definitions: {classes}"

    def test_subtitle_engine_does_not_import_whisper(self):
        src = inspect.getsource(se)
        assert "import whisper" not in src

    def test_subtitle_engine_does_not_import_render_engine(self):
        src = inspect.getsource(se)
        assert "render_engine" not in src

    def test_subtitle_engine_imports_only_from_subtitles_package(self):
        src = inspect.getsource(se)
        import_lines = [
            line.strip()
            for line in src.splitlines()
            if line.strip().startswith("from ") or line.strip().startswith("import ")
        ]
        for line in import_lines:
            assert "app.services.subtitles." in line, (
                f"Import not from subtitles package: {line}"
            )

    def test_subtitle_engine_has_no_stdlib_imports(self):
        src = inspect.getsource(se)
        stdlib = ["import os", "import re", "import subprocess", "import threading",
                  "import time", "import logging", "from pathlib", "import whisper"]
        for s in stdlib:
            assert s not in src, f"Unexpected stdlib import found: {s}"


# ---------------------------------------------------------------------------
# 2. Public symbol presence
# ---------------------------------------------------------------------------

class TestPublicSymbolPresence:
    # Cluster A — styles
    def test_ASSPreset_present(self):
        assert hasattr(se, "ASSPreset") and se.ASSPreset is not None

    def test_BOUNCE_FX_present(self):
        assert hasattr(se, "BOUNCE_FX")

    def test_normalize_subtitle_style_id_present(self):
        assert callable(se.normalize_subtitle_style_id)

    def test_get_subtitle_preset_present(self):
        assert callable(se.get_subtitle_preset)

    def test_build_ass_style_line_present(self):
        assert callable(se.build_ass_style_line)

    def test_HL_OPEN_present(self):
        assert hasattr(se, "_HL_OPEN")

    def test_HL_CLOSE_present(self):
        assert hasattr(se, "_HL_CLOSE")

    # Cluster B — srt_core
    def test_format_srt_timestamp_present(self):
        assert callable(se.format_srt_timestamp)

    def test_parse_srt_timestamp_present(self):
        assert callable(se.parse_srt_timestamp)

    def test_parse_srt_blocks_present(self):
        assert callable(se.parse_srt_blocks)

    def test_write_srt_blocks_present(self):
        assert callable(se.write_srt_blocks)

    def test_slice_srt_by_time_present(self):
        assert callable(se.slice_srt_by_time)

    def test_slice_srt_to_text_present(self):
        assert callable(se.slice_srt_to_text)

    def test_run_with_retry_present(self):
        assert callable(se._run_with_retry)

    # Cluster B.5 — output_timeline
    def test_slice_srt_to_output_timeline_present(self):
        assert callable(se.slice_srt_to_output_timeline)

    # Cluster C — ass_core
    def test_srt_to_ass_bounce_present(self):
        assert callable(se.srt_to_ass_bounce)

    def test_srt_to_ass_karaoke_present(self):
        assert callable(se.srt_to_ass_karaoke)

    def test_burn_subtitle_onto_video_present(self):
        assert callable(se.burn_subtitle_onto_video)

    def test_render_subtitle_preview_present(self):
        assert callable(se.render_subtitle_preview)

    def test_hex_to_ass_present(self):
        assert callable(se._hex_to_ass)

    # Cluster D — readability
    def test_subtitle_emphasis_pass_present(self):
        assert callable(se.subtitle_emphasis_pass)

    def test_resegment_srt_for_readability_present(self):
        assert callable(se.resegment_srt_for_readability)

    def test_HOOK_EMPHASIS_WORDS_present(self):
        assert hasattr(se, "_HOOK_EMPHASIS_WORDS")

    # Cluster E — text_transforms
    def test_apply_market_hook_text_to_srt_present(self):
        assert callable(se.apply_market_hook_text_to_srt)

    def test_apply_hook_subtitle_format_present(self):
        assert callable(se.apply_hook_subtitle_format)

    def test_resolve_hook_overlay_text_present(self):
        assert callable(se.resolve_hook_overlay_text)

    def test_apply_subtitle_execution_hints_present(self):
        assert callable(se.apply_subtitle_execution_hints)

    # Cluster F — transcription
    def test_transcribe_to_srt_present(self):
        assert callable(se.transcribe_to_srt)

    def test_extract_audio_for_transcription_present(self):
        assert callable(se.extract_audio_for_transcription)

    def test_has_audio_stream_present(self):
        assert callable(se.has_audio_stream)

    def test_get_whisper_model_present(self):
        assert callable(se.get_whisper_model)

    def test_WHISPER_CACHE_DIR_present(self):
        assert hasattr(se, "_WHISPER_CACHE_DIR")


# ---------------------------------------------------------------------------
# 3. Same-object identity — one per cluster
# ---------------------------------------------------------------------------

class TestSameObjectIdentityPerCluster:
    def test_styles_cluster_normalize_subtitle_style_id(self):
        from app.services.subtitles.styles import normalize_subtitle_style_id
        assert se.normalize_subtitle_style_id is normalize_subtitle_style_id

    def test_srt_core_cluster_parse_srt_blocks(self):
        from app.services.subtitles.srt_core import parse_srt_blocks
        assert se.parse_srt_blocks is parse_srt_blocks

    def test_output_timeline_cluster_slice_srt_to_output_timeline(self):
        from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
        assert se.slice_srt_to_output_timeline is slice_srt_to_output_timeline

    def test_ass_core_cluster_srt_to_ass_bounce(self):
        from app.services.subtitles.ass_core import srt_to_ass_bounce
        assert se.srt_to_ass_bounce is srt_to_ass_bounce

    def test_readability_cluster_subtitle_emphasis_pass(self):
        from app.services.subtitles.readability import subtitle_emphasis_pass
        assert se.subtitle_emphasis_pass is subtitle_emphasis_pass

    def test_text_transforms_cluster_apply_market_hook_text_to_srt(self):
        from app.services.subtitles.text_transforms import apply_market_hook_text_to_srt
        assert se.apply_market_hook_text_to_srt is apply_market_hook_text_to_srt

    def test_transcription_cluster_transcribe_to_srt(self):
        from app.services.subtitles.transcription import transcribe_to_srt
        assert se.transcribe_to_srt is transcribe_to_srt

    def test_ASSPreset_identity(self):
        from app.services.subtitles.styles import ASSPreset
        assert se.ASSPreset is ASSPreset

    def test_BOUNCE_FX_identity(self):
        from app.services.subtitles.styles import BOUNCE_FX
        assert se.BOUNCE_FX is BOUNCE_FX

    def test_has_audio_stream_identity(self):
        from app.services.subtitles.transcription import has_audio_stream
        assert se.has_audio_stream is has_audio_stream

    def test_PRESETS_identity(self):
        from app.services.subtitles.styles import _PRESETS
        assert se._PRESETS is _PRESETS


# ---------------------------------------------------------------------------
# 4. No upward coupling — subtitles/* does not import subtitle_engine
# ---------------------------------------------------------------------------

class TestNoUpwardCoupling:
    def _get_module_source(self, module_name: str) -> str:
        import importlib
        mod = importlib.import_module(module_name)
        return inspect.getsource(mod)

    def test_styles_does_not_import_subtitle_engine(self):
        src = self._get_module_source("app.services.subtitles.styles")
        assert "subtitle_engine" not in src

    def test_srt_core_does_not_import_subtitle_engine(self):
        src = self._get_module_source("app.services.subtitles.srt_core")
        assert "subtitle_engine" not in src

    def test_output_timeline_does_not_import_subtitle_engine(self):
        src = self._get_module_source("app.services.subtitles.output_timeline")
        assert "subtitle_engine" not in src

    def test_ass_core_does_not_import_subtitle_engine(self):
        src = self._get_module_source("app.services.subtitles.ass_core")
        assert "subtitle_engine" not in src

    def test_readability_does_not_import_subtitle_engine(self):
        src = self._get_module_source("app.services.subtitles.readability")
        assert "subtitle_engine" not in src

    def test_text_transforms_does_not_import_subtitle_engine(self):
        src = self._get_module_source("app.services.subtitles.text_transforms")
        assert "subtitle_engine" not in src

    def test_transcription_does_not_import_subtitle_engine(self):
        src = self._get_module_source("app.services.subtitles.transcription")
        assert "subtitle_engine" not in src


# ---------------------------------------------------------------------------
# 5. No render_engine coupling in subtitles package
# ---------------------------------------------------------------------------

class TestNoRenderEngineCoupling:
    def _module_import_lines(self, module_name: str) -> list[str]:
        import importlib
        mod = importlib.import_module(module_name)
        src = inspect.getsource(mod)
        return [
            line.strip()
            for line in src.splitlines()
            if line.strip().startswith(("from ", "import "))
        ]

    def _assert_no_render_engine_import(self, module_name: str):
        lines = self._module_import_lines(module_name)
        for line in lines:
            assert "render_engine" not in line, (
                f"{module_name}: unexpected render_engine import: {line}"
            )

    def test_styles_no_render_engine(self):
        self._assert_no_render_engine_import("app.services.subtitles.styles")

    def test_srt_core_no_render_engine(self):
        self._assert_no_render_engine_import("app.services.subtitles.srt_core")

    def test_output_timeline_no_render_engine(self):
        self._assert_no_render_engine_import("app.services.subtitles.output_timeline")

    def test_ass_core_no_render_engine(self):
        self._assert_no_render_engine_import("app.services.subtitles.ass_core")

    def test_readability_no_render_engine(self):
        self._assert_no_render_engine_import("app.services.subtitles.readability")

    def test_text_transforms_no_render_engine(self):
        self._assert_no_render_engine_import("app.services.subtitles.text_transforms")

    def test_transcription_imports_ffmpeg_helpers_not_render_engine(self):
        import app.services.subtitles.transcription as tc
        src = inspect.getsource(tc.has_audio_stream)
        assert "ffmpeg_helpers" in src
        assert "from app.services.render_engine" not in src
        assert "import render_engine" not in src

    def test_subtitle_engine_no_render_engine_import(self):
        src = inspect.getsource(se)
        assert "render_engine" not in src


# ---------------------------------------------------------------------------
# 6. Dependency direction — subtitle_engine only imports app.services.subtitles.*
# ---------------------------------------------------------------------------

class TestDependencyDirection:
    def test_all_imports_from_subtitles_package(self):
        src = inspect.getsource(se)
        import_lines = [
            line.strip()
            for line in src.splitlines()
            if line.strip().startswith("from ")
        ]
        assert len(import_lines) > 0, "Expected import lines in subtitle_engine.py"
        for line in import_lines:
            assert "app.services.subtitles." in line, (
                f"Non-subtitles import: {line}"
            )

    def test_subtitle_engine_has_seven_import_blocks(self):
        src = inspect.getsource(se)
        # Count "from app.services.subtitles." lines
        module_imports = [
            line for line in src.splitlines()
            if "from app.services.subtitles." in line
        ]
        # At least 7 subtitles modules referenced
        module_names = {
            line.split("from app.services.subtitles.")[1].split(" ")[0]
            for line in module_imports
            if "from app.services.subtitles." in line
        }
        expected = {
            "output_timeline", "styles", "srt_core", "readability",
            "text_transforms", "ass_core", "transcription",
        }
        assert expected.issubset(module_names), (
            f"Missing modules: {expected - module_names}"
        )

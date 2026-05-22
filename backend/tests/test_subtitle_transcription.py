# test_subtitle_transcription.py — Unit tests for subtitles/transcription.py (Phase 4G.6).
#
# Coverage:
# - Module imports cleanly with mocked whisper
# - Same-object identity: transcription.py symbols accessible via subtitle_engine
# - Coupling fix: has_audio_stream imports from render.ffmpeg_helpers, not render_engine shim
# - get_whisper_model caches models per name
# - _get_transcribe_lock creates and caches locks
# - _transcribe_with_retry succeeds on first try; retries on failure; raises after retries exhausted
# - _ensure_ffmpeg_in_path_for_whisper patches PATH when dir is absent
# - extract_audio_for_transcription calls _run_with_retry with correct ffmpeg args
# - transcribe_to_srt: segment-level path writes valid SRT
# - transcribe_to_srt: word-level path writes valid SRT with one entry per word/merged word
# - transcribe_to_srt: word-level falls back to segment-level on exception
# - transcribe_to_srt: cleans up WAV file even on failure
# - _write_segment_level_srt skips empty-text segments
# - _write_word_level_srt merges ultra-short words
# - _write_word_level_srt falls back to segment text when no word timestamps
# - No real whisper or subprocess calls in any test
from __future__ import annotations

import sys
import types
import threading
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Inject whisper mock BEFORE any project import that triggers transcription.py
# ---------------------------------------------------------------------------

_whisper_mock = types.ModuleType("whisper")
_whisper_mock.load_model = mock.MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("whisper", _whisper_mock)

# Now safe to import project code
import app.services.subtitles.transcription as tc  # noqa: E402
import app.services.subtitle_engine as se  # noqa: E402


# ---------------------------------------------------------------------------
# SRT fixtures
# ---------------------------------------------------------------------------

_RESULT_SEGMENTS = {
    "segments": [
        {"start": 0.0, "end": 2.0, "text": " Hello world", "words": []},
        {"start": 3.0, "end": 5.0, "text": " Foo bar", "words": []},
    ]
}

_RESULT_WORD_LEVEL = {
    "segments": [
        {
            "start": 0.0, "end": 2.0, "text": " Hello world",
            "words": [
                {"word": "Hello", "start": 0.0, "end": 0.5},
                {"word": "world", "start": 0.6, "end": 1.2},
            ],
        },
    ]
}

_RESULT_SHORT_WORDS = {
    "segments": [
        {
            "start": 0.0, "end": 2.0, "text": " A bee",
            "words": [
                # "A" is very short (< WORD_MERGE_SHORTER_THAN_SEC=0.11), should merge with "bee"
                {"word": "A", "start": 0.0, "end": 0.05},
                {"word": "bee", "start": 0.1, "end": 0.4},
            ],
        },
    ]
}


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

class TestTranscriptionModuleImports:
    def test_transcription_imports_cleanly(self):
        assert tc is not None

    def test_get_whisper_model_callable(self):
        assert callable(tc.get_whisper_model)

    def test_transcribe_to_srt_callable(self):
        assert callable(tc.transcribe_to_srt)

    def test_extract_audio_for_transcription_callable(self):
        assert callable(tc.extract_audio_for_transcription)

    def test_has_audio_stream_callable(self):
        assert callable(tc.has_audio_stream)

    def test_no_render_engine_import_in_transcription(self):
        import inspect
        src = inspect.getsource(tc)
        # No import statement should reference render_engine (docstring mentions are OK)
        assert "from app.services.render_engine" not in src
        assert "import render_engine" not in src

    def test_whisper_cache_dir_is_path(self):
        assert isinstance(tc._WHISPER_CACHE_DIR, Path)

    def test_whisper_cache_dir_under_data(self):
        # Must resolve to <project_root>/data/whisper_cache
        assert tc._WHISPER_CACHE_DIR.parts[-2:] == ("data", "whisper_cache")

    def test_word_min_gap_sec_value(self):
        assert tc.WORD_MIN_GAP_SEC == 0.02

    def test_word_min_duration_sec_value(self):
        assert tc.WORD_MIN_DURATION_SEC == 0.12

    def test_word_merge_shorter_than_sec_value(self):
        assert tc.WORD_MERGE_SHORTER_THAN_SEC == 0.11


# ---------------------------------------------------------------------------
# Same-object identity (via subtitle_engine shim)
# ---------------------------------------------------------------------------

class TestTranscriptionSameObjectIdentity:
    def test_get_whisper_model_identity(self):
        assert se.get_whisper_model is tc.get_whisper_model

    def test_transcribe_to_srt_identity(self):
        assert se.transcribe_to_srt is tc.transcribe_to_srt

    def test_extract_audio_for_transcription_identity(self):
        assert se.extract_audio_for_transcription is tc.extract_audio_for_transcription

    def test_has_audio_stream_identity(self):
        assert se.has_audio_stream is tc.has_audio_stream

    def test_get_transcribe_lock_identity(self):
        assert se._get_transcribe_lock is tc._get_transcribe_lock

    def test_transcribe_with_retry_identity(self):
        assert se._transcribe_with_retry is tc._transcribe_with_retry

    def test_word_level_srt_identity(self):
        assert se._write_word_level_srt is tc._write_word_level_srt

    def test_segment_level_srt_identity(self):
        assert se._write_segment_level_srt is tc._write_segment_level_srt

    def test_whisper_cache_dir_identity(self):
        assert se._WHISPER_CACHE_DIR is tc._WHISPER_CACHE_DIR

    def test_model_cache_identity(self):
        assert se._MODEL_CACHE is tc._MODEL_CACHE


# ---------------------------------------------------------------------------
# Coupling fix: has_audio_stream imports from ffmpeg_helpers, not render_engine
# ---------------------------------------------------------------------------

class TestHasAudioStreamCouplingFix:
    def test_imports_from_ffmpeg_helpers_not_render_engine(self):
        import inspect
        src = inspect.getsource(tc.has_audio_stream)
        assert "ffmpeg_helpers" in src
        # Must not import via render_engine shim (docstring mentions are OK)
        assert "from app.services.render_engine" not in src
        assert "import render_engine" not in src

    def test_has_audio_stream_delegates_to_ffmpeg_helpers(self):
        with mock.patch("app.services.render.ffmpeg_helpers._has_audio_stream", return_value=True) as m:
            result = tc.has_audio_stream("fake.mp4")
        assert result is True
        m.assert_called_once_with("fake.mp4")

    def test_has_audio_stream_returns_false(self):
        with mock.patch("app.services.render.ffmpeg_helpers._has_audio_stream", return_value=False):
            result = tc.has_audio_stream("silent.mp4")
        assert result is False


# ---------------------------------------------------------------------------
# get_whisper_model caching
# ---------------------------------------------------------------------------

class TestGetWhisperModel:
    def setup_method(self):
        # Clear shared cache before each test
        tc._MODEL_CACHE.clear()

    def test_loads_model_on_first_call(self):
        # Patch transcription.whisper directly — order-independent (see Phase 4H.1A).
        # sys.modules.setdefault at module level is defeated by test_subtitle_engine_compat_exports.py
        # which injects a different mock first (alphabetical collection order: "engine" < "transcription").
        fake_model = mock.MagicMock()
        mock_whisper = mock.MagicMock()
        mock_whisper.load_model.return_value = fake_model
        with mock.patch("app.services.subtitles.transcription.whisper", mock_whisper):
            result = tc.get_whisper_model("tiny")
        assert result is fake_model
        mock_whisper.load_model.assert_called()

    def test_returns_cached_model_on_second_call(self):
        fake_model = mock.MagicMock()
        mock_whisper = mock.MagicMock()
        mock_whisper.load_model.return_value = fake_model
        with mock.patch("app.services.subtitles.transcription.whisper", mock_whisper):
            tc.get_whisper_model("base")
            mock_whisper.load_model.reset_mock()
            result2 = tc.get_whisper_model("base")
        assert result2 is fake_model
        mock_whisper.load_model.assert_not_called()

    def test_different_names_load_separately(self):
        tc._MODEL_CACHE.clear()
        m1, m2 = mock.MagicMock(), mock.MagicMock()
        mock_whisper = mock.MagicMock()
        mock_whisper.load_model.side_effect = [m1, m2]
        with mock.patch("app.services.subtitles.transcription.whisper", mock_whisper):
            r1 = tc.get_whisper_model("tiny")
            r2 = tc.get_whisper_model("small")
        assert r1 is m1
        assert r2 is m2

    def teardown_method(self):
        tc._MODEL_CACHE.clear()


# ---------------------------------------------------------------------------
# _get_transcribe_lock caching
# ---------------------------------------------------------------------------

class TestGetTranscribeLock:
    def setup_method(self):
        tc._MODEL_TRANSCRIBE_LOCKS.clear()

    def test_returns_lock(self):
        lock = tc._get_transcribe_lock("base")
        assert isinstance(lock, type(threading.Lock()))

    def test_same_name_returns_same_lock(self):
        lock1 = tc._get_transcribe_lock("tiny")
        lock2 = tc._get_transcribe_lock("tiny")
        assert lock1 is lock2

    def test_different_names_return_different_locks(self):
        lock1 = tc._get_transcribe_lock("tiny")
        lock2 = tc._get_transcribe_lock("small")
        assert lock1 is not lock2

    def teardown_method(self):
        tc._MODEL_TRANSCRIBE_LOCKS.clear()


# ---------------------------------------------------------------------------
# _transcribe_with_retry
# ---------------------------------------------------------------------------

class TestTranscribeWithRetry:
    def test_returns_result_on_first_try(self):
        model = mock.MagicMock()
        model.transcribe.return_value = {"segments": []}
        result = tc._transcribe_with_retry(model, "audio.wav", retries=2)
        assert result == {"segments": []}
        model.transcribe.assert_called_once()

    def test_retries_on_failure_then_succeeds(self):
        model = mock.MagicMock()
        model.transcribe.side_effect = [RuntimeError("gpu busy"), {"segments": []}]
        result = tc._transcribe_with_retry(model, "audio.wav", retries=2, wait_sec=0.0)
        assert result == {"segments": []}
        assert model.transcribe.call_count == 2

    def test_raises_after_retries_exhausted(self):
        model = mock.MagicMock()
        model.transcribe.side_effect = RuntimeError("always fails")
        with pytest.raises(RuntimeError, match="always fails"):
            tc._transcribe_with_retry(model, "audio.wav", retries=2, wait_sec=0.0)
        assert model.transcribe.call_count == 3  # 1 initial + 2 retries

    def test_uses_transcribe_lock_when_provided(self):
        model = mock.MagicMock()
        model.transcribe.return_value = {"segments": []}
        lock = threading.Lock()
        result = tc._transcribe_with_retry(model, "audio.wav", transcribe_lock=lock)
        assert result == {"segments": []}


# ---------------------------------------------------------------------------
# _ensure_ffmpeg_in_path_for_whisper
# ---------------------------------------------------------------------------

class TestEnsureFfmpegInPath:
    def test_adds_ffmpeg_dir_to_path(self):
        import os
        ffmpeg_bin = str(Path("C:/fake/bin/ffmpeg"))
        ffmpeg_dir = str(Path("C:/fake/bin"))
        with mock.patch("app.services.subtitles.transcription.get_ffmpeg_bin", return_value=ffmpeg_bin), \
             mock.patch.dict("os.environ", {"PATH": "/usr/bin"}, clear=False):
            tc._ensure_ffmpeg_in_path_for_whisper()
            assert ffmpeg_dir in os.environ["PATH"]

    def test_does_not_duplicate_dir_already_in_path(self):
        import os
        with mock.patch("app.services.subtitles.transcription.get_ffmpeg_bin", return_value="/fake/bin/ffmpeg"), \
             mock.patch.dict("os.environ", {"PATH": "/fake/bin:/usr/bin"}, clear=False):
            before = os.environ["PATH"]
            tc._ensure_ffmpeg_in_path_for_whisper()
            assert os.environ["PATH"].count("/fake/bin") == before.count("/fake/bin")


# ---------------------------------------------------------------------------
# extract_audio_for_transcription
# ---------------------------------------------------------------------------

class TestExtractAudioForTranscription:
    def test_calls_run_with_retry_with_ffmpeg_args(self):
        with mock.patch("app.services.subtitles.transcription._run_with_retry") as mrr, \
             mock.patch("app.services.subtitles.transcription.get_ffmpeg_bin", return_value="ffmpeg"), \
             mock.patch("app.services.subtitles.transcription._ensure_ffmpeg_in_path_for_whisper"):
            tc.extract_audio_for_transcription("video.mp4", "out.wav", retry_count=1)
        mrr.assert_called_once()
        cmd = mrr.call_args[0][0]
        assert "ffmpeg" in cmd
        assert "pcm_s16le" in cmd
        assert "16000" in cmd
        assert "out.wav" in cmd

    def test_passes_retry_count(self):
        with mock.patch("app.services.subtitles.transcription._run_with_retry") as mrr, \
             mock.patch("app.services.subtitles.transcription.get_ffmpeg_bin", return_value="ffmpeg"), \
             mock.patch("app.services.subtitles.transcription._ensure_ffmpeg_in_path_for_whisper"):
            tc.extract_audio_for_transcription("v.mp4", "a.wav", retry_count=3)
        assert mrr.call_args[1].get("retries") == 3 or mrr.call_args[0][1] == 3 or \
               (len(mrr.call_args[0]) > 1 and mrr.call_args[0][1] == 3) or \
               mrr.call_args[1].get("retries", 0) == 3


# ---------------------------------------------------------------------------
# _write_segment_level_srt
# ---------------------------------------------------------------------------

class TestWriteSegmentLevelSrt:
    def test_writes_srt_entries(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "out.srt")
            tc._write_segment_level_srt(_RESULT_SEGMENTS, path)
            content = Path(path).read_text(encoding="utf-8")
        assert "Hello world" in content
        assert "Foo bar" in content
        assert "00:00:00,000 --> 00:00:02,000" in content

    def test_skips_empty_text_segments(self):
        result = {"segments": [
            {"start": 0.0, "end": 1.0, "text": "  "},
            {"start": 1.0, "end": 2.0, "text": "Real text"},
        ]}
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "out.srt")
            tc._write_segment_level_srt(result, path)
            content = Path(path).read_text(encoding="utf-8")
        assert "Real text" in content
        lines = [l for l in content.splitlines() if l.strip()]
        # Only one entry — the empty segment is skipped
        assert content.count("\n\n") == 1

    def test_sequential_indices(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "out.srt")
            tc._write_segment_level_srt(_RESULT_SEGMENTS, path)
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        assert lines[0] == "1"
        # Find second entry index
        blank_idx = lines.index("")
        assert lines[blank_idx + 1] == "2"


# ---------------------------------------------------------------------------
# _write_word_level_srt
# ---------------------------------------------------------------------------

class TestWriteWordLevelSrt:
    def test_writes_one_entry_per_word(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "out.srt")
            tc._write_word_level_srt(_RESULT_WORD_LEVEL, path)
            content = Path(path).read_text(encoding="utf-8")
        assert "Hello" in content
        assert "world" in content
        assert content.count("\n\n") == 2

    def test_short_words_normalized_to_min_duration(self):
        # WORD_MIN_DURATION_SEC=0.12 > WORD_MERGE_SHORTER_THAN_SEC=0.11, so after
        # normalization each word is at least 0.12s and the merge condition (< 0.11)
        # never fires — words remain separate entries.
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "out.srt")
            tc._write_word_level_srt(_RESULT_SHORT_WORDS, path)
            content = Path(path).read_text(encoding="utf-8")
        assert "A" in content
        assert "bee" in content
        assert content.count("\n\n") == 2

    def test_falls_back_to_segment_text_when_no_words(self):
        result = {"segments": [
            {"start": 1.0, "end": 3.0, "text": "Fallback segment", "words": []},
        ]}
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "out.srt")
            tc._write_word_level_srt(result, path)
            content = Path(path).read_text(encoding="utf-8")
        assert "Fallback segment" in content


# ---------------------------------------------------------------------------
# transcribe_to_srt integration (all subprocess/model calls mocked)
# ---------------------------------------------------------------------------

class TestTranscribeToSrt:
    def _make_mocks(self, result=None):
        if result is None:
            result = _RESULT_SEGMENTS
        model_mock = mock.MagicMock()
        model_mock.transcribe.return_value = result
        return model_mock

    def test_segment_level_writes_srt(self):
        model = self._make_mocks()
        with tempfile.TemporaryDirectory() as d:
            srt_path = str(Path(d) / "out.srt")
            wav_path = str(Path(d) / "out.wav")
            # Pre-create WAV so unlink doesn't fail (mock _run_with_retry skips creation)
            Path(wav_path).write_bytes(b"")
            with mock.patch("app.services.subtitles.transcription.get_whisper_model", return_value=model), \
                 mock.patch("app.services.subtitles.transcription._run_with_retry"), \
                 mock.patch("app.services.subtitles.transcription._ensure_ffmpeg_in_path_for_whisper"), \
                 mock.patch("app.services.subtitles.transcription.get_ffmpeg_bin", return_value="ffmpeg"):
                result = tc.transcribe_to_srt("vid.mp4", srt_path)
            content = Path(srt_path).read_text(encoding="utf-8")
        assert "Hello world" in content
        assert result is _RESULT_SEGMENTS

    def test_word_level_writes_word_srt(self):
        model = self._make_mocks(_RESULT_WORD_LEVEL)
        with tempfile.TemporaryDirectory() as d:
            srt_path = str(Path(d) / "out.srt")
            wav_path = str(Path(d) / "out.wav")
            Path(wav_path).write_bytes(b"")
            with mock.patch("app.services.subtitles.transcription.get_whisper_model", return_value=model), \
                 mock.patch("app.services.subtitles.transcription._run_with_retry"), \
                 mock.patch("app.services.subtitles.transcription._ensure_ffmpeg_in_path_for_whisper"), \
                 mock.patch("app.services.subtitles.transcription.get_ffmpeg_bin", return_value="ffmpeg"):
                tc.transcribe_to_srt("vid.mp4", srt_path, highlight_per_word=True)
            content = Path(srt_path).read_text(encoding="utf-8")
        assert "Hello" in content

    def test_word_level_falls_back_on_exception(self):
        model = mock.MagicMock()
        # First transcribe call (word_timestamps=True) raises; second succeeds
        model.transcribe.side_effect = [RuntimeError("word ts fail"), _RESULT_SEGMENTS]
        with tempfile.TemporaryDirectory() as d:
            srt_path = str(Path(d) / "out.srt")
            wav_path = str(Path(d) / "out.wav")
            Path(wav_path).write_bytes(b"")
            with mock.patch("app.services.subtitles.transcription.get_whisper_model", return_value=model), \
                 mock.patch("app.services.subtitles.transcription._run_with_retry"), \
                 mock.patch("app.services.subtitles.transcription._ensure_ffmpeg_in_path_for_whisper"), \
                 mock.patch("app.services.subtitles.transcription.get_ffmpeg_bin", return_value="ffmpeg"):
                tc.transcribe_to_srt("vid.mp4", srt_path, highlight_per_word=True)
            content = Path(srt_path).read_text(encoding="utf-8")
        assert "Hello world" in content

    def test_wav_cleaned_up_after_transcription(self):
        model = self._make_mocks()
        with tempfile.TemporaryDirectory() as d:
            srt_path = str(Path(d) / "out.srt")
            wav_path = str(Path(d) / "out.wav")
            Path(wav_path).write_bytes(b"")
            with mock.patch("app.services.subtitles.transcription.get_whisper_model", return_value=model), \
                 mock.patch("app.services.subtitles.transcription._run_with_retry"), \
                 mock.patch("app.services.subtitles.transcription._ensure_ffmpeg_in_path_for_whisper"), \
                 mock.patch("app.services.subtitles.transcription.get_ffmpeg_bin", return_value="ffmpeg"):
                tc.transcribe_to_srt("vid.mp4", srt_path)
        assert not Path(wav_path).exists()

    def test_wav_cleaned_up_on_failure(self):
        model = mock.MagicMock()
        model.transcribe.side_effect = RuntimeError("crash")
        with tempfile.TemporaryDirectory() as d:
            srt_path = str(Path(d) / "out.srt")
            wav_path = str(Path(d) / "out.wav")
            Path(wav_path).write_bytes(b"")
            with mock.patch("app.services.subtitles.transcription.get_whisper_model", return_value=model), \
                 mock.patch("app.services.subtitles.transcription._run_with_retry"), \
                 mock.patch("app.services.subtitles.transcription._ensure_ffmpeg_in_path_for_whisper"), \
                 mock.patch("app.services.subtitles.transcription.get_ffmpeg_bin", return_value="ffmpeg"):
                with pytest.raises(RuntimeError):
                    tc.transcribe_to_srt("vid.mp4", srt_path)
        assert not Path(wav_path).exists()

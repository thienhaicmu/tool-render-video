"""
Sprint 6 P0-3 — pin the per-part TTS MP3 cleanup contract.

Per docs/review/TEMP_FILE_AUDIT_2026-06-04.md O-13: the raw per-part
TTS MP3 (and any *.cleaned.mp3 variant emitted by
_maybe_cleanup_narration_audio) used to sit in
`TEMP_DIR/{job_id}/voice/` until the per-job prune. mix_narration_audio
merges the audio into final_part long before that, so the
intermediates are dead weight. Sprint 6 P0-3 wraps the end of
run_part_voice_mix with an unconditional glob-based cleanup.

These tests pin:
- cleanup glob removes `part_{idx:03d}.mp3` and `*.cleaned.mp3` variants
- glob is scoped to the current part — files for OTHER parts in the
  same job survive (idx isolation)
- function still returns None and never raises when cleanup fails
- ctx.voice_audio_path (manual user audio at a different path) is not
  matched by the glob — pinned indirectly by the same isolation rule
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _make_ctx(job_id: str = "test-job") -> MagicMock:
    """Build a ctx that drives run_part_voice_mix past every branch
    cheaply — voice_enabled=False means no TTS runs, no mix runs, and
    we land directly in the cleanup block at the bottom of the
    function."""
    ctx = MagicMock()
    ctx.payload.voice_enabled = False
    ctx.payload.reup_bgm_enable = False
    ctx.payload.subtitle_translate_enabled = False
    ctx.payload.video_codec = "libx264"
    ctx.payload.cleanup_temp_files = False
    ctx.voice_audio_path = None
    ctx.job_id = job_id
    ctx.effective_channel = "manual"
    ctx.cancel_registry.is_cancelled.return_value = False
    return ctx


def _run(ctx, idx, srt_part, translated_srt, final_part, part_manifest):
    from app.orchestration.stages.part_voice_mix import run_part_voice_mix
    return run_part_voice_mix(
        ctx=ctx,
        idx=idx,
        seg={"start": 0.0, "end": 5.0, "duration": 5.0},
        srt_part=srt_part,
        translated_srt_part=translated_srt,
        final_part=final_part,
        part_manifest=part_manifest,
    )


@pytest.fixture
def patched_temp_dir(tmp_path, monkeypatch):
    """Redirect part_voice_mix's TEMP_DIR to a fresh tmp dir so this
    test can drop files into the exact path the cleanup glob targets."""
    monkeypatch.setattr(
        "app.orchestration.stages.part_voice_mix.TEMP_DIR",
        tmp_path,
    )
    return tmp_path


def _stage_voice_files(tmp_root: Path, job_id: str, idx: int, *, cleaned_too: bool) -> dict:
    voice_dir = tmp_root / job_id / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    raw = voice_dir / f"part_{idx:03d}.mp3"
    raw.write_bytes(b"raw tts mp3")
    paths = {"raw": raw}
    if cleaned_too:
        cleaned = voice_dir / f"part_{idx:03d}.cleaned.mp3"
        cleaned.write_bytes(b"cleaned tts mp3")
        paths["cleaned"] = cleaned
    return paths


def _make_srt_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    srt = tmp_path / "p.srt"; srt.write_text("s", encoding="utf-8")
    translated = tmp_path / "p_t.srt"
    final_video = tmp_path / "p.mp4"; final_video.write_bytes(b"v" * 100)
    return srt, translated, final_video


class TestPerPartMp3Cleanup:
    def test_raw_mp3_removed_on_voice_disabled_path(self, patched_temp_dir, tmp_path):
        """Even when no TTS ran (voice_enabled=False), the cleanup glob
        still executes at the end of the function. Drops a file that
        was somehow left behind from a previous run — the unconditional
        cleanup catches it."""
        ctx = _make_ctx(job_id="job-A")
        paths = _stage_voice_files(patched_temp_dir, "job-A", 1, cleaned_too=False)
        srt, translated, final_part = _make_srt_files(tmp_path)
        _run(ctx, 1, srt, translated, final_part, MagicMock())
        assert not paths["raw"].exists()

    def test_cleaned_variant_also_removed(self, patched_temp_dir, tmp_path):
        """`part_001.cleaned.mp3` from _maybe_cleanup_narration_audio
        is matched by the same glob as the raw MP3 — both go."""
        ctx = _make_ctx(job_id="job-A")
        paths = _stage_voice_files(patched_temp_dir, "job-A", 1, cleaned_too=True)
        srt, translated, final_part = _make_srt_files(tmp_path)
        _run(ctx, 1, srt, translated, final_part, MagicMock())
        assert not paths["raw"].exists()
        assert not paths["cleaned"].exists()

    def test_other_parts_artefacts_survive(self, patched_temp_dir, tmp_path):
        """idx isolation: cleaning up part 1 must not touch files
        belonging to part 2."""
        ctx = _make_ctx(job_id="job-A")
        _stage_voice_files(patched_temp_dir, "job-A", 1, cleaned_too=False)
        other = _stage_voice_files(patched_temp_dir, "job-A", 2, cleaned_too=True)
        srt, translated, final_part = _make_srt_files(tmp_path)
        _run(ctx, 1, srt, translated, final_part, MagicMock())
        # Part 2 artefacts untouched.
        assert other["raw"].exists()
        assert other["cleaned"].exists()

    def test_cleanup_noop_when_voice_dir_missing(self, patched_temp_dir, tmp_path):
        """No voice/ dir exists at all (e.g. brand-new render with no
        TTS path taken) — function must not raise."""
        ctx = _make_ctx(job_id="empty-job")
        srt, translated, final_part = _make_srt_files(tmp_path)
        # Should return cleanly even though no voice dir exists.
        assert _run(ctx, 1, srt, translated, final_part, MagicMock()) is None
        assert not (patched_temp_dir / "empty-job" / "voice").exists()

    def test_returns_none_after_cleanup(self, patched_temp_dir, tmp_path):
        """Function contract: side-effect only, returns None. Pinned in
        smoke test already; re-pinned here under the cleanup path."""
        ctx = _make_ctx(job_id="job-A")
        _stage_voice_files(patched_temp_dir, "job-A", 1, cleaned_too=False)
        srt, translated, final_part = _make_srt_files(tmp_path)
        result = _run(ctx, 1, srt, translated, final_part, MagicMock())
        assert result is None

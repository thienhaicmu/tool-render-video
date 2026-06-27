"""A1 audit closure (2026-06-27) — NVENC codec-resolver parity guard.

Background
----------
The NVENC GPU session cap is protected by a semaphore. Two code paths
decide *whether an NVENC encoder will run* using TWO SEPARATE resolver
functions:

  - Callers in ``encoder/clip_renderer.py`` decide whether to acquire
    ``NVENC_SEMAPHORE`` based on
    ``ffmpeg_helpers._resolve_codec(video_codec, encoder_mode)``.

  - ``motion/crop.py`` then resolves the codec AGAIN, independently,
    via ``encoder_helpers.resolve_encoder(video_codec, encoder_mode)``
    (imported as ``_resolve_encoder``) and runs a RAW ``subprocess.Popen``
    at crop.py:756 that does NOT pass through
    ``_run_ffmpeg_with_retry`` — so there is NO auto-lock safety net on
    that path.

Today the two functions are byte-for-byte equivalent in their NVENC
decision, so the caller's acquire decision always matches the codec
crop actually runs. This test PINS that equivalence.

Why it matters
--------------
If a future edit changes ONE resolver (e.g. adds ``av1_nvenc``, or
tweaks the ``h265`` branch) and not the other, the caller can resolve
to a CPU codec (and skip the semaphore) while crop independently
resolves to an NVENC codec and opens an unsemaphored GPU session via
the raw Popen path. That is the exact silent-failure mode where
exceeding the NVENC session cap makes ALL concurrent renders fail at
once. This test turns that divergence into a red CI run instead of a
production crash.

Companion guard: ``test_nvenc_semaphore_external_acquire.py`` pins that
every ``render_motion_aware_crop`` call site acquires the semaphore.
This file pins that the acquire DECISION is computed from a codec
resolution identical to the one crop uses.
"""
from __future__ import annotations

import itertools

import pytest

from app.features.render.engine.encoder import encoder_helpers, ffmpeg_helpers

# The two independent resolvers whose outputs must never diverge.
_resolve_codec = ffmpeg_helpers._resolve_codec          # used by the caller (acquire decision)
_resolve_encoder = encoder_helpers.resolve_encoder      # used by motion/crop.py (actual codec)

# Every codec / mode combination the render pipeline can pass through.
_CODECS = ("h264", "h265", "", "av1", "H265", "H264")
_MODES = ("auto", "nvenc", "cpu", "", "AUTO", "NVENC")

# Availability scenarios: which encoder names report as present + runtime-ready.
_SCENARIOS = {
    "both_nvenc": {"h264_nvenc", "hevc_nvenc"},
    "no_nvenc": set(),
    "only_h264_nvenc": {"h264_nvenc"},
    "only_hevc_nvenc": {"hevc_nvenc"},
}


def _patch_availability(monkeypatch, available: set[str]) -> None:
    """Force BOTH resolvers to see the same NVENC availability.

    ``ffmpeg_helpers`` binds its own module-level aliases
    (``_has_encoder`` / ``_nvenc_runtime_ready``) imported by value from
    ``encoder_helpers``, so each name must be patched independently —
    patching only the ``encoder_helpers`` originals would leave the
    ``ffmpeg_helpers`` aliases pointing at the real (GPU-probing)
    functions.
    """
    def fake_has_encoder(name: str) -> bool:
        return name in available

    def fake_runtime_ready(name: str) -> bool:
        return name in available

    monkeypatch.setattr(encoder_helpers, "has_encoder", fake_has_encoder)
    monkeypatch.setattr(encoder_helpers, "nvenc_runtime_ready", fake_runtime_ready)
    monkeypatch.setattr(ffmpeg_helpers, "_has_encoder", fake_has_encoder)
    monkeypatch.setattr(ffmpeg_helpers, "_nvenc_runtime_ready", fake_runtime_ready)


@pytest.mark.parametrize("scenario", sorted(_SCENARIOS))
@pytest.mark.parametrize("codec,mode", list(itertools.product(_CODECS, _MODES)))
def test_resolvers_agree_on_every_codec_mode_scenario(monkeypatch, scenario, codec, mode):
    """``_resolve_codec`` (caller / acquire decision) and
    ``resolve_encoder`` (motion/crop actual codec) MUST return the same
    encoder for every (codec, mode, availability) combination.

    A mismatch means the caller could skip the NVENC semaphore while
    crop opens an unsemaphored NVENC session — the silent fail-all
    class. See module docstring.
    """
    _patch_availability(monkeypatch, _SCENARIOS[scenario])

    from_caller = _resolve_codec(codec, encoder_mode=mode)
    from_crop = _resolve_encoder(codec, encoder_mode=mode)

    assert from_caller == from_crop, (
        f"A1 regression — NVENC codec resolvers DIVERGED for "
        f"codec={codec!r} mode={mode!r} scenario={scenario}: "
        f"caller(_resolve_codec)={from_caller!r} vs "
        f"crop(resolve_encoder)={from_crop!r}. The acquire decision no "
        f"longer matches the codec motion/crop.py actually runs through "
        f"its raw Popen path — an NVENC session can be opened without "
        f"holding NVENC_SEMAPHORE. Re-unify the two resolvers before "
        f"landing."
    )


def test_parity_matrix_actually_exercises_nvenc_selection(monkeypatch):
    """Guard against a vacuous parity test: confirm that under
    ``both_nvenc`` availability the resolvers genuinely select an NVENC
    encoder (not a CPU fallback that would make agreement trivial).
    """
    _patch_availability(monkeypatch, _SCENARIOS["both_nvenc"])

    # h264 + auto must select the NVENC encoder on both paths.
    assert _resolve_codec("h264", encoder_mode="auto") == "h264_nvenc"
    assert _resolve_encoder("h264", encoder_mode="auto") == "h264_nvenc"
    # h265 + auto must select the HEVC NVENC encoder on both paths.
    assert _resolve_codec("h265", encoder_mode="auto") == "hevc_nvenc"
    assert _resolve_encoder("h265", encoder_mode="auto") == "hevc_nvenc"


def test_cpu_fallback_is_consistent_when_nvenc_absent(monkeypatch):
    """When no NVENC encoder is available, BOTH resolvers must fall back
    to the same CPU encoder (libx264 / libx265). This is the path where
    the caller correctly skips the semaphore — crop must agree so it
    does not run NVENC unguarded.
    """
    _patch_availability(monkeypatch, _SCENARIOS["no_nvenc"])

    assert _resolve_codec("h264", encoder_mode="auto") == "libx264"
    assert _resolve_encoder("h264", encoder_mode="auto") == "libx264"
    assert _resolve_codec("h265", encoder_mode="nvenc") == "libx265"
    assert _resolve_encoder("h265", encoder_mode="nvenc") == "libx265"

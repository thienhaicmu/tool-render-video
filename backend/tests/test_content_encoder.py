"""W5-7 regression guard — content NVENC encode gate (OPT-IN, default CPU).

The content scene-mux burn (``content_scene_render._content_gpu_encode``) and
the xfade assembler (``content_assembler._gpu_encode``) MAY use NVENC
(h264_nvenc), but only as an opt-in. Gate:

  - default / any value other than auto|nvenc|gpu  → libx264 (byte-identical);
  - ``CONTENT_ENCODER`` in {auto, nvenc, gpu}       → NVENC when the GPU is ready.

NVENC was measured (RTX 3060) to give NO speedup for content scenes and to steal
a scarce shared NVENC session from clip/recap renders, so the DEFAULT is CPU.
QSV is intentionally NOT used so the CPU path is byte-identical libx264. The
``NVENC_SEMAPHORE`` acquire is delegated to ``_run_ffmpeg_with_retry`` (auto-locks
on an h264_nvenc argv), so these files carry no hand-rolled acquire;
``content_background.py`` is separately pinned to NEVER use NVENC by
``test_nvenc_semaphore_external_acquire.py``.
"""
from __future__ import annotations

import app.features.render.engine.stages.content_scene_render as csr
import app.features.render.engine.stages.content_assembler as ca
import app.features.render.engine.encoder.ffmpeg_helpers as fh


def test_default_is_cpu(monkeypatch):
    """Unset CONTENT_ENCODER → CPU even when the GPU is ready (conservative)."""
    monkeypatch.delenv("CONTENT_ENCODER", raising=False)
    monkeypatch.setattr(fh, "nvenc_available", lambda: True)
    assert csr._content_gpu_encode() is False
    assert ca._gpu_encode() is False


def test_explicit_cpu_forces_cpu(monkeypatch):
    monkeypatch.setenv("CONTENT_ENCODER", "cpu")
    monkeypatch.setattr(fh, "nvenc_available", lambda: True)
    assert csr._content_gpu_encode() is False
    assert ca._gpu_encode() is False


def test_opt_in_enables_nvenc_when_available(monkeypatch):
    """auto|nvenc + a ready GPU → NVENC; a not-ready GPU → CPU fallback."""
    for mode in ("auto", "nvenc"):
        monkeypatch.setenv("CONTENT_ENCODER", mode)
        monkeypatch.setattr(fh, "nvenc_available", lambda: True)
        assert csr._content_gpu_encode() is True
        assert ca._gpu_encode() is True
        monkeypatch.setattr(fh, "nvenc_available", lambda: False)
        assert csr._content_gpu_encode() is False
        assert ca._gpu_encode() is False


def test_gate_never_raises(monkeypatch):
    """Sacred Contract #3 spirit — any probe failure → safe CPU path, no raise."""
    monkeypatch.setenv("CONTENT_ENCODER", "auto")

    def _boom():
        raise RuntimeError("nvenc probe blew up")

    monkeypatch.setattr(fh, "nvenc_available", _boom)
    assert csr._content_gpu_encode() is False
    assert ca._gpu_encode() is False

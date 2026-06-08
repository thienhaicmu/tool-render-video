"""Tests for the motion_crop_quality indicator (audit FINDING-T01).

Surfaces the silent-degrade signal: when MediaPipe is unavailable, the
motion-aware crop pipeline falls back to OpenCV Haar (face-only, no
pose). This was invisible to the FE before Batch 3 — now `motion_crop_quality`
is reported via the ai-diagnostics endpoint and the FE can hint
"install AI extras for best crop".
"""
from __future__ import annotations

import pytest

from app.features.render.ai import dependencies as deps


def test_motion_crop_quality_returns_high_when_mediapipe_available(monkeypatch):
    monkeypatch.setattr(deps, "has_mediapipe", lambda: True)
    assert deps.motion_crop_quality() == "high"


def test_motion_crop_quality_returns_low_when_mediapipe_absent(monkeypatch):
    monkeypatch.setattr(deps, "has_mediapipe", lambda: False)
    assert deps.motion_crop_quality() == "low"


def test_motion_crop_quality_unknown_on_probe_failure(monkeypatch):
    def _boom():
        raise RuntimeError("simulated probe failure")

    monkeypatch.setattr(deps, "has_mediapipe", _boom)
    assert deps.motion_crop_quality() == "unknown"


def test_dependency_status_includes_motion_crop_quality():
    status = deps.get_ai_dependency_status()
    assert "motion_crop_quality" in status
    assert status["motion_crop_quality"] in {"high", "low", "unknown"}


def test_dependency_status_motion_crop_quality_aligns_with_mediapipe(monkeypatch):
    """The motion_crop_quality field in the status dict must agree with
    the mediapipe field — a divergence would mean the indicator is lying
    to the FE.
    """
    monkeypatch.setattr(deps, "has_mediapipe", lambda: True)
    status = deps.get_ai_dependency_status()
    assert status["mediapipe"] is True
    assert status["motion_crop_quality"] == "high"

    monkeypatch.setattr(deps, "has_mediapipe", lambda: False)
    status = deps.get_ai_dependency_status()
    assert status["mediapipe"] is False
    assert status["motion_crop_quality"] == "low"


def test_motion_crop_quality_never_raises():
    """Contract: this helper must never propagate an exception to its
    caller, even under monkeypatch chaos.
    """
    # Direct call must not raise.
    result = deps.motion_crop_quality()
    assert isinstance(result, str)

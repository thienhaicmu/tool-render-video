"""P3 perf — hardware-accelerated source decode helper.

Pins that ENABLE_HWDECODE is opt-in (off by default → no pipeline change) and
that when on, `-hwaccel <method>` is inserted right before the first -i (so the
existing CPU filters still receive system-memory frames). The execution path
falls back to software decode on failure — exercised in the integration tests;
here we pin the pure argv shaping + gate.
"""
from __future__ import annotations

from app.features.render.engine.encoder import clip_renderer as cr


def test_hwdecode_off_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_HWDECODE", raising=False)
    assert cr._hwdecode_enabled() is False


def test_hwdecode_enabled_via_env(monkeypatch):
    monkeypatch.setenv("ENABLE_HWDECODE", "1")
    assert cr._hwdecode_enabled() is True


def test_add_hwaccel_inserts_before_first_input(monkeypatch):
    monkeypatch.delenv("HWDECODE_METHOD", raising=False)
    cmd = ["ffmpeg", "-y", "-i", "src.mp4", "-vf", "scale=1920:1080",
           "-c:v", "libx264", "out.mp4"]
    got = cr._add_hwaccel_decode(cmd)
    assert got[:4] == ["ffmpeg", "-y", "-hwaccel", "auto"]
    assert got[4:6] == ["-i", "src.mp4"]          # -hwaccel precedes the input
    assert got[-1] == "out.mp4"                     # rest of argv intact


def test_add_hwaccel_method_override(monkeypatch):
    monkeypatch.setenv("HWDECODE_METHOD", "qsv")
    got = cr._add_hwaccel_decode(["ffmpeg", "-y", "-i", "a.mp4", "out.mp4"])
    assert "-hwaccel" in got and got[got.index("-hwaccel") + 1] == "qsv"


def test_add_hwaccel_noop_without_input():
    args = ["ffmpeg", "-version"]
    assert cr._add_hwaccel_decode(args) == args     # no -i → unchanged

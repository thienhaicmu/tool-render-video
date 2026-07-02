"""Pin gate MICRO_PACING_GPU (P1-A) — chọn encoder cho pass micro-pacing.

Mặc định BẬT (quyết định chủ dự án 2026-07 — máy render khách có GPU).
Bất biến còn lại: máy không resolve ra GPU encoder phải nhận đúng nguyên
văn cờ legacy libx264 medium crf17 (bit-identical), và kill switch
``MICRO_PACING_GPU=0`` phải ép legacy kể cả khi có GPU.

Literal codec NVENC cố ý KHÔNG xuất hiện trong clip_ops.py — chúng sống
trong encoder_helpers.gpu_pacing_flags để giữ phân loại false-positive của
tests/test_nvenc_semaphore_external_acquire.py.
"""
from app.features.render.engine.encoder.clip_ops import (
    _PACING_LEGACY_FLAGS,
    _pacing_encode_flags,
)

_LEGACY = ["-c:v", "libx264", "-preset", "medium", "-crf", "17"]
_NVENC_H264 = "h264" + "_nvenc"  # tránh literal trực tiếp trong test của clip_ops


def test_default_env_without_gpu_uses_exact_legacy_flags(monkeypatch):
    # Máy không GPU (resolver trả CPU codec): default BẬT vẫn phải ra
    # legacy nguyên văn — khách không có NVIDIA không đổi hành vi.
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.delenv("MICRO_PACING_GPU", raising=False)
    monkeypatch.setattr(eh, "resolve_encoder", lambda c, m="auto": "libx264")
    flags, used_gpu = _pacing_encode_flags("h264", "auto")
    assert flags == _LEGACY
    assert used_gpu is False


def test_default_env_with_gpu_uses_gpu_flags(monkeypatch):
    # Pin default BẬT: env không set + máy có GPU → cờ GPU.
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.delenv("MICRO_PACING_GPU", raising=False)
    monkeypatch.setattr(eh, "resolve_encoder", lambda c, m="auto": _NVENC_H264)
    flags, used_gpu = _pacing_encode_flags("h264", "auto")
    assert used_gpu is True
    assert flags[:2] == ["-c:v", _NVENC_H264]


def test_kill_switch_env_zero_forces_legacy_even_with_gpu(monkeypatch):
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.setenv("MICRO_PACING_GPU", "0")
    monkeypatch.setattr(eh, "resolve_encoder", lambda c, m="auto": _NVENC_H264)
    flags, used_gpu = _pacing_encode_flags("h264", "auto")
    assert flags == _LEGACY
    assert used_gpu is False


def test_gpu_flags_carry_quality_targets(monkeypatch):
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.setenv("MICRO_PACING_GPU", "1")
    monkeypatch.setattr(eh, "resolve_encoder", lambda c, m="auto": _NVENC_H264)
    flags, used_gpu = _pacing_encode_flags("h264", "auto")
    assert used_gpu is True
    # p5 = mapping chuẩn của "medium" cho NVENC (encoder_helpers.map_preset_for_encoder)
    assert flags[2:4] == ["-preset", "p5"]
    # Cùng mục tiêu chất lượng với legacy: cq 17, VBR chất lượng cao.
    _i = flags.index("-cq")
    assert flags[_i + 1] == "17"
    assert "vbr_hq" in flags


def test_legacy_constant_not_mutated_between_calls(monkeypatch):
    # _pacing_encode_flags trả bản copy — caller sửa list không được làm
    # bẩn hằng dùng cho fallback GPU→CPU.
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.setenv("MICRO_PACING_GPU", "0")
    flags, _ = _pacing_encode_flags("h264", "auto")
    flags.append("--dirty")
    assert _pacing_encode_flags("h264", "auto")[0] == _LEGACY
    assert _PACING_LEGACY_FLAGS == _LEGACY
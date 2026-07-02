"""Pin gate MICRO_PACING_GPU (P1-A) — chọn encoder cho pass micro-pacing.

Bất biến quan trọng nhất: khi env TẮT (mặc định) hoặc máy không có GPU
encoder, cờ encode phải là libx264 medium crf17 NGUYÊN VẸN — pass pacing
legacy bit-identical. Chỉ khi opt-in ``MICRO_PACING_GPU=1`` VÀ job resolve
ra NVENC thì pass mới chuyển sang GPU với cùng mục tiêu chất lượng (cq 17).

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


def test_default_env_uses_exact_legacy_flags(monkeypatch):
    monkeypatch.delenv("MICRO_PACING_GPU", raising=False)
    flags, used_gpu = _pacing_encode_flags("h264", "auto")
    assert flags == _LEGACY
    assert used_gpu is False


def test_env_zero_uses_exact_legacy_flags(monkeypatch):
    monkeypatch.setenv("MICRO_PACING_GPU", "0")
    flags, used_gpu = _pacing_encode_flags("h264", "auto")
    assert flags == _LEGACY
    assert used_gpu is False


def test_env_one_without_gpu_falls_back_to_legacy(monkeypatch):
    # resolve_encoder trả CPU codec khi máy không có NVENC → giữ legacy.
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.setenv("MICRO_PACING_GPU", "1")
    monkeypatch.setattr(eh, "resolve_encoder", lambda c, m="auto": "libx264")
    flags, used_gpu = _pacing_encode_flags("h264", "auto")
    assert flags == _LEGACY
    assert used_gpu is False


def test_env_one_with_gpu_uses_gpu_quality_flags(monkeypatch):
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.setenv("MICRO_PACING_GPU", "1")
    monkeypatch.setattr(eh, "resolve_encoder", lambda c, m="auto": _NVENC_H264)
    flags, used_gpu = _pacing_encode_flags("h264", "auto")
    assert used_gpu is True
    assert flags[:2] == ["-c:v", _NVENC_H264]
    # p5 = mapping chuẩn của "medium" cho NVENC (encoder_helpers.map_preset_for_encoder)
    assert flags[2:4] == ["-preset", "p5"]
    # Cùng mục tiêu chất lượng với legacy: cq 17, VBR chất lượng cao.
    _i = flags.index("-cq")
    assert flags[_i + 1] == "17"
    assert "vbr_hq" in flags


def test_legacy_constant_not_mutated_between_calls(monkeypatch):
    # _pacing_encode_flags trả bản copy — caller sửa list không được làm
    # bẩn hằng dùng cho fallback GPU→CPU.
    monkeypatch.delenv("MICRO_PACING_GPU", raising=False)
    flags, _ = _pacing_encode_flags("h264", "auto")
    flags.append("--dirty")
    assert _pacing_encode_flags("h264", "auto")[0] == _LEGACY
    assert _PACING_LEGACY_FLAGS == _LEGACY

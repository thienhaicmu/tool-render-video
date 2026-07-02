"""Pin default card-first của chuỗi encoder (quyết định chủ dự án 2026-07).

``ENABLE_QSV`` mặc định BẬT: resolver đi NVENC → QSV → CPU, mỗi bậc có
probe runtime thật (máy không có phần cứng tương ứng tự rơi bậc dưới).
Kill switch ``ENABLE_QSV=0`` phải ép bỏ bậc QSV kể cả khi phần cứng có.
"""
from app.features.render.engine.encoder.encoder_helpers import _maybe_qsv, qsv_enabled


def test_qsv_enabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_QSV", raising=False)
    assert qsv_enabled() is True


def test_qsv_kill_switch(monkeypatch):
    monkeypatch.setenv("ENABLE_QSV", "0")
    assert qsv_enabled() is False


def test_kill_switch_skips_qsv_tier_even_when_hardware_present(monkeypatch):
    # Cô lập logic env: giả phần cứng QSV sẵn sàng — env=0 vẫn phải trả None
    # (caller rơi tiếp về CPU).
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.setenv("ENABLE_QSV", "0")
    monkeypatch.setattr(eh, "has_encoder", lambda name: True)
    monkeypatch.setattr(eh, "qsv_runtime_ready", lambda name: True)
    assert _maybe_qsv("h264") is None
    assert _maybe_qsv("h265") is None


def test_default_resolves_qsv_when_hardware_present(monkeypatch):
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.delenv("ENABLE_QSV", raising=False)
    monkeypatch.setattr(eh, "has_encoder", lambda name: True)
    monkeypatch.setattr(eh, "qsv_runtime_ready", lambda name: True)
    assert _maybe_qsv("h264") == "h264_qsv"
    assert _maybe_qsv("h265") == "hevc_qsv"


def test_runtime_probe_failure_falls_through_to_cpu(monkeypatch):
    # Driver hỏng / máy không iGPU: probe fail → None → caller dùng libx264.
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.delenv("ENABLE_QSV", raising=False)
    monkeypatch.setattr(eh, "has_encoder", lambda name: True)
    monkeypatch.setattr(eh, "qsv_runtime_ready", lambda name: False)
    assert _maybe_qsv("h264") is None


def test_gpu_pacing_flags_accepts_qsv(monkeypatch):
    # Pass micro-pacing cũng theo luật card-first: QSV → global_quality 17.
    import app.features.render.engine.encoder.encoder_helpers as eh

    monkeypatch.setattr(eh, "resolve_encoder", lambda c, m="auto": "h264_qsv")
    flags = eh.gpu_pacing_flags("h264", "auto")
    assert flags is not None
    assert flags[:2] == ["-c:v", "h264_qsv"]
    _i = flags.index("-global_quality")
    assert flags[_i + 1] == "17"

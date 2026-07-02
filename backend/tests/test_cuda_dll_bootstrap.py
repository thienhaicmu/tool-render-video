"""Pin bootstrap DLL CUDA cho faster-whisper trên Windows.

Wheel ``nvidia-*-cu12`` cài DLL vào ``site-packages/nvidia/<pkg>/bin`` —
không nằm trên loader search path. Thiếu ``_ensure_cuda_dll_dirs``,
ctranslate2 fail load cublas/cudnn và Whisper âm thầm rơi về CPU int8
trên máy khách có GPU. Bootstrap phải: tìm đúng các thư mục bin có DLL,
idempotent, never-raise, no-op khi wheel chưa cài.
"""
import app.features.render.engine.subtitle.transcription.adapters as adapters
from app.features.render.engine.subtitle.transcription.adapters import (
    _cuda_dll_bin_dirs,
    _ensure_cuda_dll_dirs,
)


def _fake_nvidia_tree(tmp_path):
    root = tmp_path / "nvidia"
    (root / "cublas" / "bin").mkdir(parents=True)
    (root / "cublas" / "bin" / "cublas64_12.dll").write_bytes(b"x")
    (root / "cudnn" / "bin").mkdir(parents=True)
    (root / "cudnn" / "bin" / "cudnn64_9.dll").write_bytes(b"x")
    # Package không có bin/ — phải bị bỏ qua.
    (root / "cuda_runtime" / "lib").mkdir(parents=True)
    # bin/ rỗng (không DLL) — phải bị bỏ qua.
    (root / "nvjitlink" / "bin").mkdir(parents=True)
    return root


def test_bin_dirs_found_only_with_dlls(tmp_path):
    root = _fake_nvidia_tree(tmp_path)
    dirs = _cuda_dll_bin_dirs([str(root)])
    names = sorted(d.parent.name for d in dirs)
    assert names == ["cublas", "cudnn"]


def test_bin_dirs_empty_and_missing_roots():
    assert _cuda_dll_bin_dirs([]) == []
    assert _cuda_dll_bin_dirs(None) == []
    assert _cuda_dll_bin_dirs(["Z:/khong/ton/tai"]) == []


def test_ensure_never_raises_and_is_idempotent(monkeypatch):
    # Reset cờ module để test độc lập với các lần gọi trước trong session.
    monkeypatch.setattr(adapters, "_CUDA_DLL_BOOTSTRAP_DONE", False)
    monkeypatch.setattr(adapters, "_CUDA_DLL_DIRS_FOUND", [])
    first = _ensure_cuda_dll_dirs()
    second = _ensure_cuda_dll_dirs()
    assert isinstance(first, list)
    assert first == second  # idempotent — lần 2 trả cache


def test_ensure_registers_fake_wheel_dirs(monkeypatch, tmp_path):
    # Giả wheel nvidia đã cài: find_spec trỏ vào cây tmp — bootstrap phải
    # đăng ký 2 thư mục bin và prepend chúng vào PATH.
    import importlib.util
    root = _fake_nvidia_tree(tmp_path)

    class _Spec:
        submodule_search_locations = [str(root)]

    monkeypatch.setattr(adapters, "_CUDA_DLL_BOOTSTRAP_DONE", False)
    monkeypatch.setattr(adapters, "_CUDA_DLL_DIRS_FOUND", [])
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: _Spec())
    dirs = _ensure_cuda_dll_dirs()
    if adapters.os.name == "nt":
        assert len(dirs) == 2
        assert all(d in adapters.os.environ["PATH"] for d in dirs)
    else:  # non-Windows: bootstrap là no-op theo thiết kế
        assert dirs == []


def test_diagnostics_exposes_whisper_block():
    from app.features.render.ai.diagnostics import get_ai_runtime_diagnostics

    diag = get_ai_runtime_diagnostics()
    w = diag.get("whisper")
    assert isinstance(w, dict)
    for key in (
        "faster_whisper_installed",
        "cuda_dll_dirs_registered",
        "ctranslate2_cuda_devices",
        "resolved_device",
        "resolved_compute_type",
    ):
        assert key in w

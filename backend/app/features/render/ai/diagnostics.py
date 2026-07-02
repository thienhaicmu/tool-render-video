"""
diagnostics.py — AI runtime diagnostics for packaging and observability.

Returns a compact, read-only snapshot of AI system health.
Never raises. Never loads models. Never triggers embeddings.
Uses dependency detectors only — no heavy imports at call time.

Public API:
    get_ai_runtime_diagnostics() -> dict
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.diagnostics")


def get_ai_runtime_diagnostics() -> dict:
    """Return compact AI runtime diagnostics.

    Safe to call from any context — startup, health checks, packaging tests.
    Never raises. Never loads sentence-transformers, faiss, or any heavy lib.
    """
    try:
        return _collect()
    except Exception as exc:
        logger.debug("ai_diagnostics_collection_failed: %s", exc)
        return {
            "dependencies": {},
            "startup_safe": True,
            "embedding_available": False,
            "vector_store": {"faiss_available": False, "fallback_mode": True},
            "memory": {
                "sqlite_available": False,
                "count": None,
                "db_path": None,
                "warnings": ["diagnostics_collection_error"],
            },
            "whisper": {
                "faster_whisper_installed": False,
                "cuda_dll_dirs_registered": [],
                "ctranslate2_cuda_devices": None,
                "resolved_device": None,
                "resolved_compute_type": None,
            },
            "warnings": ["diagnostics_collection_error"],
        }


def _collect() -> dict:
    from app.features.render.ai.dependencies import get_ai_dependency_status, has_sentence_transformers, has_faiss

    dep_status = get_ai_dependency_status()
    warnings: list[str] = []

    # Check embedding library presence — NOT model load
    embedding_available = has_sentence_transformers()

    # Vector store: FAISS or cosine fallback
    faiss_ok = has_faiss()
    vs_status = {
        "faiss_available": faiss_ok,
        "fallback_mode": not faiss_ok,
    }

    mem_status = _memory_diagnostics(warnings)
    whisper_status = _whisper_diagnostics(warnings)

    return {
        "dependencies": dep_status,
        "startup_safe": True,
        "embedding_available": embedding_available,
        "vector_store": vs_status,
        "memory": mem_status,
        "whisper": whisper_status,
        "warnings": warnings,
    }


def _whisper_diagnostics(warnings: list[str]) -> dict:
    """Trạng thái thiết bị Whisper — trả lời câu "máy này transcribe bằng
    GPU hay CPU?" qua một HTTP call thay vì phải đọc log máy khách.

    Import ctranslate2 (native lib, nhẹ) nhưng KHÔNG load model nào —
    giữ tinh thần "diagnostics không kéo heavy model" của module này.
    Never raises.
    """
    out: dict = {
        "faster_whisper_installed": False,
        "cuda_dll_dirs_registered": [],
        "ctranslate2_cuda_devices": None,
        "resolved_device": None,
        "resolved_compute_type": None,
    }
    try:
        import importlib.util
        out["faster_whisper_installed"] = (
            importlib.util.find_spec("faster_whisper") is not None
        )
    except Exception:
        pass
    try:
        from app.features.render.engine.subtitle.transcription.adapters import (
            _detect_fw_device_compute,
            _ensure_cuda_dll_dirs,
        )
        out["cuda_dll_dirs_registered"] = _ensure_cuda_dll_dirs()
        device, compute = _detect_fw_device_compute()
        out["resolved_device"] = device
        out["resolved_compute_type"] = compute
        import ctranslate2  # noqa: PLC0415
        out["ctranslate2_cuda_devices"] = int(ctranslate2.get_cuda_device_count())
    except Exception as exc:
        warnings.append(f"whisper_diagnostics_partial: {exc}")
    if out["faster_whisper_installed"] and out["resolved_device"] == "cpu":
        # Máy có GPU NVIDIA mà thấy dòng này → thiếu wheel nvidia-*-cu12
        # (cài requirements-ai.txt) hoặc driver; xem cuda_dll_dirs_registered.
        warnings.append("whisper_running_on_cpu")
    return out


def _memory_diagnostics(warnings: list[str]) -> dict:
    """Return static "not available" status — RAG memory store removed in Phase G."""
    return {
        "sqlite_available": False,
        "count": None,
        "db_path": None,
        "warnings": ["memory_store_retired"],
    }

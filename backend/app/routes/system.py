"""
routes/system.py — system resource snapshot endpoint (S4.2).

Surfaces CPU / GPU / disk usage so the Clip Studio status bar can show
live load dots instead of hard-coded "off" placeholders. Designed for
*polling* (3 s cadence from the FE), so every call is cheap and the
endpoint never raises — missing libs and missing GPUs collapse to
null in the response and the FE renders the corresponding dot as off.

Optional deps (lazy-imported per Sacred Contract pattern):
- ``psutil``     — CPU % + RAM usage. When unavailable, both fields
                   return null. Install via ``pip install psutil``.
- ``pynvml``     — NVIDIA GPU stats (utilisation, memory). When absent
                   or no NVIDIA driver is present, gpu_* fields return
                   null. Install via ``pip install pynvml``.

The endpoint is deliberately namespaced under ``/api/system`` so future
system-level concerns (boot status, version probes, etc.) can join
without polluting ``/api/settings`` (user prefs) or ``/api/jobs`` (job
state). Zero side effects — pure read.
"""
from __future__ import annotations

import shutil
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/system", tags=["system"])


class ResourceSnapshot(BaseModel):
    """Single point-in-time read of host resources.

    Every field is Optional so the FE can show a dot per metric without
    every dot depending on every other metric being available. ``null``
    in any field means "unable to measure" (lib missing, hardware absent,
    or transient failure); the FE renders such dots as off/gray.
    """
    cpu_percent: Optional[float] = None
    ram_percent: Optional[float] = None
    ram_used_mb: Optional[int] = None
    ram_total_mb: Optional[int] = None
    gpu_percent: Optional[float] = None
    gpu_mem_used_mb: Optional[int] = None
    gpu_mem_total_mb: Optional[int] = None
    gpu_name: Optional[str] = None
    disk_free_mb: Optional[int] = None
    disk_total_mb: Optional[int] = None


def _measure_cpu_ram() -> dict:
    """Best-effort CPU + RAM read via psutil. Returns empty dict when
    psutil isn't installed so callers can merge into the response without
    knowing the lib state."""
    try:
        import psutil  # type: ignore
    except Exception:
        return {}
    out: dict = {}
    try:
        # interval=None returns the cumulative delta since the last call;
        # over a 3 s poll cadence that's effectively the moving average.
        # First call after import returns 0.0 — acceptable for a status
        # dot that animates over multiple polls.
        out["cpu_percent"] = float(psutil.cpu_percent(interval=None))
    except Exception:
        pass
    try:
        vm = psutil.virtual_memory()
        out["ram_percent"] = float(vm.percent)
        out["ram_used_mb"] = int(vm.used / 1024 / 1024)
        out["ram_total_mb"] = int(vm.total / 1024 / 1024)
    except Exception:
        pass
    return out


def _measure_gpu_smi() -> dict:
    """Fallback NVIDIA GPU read via the ``nvidia-smi`` CLI.

    pynvml needs the driver's ``nvml.dll`` on the DLL search path, which is
    absent on some machines that still have the NVENC/CUDA *runtime* (encode
    works, but ``nvmlInit`` raises ``NVMLError_LibraryNotFound``). ``nvidia-smi``
    ships with every full driver install and is more reliable cross-machine.
    Best-effort — returns {} on any failure. Reads GPU 0 only."""
    import os
    import shutil
    import subprocess
    exe = shutil.which("nvidia-smi")
    if exe is None:
        _win = r"C:\Windows\System32\nvidia-smi.exe"
        exe = _win if os.path.isfile(_win) else None
    if exe is None:
        return {}
    try:
        proc = subprocess.run(
            [exe, "--query-gpu=name,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        line = (proc.stdout or "").strip().splitlines()
        if not line:
            return {}
        name, util, used, total = (x.strip() for x in line[0].split(",")[:4])
        out: dict = {"gpu_name": name or None}
        try:
            out["gpu_percent"] = float(util)
        except Exception:
            pass
        try:
            out["gpu_mem_used_mb"] = int(float(used))
            out["gpu_mem_total_mb"] = int(float(total))
        except Exception:
            pass
        return out
    except Exception:
        return {}


def _measure_gpu() -> dict:
    """Best-effort NVIDIA GPU read. Tries pynvml (nvml.dll) first, then falls
    back to the nvidia-smi CLI when the NVML shared library isn't found (some
    hosts have the NVENC runtime but not nvml.dll). Reads GPU 0 only — the
    NVENC semaphore in encoder/ffmpeg_helpers.py is single-GPU as well
    so a multi-GPU host with the renderer pinned to one card is the
    expected steady state."""
    try:
        import pynvml  # type: ignore
    except Exception:
        return _measure_gpu_smi()
    out: dict = {}
    try:
        pynvml.nvmlInit()
    except Exception:
        return _measure_gpu_smi()
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            out["gpu_percent"] = float(util.gpu)
        except Exception:
            pass
        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            out["gpu_mem_used_mb"] = int(mem.used / 1024 / 1024)
            out["gpu_mem_total_mb"] = int(mem.total / 1024 / 1024)
        except Exception:
            pass
        try:
            raw = pynvml.nvmlDeviceGetName(handle)
            out["gpu_name"] = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        except Exception:
            pass
    except Exception:
        pass
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    return out


def _measure_disk() -> dict:
    """stdlib disk usage — no optional lib needed. Reads the drive the
    process is running on, which on Windows is whatever drive the venv
    is installed on (typically the same as the data dir)."""
    try:
        usage = shutil.disk_usage("/")
        return {
            "disk_free_mb": int(usage.free / 1024 / 1024),
            "disk_total_mb": int(usage.total / 1024 / 1024),
        }
    except Exception:
        return {}


@router.get("/resources", response_model=ResourceSnapshot)
def get_system_resources() -> ResourceSnapshot:
    """Return a current resource snapshot. Never 5xx — every measurement
    fails silently to null. Designed for high-frequency polling.
    """
    data: dict = {}
    data.update(_measure_cpu_ram())
    data.update(_measure_gpu())
    data.update(_measure_disk())
    return ResourceSnapshot(**data)

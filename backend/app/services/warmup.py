"""
Startup warmup — pre-download & pre-load mọi thứ cần thiết.

Chạy background ngay khi server khởi động:
  1. ffmpeg / ffprobe  — kiểm tra binary
  2. yt-dlp            — kiểm tra version
  3. OpenCV cascades   — load face/body models
  4. Whisper models    — tiny (75MB) + base (145MB) + small (488MB)
  5. Ollama            — start service nếu chưa chạy, pull model nếu chưa có

Expose GET /api/warmup/status để UI hiển thị tiến trình.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# State
# ──────────────────────────────────────────────────────────────────────────────

_state: Dict[str, dict] = {}
_lock = threading.Lock()
_warmup_done = threading.Event()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def _set(key: str, status: str, message: str = "", size_mb: float = 0.0):
    with _lock:
        _state[key] = {
            "key": key,
            "status": status,   # pending | running | ready | skipped | error
            "message": message,
            "size_mb": round(size_mb, 1),
        }


def get_status() -> dict:
    with _lock:
        items = list(_state.values())
    total = len(items)
    ready_or_skip = sum(1 for i in items if i["status"] in ("ready", "skipped"))
    errors = [i["key"] for i in items if i["status"] == "error"]
    in_progress = [i for i in items if i["status"] == "running"]
    return {
        "done": _warmup_done.is_set(),
        "ready_count": ready_or_skip,
        "total_count": total,
        "all_ready": ready_or_skip == total and total > 0,
        "in_progress": in_progress[0]["message"] if in_progress else "",
        "items": items,
        "errors": errors,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 1. ffmpeg
# ──────────────────────────────────────────────────────────────────────────────

def _warmup_ffmpeg():
    _set("ffmpeg", "running", "Checking ffmpeg...")
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        ffmpeg = get_ffmpeg_bin()
        r = subprocess.run([ffmpeg, "-version"], capture_output=True, timeout=10)
        if r.returncode != 0:
            raise RuntimeError("ffmpeg -version failed")
        ver = r.stdout.decode(errors="ignore").splitlines()[0] if r.stdout else "ok"
        _set("ffmpeg", "ready", ver[:80])
    except Exception as exc:
        _set("ffmpeg", "error", f"ffmpeg not found: {exc}")
        logger.warning("Warmup ffmpeg: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# 2. yt-dlp
# ──────────────────────────────────────────────────────────────────────────────

def _warmup_ytdlp():
    _set("yt_dlp", "running", "Checking yt-dlp...")
    try:
        import yt_dlp
        version = getattr(yt_dlp, "__version__", "unknown")
        _set("yt_dlp", "ready", f"yt-dlp {version}")
    except Exception as exc:
        _set("yt_dlp", "error", str(exc))
        logger.warning("Warmup yt-dlp: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# 3. OpenCV cascades
# ──────────────────────────────────────────────────────────────────────────────

def _warmup_cascades():
    _set("opencv_cascades", "running", "Loading face/body detection models...")
    try:
        import cv2
        face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        body = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_fullbody.xml")
        if face.empty() or body.empty():
            raise RuntimeError("Cascade XML files missing")
        _set("opencv_cascades", "ready", "Face + body cascades loaded")
    except Exception as exc:
        _set("opencv_cascades", "error", str(exc))
        logger.warning("Warmup cascades: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Whisper models
# ──────────────────────────────────────────────────────────────────────────────

_WHISPER_MODELS = [
    ("tiny",  75),
    ("base",  145),
    ("small", 488),
]


_WHISPER_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "whisper_cache"
_WHISPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _warmup_whisper(name: str, size_mb: int):
    key = f"whisper_{name}"
    _set(key, "running", f"Loading Whisper {name} (~{size_mb}MB)...", size_mb)
    try:
        import whisper
        whisper.load_model(name, download_root=str(_WHISPER_CACHE_DIR))
        _set(key, "ready", f"Whisper {name} ready", size_mb)
        logger.info("Warmup: Whisper %s ready (cache=%s)", name, _WHISPER_CACHE_DIR)
    except Exception as exc:
        _set(key, "error", f"Whisper {name} failed: {exc}", size_mb)
        logger.warning("Warmup Whisper %s: %s", name, exc)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Ollama — install check, auto-start, model pull
# ──────────────────────────────────────────────────────────────────────────────

def _find_ollama_bin() -> str | None:
    """Find ollama binary on Windows/Mac/Linux."""
    found = shutil.which("ollama")
    if found:
        return found
    # Common Windows install paths
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path("C:/Program Files/Ollama/ollama.exe"),
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def _ollama_api(path: str, payload: dict | None = None, timeout: int = 10) -> dict:
    """Call Ollama REST API. Returns parsed JSON or raises."""
    import urllib.request
    url = f"{OLLAMA_URL}{path}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _ollama_running() -> bool:
    try:
        _ollama_api("/api/tags", timeout=3)
        return True
    except Exception:
        return False


def _ollama_model_exists(model: str) -> bool:
    try:
        data = _ollama_api("/api/tags", timeout=5)
        names = [m.get("name", "") for m in data.get("models", [])]
        # Match "llama3.2:3b" or "llama3.2" etc.
        base = model.split(":")[0]
        return any(model in n or base in n for n in names)
    except Exception:
        return False


def _start_ollama_service(ollama_bin: str):
    """Start `ollama serve` in background. Returns immediately."""
    try:
        # Redirect Ollama model cache to project D: drive
        _ollama_data_dir = Path(__file__).resolve().parents[3] / "data" / "ollama"
        _ollama_data_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.setdefault("OLLAMA_MODELS", str(_ollama_data_dir / "models"))
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            env=env,
        )
        # Wait up to 8s for it to come up
        import time
        for _ in range(16):
            time.sleep(0.5)
            if _ollama_running():
                return True
        return False
    except Exception as exc:
        logger.warning("Warmup: failed to start ollama serve: %s", exc)
        return False


def _pull_ollama_model(model: str):
    """
    Pull an Ollama model using streaming API.
    Updates warmup state with live progress.
    """
    import urllib.request
    key = "ollama_model"
    url = f"{OLLAMA_URL}/api/pull"
    payload = json.dumps({"name": model, "stream": True}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            for raw_line in resp:
                line = raw_line.decode(errors="ignore").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue

                status_msg = chunk.get("status", "")
                total = chunk.get("total", 0)
                completed = chunk.get("completed", 0)

                if total and completed:
                    pct = int(completed / total * 100)
                    size_mb = round(total / 1024 / 1024, 0)
                    _set(key, "running",
                         f"Pulling {model}: {pct}% ({size_mb:.0f}MB)",
                         round(total / 1024 / 1024, 1))
                elif status_msg:
                    _set(key, "running", f"{model}: {status_msg}")

                if chunk.get("status") == "success":
                    break
    except Exception as exc:
        raise RuntimeError(f"Model pull failed: {exc}") from exc


def _warmup_ollama():
    key_svc = "ollama_service"
    key_mdl = "ollama_model"
    _set(key_svc, "running", "Checking Ollama...")
    _set(key_mdl, "pending", f"Model {OLLAMA_MODEL} pending")

    # 1. Find binary
    ollama_bin = _find_ollama_bin()
    if not ollama_bin:
        _set(key_svc, "skipped", "Ollama not installed — captions use Smart Template")
        _set(key_mdl, "skipped", "Skipped (Ollama not installed)")
        logger.info("Warmup: Ollama not installed, skipping")
        return

    _set(key_svc, "running", f"Ollama found: {ollama_bin}")

    # 2. Start service if not running
    if not _ollama_running():
        _set(key_svc, "running", "Starting Ollama service...")
        ok = _start_ollama_service(ollama_bin)
        if not ok:
            _set(key_svc, "error", "Ollama installed but could not start service")
            _set(key_mdl, "skipped", "Skipped (service not running)")
            return

    _set(key_svc, "ready", f"Ollama service running at {OLLAMA_URL}")
    logger.info("Warmup: Ollama service ready")

    # 3. Pull model if not already downloaded
    _set(key_mdl, "running", f"Checking model {OLLAMA_MODEL}...")
    if _ollama_model_exists(OLLAMA_MODEL):
        _set(key_mdl, "ready", f"{OLLAMA_MODEL} already downloaded")
        logger.info("Warmup: Ollama model %s already exists", OLLAMA_MODEL)
        return

    _set(key_mdl, "running", f"Pulling {OLLAMA_MODEL} (first time)...")
    logger.info("Warmup: pulling Ollama model %s", OLLAMA_MODEL)
    try:
        _pull_ollama_model(OLLAMA_MODEL)
        _set(key_mdl, "ready", f"{OLLAMA_MODEL} downloaded and ready")
        logger.info("Warmup: Ollama model %s ready", OLLAMA_MODEL)
    except Exception as exc:
        _set(key_mdl, "error", f"Pull failed: {exc}")
        logger.warning("Warmup: Ollama model pull failed: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# Main runner
# ──────────────────────────────────────────────────────────────────────────────

def _run_warmup():
    logger.info("Warmup: starting background pre-load")

    # Init all keys as pending
    _set("ffmpeg", "pending", "ffmpeg pending")
    _set("yt_dlp", "pending", "yt-dlp pending")
    _set("opencv_cascades", "pending", "OpenCV cascades pending")
    for name, size in _WHISPER_MODELS:
        _set(f"whisper_{name}", "pending", f"Whisper {name} pending", size)
    _set("ollama_service", "pending", "Ollama service pending")
    _set("ollama_model",   "pending", f"Ollama model {OLLAMA_MODEL} pending")

    # Fast checks (no download)
    _warmup_ffmpeg()
    _warmup_ytdlp()
    _warmup_cascades()

    # Whisper: tiny first → user can render với fast profile ngay
    for name, size in _WHISPER_MODELS:
        _warmup_whisper(name, size)

    # Ollama: last (heaviest download, optional)
    _warmup_ollama()

    _warmup_done.set()
    st = get_status()
    logger.info(
        "Warmup complete: %d/%d ready/skipped, errors: %s",
        st["ready_count"], st["total_count"], st["errors"] or "none",
    )


def start_warmup():
    """Launch warmup in a daemon background thread. Non-blocking."""
    t = threading.Thread(target=_run_warmup, name="warmup", daemon=True)
    t.start()

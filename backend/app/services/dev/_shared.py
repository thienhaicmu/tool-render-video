"""Bottom-layer utilities shared across dev/ sub-modules.

Audit MT-1 (Batch 10J 2026-06-06): pure helpers extracted from the
1542-LOC ``app.services.dev_commands`` monolith. No inter-module deps
beyond stdlib + ``app.core.config``.
"""
from __future__ import annotations

import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _run_git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(PROJECT_ROOT), capture_output=True, text=True)


def _http_get(url: str, timeout: int = 6) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None, str(e)


def _service_url() -> str:
    host = str(os.getenv("HOST", "127.0.0.1")).strip() or "127.0.0.1"
    port = str(os.getenv("PORT", "8000")).strip() or "8000"
    return f"http://{host}:{port}"


def _read_tail_lines(path: Path, max_bytes: int = 500_000, max_lines: int = 3000) -> list[str]:
    size = path.stat().st_size
    start = max(0, size - max_bytes)
    with path.open("rb") as f:
        if start:
            f.seek(start)
            f.readline()
        data = f.read().decode("utf-8", errors="replace")
    lines = data.splitlines()
    return lines[-max_lines:] if len(lines) > max_lines else lines


def _err_code(text: str) -> str:
    m = re.search(r"\b([A-Z]{2}\d{3,4})\b", text or "")
    return m.group(1) if m else ""


def _to_epoch(ts: str) -> float | None:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        # Supports ISO forms like 2026-04-15T08:00:00Z
        raw = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(raw).timestamp()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            continue
    return None


def _severity(level: str) -> int:
    lv = (level or "").upper()
    if lv in {"CRITICAL", "FATAL"}:
        return 4
    if lv == "ERROR":
        return 3
    return 1


def _existing_repo_files(rels: list[str]) -> list[str]:
    out = []
    for rel in rels:
        p = PROJECT_ROOT / rel
        if p.exists():
            out.append(str(p))
    return out

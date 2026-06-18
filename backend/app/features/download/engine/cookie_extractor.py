"""
Chrome cookie extractor for Windows — no pywin32 required.

Reads Chrome's SQLite cookie database directly in read-only mode
(works even while Chrome is running, bypasses the file-lock issue
that blocks yt-dlp's built-in --cookies-from-browser on Windows).

Decryption support:
  v10 / v11  — Chrome 80–126: AES-256-GCM, master key from Local State via DPAPI
  v20+       — Chrome 127+:   App-Bound Encryption (cannot be decrypted outside Chrome
                               process space); cookies are exported as empty-value
                               placeholders so session state is still sent
  legacy     — Pre-Chrome 80: raw DPAPI per-cookie

Output: Netscape cookies.txt format consumed by yt-dlp via cookiefile=...

Usage:
    path = extract_youtube_cookies(output_path)  # returns True on success
"""
from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.downloader.cookies")

# Registrable domains we keep cookies for (YouTube auth flows through both).
# Matched by suffix so subdomains (accounts.google.com, music.youtube.com,
# .youtube.com host_key form, etc.) are all retained — the previous exact-set
# match dropped most relevant Google/YouTube cookies.
_YOUTUBE_BASE_DOMAINS = ("youtube.com", "google.com")


def _is_youtube_auth_host(host: str) -> bool:
    h = (host or "").lstrip(".").lower()
    return any(h == d or h.endswith("." + d) for d in _YOUTUBE_BASE_DOMAINS)

# Chrome profile paths to try (default profile first)
def _chrome_paths() -> list[tuple[Path, Path]]:
    """Return (cookie_db, local_state) pairs for each Chrome-family browser."""
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        local_app / "Google/Chrome/User Data",
        local_app / "Microsoft/Edge/User Data",
        local_app / "BraveSoftware/Brave-Browser/User Data",
        local_app / "Chromium/User Data",
        local_app / "Vivaldi/User Data",
    ]
    results = []
    for base in candidates:
        if not base.is_dir():
            continue
        state = base / "Local State"
        if not state.is_file():
            continue
        for profile in ("Default", "Profile 1", "Profile 2"):
            for sub in ("Network/Cookies", "Cookies"):
                db = base / profile / sub
                if db.is_file():
                    results.append((db, state))
    return results


# ── Windows DPAPI (no pywin32) ────────────────────────────────────────────────

class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_decrypt(ciphertext: bytes) -> Optional[bytes]:
    try:
        buf      = ctypes.create_string_buffer(ciphertext)
        blob_in  = _DataBlob(len(ciphertext), buf)
        blob_out = _DataBlob()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0,
            ctypes.byref(blob_out),
        )
        if not ok:
            return None
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result
    except Exception as exc:
        logger.debug("dpapi_decrypt error: %s", exc)
        return None


# ── AES-256-GCM (Chrome v10/v11) ─────────────────────────────────────────────

def _aes_gcm_decrypt(key: bytes, ciphertext: bytes) -> Optional[bytes]:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = ciphertext[3:15]
        data  = ciphertext[15:]
        return AESGCM(key).decrypt(nonce, data, None)
    except Exception as exc:
        logger.debug("aes_gcm_decrypt error: %s", exc)
        return None


def _load_master_key(local_state_path: Path) -> Optional[bytes]:
    try:
        raw = json.loads(local_state_path.read_text(encoding="utf-8"))
        b64 = raw.get("os_crypt", {}).get("encrypted_key", "")
        if not b64:
            return None
        enc_key = base64.b64decode(b64)
        if enc_key[:5] == b"DPAPI":
            enc_key = enc_key[5:]
        return _dpapi_decrypt(enc_key)
    except Exception as exc:
        logger.debug("load_master_key error: %s", exc)
        return None


# ── Netscape format ───────────────────────────────────────────────────────────

def _netscape_line(host: str, http_only: bool, path: str, secure: bool,
                   expiry: int, name: str, value: str) -> str:
    return "\t".join([
        host,
        "TRUE" if host.startswith(".") else "FALSE",
        path,
        "TRUE" if secure else "FALSE",
        str(expiry),
        name,
        value,
    ])


def _chrome_epoch_to_unix(chrome_ts: int) -> int:
    if chrome_ts <= 0:
        return int(time.time()) + 3600 * 24 * 365 * 2
    return (chrome_ts - 11_644_473_600_000_000) // 1_000_000


def _to_str(v: object) -> str:
    """Safely convert a column value that may arrive as bytes or str."""
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", errors="ignore")
    return str(v) if v is not None else ""


def _to_bytes(v: object) -> bytes:
    """Safely convert encrypted_value to bytes regardless of sqlite3 type affinity."""
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v)
    if isinstance(v, str):
        return v.encode("latin-1", errors="replace")
    return b""


# ── SQLite read helpers ───────────────────────────────────────────────────────

def _open_db_readonly(cookie_db: Path) -> Optional[sqlite3.Connection]:
    """
    Open Chrome's cookie DB read-only.

    Strategy 1: sqlite3 URI with mode=ro&immutable=1 — works for most profiles.
    Strategy 2: copy to a temp file first — for WAL-locked DBs where even
                read-only URI fails (happens with Edge and non-default Chrome
                profiles that are being actively written).
    """
    # Strategy 1 — in-place read-only URI
    try:
        uri  = f"file:{cookie_db.as_posix()}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        # text_factory=bytes: receive ALL columns as bytes, avoids UTF-8
        # decode errors on encrypted_value which contains raw binary data.
        conn.text_factory = bytes
        # Quick smoke-test
        conn.execute("SELECT count(*) FROM cookies").fetchone()
        return conn
    except Exception:
        pass

    # Strategy 2 — copy to temp file (bypasses WAL lock)
    conn = None
    _fd, _tmp_name = tempfile.mkstemp(suffix=".db", prefix="chrome_cookies_")
    os.close(_fd)
    tmp = Path(_tmp_name)
    try:
        shutil.copy2(str(cookie_db), str(tmp))
        conn = sqlite3.connect(str(tmp), check_same_thread=False)
        conn.text_factory = bytes
        conn.execute("SELECT count(*) FROM cookies").fetchone()

        # Wrap close to auto-delete the temp file
        _orig_close = conn.close
        def _close_and_delete():
            try:
                _orig_close()
            finally:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
        conn.close = _close_and_delete  # type: ignore[method-assign]
        return conn
    except Exception:
        # Smoke-test / copy failed before close-wrapping — clean up so we don't
        # leak the temp .db on every locked-and-unreadable profile.
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return None


# ── Main export function ──────────────────────────────────────────────────────

def extract_youtube_cookies(output_path: Path) -> bool:
    """
    Extract YouTube auth cookies from Chrome and write Netscape cookies.txt.

    Returns True on success (at least one cookie written), False otherwise.

    Chrome 127+ (v20 App-Bound Encryption):
      v20 cookies cannot be decrypted outside Chrome's process space.
      They are exported with an empty value so the cookie name/domain still
      reaches yt-dlp — this alone is often enough for age-gating checks.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for cookie_db, local_state in _chrome_paths():
        master_key = _load_master_key(local_state)

        conn = _open_db_readonly(cookie_db)
        if conn is None:
            logger.warning(
                "cookie_extractor: cannot open %s (locked by browser, skipping)",
                cookie_db,
            )
            continue

        try:
            rows = conn.execute(
                "SELECT host_key, path, is_secure, expires_utc, "
                "name, encrypted_value, is_httponly "
                "FROM cookies "
                "WHERE host_key LIKE '%youtube%' OR host_key LIKE '%google%'"
            ).fetchall()
        except Exception as exc:
            logger.warning("cookie_extractor: query failed %s — %s", cookie_db, exc)
            conn.close()
            continue
        conn.close()

        if not rows:
            continue

        lines: list[str] = []
        n_v10 = n_v20 = n_dpapi = n_fail = 0

        for row in rows:
            host_raw, path_raw, secure, expiry_chrome, name_raw, enc_val_raw, http_only = row

            host     = _to_str(host_raw)
            path     = _to_str(path_raw)
            name     = _to_str(name_raw)
            enc_val  = _to_bytes(enc_val_raw)

            if not _is_youtube_auth_host(host):
                continue

            value = ""
            if enc_val:
                prefix = enc_val[:3]
                if prefix in (b"v10", b"v11"):
                    if master_key:
                        plain = _aes_gcm_decrypt(master_key, enc_val)
                        value = plain.decode("utf-8", errors="replace") if plain else ""
                        n_v10 += 1
                    else:
                        n_fail += 1
                elif enc_val[:3] == b"v20" or (len(enc_val) > 3 and enc_val[1:3] == b"v2"):
                    # Chrome 127+ App-Bound Encryption — cannot decrypt outside Chrome
                    # Export with empty value; cookie presence alone helps some checks
                    value = ""
                    n_v20 += 1
                else:
                    # Legacy DPAPI (pre-Chrome 80)
                    plain = _dpapi_decrypt(enc_val)
                    value = plain.decode("utf-8", errors="replace") if plain else ""
                    n_dpapi += 1

            expiry_unix = _chrome_epoch_to_unix(int(expiry_chrome or 0))
            lines.append(
                _netscape_line(host, bool(http_only), path, bool(secure), expiry_unix, name, value)
            )

        if lines:
            header = (
                "# Netscape HTTP Cookie File\n"
                "# Generated by AI Clip Studio cookie extractor\n"
                f"# Extracted: {datetime.now(timezone.utc).isoformat()}\n"
                f"# Source: {cookie_db}\n"
                f"# Cookies: v10/v11={n_v10} v20(no-decrypt)={n_v20} dpapi={n_dpapi} fail={n_fail}\n\n"
            )
            output_path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
            logger.info(
                "cookie_extractor: wrote %d cookies → %s  (v10/v11=%d v20=%d dpapi=%d fail=%d)",
                len(lines), output_path, n_v10, n_v20, n_dpapi, n_fail,
            )
            if n_v20 > 0 and n_v10 == 0:
                logger.warning(
                    "cookie_extractor: ALL cookies are v20 (Chrome 127+ App-Bound Encryption). "
                    "Values cannot be decrypted — YouTube auth may still fail. "
                    "Workaround: export cookies manually via a browser extension "
                    "(e.g. 'Get cookies.txt LOCALLY') and set YTDLP_COOKIEFILE=<path>.",
                )
            return True

    logger.warning("cookie_extractor: no Chrome profile with YouTube cookies found")
    return False

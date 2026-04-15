import json
import os
import re
import shutil
import subprocess
import time
import uuid
import threading
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright._impl._errors import TargetClosedError

from app.core.config import CHANNELS_DIR, REPORTS_DIR
from app.services.report_service import append_rows

UTC_MINUS_9 = timezone(timedelta(hours=-9))
_UPLOAD_RUN_LOCK = threading.Lock()
_UPLOAD_RUNS: dict[str, dict] = {}


def _term_log(msg: str):
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    try:
        print(f"[{ts}] [UPLOAD] {msg}", flush=True)
    except Exception:
        pass


def _safe_account_key(account_key: str | None) -> str:
    key = (account_key or "default").strip().lower()
    key = re.sub(r"[^a-z0-9_-]+", "_", key)
    key = key.strip("_")
    return key or "default"


def _resolve_config_mode(config_mode: str | None) -> str:
    mode = (config_mode or "ui").strip().lower()
    if mode not in {"ui", "json", "mixed"}:
        return "ui"
    return mode


def _filter_runtime_overrides(overrides: dict, config_mode: str) -> dict:
    mode = _resolve_config_mode(config_mode)
    if mode == "json":
        return {}
    if mode == "ui":
        return dict(overrides)
    # mixed: only apply explicit non-empty values and positive feature flags.
    filtered: dict = {}
    for k, v in (overrides or {}).items():
        if v is None:
            continue
        if isinstance(v, str):
            if not v.strip():
                continue
            filtered[k] = v
            continue
        if isinstance(v, bool):
            if v:
                filtered[k] = v
            continue
        filtered[k] = v
    return filtered


def _upload_settings_path(channel_code: str) -> Path:
    return CHANNELS_DIR / channel_code / "account" / "upload_settings.json"


def _default_upload_settings(channel_code: str) -> dict:
    return {
        "channel_code": channel_code,
        "video_output_subdir": "video_out",
        "default_video_input_dir": "video_out",
        "timezone_schedule": "LOCAL",
        "schedule_slots": ["07:00", "17:00"],
        "network_mode": "direct",
        "proxy_server": "",
        "proxy_username": "",
        "proxy_password": "",
        "proxy_bypass": "",
        "use_gpm": False,
        "gpm_profile_id": "",
        "gpm_browser_ws": "",
        "browser_preference": "chromeportable",
        "browser_executable": "",
        "upload_url": "https://www.tiktok.com/upload",
    }


def load_upload_settings(channel_code: str) -> dict:
    p = _upload_settings_path(channel_code)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        data = _default_upload_settings(channel_code)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("invalid settings")
        merged = _default_upload_settings(channel_code)
        merged.update(data)
        changed = False
        default_input = str(merged.get("default_video_input_dir") or "").replace("\\", "/").strip("/")
        if default_input.lower() in {"video", "upload/video_output"}:
            merged["default_video_input_dir"] = "video_out"
            changed = True
        if str(merged.get("video_output_subdir") or "").strip().lower() == "video":
            merged["video_output_subdir"] = "video_out"
            changed = True
        tz_value = str(merged.get("timezone_schedule") or "").strip().upper()
        if tz_value == "UTC-9":
            merged["timezone_schedule"] = "LOCAL"
            changed = True
        if changed:
            p.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        return merged
    except Exception:
        data = _default_upload_settings(channel_code)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data


def save_upload_settings(channel_code: str, updates: dict | None = None) -> dict:
    p = _upload_settings_path(channel_code)
    current = load_upload_settings(channel_code)
    merged = dict(current)
    for k, v in (updates or {}).items():
        if v is None:
            continue
        merged[k] = v
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return merged


def _channel_base_dir(channel_code: str, root_path: str | None = None) -> Path:
    rp = str(root_path or "").strip()
    if rp:
        return Path(rp) / channel_code
    return CHANNELS_DIR / channel_code


def _profile_base(channel_code: str, account_key: str, root_path: str | None = None) -> Path:
    return _channel_base_dir(channel_code, root_path=root_path) / "account" / "profiles" / _safe_account_key(account_key)


def _preferred_browser_key(browser_preference: str | None) -> str:
    pref = str(browser_preference or "chromeportable").strip().lower()
    return "firefoxportable" if "firefox" in pref else "chromeportable"


def _default_user_data_dir(
    channel_code: str,
    account_key: str,
    browser_preference: str | None,
    root_path: str | None = None,
) -> Path:
    key = _safe_account_key(account_key)
    browser_key = _preferred_browser_key(browser_preference)
    # Per-account + per-browser profile folder (first-time profile naming by account_key)
    # Example: .../account/profiles/t1_main/browser-profile/chromeportable_t1_main
    return _profile_base(channel_code, key, root_path=root_path).resolve() / "browser-profile" / f"{browser_key}_{key}"


def _default_profile_config(channel_code: str, account_key: str, settings: dict | None = None) -> dict:
    base = (CHANNELS_DIR / channel_code).resolve()
    profile_root = _profile_base(channel_code, account_key).resolve()
    settings = settings or load_upload_settings(channel_code)
    default_input_subdir = str(settings.get("default_video_input_dir") or settings.get("video_output_subdir") or "Video")
    browser_pref = settings.get("browser_preference", "chromeportable")
    return {
        "channel_code": channel_code,
        "account_key": _safe_account_key(account_key),
        "platform": "tiktok",
        "user_data_dir": str(_default_user_data_dir(channel_code, account_key, browser_pref)),
        "video_input_dir": str((base / default_input_subdir).resolve()),
        "uploaded_dir": str(base / "upload" / "uploaded" / _safe_account_key(account_key)),
        "failed_dir": str(base / "upload" / "failed" / _safe_account_key(account_key)),
        "hashtags_file": str(base / "hashtag" / "hashtags.txt"),
        "schedule_slots": settings.get("schedule_slots", ["07:00", "17:00"]),
        "timezone_schedule": settings.get("timezone_schedule", "LOCAL"),
        "upload_url": settings.get("upload_url", "https://www.tiktok.com/upload"),
        "network_mode": settings.get("network_mode", "direct"),
        "proxy_server": settings.get("proxy_server", ""),
        "proxy_username": settings.get("proxy_username", ""),
        "proxy_password": settings.get("proxy_password", ""),
        "proxy_bypass": settings.get("proxy_bypass", ""),
        "use_gpm": bool(settings.get("use_gpm", False)),
        "gpm_profile_id": settings.get("gpm_profile_id", ""),
        "gpm_browser_ws": settings.get("gpm_browser_ws", ""),
        "browser_preference": browser_pref,
        "browser_executable": settings.get("browser_executable", ""),
        "login_username": "",
        "login_password": "",
        "tiktok_username": "",
        "tiktok_password": "",
        "mail_username": "",
        "mail_password": "",
        "selectors": {
            # Each value is a list of fallback selectors tried in order.
            # String values are also accepted (treated as single-item list).
            "file_input": ["input[type='file']"],
            "upload_option": [
                "button:has-text('Select video')",
                "button:has-text('Upload')",
                "button:has-text('Choose file')",
            ],
            "caption": [
                "[data-e2e='caption-input']",
                "div[data-e2e='caption-input']",
                "[contenteditable='true'][data-text]",
                "[contenteditable='true']",
                "div[contenteditable]",
            ],
            "schedule_toggle": [
                "[data-e2e='schedule-video-toggle']",
                "[aria-label*='schedule' i]",
                "button:has-text('Schedule')",
                "label:has-text('Schedule')",
            ],
            "schedule_date_input": [
                "[data-e2e='date-input']",
                "input[placeholder*='Date']",
                "input[placeholder*='date']",
                "input[placeholder*='ngày' i]",
                "input[type='date']",
            ],
            "schedule_time_input": [
                "[data-e2e='time-input']",
                "input[placeholder*='Time']",
                "input[placeholder*='time']",
                "input[placeholder*='giờ' i]",
                "input[type='time']",
            ],
            "submit": [
                "[data-e2e='post-button']",
                "button:has-text('Post')",
                "button:has-text('Submit')",
                "button:has-text('Đăng')",
                "button[type='submit']",
            ],
            "login_username": [
                "input[name='username']",
                "input[type='text'][autocomplete='username']",
                "input[placeholder*='Email' i]",
                "input[placeholder*='Phone' i]",
                "input[placeholder*='Username' i]",
            ],
            "login_password": [
                "input[name='password']",
                "input[type='password']",
            ],
            "login_submit": [
                "button[type='submit']",
                "button:has-text('Log in')",
                "button:has-text('Login')",
                "button:has-text('Dang nhap')",
            ],
        },
    }


def _profile_config_path(channel_code: str, account_key: str) -> Path:
    return _profile_base(channel_code, account_key) / "account.json"


def ensure_upload_account_profile(channel_code: str, account_key: str = "default", overrides: dict | None = None):
    key = _safe_account_key(account_key)
    settings = load_upload_settings(channel_code)
    profile_root = _profile_base(channel_code, key)
    profile_root.mkdir(parents=True, exist_ok=True)
    cfg_path = _profile_config_path(channel_code, key)
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    else:
        cfg = _default_profile_config(channel_code, key, settings=settings)

    # Backward compatibility: import legacy account.json if present and profile config is new.
    legacy = CHANNELS_DIR / channel_code / "account" / "account.json"
    if (not cfg_path.exists()) and legacy.exists():
        try:
            legacy_cfg = json.loads(legacy.read_text(encoding="utf-8"))
            cfg.update(legacy_cfg)
        except Exception:
            pass

    cfg["account_key"] = key
    cfg["channel_code"] = channel_code
    cfg.setdefault("schedule_slots", settings.get("schedule_slots", ["07:00", "17:00"]))
    cfg.setdefault("timezone_schedule", settings.get("timezone_schedule", "LOCAL"))
    cfg.setdefault("upload_url", settings.get("upload_url", "https://www.tiktok.com/upload"))
    cfg.setdefault("network_mode", settings.get("network_mode", "direct"))
    cfg.setdefault("proxy_server", settings.get("proxy_server", ""))
    cfg.setdefault("proxy_username", settings.get("proxy_username", ""))
    cfg.setdefault("proxy_password", settings.get("proxy_password", ""))
    cfg.setdefault("proxy_bypass", settings.get("proxy_bypass", ""))
    cfg.setdefault("use_gpm", bool(settings.get("use_gpm", False)))
    cfg.setdefault("gpm_profile_id", settings.get("gpm_profile_id", ""))
    cfg.setdefault("gpm_browser_ws", settings.get("gpm_browser_ws", ""))
    cfg.setdefault("browser_preference", settings.get("browser_preference", "chromeportable"))
    cfg.setdefault("browser_executable", settings.get("browser_executable", ""))
    cfg.setdefault("login_username", "")
    cfg.setdefault("login_password", "")
    cfg.setdefault("tiktok_username", "")
    cfg.setdefault("tiktok_password", "")
    cfg.setdefault("mail_username", "")
    cfg.setdefault("mail_password", "")
    if "video_input_dir" not in cfg or not str(cfg.get("video_input_dir") or "").strip():
        default_input_subdir = str(settings.get("default_video_input_dir") or settings.get("video_output_subdir") or "Video")
        cfg["video_input_dir"] = str(((CHANNELS_DIR / channel_code).resolve() / default_input_subdir).resolve())
    if overrides:
        for k, v in overrides.items():
            if v is None:
                continue
            if isinstance(v, str) and v == "":
                continue
            cfg[k] = v

    _sync_profile_dir_for_browser(cfg)

    cfg = _normalize_channel_paths(channel_code, cfg)
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    # Ensure all required directories exist.
    for p in (
        Path(cfg["user_data_dir"]),
        Path(cfg["video_input_dir"]),
        Path(cfg["uploaded_dir"]),
        Path(cfg["failed_dir"]),
        Path(CHANNELS_DIR / channel_code / "logs"),
    ):
        p.mkdir(parents=True, exist_ok=True)
    return cfg


def list_upload_accounts(channel_code: str):
    root = CHANNELS_DIR / channel_code / "account" / "profiles"
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()])


def load_channel_config(channel_code: str, account_key: str = "default", overrides: dict | None = None):
    return ensure_upload_account_profile(channel_code, account_key=account_key, overrides=overrides)


def _normalize_channel_paths(channel_code: str, cfg: dict):
    base = (CHANNELS_DIR / channel_code).resolve()
    key = _safe_account_key(cfg.get("account_key"))
    preferred_user_data_fallback = _default_user_data_dir(channel_code, key, cfg.get("browser_preference"))

    def _map_path(value: str | None, fallback: Path) -> str:
        if not value:
            return str(fallback)
        s = str(value).strip().replace("\\", "/")
        legacy_prefix = f"/data/channels/{channel_code}/"
        if s.startswith(legacy_prefix):
            rel = s[len(legacy_prefix):]
            return str((base / rel).resolve())
        p = Path(value)
        if p.is_absolute():
            return str(p)
        return str((base / p).resolve())

    cfg["user_data_dir"] = _map_path(cfg.get("user_data_dir"), preferred_user_data_fallback)
    cfg["video_input_dir"] = _map_path(cfg.get("video_input_dir"), base / "video_out")
    cfg["uploaded_dir"] = _map_path(cfg.get("uploaded_dir"), base / "upload" / "uploaded")
    cfg["failed_dir"] = _map_path(cfg.get("failed_dir"), base / "upload" / "failed")
    cfg["hashtags_file"] = _map_path(cfg.get("hashtags_file"), base / "hashtag" / "hashtags.txt")
    browser_exec = str(cfg.get("browser_executable") or "").strip()
    if browser_exec:
        cfg["browser_executable"] = _map_path(browser_exec, base / "browser-profile")
    return cfg


def _parse_timezone(label: str | None):
    raw_label = (label or "LOCAL").strip().upper()
    if raw_label in {"LOCAL", "SYSTEM"}:
        return datetime.now().astimezone().tzinfo or UTC_MINUS_9
    raw = raw_label.replace("UTC", "")
    if not raw:
        return UTC_MINUS_9
    sign = 1
    if raw.startswith("+"):
        sign = 1
        raw = raw[1:]
    elif raw.startswith("-"):
        sign = -1
        raw = raw[1:]
    try:
        hours = int(raw.split(":")[0])
        return timezone(timedelta(hours=sign * hours))
    except Exception:
        return UTC_MINUS_9


def _parse_schedule_slots(raw_slots) -> list[tuple[int, int]]:
    if not isinstance(raw_slots, list) or not raw_slots:
        return [(7, 0), (17, 0)]
    parsed = []
    for item in raw_slots:
        text = str(item).strip()
        m = re.match(r"^(\d{1,2}):(\d{2})$", text)
        if not m:
            continue
        h = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= h <= 23 and 0 <= mm <= 59:
            parsed.append((h, mm))
    return sorted(parsed) if parsed else [(7, 0), (17, 0)]


def compute_schedule_slots(count: int, tz: timezone = UTC_MINUS_9, slot_times: list[tuple[int, int]] | None = None):
    slot_times = slot_times or [(7, 0), (17, 0)]
    now_local = datetime.now(tz)
    slots = []
    day_offset = 0
    while len(slots) < max(0, count):
        current_day = now_local.date() + timedelta(days=day_offset)
        for hour, minute in slot_times:
            slot_local = datetime.combine(current_day, dt_time(hour=hour, minute=minute), tzinfo=tz)
            if slot_local > now_local:
                slots.append(slot_local)
            if len(slots) >= count:
                break
        day_offset += 1
    return [x.isoformat() for x in slots]


def _extract_part_no(name: str) -> int:
    stem = Path(name).stem.lower()
    m = re.search(r"(?:^|[_\-\s])part[_\-\s]*(\d{1,5})(?:$|[_\-\s])", f" {stem} ")
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    m = re.search(r"(\d{1,5})$", stem)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    return 10**9


def _resolve_video_input_dir(cfg: dict) -> Path:
    primary = Path(cfg["video_input_dir"])
    channel_base = (CHANNELS_DIR / str(cfg.get("channel_code") or "")).resolve()
    candidates = [primary, channel_base / "video_out", channel_base / "upload" / "video_output"]
    # Common fallbacks for existing channel layouts.
    candidates.extend([
        channel_base / "upload" / "source",
        channel_base / "video_out",
        channel_base / "Video",
    ])
    # Prefer folder that actually has video files.
    for c in candidates:
        if c.exists() and c.is_dir() and any(_collect_video_files(c)):
            return c
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    primary.mkdir(parents=True, exist_ok=True)
    return primary


def _collect_video_files(input_dir: Path) -> list[Path]:
    exts = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
    files = []
    try:
        for p in input_dir.iterdir():
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)
    except Exception:
        return []
    return files


def list_ranked_videos(channel_code: str, max_items: int = 0):
    cfg = load_channel_config(channel_code)
    input_dir = _resolve_video_input_dir(cfg)
    files = sorted(
        _collect_video_files(input_dir),
        key=lambda p: (_extract_part_no(p.name), p.name.lower()),
    )
    if max_items and max_items > 0:
        files = files[:max_items]
    return files


def _list_ranked_videos_from_cfg(cfg: dict, max_items: int = 0, selected_files: list[str] | None = None):
    input_dir = _resolve_video_input_dir(cfg)
    files = sorted(
        _collect_video_files(input_dir),
        key=lambda p: (_extract_part_no(p.name), p.name.lower()),
    )
    if selected_files:
        requested = {str(x or "").strip().lower() for x in selected_files if str(x or "").strip()}
        if requested:
            files = [p for p in files if p.name.lower() in requested]
    if max_items and max_items > 0:
        files = files[:max_items]
    return files


def _read_hashtags(hashtags_file: str | None):
    if not hashtags_file:
        return []
    path = Path(hashtags_file)
    if not path.exists():
        return []
    tags = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("#"):
            line = f"#{line}"
        tags.append(line)
    return tags


def _slug_to_text(stem: str):
    text = stem.replace("_", " ").replace("-", " ")
    text = re.sub(r"\bpart\s*\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:140] if text else "New video"


def _build_caption(
    video_path: Path,
    caption_prefix: str,
    hashtags: list[str],
    include_hashtags: bool,
    caption_mode: str = "template",
):
    """
    Build TikTok caption.

    caption_mode:
      "template" — smart hook từ transcript/tên file (mặc định, luôn hoạt động)
      "ollama"   — Ollama local LLM (cần cài Ollama)
      "claude"   — Claude API (cần ANTHROPIC_API_KEY)
      "auto"     — thử claude → ollama → template
    """
    from app.services.caption_engine import generate_caption

    # Tìm SRT đi kèm video (cùng tên, đuôi .srt)
    srt_path = video_path.with_suffix(".srt")
    if not srt_path.exists():
        srt_path = None

    tags = hashtags if include_hashtags else []

    try:
        caption = generate_caption(
            srt_path=srt_path,
            video_title=_slug_to_text(video_path.stem),
            hashtags=tags,
            mode=caption_mode,
        )
    except Exception as exc:
        # Fallback tuyệt đối: tên file + hashtag
        import logging
        logging.getLogger(__name__).warning("caption_engine failed: %s", exc)
        base = _slug_to_text(video_path.stem)
        tag_str = " ".join(tags[:8]) if tags else ""
        caption = f"{base} {tag_str}".strip()

    # Thêm prefix nếu có
    prefix = (caption_prefix or "").strip()
    if prefix:
        caption = f"{prefix} {caption}".strip()

    return caption[:2200]


def _safe_move(src: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    candidate = dst_dir / src.name
    if not candidate.exists():
        shutil.move(str(src), candidate)
        return candidate
    stem = src.stem
    suffix = src.suffix
    idx = 1
    while True:
        candidate = dst_dir / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            shutil.move(str(src), candidate)
            return candidate
        idx += 1


def _try_locator(page, selector_or_list, timeout: int = 10000):
    """
    Try selectors in order, return the first visible one.
    Accepts a single selector string or a list of fallback selectors.
    Raises the last exception if none match.
    """
    candidates = selector_or_list if isinstance(selector_or_list, list) else [selector_or_list]
    per_timeout = max(2000, timeout // max(1, len(candidates)))
    last_exc: Exception = RuntimeError(f"No selector matched: {candidates}")
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=per_timeout)
            return loc
        except Exception as exc:
            last_exc = exc
    raise last_exc


def _selector_list(selector_or_list) -> list[str]:
    if isinstance(selector_or_list, list):
        return [str(x).strip() for x in selector_or_list if str(x).strip()]
    s = str(selector_or_list or "").strip()
    return [s] if s else []


def _wait_any_selector(page, selector_or_list, timeout_ms: int = 20000):
    candidates = _selector_list(selector_or_list)
    if not candidates:
        return None
    deadline = time.time() + (timeout_ms / 1000.0)
    last_exc = None
    while time.time() < deadline:
        for sel in candidates:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    try:
                        if loc.is_visible():
                            return sel
                    except Exception:
                        return sel
            except Exception as exc:
                last_exc = exc
        page.wait_for_timeout(300)
    if last_exc:
        raise last_exc
    return None


def _first_existing_selector(page, selector_or_list):
    for sel in _selector_list(selector_or_list):
        try:
            if page.locator(sel).count() > 0:
                return sel
        except Exception:
            continue
    return None


def _wait_upload_started(page, video_path: Path, timeout_ms: int = 120000) -> bool:
    markers = [
        "[data-e2e*='upload' i]",
        "text=/uploading|processing|uploaded|đang tải|đang xử lý/i",
        "text=/\\b\\d{1,3}%\\b/i",
        f"text={video_path.name}",
    ]
    try:
        return bool(_wait_any_selector(page, markers, timeout_ms=timeout_ms))
    except Exception:
        return False


def _wait_upload_outcome(page, timeout_ms: int = 180000) -> tuple[str, str]:
    success_markers = [
        "text=/uploaded|posted|scheduled|success|thành công|đã lên lịch/i",
        "[data-e2e*='success' i]",
    ]
    failure_markers = [
        "text=/failed|couldn't upload|cannot upload|error|thất bại/i",
        "text=/try again|retry/i",
        "[data-e2e*='error' i]",
    ]
    blocked_markers = [
        "text=/verify|captcha|suspicious|blocked|challenge/i",
        "text=/log in|login|sign in/i",
    ]
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        if _first_existing_selector(page, blocked_markers):
            return ("blocked", "Upload blocked by verification/login challenge.")
        if _first_existing_selector(page, failure_markers):
            return ("failed", "Upload failed according to TikTok UI state.")
        if _first_existing_selector(page, success_markers):
            return ("success", "Upload completed successfully.")
        page.wait_for_timeout(1000)
    return ("timeout", "Upload outcome timeout: success/failure state not detected.")


def _try_select_upload_option(page, selectors: dict):
    option_selector = selectors.get("upload_option")
    if not option_selector:
        return
    try:
        sel = _wait_any_selector(page, option_selector, timeout_ms=5000)
        if sel:
            page.locator(sel).first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass


def _screenshot_on_error(page, label: str):
    """Save a debug screenshot when an upload step fails."""
    try:
        shots_dir = Path(__file__).parents[3] / "data" / "debug_screenshots"
        shots_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = shots_dir / f"{label}_{ts}.png"
        page.screenshot(path=str(path))
    except Exception:
        pass


def _set_caption(page, selector_or_list, caption: str):
    try:
        target = _try_locator(page, selector_or_list, timeout=20000)
    except Exception as exc:
        _screenshot_on_error(page, "caption_not_found")
        raise RuntimeError(f"Caption field not found: {exc}") from exc
    try:
        target.fill(caption)
        return
    except Exception:
        pass
    target.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(caption, delay=8)


def _set_schedule(page, selectors: dict, scheduled_iso: str):
    scheduled_dt = datetime.fromisoformat(scheduled_iso)
    date_text = scheduled_dt.strftime("%Y-%m-%d")
    time_text = scheduled_dt.strftime("%H:%M")

    toggle = selectors.get("schedule_toggle")
    if toggle:
        try:
            _try_locator(page, toggle, timeout=10000).click()
            page.wait_for_timeout(500)
        except Exception:
            _screenshot_on_error(page, "schedule_toggle_not_found")

    date_input = selectors.get("schedule_date_input")
    if date_input:
        try:
            date_el = _try_locator(page, date_input, timeout=10000)
            date_el.click()
            date_el.fill(date_text)
            date_el.press("Enter")
        except Exception:
            _screenshot_on_error(page, "schedule_date_not_found")

    time_input = selectors.get("schedule_time_input")
    if time_input:
        try:
            time_el = _try_locator(page, time_input, timeout=10000)
            time_el.click()
            time_el.fill(time_text)
            time_el.press("Enter")
        except Exception:
            _screenshot_on_error(page, "schedule_time_not_found")


def _try_autofill_login(page, cfg: dict) -> bool:
    username = str(cfg.get("tiktok_username") or cfg.get("login_username") or "").strip()
    password = str(cfg.get("tiktok_password") or cfg.get("login_password") or "").strip()
    if not username or not password:
        return False
    selectors = cfg.get("selectors", {})
    user_sel = selectors.get("login_username")
    pass_sel = selectors.get("login_password")
    if not user_sel or not pass_sel:
        return False
    try:
        user_el = _try_locator(page, user_sel, timeout=10000)
        pass_el = _try_locator(page, pass_sel, timeout=10000)
        user_el.click()
        user_el.fill(username)
        pass_el.click()
        pass_el.fill(password)
        submit_sel = selectors.get("login_submit")
        if submit_sel:
            try:
                _try_locator(page, submit_sel, timeout=3000).click()
            except Exception:
                pass
        return True
    except Exception:
        return False


def _guess_mail_login_url(mail_username: str) -> str:
    m = (mail_username or "").strip().lower()
    if "@gmail." in m:
        return "https://accounts.google.com/signin/v2/identifier?service=mail"
    if any(x in m for x in ["@hotmail.", "@outlook.", "@live.", "@msn."]):
        return "https://outlook.live.com/mail/0/"
    return "https://outlook.live.com/mail/0/"


def _try_autofill_mail_login(page, mail_username: str, mail_password: str) -> bool:
    user = (mail_username or "").strip()
    pwd = (mail_password or "").strip()
    if not user or not pwd:
        return False
    try:
        # Generic email/username fields
        user_selectors = [
            "input[type='email']",
            "input[name='loginfmt']",
            "input[name='identifier']",
            "input[name='username']",
            "input[type='text'][autocomplete='username']",
        ]
        pass_selectors = [
            "input[type='password']",
            "input[name='passwd']",
            "input[name='password']",
        ]
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "#idSIButton9",
            "button:has-text('Next')",
            "button:has-text('Sign in')",
            "button:has-text('Đăng nhập')",
        ]
        uel = _try_locator(page, user_selectors, timeout=8000)
        uel.click()
        uel.fill(user)
        try:
            _try_locator(page, submit_selectors, timeout=2000).click()
            page.wait_for_timeout(1200)
        except Exception:
            pass
        pel = _try_locator(page, pass_selectors, timeout=8000)
        pel.click()
        pel.fill(pwd)
        try:
            _try_locator(page, submit_selectors, timeout=3000).click()
        except Exception:
            pass
        return True
    except Exception:
        return False


def _upload_once(cfg: dict, video_path: Path, scheduled_iso: str, caption: str, use_schedule: bool, headless: bool):
    selectors = cfg.get("selectors", {})
    upload_url = cfg.get("upload_url", "https://www.tiktok.com/upload")
    if not video_path.exists() or not video_path.is_file():
        raise RuntimeError(f"Upload source file not found: {video_path}")

    with sync_playwright() as p:
        context = _launch_persistent_context(p, cfg, headless=headless)
        try:
            page = context.new_page()
            page.goto(upload_url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(1200)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            file_input = selectors.get("file_input", "input[type='file']")
            if not _is_upload_logged_in(page, file_input):
                raise RuntimeError("Upload session is not authenticated. Please login first.")

            _try_select_upload_option(page, selectors)
            input_selector = _wait_any_selector(page, file_input, timeout_ms=45000)
            if not input_selector:
                _try_select_upload_option(page, selectors)
                input_selector = _wait_any_selector(page, file_input, timeout_ms=20000) or _first_existing_selector(page, file_input)
            if not input_selector:
                _screenshot_on_error(page, "upload_input_not_found")
                raise RuntimeError("Upload file input is not available on upload screen after readiness checks.")
            try:
                page.set_input_files(input_selector, str(video_path))
            except Exception:
                page.locator(input_selector).first.set_input_files(str(video_path))

            if not _wait_upload_started(page, video_path, timeout_ms=120000):
                _screenshot_on_error(page, "upload_not_started")
                raise RuntimeError("Upload did not start after selecting file.")

            caption_selector = selectors.get("caption")
            if caption_selector and caption:
                _set_caption(page, caption_selector, caption)

            if use_schedule:
                _set_schedule(page, selectors, scheduled_iso)

            submit_selector = selectors.get("submit")
            if submit_selector:
                try:
                    _try_locator(page, submit_selector, timeout=12000).click()
                except Exception:
                    _screenshot_on_error(page, "submit_not_found")
                    raise

            outcome, outcome_message = _wait_upload_outcome(page, timeout_ms=180000)
            if outcome != "success":
                _screenshot_on_error(page, f"upload_{outcome}")
                raise RuntimeError(outcome_message)

            return {
                "upload_url": upload_url,
                "scheduled_time": scheduled_iso,
                "caption": caption,
                "upload_state": outcome,
                "upload_message": outcome_message,
            }
        finally:
            context.close()


def _build_launch_kwargs(cfg: dict, headless: bool) -> dict:
    Path(cfg["user_data_dir"]).mkdir(parents=True, exist_ok=True)
    launch_kwargs = {
        "user_data_dir": cfg["user_data_dir"],
        "headless": headless,
    }
    if cfg.get("network_mode", "direct").lower() == "proxy":
        if not str(cfg.get("proxy_server") or "").strip():
            raise RuntimeError("Proxy mode is enabled but proxy_server is empty.")
        proxy_cfg = {"server": cfg.get("proxy_server")}
        if cfg.get("proxy_username"):
            proxy_cfg["username"] = cfg.get("proxy_username")
        if cfg.get("proxy_password"):
            proxy_cfg["password"] = cfg.get("proxy_password")
        if cfg.get("proxy_bypass"):
            proxy_cfg["bypass"] = cfg.get("proxy_bypass")
        launch_kwargs["proxy"] = proxy_cfg
    return launch_kwargs


def _profile_dir_is_writable(profile_dir: Path) -> bool:
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
        probe = profile_dir / ".write_probe.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _browser_profile_name_matches(cfg: dict) -> bool:
    user_data_dir = str(cfg.get("user_data_dir") or "").strip()
    if not user_data_dir:
        return False
    key = _safe_account_key(cfg.get("account_key"))
    browser_key = _preferred_browser_key(cfg.get("browser_preference"))
    name = Path(user_data_dir).name.lower()
    expected = f"{browser_key}_{key}".lower()
    return name.startswith(expected)


def _sync_profile_dir_for_browser(cfg: dict):
    """
    Keep user_data_dir consistent with selected browser_preference/account_key.
    Prevents cases like firefox.exe launched with chromeportable_* profile folder.
    """
    channel_code = str(cfg.get("channel_code") or "").strip()
    root_path = str(cfg.get("root_path") or "").strip() or None
    key = _safe_account_key(cfg.get("account_key"))
    expected = _default_user_data_dir(channel_code, key, cfg.get("browser_preference"), root_path=root_path).resolve()
    current_raw = str(cfg.get("user_data_dir") or "").strip()
    current = Path(current_raw).resolve() if current_raw else None

    must_reset = (
        (current is None)
        or (not _browser_profile_name_matches(cfg))
        or ("\\data\\channels\\" in current_raw.lower())
        or ("/data/channels/" in current_raw.lower())
    )
    if must_reset:
        cfg["user_data_dir"] = str(expected)
        current = expected

    # If profile dir is not writable, rotate to recovery dir.
    if current is not None and not _profile_dir_is_writable(current):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        browser_key = _preferred_browser_key(cfg.get("browser_preference"))
        recovery = (_profile_base(channel_code, key, root_path=root_path).resolve() / "browser-profile" / f"{browser_key}_{key}_recover_{ts}")
        recovery.mkdir(parents=True, exist_ok=True)
        cfg["user_data_dir"] = str(recovery)


def _resolve_browser_type_and_executable(cfg: dict) -> tuple[str, str | None]:
    """
    Resolve upload browser launcher:
    - Prefer configured browser_executable (if exists).
    - Then auto-detect portable browser under channels/{channel}/browser-profile.
    - Fallback to Playwright bundled chromium.
    Returns: (browser_type, executable_path_or_none)
    browser_type in {"chromium", "firefox"}
    """
    pref = str(cfg.get("browser_preference") or "chromeportable").strip().lower()
    channel_base = _channel_base_dir(str(cfg.get("channel_code") or ""), str(cfg.get("root_path") or "")).resolve()
    browser_root = channel_base / "browser-profile"
    _term_log(f"Resolve browser | channel={cfg.get('channel_code')} | pref={pref} | root={browser_root}")

    configured_exec = str(cfg.get("browser_executable") or "").strip()
    if configured_exec:
        p = Path(configured_exec).expanduser()
        if p.is_file():
            name = p.name.lower()
            _term_log(f"Using configured executable: {p}")
            if "firefox" in name or pref in ("firefoxportable", "firefox"):
                return "firefox", str(p)
            return "chromium", str(p)

    # Auto-discovery candidates inside channel/{channel}/browser-profile
    chrome_candidates = [
        browser_root / "GoogleChromePortable" / "ChromePortable.exe",
        browser_root / "ChromePortable" / "ChromePortable.exe",
        browser_root / "chromeportable" / "ChromePortable.exe",
        browser_root / "chromeportable" / "chrome.exe",
        browser_root / "chrome-portable" / "chrome.exe",
        browser_root / "ChromePortable" / "chrome.exe",
        browser_root / "ChromePortable" / "App" / "Chrome-bin" / "chrome.exe",
        browser_root / "GoogleChromePortable" / "App" / "Chrome-bin" / "chrome.exe",
    ]
    firefox_candidates = [
        browser_root / "FirefoxPortable" / "FirefoxPortable.exe",
        browser_root / "firefoxportable" / "FirefoxPortable.exe",
        browser_root / "firefoxportable" / "firefox.exe",
        browser_root / "firefoxportable" / "App" / "Firefox64" / "firefox.exe",
        browser_root / "firefoxportable" / "App" / "Firefox" / "firefox.exe",
        browser_root / "firefox-portable" / "firefox.exe",
        browser_root / "FirefoxPortable" / "firefox.exe",
        browser_root / "FirefoxPortable" / "App" / "Firefox64" / "firefox.exe",
        browser_root / "FirefoxPortable" / "App" / "Firefox" / "firefox.exe",
        browser_root / "FirefoxPortable" / "App" / "firefox.exe",
    ]

    # Also scan nested layouts, e.g. browser-profile/<account_key>/FirefoxPortable/App/Firefox64/firefox.exe
    recursive_firefox_portable = []
    recursive_firefox_core = []
    recursive_chrome_portable = []
    recursive_chrome_core = []
    if browser_root.exists():
        try:
            for p in browser_root.rglob("FirefoxPortable.exe"):
                if p.is_file():
                    recursive_firefox_portable.append(p)
            for p in browser_root.rglob("ChromePortable.exe"):
                if p.is_file():
                    recursive_chrome_portable.append(p)
            for p in browser_root.rglob("firefox.exe"):
                if p.is_file():
                    recursive_firefox_core.append(p)
            for p in browser_root.rglob("chrome.exe"):
                if p.is_file():
                    recursive_chrome_core.append(p)
        except Exception:
            pass

    if pref in ("firefoxportable", "firefox"):
        for c in firefox_candidates:
            if c.is_file():
                _term_log(f"Auto-detected Firefox executable: {c}")
                return "firefox", str(c)
        for c in recursive_firefox_portable:
            _term_log(f"Auto-detected Firefox portable launcher (nested): {c}")
            return "firefox", str(c)
        for c in recursive_firefox_core:
            _term_log(f"Auto-detected Firefox executable (nested): {c}")
            return "firefox", str(c)
        # User may keep only the PortableApps installer (*.paf.exe) without extracted runtime.
        has_firefox_paf_installer = any(browser_root.glob("FirefoxPortable*.paf.exe"))
        if has_firefox_paf_installer:
            raise RuntimeError(
                "FirefoxPortable not extracted yet. Found only *.paf.exe installer under "
                f"'{browser_root}'. Please run installer to create FirefoxPortable/App/.../firefox.exe, "
                "or set Browser Executable to the real firefox.exe."
            )
        for c in chrome_candidates:
            if c.is_file():
                _term_log(f"Firefox preferred but only Chromium found, fallback: {c}")
                return "chromium", str(c)
        for c in recursive_chrome_portable:
            _term_log(f"Firefox preferred but only Chromium portable launcher found (nested fallback): {c}")
            return "chromium", str(c)
        for c in recursive_chrome_core:
            _term_log(f"Firefox preferred but only Chromium found (nested fallback): {c}")
            return "chromium", str(c)
    else:
        for c in chrome_candidates:
            if c.is_file():
                _term_log(f"Auto-detected Chromium executable: {c}")
                return "chromium", str(c)
        for c in recursive_chrome_portable:
            _term_log(f"Auto-detected Chromium portable launcher (nested): {c}")
            return "chromium", str(c)
        for c in recursive_chrome_core:
            _term_log(f"Auto-detected Chromium executable (nested): {c}")
            return "chromium", str(c)
        for c in firefox_candidates:
            if c.is_file():
                _term_log(f"Chromium preferred but only Firefox found, fallback: {c}")
                return "firefox", str(c)
        for c in recursive_firefox_portable:
            _term_log(f"Chromium preferred but only Firefox portable launcher found (nested fallback): {c}")
            return "firefox", str(c)
        for c in recursive_firefox_core:
            _term_log(f"Chromium preferred but only Firefox found (nested fallback): {c}")
            return "firefox", str(c)

    # Last fallback: use Playwright installed chromium/firefox (no executable_path).
    if pref in ("firefoxportable", "firefox"):
        _term_log("No local Firefox executable found; fallback to Playwright Firefox runtime.")
        return "firefox", None
    _term_log("No local Chromium executable found; fallback to Playwright Chromium runtime.")
    return "chromium", None


def _portable_installer_for_pref(browser_root: Path, pref: str) -> Path | None:
    # Search both top-level and nested folders inside channel/browser-profile.
    if pref in ("firefoxportable", "firefox"):
        patterns = ["FirefoxPortable*.paf.exe"]
    else:
        patterns = ["*Chrome*Portable*.paf.exe", "ChromePortable*.paf.exe", "GoogleChromePortable*.paf.exe"]

    found: list[Path] = []
    for pat in patterns:
        try:
            found.extend([p for p in browser_root.glob(pat) if p.is_file()])
        except Exception:
            pass
        try:
            found.extend([p for p in browser_root.rglob(pat) if p.is_file()])
        except Exception:
            pass
    if not found:
        return None
    # Pick newest file when multiple installers exist.
    found = sorted(set(found), key=lambda p: p.stat().st_mtime)
    return found[-1]


def _is_windows_exe_file(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(2) == b"MZ"
    except Exception:
        return False


def _file_head_preview(path: Path, n: int = 16) -> str:
    try:
        with path.open("rb") as f:
            raw = f.read(n)
        if not raw:
            return "empty"
        return " ".join(f"{b:02X}" for b in raw)
    except Exception:
        return "unreadable"


def _ensure_account_browser_launcher(
    channel_code: str,
    account_key: str,
    browser_type: str,
    executable_path: str | None,
    root_path: str | None = None,
) -> str:
    if not executable_path:
        return ""
    key = _safe_account_key(account_key)
    channel_base = _channel_base_dir(channel_code, root_path=root_path).resolve()
    browser_root = channel_base / "browser-profile"
    if browser_type == "firefox":
        source_candidates = [
            browser_root / "FirefoxPortable" / "FirefoxPortable.exe",
            browser_root / "firefoxportable" / "FirefoxPortable.exe",
        ]
    else:
        source_candidates = [
            browser_root / "GoogleChromePortable" / "ChromePortable.exe",
            browser_root / "ChromePortable" / "ChromePortable.exe",
            browser_root / "chromeportable" / "ChromePortable.exe",
        ]
    source = None
    for c in source_candidates:
        if c.is_file():
            source = c
            break
    if source is None:
        p = Path(executable_path)
        if p.is_file():
            source = p
    if source is None:
        return ""
    launch_targets = [
        browser_root / f"{key}.exe",
        _profile_base(channel_code, key, root_path=root_path) / "browser-launchers" / f"{key}.exe",
    ]
    for t in launch_targets:
        t.parent.mkdir(parents=True, exist_ok=True)
        try:
            if (not t.exists()) or (t.stat().st_size != source.stat().st_size):
                shutil.copy2(source, t)
        except Exception:
            pass
    return str(launch_targets[0])


def _bootstrap_portable_browser(cfg: dict, allow_install_from_paf: bool = True) -> dict:
    """
    First-login bootstrap:
    - If portable runtime is missing but *.paf.exe exists, execute installer.
    - Wait until real executable appears.
    - Create account_key launcher executable.
    """
    channel_code = str(cfg.get("channel_code") or "").strip()
    root_path = str(cfg.get("root_path") or "").strip() or None
    account_key = _safe_account_key(cfg.get("account_key"))
    pref = str(cfg.get("browser_preference") or "chromeportable").strip().lower()
    channel_base = _channel_base_dir(channel_code, root_path=root_path).resolve()
    browser_root = channel_base / "browser-profile"
    browser_root.mkdir(parents=True, exist_ok=True)
    _term_log(f"Bootstrap portable browser | channel={channel_code} | account={account_key} | pref={pref} | root={browser_root}")

    bootstrap_note = "runtime_ready"
    try:
        browser_type, executable = _resolve_browser_type_and_executable(cfg)
    except Exception:
        browser_type, executable = ("firefox" if "firefox" in pref else "chromium"), None
    _term_log(f"Initial runtime probe | type={browser_type} | executable={executable or '-'}")
    if not executable:
        installer = _portable_installer_for_pref(browser_root, pref)
        if installer and allow_install_from_paf:
            bootstrap_note = f"installer_started:{installer.name}"
            if not _is_windows_exe_file(installer):
                sig = _file_head_preview(installer)
                raise RuntimeError(
                    f"Portable installer is invalid/corrupted: '{installer.name}' (header: {sig}). "
                    "Expected a real Windows EXE (MZ). Re-download official *.paf.exe and replace this file."
                )
            _term_log(f"Runtime missing, starting installer: {installer}")
            try:
                proc = subprocess.Popen([str(installer)], cwd=str(browser_root))
            except Exception as e:
                raise RuntimeError(
                    f"Cannot start portable installer '{installer.name}': {e}. "
                    "Please re-download installer and run as normal user (not blocked/corrupted file)."
                )
            deadline = time.time() + 300
            while time.time() < deadline:
                try:
                    browser_type, executable = _resolve_browser_type_and_executable(cfg)
                    if executable:
                        _term_log(f"Runtime detected after installer | type={browser_type} | executable={executable}")
                        break
                except Exception:
                    pass
                if proc.poll() is not None:
                    # Installer exited but runtime not found yet; keep polling briefly.
                    time.sleep(1.0)
                else:
                    time.sleep(1.0)
        if not executable:
            if installer and not allow_install_from_paf:
                raise RuntimeError(
                    "Portable runtime is not ready for this channel. "
                    "Install/extract browser runtime during Create Channel first, then run Login/Upload."
                )
            raise RuntimeError(
                "Portable browser runtime not found. "
                f"Please install/extract under '{browser_root}' and ensure real browser exe exists."
            )
    _term_log(f"Bootstrap result | type={browser_type} | executable={executable or '-'}")
    launcher_exe = _ensure_account_browser_launcher(
        channel_code,
        account_key,
        browser_type,
        executable,
        root_path=root_path,
    )
    if launcher_exe:
        _term_log(f"Account launcher prepared: {launcher_exe}")
    if executable:
        cfg["browser_executable"] = executable
    return {
        "browser_type": browser_type,
        "browser_executable": executable or "",
        "account_launcher_executable": launcher_exe,
        "bootstrap_note": bootstrap_note,
    }


def bootstrap_portable_runtime_for_channel(
    channel_code: str,
    account_key: str = "default",
    browser_preference: str = "chromeportable",
    root_path: str | None = None,
) -> dict:
    """
    Ensure portable runtime exists and profile directory is prepared for a channel/account.
    This is used by channel creation flow to enforce first-time browser bootstrap.
    """
    key = _safe_account_key(account_key)
    browser_pref = str(browser_preference or "chromeportable").strip().lower()
    cfg = {
        "channel_code": channel_code,
        "account_key": key,
        "browser_preference": browser_pref,
        "root_path": (str(root_path or "").strip() or None),
        "user_data_dir": str(_default_user_data_dir(channel_code, key, browser_pref, root_path=root_path)),
    }
    Path(str(cfg["user_data_dir"])).mkdir(parents=True, exist_ok=True)
    info = _bootstrap_portable_browser(cfg, allow_install_from_paf=True)
    info["profile_dir"] = str(cfg.get("user_data_dir") or "")
    info["account_key"] = key
    return info


def _launch_persistent_context(playwright, cfg: dict, headless: bool):
    _sync_profile_dir_for_browser(cfg)
    launch_kwargs = _build_launch_kwargs(cfg, headless=headless)
    browser_type, executable = _resolve_browser_type_and_executable(cfg)
    if executable:
        launch_kwargs["executable_path"] = executable
    _term_log(
        f"Launch persistent context | type={browser_type} | headless={headless} | "
        f"profile={launch_kwargs.get('user_data_dir')} | exe={launch_kwargs.get('executable_path', '-')}"
    )
    try:
        if browser_type == "firefox":
            return playwright.firefox.launch_persistent_context(**launch_kwargs)
        return playwright.chromium.launch_persistent_context(**launch_kwargs)
    except Exception as e:
        # Recovery path for permission-locked profile directories on Windows.
        msg = str(e).lower()
        if "access is denied" in msg or "target page, context or browser has been closed" in msg:
            key = _safe_account_key(cfg.get("account_key"))
            channel_code = str(cfg.get("channel_code") or "").strip()
            root_path = str(cfg.get("root_path") or "").strip() or None
            browser_key = _preferred_browser_key(cfg.get("browser_preference"))
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            recovery = (_profile_base(channel_code, key, root_path=root_path).resolve() / "browser-profile" / f"{browser_key}_{key}_recover_{ts}")
            _term_log(f"Launch failed, switching to recovery profile: {recovery} | reason={e}")
            cfg["user_data_dir"] = str(recovery)
            launch_kwargs = _build_launch_kwargs(cfg, headless=headless)
            if executable:
                launch_kwargs["executable_path"] = executable
            _term_log(
                f"Retry launch | type={browser_type} | headless={headless} | "
                f"profile={launch_kwargs.get('user_data_dir')} | exe={launch_kwargs.get('executable_path', '-')}"
            )
            if browser_type == "firefox":
                return playwright.firefox.launch_persistent_context(**launch_kwargs)
            return playwright.chromium.launch_persistent_context(**launch_kwargs)
        _term_log(f"Launch persistent context failed: {e}")
        raise


def _is_upload_logged_in(page, file_input_selector) -> bool:
    current_url = (page.url or "").lower()
    redirected_to_login = ("login" in current_url) or ("signin" in current_url)
    has_file_input = _first_existing_selector(page, file_input_selector) is not None
    return bool(has_file_input and not redirected_to_login)


def check_login_with_persistent_profile(channel_code: str, account_key: str = "default", overrides: dict | None = None):
    cfg = load_channel_config(channel_code, account_key=account_key, overrides=overrides)
    _term_log(
        f"Check login start | channel={channel_code} | account={cfg.get('account_key')} | "
        f"pref={cfg.get('browser_preference')} | profile={cfg.get('user_data_dir')}"
    )
    selectors = cfg.get("selectors", {})
    upload_url = cfg.get("upload_url", "https://www.tiktok.com/upload")
    file_input = selectors.get("file_input", "input[type='file']")
    with sync_playwright() as p:
        context = _launch_persistent_context(p, cfg, headless=True)
        try:
            page = context.new_page()
            page.goto(upload_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            logged_in = _is_upload_logged_in(page, file_input)
            message = "Account login is valid." if logged_in else "Account is not logged in or session expired."
            return {
                "status": "ok",
                "channel_code": channel_code,
                "account_key": cfg.get("account_key", _safe_account_key(account_key)),
                "logged_in": logged_in,
                "message": message,
                "url": page.url,
            }
        finally:
            try:
                context.close()
            except Exception:
                pass


def login_with_persistent_profile(channel_code: str, account_key: str = "default", overrides: dict | None = None):
    cfg = load_channel_config(channel_code, account_key=account_key, overrides=overrides)
    _term_log(
        f"Login start | channel={channel_code} | account={cfg.get('account_key')} | "
        f"pref={cfg.get('browser_preference')} | profile={cfg.get('user_data_dir')}"
    )
    # Login/Upload path: never run *.paf installer here.
    # Installer/bootstrap is handled at Create Channel time only.
    bootstrap_info = _bootstrap_portable_browser(cfg, allow_install_from_paf=False)
    browser_type = bootstrap_info.get("browser_type") or "chromium"
    executable = bootstrap_info.get("browser_executable") or ""
    selectors = cfg.get("selectors", {})
    file_input = selectors.get("file_input", "input[type='file']")
    login_confirmed = False
    with sync_playwright() as p:
        context = _launch_persistent_context(p, cfg, headless=False)
        message = "Login flow started."
        # Step 1: mailbox login first (for OTP retrieval flow).
        mail_user = str(cfg.get("mail_username") or "").strip()
        mail_pass = str(cfg.get("mail_password") or "").strip()
        mail_page = None
        if mail_user and mail_pass:
            mail_page = context.new_page()
            mail_page.goto(_guess_mail_login_url(mail_user), wait_until="domcontentloaded", timeout=90000)
            mail_page.wait_for_timeout(1500)
            _try_autofill_mail_login(mail_page, mail_user, mail_pass)
            message = "Mailbox opened first. Complete mailbox login to receive OTP."
        # Step 2: TikTok login
        page = context.new_page()
        page.goto(cfg.get("upload_url", "https://www.tiktok.com/upload"))
        page.wait_for_timeout(1800)
        prefilled = _try_autofill_login(page, cfg)
        if mail_user and mail_pass:
            message = "Mailbox login opened first, then TikTok login opened. Complete captcha/2FA if required."
        elif prefilled:
            message = "Login window opened. Credentials were auto-filled. Complete captcha/2FA if required."
        try:
            # Keep both tabs open and wait for user OTP verification on TikTok.
            deadline = time.time() + 600
            while time.time() < deadline:
                try:
                    if _is_upload_logged_in(page, file_input):
                        login_confirmed = True
                        message = "TikTok login confirmed. Session saved to channel profile."
                        break
                except Exception:
                    pass
                page.wait_for_timeout(2000)
            if not login_confirmed and not message.lower().startswith("login window was closed"):
                message = "Login timeout. Complete login manually and click Login again to re-check."
        except TargetClosedError:
            # User closed browser/tab manually after login (or canceled) -> do not fail API.
            message = "Login window was closed by user. Session may be saved if login was completed."
        finally:
            try:
                context.close()
            except Exception:
                pass
    return {
        "status": "ok",
        "message": message,
        "mail_credential_present": bool(str(cfg.get("mail_username") or "").strip() and str(cfg.get("mail_password") or "").strip()),
        "browser_type": browser_type,
        "browser_executable": executable or "",
        "account_launcher_executable": bootstrap_info.get("account_launcher_executable", ""),
        "bootstrap_note": bootstrap_info.get("bootstrap_note", ""),
        "user_data_dir": str(cfg.get("user_data_dir") or ""),
        "login_confirmed": login_confirmed,
    }


def upload_one_video(cfg: dict, video_path: Path, scheduled_iso: str, caption: str, use_schedule: bool, retry_count: int = 1, headless: bool = False):
    max_attempt = max(1, retry_count + 1)
    last_error = None
    for attempt in range(1, max_attempt + 1):
        try:
            detail = _upload_once(
                cfg=cfg,
                video_path=video_path,
                scheduled_iso=scheduled_iso,
                caption=caption,
                use_schedule=use_schedule,
                headless=headless,
            )
            return attempt, detail
        except Exception as e:
            last_error = e
            if attempt < max_attempt:
                time.sleep(1.1 * attempt)
    raise RuntimeError(f"Upload failed after {max_attempt} attempts: {last_error}")


def upload_schedule(
    channel_code: str,
    config_mode: str = "ui",
    dry_run: bool = True,
    max_items: int = 0,
    include_hashtags: bool = True,
    caption_prefix: str = "",
    caption_mode: str = "template",
    use_schedule: bool = True,
    retry_count: int = 1,
    headless: bool = False,
    account_key: str = "default",
    network_mode: str = "direct",
    proxy_server: str = "",
    proxy_username: str = "",
    proxy_password: str = "",
    proxy_bypass: str = "",
    use_gpm: bool = False,
    gpm_profile_id: str = "",
    gpm_browser_ws: str = "",
    browser_preference: str = "chromeportable",
    browser_executable: str = "",
    login_username: str = "",
    login_password: str = "",
    tiktok_username: str = "",
    tiktok_password: str = "",
    mail_username: str = "",
    mail_password: str = "",
    video_input_dir: str = "",
    schedule_slot_1: str = "07:00",
    schedule_slot_2: str = "17:00",
    schedule_slots: list[str] | None = None,
    schedule_use_local_tz: bool = True,
    selected_files: list[str] | None = None,
    progress_cb=None,
):
    runtime_overrides = _filter_runtime_overrides(
        {
            "network_mode": network_mode,
            "proxy_server": proxy_server,
            "proxy_username": proxy_username,
            "proxy_password": proxy_password,
            "proxy_bypass": proxy_bypass,
            "use_gpm": use_gpm,
            "gpm_profile_id": gpm_profile_id,
            "gpm_browser_ws": gpm_browser_ws,
            "browser_preference": browser_preference,
            "browser_executable": browser_executable,
            "login_username": login_username,
            "login_password": login_password,
            "tiktok_username": tiktok_username,
            "tiktok_password": tiktok_password,
            "mail_username": mail_username,
            "mail_password": mail_password,
            "video_input_dir": video_input_dir,
        },
        config_mode=config_mode,
    )
    cfg = load_channel_config(
        channel_code,
        account_key=account_key,
        overrides=runtime_overrides,
    )
    files = _list_ranked_videos_from_cfg(cfg, max_items=max_items, selected_files=selected_files)
    incoming_slots = [str(x or "").strip() for x in (schedule_slots or []) if str(x or "").strip()]
    if not incoming_slots:
        incoming_slots = [str(schedule_slot_1 or "").strip(), str(schedule_slot_2 or "").strip()]
    incoming_slots = [s for s in incoming_slots if s]
    slot_times = _parse_schedule_slots(incoming_slots if incoming_slots else cfg.get("schedule_slots", ["07:00", "17:00"]))
    if schedule_use_local_tz:
        schedule_tz = datetime.now().astimezone().tzinfo or UTC_MINUS_9
    else:
        schedule_tz = _parse_timezone(cfg.get("timezone_schedule", "LOCAL"))
    slots = compute_schedule_slots(len(files), tz=schedule_tz, slot_times=slot_times)
    hashtags = _read_hashtags(cfg.get("hashtags_file"))

    uploaded_dir = Path(cfg["uploaded_dir"])
    failed_dir = Path(cfg["failed_dir"])
    uploaded_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    items = []

    total = len(files)
    for idx, (file_path, slot) in enumerate(zip(files, slots), start=1):
        caption = _build_caption(file_path, caption_prefix, hashtags, include_hashtags, caption_mode)
        status = "scheduled_dry_run" if dry_run else "queued_for_upload"
        attempts = 0
        detail = ""
        scheduled_local = datetime.fromisoformat(slot).strftime("%Y-%m-%d %H:%M")
        if progress_cb:
            progress_cb({
                "stage": "uploading",
                "current_index": idx,
                "total": total,
                "file_name": file_path.name,
                "status": "running",
                "message": f"Processing {idx}/{total}: {file_path.name} | slot {scheduled_local}",
            })

        if not dry_run:
            try:
                attempts, upload_detail = upload_one_video(
                    cfg=cfg,
                    video_path=file_path,
                    scheduled_iso=slot,
                    caption=caption,
                    use_schedule=use_schedule,
                    retry_count=retry_count,
                    headless=headless,
                )
                _safe_move(file_path, uploaded_dir)
                status = "uploaded"
                detail = json.dumps(upload_detail, ensure_ascii=False)
            except Exception as e:
                _safe_move(file_path, failed_dir)
                status = "failed"
                detail = str(e)

        item = {
            "timestamp": datetime.utcnow().isoformat(),
            "channel_code": channel_code,
            "file_name": file_path.name,
            "scheduled_time": slot,
            "status": status,
            "attempts": attempts,
            "caption": caption,
            "detail": detail,
        }
        items.append(item)
        rows.append([
            item["timestamp"],
            item["channel_code"],
            item["file_name"],
            item["scheduled_time"],
            item["status"],
            item["attempts"],
            item["caption"],
            item["detail"],
        ])
        if progress_cb:
            progress_cb({
                "stage": "uploading",
                "current_index": idx,
                "total": total,
                "file_name": file_path.name,
                "status": item["status"],
                "message": f"{item['status']}: {file_path.name}",
            })

    append_rows(
        REPORTS_DIR / "upload_report.xlsx",
        ["timestamp", "channel_code", "file_name", "scheduled_time", "status", "attempts", "caption", "detail"],
        rows,
    )

    return {
        "channel_code": channel_code,
        "account_key": cfg.get("account_key", _safe_account_key(account_key)),
        "count": len(files),
        "dry_run": dry_run,
        "use_schedule": use_schedule,
        "schedule_slots": [f"{h:02d}:{m:02d}" for h, m in slot_times],
        "timezone": str(schedule_tz),
        "selected_files": [p.name for p in files],
        "items": items,
    }


def create_upload_run(channel_code: str, account_key: str):
    run_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with _UPLOAD_RUN_LOCK:
        _UPLOAD_RUNS[run_id] = {
            "run_id": run_id,
            "channel_code": channel_code,
            "account_key": _safe_account_key(account_key),
            "status": "queued",
            "stage": "queued",
            "message": "Upload queued",
            "progress_percent": 0,
            "current_index": 0,
            "total": 0,
            "items": [],
            "result": None,
            "error": "",
            "created_at": now,
            "updated_at": now,
        }
    return run_id


def update_upload_run(run_id: str, patch: dict):
    now = datetime.utcnow().isoformat()
    with _UPLOAD_RUN_LOCK:
        state = _UPLOAD_RUNS.get(run_id)
        if not state:
            return
        state.update(patch or {})
        state["updated_at"] = now


def get_upload_run(run_id: str):
    with _UPLOAD_RUN_LOCK:
        state = _UPLOAD_RUNS.get(run_id)
        if not state:
            return None
        return json.loads(json.dumps(state))


def execute_upload_run(run_id: str, payload: dict):
    # Apply Ollama model override from payload before run
    if payload.get("ollama_model"):
        os.environ["OLLAMA_MODEL"] = str(payload["ollama_model"])
    update_upload_run(run_id, {"status": "running", "stage": "starting", "message": "Starting upload run"})
    try:
        def _cb(step: dict):
            cur = int(step.get("current_index") or 0)
            total = int(step.get("total") or 0)
            pct = int((cur / total) * 100) if total > 0 else 0
            update_upload_run(run_id, {
                "stage": step.get("stage", "uploading"),
                "message": step.get("message", ""),
                "current_index": cur,
                "total": total,
                "progress_percent": pct,
            })
            file_name = step.get("file_name")
            if file_name:
                with _UPLOAD_RUN_LOCK:
                    state = _UPLOAD_RUNS.get(run_id)
                    if state is not None:
                        state["items"].append({
                            "ts": datetime.utcnow().isoformat(),
                            "file_name": file_name,
                            "status": step.get("status", "running"),
                            "message": step.get("message", ""),
                        })

        result = upload_schedule(
            channel_code=payload["channel_code"],
            config_mode=str(payload.get("config_mode", "ui")),
            dry_run=bool(payload.get("dry_run", True)),
            max_items=int(payload.get("max_items", 0)),
            include_hashtags=bool(payload.get("include_hashtags", True)),
            caption_prefix=str(payload.get("caption_prefix", "")),
            caption_mode=str(payload.get("caption_mode", "template")),
            use_schedule=bool(payload.get("use_schedule", True)),
            retry_count=int(payload.get("retry_count", 1)),
            headless=bool(payload.get("headless", False)),
            account_key=str(payload.get("account_key", "default")),
            network_mode=str(payload.get("network_mode", "direct")),
            proxy_server=str(payload.get("proxy_server", "")),
            proxy_username=str(payload.get("proxy_username", "")),
            proxy_password=str(payload.get("proxy_password", "")),
            proxy_bypass=str(payload.get("proxy_bypass", "")),
            use_gpm=bool(payload.get("use_gpm", False)),
            gpm_profile_id=str(payload.get("gpm_profile_id", "")),
            gpm_browser_ws=str(payload.get("gpm_browser_ws", "")),
            browser_preference=str(payload.get("browser_preference", "chromeportable")),
            browser_executable=str(payload.get("browser_executable", "")),
            login_username=str(payload.get("login_username", "")),
            login_password=str(payload.get("login_password", "")),
            tiktok_username=str(payload.get("tiktok_username", "")),
            tiktok_password=str(payload.get("tiktok_password", "")),
            mail_username=str(payload.get("mail_username", "")),
            mail_password=str(payload.get("mail_password", "")),
            video_input_dir=str(payload.get("video_input_dir", "")),
            schedule_slot_1=str(payload.get("schedule_slot_1", "07:00")),
            schedule_slot_2=str(payload.get("schedule_slot_2", "17:00")),
            schedule_slots=payload.get("schedule_slots") or [],
            schedule_use_local_tz=bool(payload.get("schedule_use_local_tz", True)),
            selected_files=payload.get("selected_files") or [],
            progress_cb=_cb,
        )
        update_upload_run(run_id, {
            "status": "completed",
            "stage": "done",
            "message": f"Upload completed: {result.get('count', 0)} item(s)",
            "progress_percent": 100,
            "result": result,
        })
    except Exception as e:
        update_upload_run(run_id, {
            "status": "failed",
            "stage": "failed",
            "message": f"Upload failed: {e}",
            "error": str(e),
            "progress_percent": 100,
        })

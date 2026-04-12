import re
import json
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.models.schemas import ChannelCreate, ChannelInfo
from app.services.channel_service import ensure_channel, list_channels
from app.services.upload_engine import (
    load_upload_settings,
    save_upload_settings,
    ensure_upload_account_profile,
    bootstrap_portable_runtime_for_channel,
)
from app.core.config import CHANNELS_DIR

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("")
def get_channels():
    return {"items": list_channels()}


@router.get("/root")
def get_channels_root():
    return {"channels_root": str(CHANNELS_DIR.resolve())}


@router.get("/scan")
def scan_channels(root_path: str, prefix: str = "", strict: int = 1):
    rp = Path(str(root_path or "").strip())
    if not rp:
        raise HTTPException(status_code=400, detail="root_path is required")
    if not rp.exists() or not rp.is_dir():
        raise HTTPException(status_code=400, detail="root_path does not exist or is not a directory")
    strict_mode = int(strict or 0) == 1

    def _is_valid_channel_dir(p: Path) -> bool:
        """Strict channel shape validation to avoid picking random folders."""
        # Required baseline: account + upload settings + at least one video source folder.
        has_account_dir = (p / "account").is_dir()
        has_settings = (p / "account" / "upload_settings.json").is_file()
        has_profiles = (p / "account" / "profiles").is_dir()
        has_upload_dir = (p / "upload").is_dir()
        has_video_out = (p / "video_out").is_dir() or (p / "upload" / "video_output").is_dir()
        return has_account_dir and has_settings and has_profiles and has_upload_dir and has_video_out

    candidates = sorted([p for p in rp.iterdir() if p.is_dir()], key=lambda x: x.name.lower())
    if strict_mode:
        candidates = [p for p in candidates if _is_valid_channel_dir(p)]
    items: list[str] = [p.name for p in candidates]
    pfx = str(prefix or "").strip()
    if pfx:
        pfx_lower = pfx.lower()
        items = [x for x in items if x.lower().startswith(pfx_lower)]
    return {
        "root_path": str(rp.resolve()),
        "prefix": pfx,
        "strict": strict_mode,
        "items": items,
    }


def _safe_key(raw: str) -> str:
    import re as _re
    text = str(raw or "default").strip().lower()
    normalized = _re.sub(r"[^a-z0-9_-]+", "_", text).strip("_")
    return normalized or "default"


def _write_channel_settings(base: Path, channel_code: str, settings_data: dict):
    """Write upload_settings.json directly to channel base path."""
    settings_path = base / "account" / "upload_settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    if settings_path.exists():
        try:
            current = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    current.update({"channel_code": channel_code})
    current.update(settings_data)
    settings_path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def _write_channel_profile(base: Path, channel_code: str, account_key: str,
                           browser_pref: str, overrides: dict):
    """Write account profile JSON directly to channel base path."""
    key = _safe_key(account_key)
    profile_dir = base / "account" / "profiles" / key
    profile_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = profile_dir / "account.json"

    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    else:
        base_str = str(base)
        browser_dir = f"{base_str}/account/profiles/{key}/browser-profile/{browser_pref}_{key}"
        cfg = {
            "channel_code": channel_code,
            "account_key": key,
            "platform": "tiktok",
            "user_data_dir": browser_dir,
            "video_input_dir": f"{base_str}/video_out",
            "video_output_dir": f"{base_str}/video_out",
            "uploaded_dir": f"{base_str}/upload/uploaded",
            "failed_dir": f"{base_str}/upload/failed",
            "hashtags_file": f"{base_str}/hashtag/hashtags.txt",
            "schedule_slots": ["07:00", "17:00"],
            "timezone_schedule": "LOCAL",
            "upload_url": "https://www.tiktok.com/upload",
        }

    # Import legacy account.json if present
    legacy = base / "account" / "account.json"
    if (not cfg_path.exists()) and legacy.exists():
        try:
            cfg.update(json.loads(legacy.read_text(encoding="utf-8")))
        except Exception:
            pass

    cfg["account_key"] = key
    cfg["channel_code"] = channel_code
    for k, v in overrides.items():
        if v is None or (isinstance(v, str) and v == ""):
            continue
        cfg[k] = v

    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    # Ensure directories exist
    for dir_key in ("user_data_dir", "video_input_dir", "uploaded_dir", "failed_dir"):
        dir_val = str(cfg.get(dir_key) or "").strip()
        if dir_val:
            Path(dir_val).mkdir(parents=True, exist_ok=True)

    return cfg


def _seed_portable_installers_to_channel(base: Path) -> list[str]:
    """
    Copy portable browser installers into channel/browser-profile so first login can bootstrap runtime.
    Source: <project_root>/data/installers/portableapps
    """
    copied: list[str] = []
    channel_browser_root = base / "browser-profile"
    channel_browser_root.mkdir(parents=True, exist_ok=True)

    project_root = Path(__file__).resolve().parents[3]
    installers_root = project_root / "data" / "installers" / "portableapps"
    if not installers_root.exists() or not installers_root.is_dir():
        return copied

    patterns = [
        "FirefoxPortable*.paf.exe",
        "GoogleChromePortable*.paf.exe",
        "ChromePortable*.paf.exe",
    ]
    candidates: list[Path] = []
    for pat in patterns:
        candidates.extend(sorted(installers_root.glob(pat)))

    seen = set()
    def _is_windows_exe_file(path: Path) -> bool:
        try:
            with path.open("rb") as f:
                return f.read(2) == b"MZ"
        except Exception:
            return False

    for src in candidates:
        if not src.is_file():
            continue
        name_key = src.name.lower()
        if name_key in seen:
            continue
        seen.add(name_key)
        if not _is_windows_exe_file(src):
            # Skip corrupted / HTML download placeholder files.
            continue
        dst = channel_browser_root / src.name
        if dst.exists() and dst.stat().st_size > 0 and _is_windows_exe_file(dst):
            continue
        try:
            shutil.copy2(src, dst)
            copied.append(src.name)
        except Exception:
            # non-fatal; channel creation should still succeed
            pass
    return copied


@router.post("")
def create_channel(payload: ChannelCreate):
    channel_code = payload.channel_code
    custom_root = None
    if str(payload.channel_path or "").strip():
        raw = str(payload.channel_path).strip()
        p = Path(raw)
        if not p.is_absolute():
            p = (CHANNELS_DIR / p).resolve()
        else:
            p = p.resolve()
        channel_code = p.name
        if p.parent.resolve() != CHANNELS_DIR.resolve():
            custom_root = p.parent.resolve()

    base = ensure_channel(channel_code, root_dir=custom_root)

    slots: list[str] = []
    for s in payload.schedule_slots or []:
        text = str(s or "").strip()
        if re.match(r"^\d{1,2}:\d{2}$", text):
            hh, mm = [int(x) for x in text.split(":")]
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                slots.append(f"{hh:02d}:{mm:02d}")
    if not slots:
        slots = ["07:00", "17:00"]

    browser_pref = str(payload.browser_preference or "chromeportable").strip().lower()
    if browser_pref not in {"chromeportable", "firefoxportable"}:
        browser_pref = "chromeportable"
    network_mode = str(payload.network_mode or "direct").strip().lower()
    if network_mode not in {"direct", "proxy"}:
        network_mode = "direct"
    output_subdir_raw = str(payload.video_output_subdir or "video_out").strip()
    output_subdir = output_subdir_raw.replace("\\", "/").strip() or "video_out"
    output_dir_path = Path(output_subdir)
    if output_dir_path.is_absolute():
        resolved_output_dir = output_dir_path
    else:
        resolved_output_dir = (base / output_subdir.strip("/")).resolve()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve login credentials: credential_line has highest priority.
    tiktok_user = str(payload.tiktok_username or "").strip()
    tiktok_pass = str(payload.tiktok_password or "").strip()
    mail_user = str(payload.mail_username or "").strip()
    mail_pass = str(payload.mail_password or "").strip()
    cred_line = str(payload.credential_line or "").strip()
    if cred_line:
        parts = [x.strip() for x in cred_line.split("|")]
        if len(parts) == 4 and all(parts):
            tiktok_user, tiktok_pass, mail_user, mail_pass = parts

    account_key = str(payload.account_key or "").strip() or tiktok_user or "default"

    if custom_root:
        # Custom root: write config files directly to the channel folder
        _write_channel_settings(base, channel_code, {
            "video_output_subdir": output_subdir,
            "default_video_input_dir": output_subdir,
            "schedule_slots": slots,
            "network_mode": network_mode,
            "proxy_server": str(payload.proxy_server or "").strip(),
            "proxy_username": str(payload.proxy_username or "").strip(),
            "proxy_password": str(payload.proxy_password or "").strip(),
            "browser_preference": browser_pref,
        })
        cfg = _write_channel_profile(base, channel_code, account_key, browser_pref, {
            "browser_preference": browser_pref,
            "network_mode": network_mode,
            "proxy_server": str(payload.proxy_server or "").strip(),
            "proxy_username": str(payload.proxy_username or "").strip(),
            "proxy_password": str(payload.proxy_password or "").strip(),
            "tiktok_username": tiktok_user,
            "tiktok_password": tiktok_pass,
            "mail_username": mail_user,
            "mail_password": mail_pass,
            "login_username": tiktok_user,
            "login_password": tiktok_pass,
            "video_input_dir": str(resolved_output_dir),
        })
    else:
        # Default CHANNELS_DIR: use upload_engine functions
        save_upload_settings(channel_code, {
            "video_output_subdir": output_subdir,
            "default_video_input_dir": output_subdir,
            "schedule_slots": slots,
            "network_mode": network_mode,
            "proxy_server": str(payload.proxy_server or "").strip(),
            "proxy_username": str(payload.proxy_username or "").strip(),
            "proxy_password": str(payload.proxy_password or "").strip(),
            "browser_preference": browser_pref,
        })
        cfg = ensure_upload_account_profile(
            channel_code,
            account_key=account_key,
            overrides={
                "browser_preference": browser_pref,
                "network_mode": network_mode,
                "proxy_server": str(payload.proxy_server or "").strip(),
                "proxy_username": str(payload.proxy_username or "").strip(),
                "proxy_password": str(payload.proxy_password or "").strip(),
                "tiktok_username": tiktok_user,
                "tiktok_password": tiktok_pass,
                "mail_username": mail_user,
                "mail_password": mail_pass,
                "login_username": tiktok_user,
                "login_password": tiktok_pass,
                "video_input_dir": str(resolved_output_dir),
            },
        )

    hashtags_raw = str(payload.default_hashtags or "").strip()
    if hashtags_raw:
        tags: list[str] = []
        for token in re.split(r"[\n,]+", hashtags_raw):
            t = token.strip()
            if not t:
                continue
            if not t.startswith("#"):
                t = f"#{t}"
            tags.append(t)
        if tags:
            (base / "hashtag" / "hashtags.txt").write_text("\n".join(tags) + "\n", encoding="utf-8")

    effective_key = cfg.get("account_key", account_key)
    copied_installers = _seed_portable_installers_to_channel(base)
    bootstrap_root = str(base.parent.resolve()) if custom_root else None
    try:
        bootstrap_info = bootstrap_portable_runtime_for_channel(
            channel_code=channel_code,
            account_key=str(effective_key),
            browser_preference=browser_pref,
            root_path=bootstrap_root,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=(
                "Create channel failed at portable bootstrap. "
                f"Please verify installer/runtime under '{base / 'browser-profile'}'. Error: {e}"
            ),
        ) from e

    return {
        "status": "ok",
        "channel": channel_code,
        "path": str(base),
        "video_output_dir": str(resolved_output_dir),
        "account_key": effective_key,
        "profile_config": str(base / "account" / "profiles" / str(effective_key) / "account.json"),
        "upload_settings": str(base / "account" / "upload_settings.json"),
        "portable_installers_seeded": copied_installers,
        "portable_bootstrap": bootstrap_info,
    }


@router.get("/{channel_code}", response_model=ChannelInfo)
def channel_info(channel_code: str, root_path: str = ""):
    rp = Path(root_path.strip()) if root_path.strip() else None
    if rp and rp.is_dir():
        base = rp / channel_code
        if not base.is_dir():
            raise HTTPException(status_code=404, detail=f"Channel folder not found: {base}")
        settings_path = base / "account" / "upload_settings.json"
        settings = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except Exception:
                pass
    else:
        base = ensure_channel(channel_code)
        settings = load_upload_settings(channel_code)

    render_subdir = str(settings.get("default_video_input_dir") or settings.get("video_output_subdir") or "video_out").strip()
    render_subdir = render_subdir.replace("\\", "/").strip("/") or "video_out"
    return ChannelInfo(
        channel_code=channel_code,
        hashtags_file=str(base / "hashtag" / "hashtags.txt"),
        input_dir=str((base / render_subdir).resolve()),
        uploaded_dir=str(base / "upload" / "uploaded"),
        failed_dir=str(base / "upload" / "failed"),
        browser_profile_dir=str(base / "browser-profile"),
    )


@router.get("/{channel_code}/config")
def channel_config(channel_code: str, root_path: str = "", account_key: str = "default"):
    """Read channel settings + profile from any root folder or default CHANNELS_DIR."""
    rp = Path(root_path.strip()) if root_path.strip() else None
    key = _safe_key(account_key)

    if rp and rp.is_dir():
        base = rp / channel_code
    else:
        base = CHANNELS_DIR / channel_code

    if not base.is_dir():
        raise HTTPException(status_code=404, detail=f"Channel folder not found: {base}")

    # Read upload_settings.json
    settings_path = base / "account" / "upload_settings.json"
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    def _pick(d: dict, *keys: str) -> str:
        for k in keys:
            v = str(d.get(k) or "").strip()
            if v:
                return v
        return ""

    def _has_full_creds(d: dict) -> bool:
        return bool(
            _pick(d, "tiktok_username", "login_username")
            and _pick(d, "tiktok_password", "login_password")
            and _pick(d, "mail_username")
            and _pick(d, "mail_password")
        )

    # Read account profile by requested key
    profile_path = base / "account" / "profiles" / key / "account.json"
    profile = {}
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Fallback A: if requested profile is missing/empty credentials, try any other profile with credentials.
    if not _has_full_creds(profile):
        profiles_root = base / "account" / "profiles"
        if profiles_root.exists() and profiles_root.is_dir():
            for prof_dir in sorted([p for p in profiles_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
                candidate = prof_dir / "account.json"
                if not candidate.exists():
                    continue
                try:
                    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if _has_full_creds(candidate_data):
                    merged = dict(candidate_data)
                    # keep requested account key if explicitly asked non-default
                    if key and key != "default":
                        merged["account_key"] = key
                    profile = merged
                    break

    # Fallback B: legacy account.json
    if not _has_full_creds(profile):
        legacy = base / "account" / "account.json"
        if legacy.exists():
            try:
                legacy_data = json.loads(legacy.read_text(encoding="utf-8"))
                # merge only missing credential fields from legacy
                for k_cred in ("tiktok_username", "tiktok_password", "mail_username", "mail_password", "login_username", "login_password"):
                    if not str(profile.get(k_cred) or "").strip() and str(legacy_data.get(k_cred) or "").strip():
                        profile[k_cred] = legacy_data.get(k_cred)
            except Exception:
                pass

    profile.setdefault("account_key", key)
    profile.setdefault("channel_code", channel_code)

    # Optional credential line fallback from channel files:
    # tiktok_user|tiktok_pass|mail_user|mail_pass
    if not str(profile.get("credential_line") or "").strip():
        cred_candidates = [
            base / "account" / "templates" / "credential_line.txt",
            base / "account" / "templates" / "credential_line_template.txt",
            base / "account" / "credential_line.txt",
        ]
        for cf in cred_candidates:
            if not cf.exists():
                continue
            try:
                for line in cf.read_text(encoding="utf-8").splitlines():
                    t = line.strip()
                    if not t or t.startswith("#"):
                        continue
                    parts = [x.strip() for x in t.split("|")]
                    if len(parts) == 4 and all(parts):
                        profile["credential_line"] = t
                        if not str(profile.get("tiktok_username") or "").strip():
                            profile["tiktok_username"] = parts[0]
                        if not str(profile.get("tiktok_password") or "").strip():
                            profile["tiktok_password"] = parts[1]
                        if not str(profile.get("mail_username") or "").strip():
                            profile["mail_username"] = parts[2]
                        if not str(profile.get("mail_password") or "").strip():
                            profile["mail_password"] = parts[3]
                        break
            except Exception:
                pass
            if str(profile.get("credential_line") or "").strip():
                break

    # Auto-build credential line when raw fields exist.
    if not str(profile.get("credential_line") or "").strip():
        tu = _pick(profile, "tiktok_username", "login_username")
        tp = _pick(profile, "tiktok_password", "login_password")
        mu = _pick(profile, "mail_username")
        mp = _pick(profile, "mail_password")
        if tu and tp and mu and mp:
            profile["credential_line"] = f"{tu}|{tp}|{mu}|{mp}"

    return {
        "status": "ok",
        "channel_code": channel_code,
        "account_key": profile.get("account_key", key),
        "settings": settings,
        "profile": profile,
    }

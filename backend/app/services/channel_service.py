from pathlib import Path
import json
from app.core.config import CHANNELS_DIR


def ensure_channel(channel_code: str, root_dir=None):
    root = Path(root_dir) if root_dir else CHANNELS_DIR
    root.mkdir(parents=True, exist_ok=True)
    base = root / channel_code
    for p in [
        # Primary upload/render I/O (new standard)
        base / "video_out",
        # Upload pipeline folders
        base / "upload" / "source",
        base / "upload" / "queue",
        base / "upload" / "uploaded",
        base / "upload" / "failed",
        base / "upload" / "archive",
        base / "upload" / "logs",
        # Legacy compatibility (do not remove to avoid breaking old runs)
        base / "upload" / "video_output",
        # Metadata/auth/config
        base / "hashtag",
        base / "account",
        base / "account" / "profiles",
        base / "account" / "templates",
        base / "account" / "mailbox",
        # Portable browser binaries root (user-managed)
        base / "browser-profile",
        # Runtime logs
        base / "logs" / "upload",
        base / "logs" / "render",
    ]:
        p.mkdir(parents=True, exist_ok=True)

    hashtags = base / "hashtag" / "hashtags.txt"
    if not hashtags.exists():
        hashtags.write_text("#fyp\n#viral\n#xuhuong\n", encoding="utf-8")

    account = base / "account" / "account.json"
    if not account.exists():
        base_str = str(base)
        default_profile_dir = f"{base_str}/account/profiles/default/browser-profile/chromeportable_default"
        account.write_text(json.dumps({
            "channel_code": channel_code,
            "platform": "tiktok",
            "user_data_dir": default_profile_dir,
            "video_input_dir": f"{base_str}/video_out",
            "video_output_dir": f"{base_str}/video_out",
            "uploaded_dir": f"{base_str}/upload/uploaded",
            "failed_dir": f"{base_str}/upload/failed",
            "hashtags_file": f"{base_str}/hashtag/hashtags.txt",
            "schedule_slots": ["07:00", "17:00"],
            "timezone_schedule": "LOCAL",
            "upload_url": "https://www.tiktok.com/upload",
            "selectors": {
                "file_input": "input[type='file']",
                "caption": "[contenteditable='true']",
                "schedule_toggle": "[data-e2e='schedule-video-toggle']",
                "schedule_date_input": "input[placeholder*='Date']",
                "schedule_time_input": "input[placeholder*='Time']",
                "submit": "button[type='submit']"
            }
        }, indent=2), encoding="utf-8")

    upload_settings = base / "account" / "upload_settings.json"
    if not upload_settings.exists():
        upload_settings.write_text(json.dumps({
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
            "upload_url": "https://www.tiktok.com/upload"
        }, indent=2), encoding="utf-8")

    # One-line credential format template:
    # tiktok_user|tiktok_pass|mail_user|mail_pass
    cred_tpl = base / "account" / "templates" / "credential_line_template.txt"
    if not cred_tpl.exists():
        cred_tpl.write_text(
            "# Format: tiktok_user|tiktok_pass|mail_user|mail_pass\n"
            "# Example:\n"
            "# user6188823432588|Hm@12345|eistotoppuw@hotmail.com|4UYRszyOS4weuxO\n",
            encoding="utf-8",
        )

    channel_readme = base / "CHANNEL_STRUCTURE.txt"
    if not channel_readme.exists():
        channel_readme.write_text(
            "Channel folder structure\n"
            "========================\n\n"
            "video_out/\n"
            "  - Final videos for upload (primary source for Upload mode)\n\n"
            "upload/source/\n"
            "  - Downloaded original source videos\n"
            "upload/queue/\n"
            "  - Optional queue staging\n"
            "upload/uploaded/\n"
            "  - Uploaded successful files\n"
            "upload/failed/\n"
            "  - Upload failed files\n"
            "upload/archive/\n"
            "  - Archived files\n"
            "upload/logs/\n"
            "  - Upload runtime logs\n\n"
            "account/upload_settings.json\n"
            "  - Channel-level upload defaults (proxy/network/browser)\n"
            "account/profiles/{account_key}/account.json\n"
            "  - Per-account config/profile\n"
            "account/profiles/{account_key}/browser-profile/\n"
            "  - Persistent browser user data for that account\n"
            "  - First-time profile folder is auto-named by account_key:\n"
            "    chromeportable_{account_key} or firefoxportable_{account_key}\n"
            "account/templates/credential_line_template.txt\n"
            "  - One-line credential format reference\n\n"
            "browser-profile/\n"
            "  - Place portable browser binaries here (FirefoxPortable/ChromePortable)\n\n"
            "logs/upload/\n"
            "logs/render/\n",
            encoding="utf-8",
        )
    return base


def list_channels():
    CHANNELS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted([p.name for p in CHANNELS_DIR.iterdir() if p.is_dir()])

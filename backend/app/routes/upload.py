import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from app.models.schemas import UploadAccountCreate, UploadAccountUpdate, UploadQueueAddRequest, UploadRequest
from app.services.db import (
    add_upload_queue_item,
    cancel_upload_queue_item,
    create_upload_account_row,
    disable_upload_account_row,
    get_upload_account_row,
    get_upload_queue_item,
    list_upload_account_rows,
    list_upload_queue,
    mark_upload_queue_failed,
    mark_upload_queue_success,
    mark_upload_queue_uploading,
    update_upload_account_row,
)
from app.services.upload_engine import (
    upload_schedule,
    login_with_persistent_profile,
    check_login_with_persistent_profile,
    list_upload_accounts,
    list_ranked_videos,
    load_channel_config,
    _resolve_video_input_dir,
    ensure_upload_account_profile,
    create_upload_run,
    execute_upload_run,
    get_upload_run,
    load_upload_settings,
    save_upload_settings,
    upload_one_video,
)
from app.services.channel_service import ensure_channel

router = APIRouter(prefix="/api/upload", tags=["upload"])
logger = logging.getLogger("app.upload")


def _safe_account_key(raw: str) -> str:
    text = str(raw or "default").strip().lower()
    normalized = re.sub(r"[^a-z0-9_-]+", "_", text).strip("_")
    return normalized or "default"


def _extract_part_no_local(name: str) -> int:
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


def _resolve_upload_overrides(payload: UploadRequest) -> dict:
    mode = (payload.config_mode or "ui").strip().lower()
    base = {
        "root_path": payload.root_path,
        "network_mode": payload.network_mode,
        "proxy_server": payload.proxy_server,
        "proxy_username": payload.proxy_username,
        "proxy_password": payload.proxy_password,
        "proxy_bypass": payload.proxy_bypass,
        "use_gpm": payload.use_gpm,
        "gpm_profile_id": payload.gpm_profile_id,
        "gpm_browser_ws": payload.gpm_browser_ws,
        "browser_preference": payload.browser_preference,
        "browser_executable": payload.browser_executable,
        "user_data_dir": payload.user_data_dir,
        "video_input_dir": payload.video_input_dir,
        "login_username": payload.login_username,
        "login_password": payload.login_password,
        "tiktok_username": payload.tiktok_username,
        "tiktok_password": payload.tiktok_password,
        "mail_username": payload.mail_username,
        "mail_password": payload.mail_password,
    }
    if mode == "json":
        return {}
    if mode == "mixed":
        out = {}
        for k, v in base.items():
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            if isinstance(v, bool) and v is False:
                continue
            out[k] = v
        return out
    return base


@router.get("/accounts")
def list_upload_account_manager_accounts(include_disabled: bool = True):
    items = list_upload_account_rows(include_disabled=include_disabled)
    return {"status": "ok", "count": len(items), "items": items}


@router.post("/accounts")
def create_upload_account_manager_account(payload: UploadAccountCreate):
    data = payload.model_dump()
    account = create_upload_account_row(data)
    logger.info(
        "upload_account_create account_id=%s platform=%s channel_code=%s account_key=%s",
        account.get("account_id"),
        account.get("platform"),
        account.get("channel_code"),
        account.get("account_key"),
    )
    return {"status": "ok", "item": account}


@router.patch("/accounts/{account_id}")
def update_upload_account_manager_account(account_id: str, payload: UploadAccountUpdate):
    current = get_upload_account_row(account_id)
    if not current:
        raise HTTPException(status_code=404, detail="Upload account not found")
    changes = payload.model_dump(exclude_unset=True)
    account = update_upload_account_row(account_id, changes)
    return {"status": "ok", "item": account}


@router.delete("/accounts/{account_id}")
def disable_upload_account_manager_account(account_id: str):
    current = get_upload_account_row(account_id)
    if not current:
        raise HTTPException(status_code=404, detail="Upload account not found")
    account = disable_upload_account_row(account_id)
    logger.info("upload_account_disable account_id=%s", account_id)
    return {"status": "ok", "item": account}


@router.post("/queue/add")
def add_to_upload_queue(payload: UploadQueueAddRequest):
    video_path = str(payload.video_path or "").strip()
    channel_code = str(payload.channel_code or "").strip()
    if not video_path:
        raise HTTPException(status_code=400, detail="video_path is required")
    if not channel_code:
        raise HTTPException(status_code=400, detail="channel_code is required")
    platform = str(payload.platform or "tiktok").strip().lower() or "tiktok"
    row = add_upload_queue_item(
        video_path=video_path,
        render_job_id=str(payload.render_job_id or "").strip(),
        part_no=int(payload.part_no or 0),
        channel_code=channel_code,
        account_id=str(payload.account_id or "").strip(),
        platform=platform,
        caption=str(payload.caption or ""),
        hashtags=payload.hashtags or [],
    )
    logger.info(
        "upload_queue_add queue_id=%s video_path=%s channel_code=%s",
        row.get("queue_id"),
        video_path,
        channel_code,
    )
    return {"status": "ok", "queue_id": row.get("queue_id"), "item": row}


@router.get("/queue")
def get_upload_queue():
    items = list_upload_queue(limit=50)
    return {"status": "ok", "count": len(items), "items": items}


def _queue_account_key(row: dict) -> str:
    # Phase 2 has no account resolver yet; account_id is treated as the existing account_key.
    return _safe_account_key(row.get("account_id") or "default")


@router.post("/queue/{queue_id}/run")
def run_upload_queue_item(queue_id: str):
    row = get_upload_queue_item(queue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload queue item not found")

    current_status = str(row.get("status") or "").lower()
    if current_status == "uploading":
        raise HTTPException(status_code=409, detail="Upload queue item is already uploading")
    if current_status not in {"pending", "failed"}:
        raise HTTPException(status_code=409, detail=f"Upload queue item cannot run from status '{current_status}'")

    video_path = Path(str(row.get("video_path") or "").strip())
    if not video_path.exists() or not video_path.is_file():
        error = f"Video file not found: {video_path}"
        mark_upload_queue_failed(queue_id, error)
        raise HTTPException(status_code=400, detail=error)

    locked_row, acquired = mark_upload_queue_uploading(queue_id)
    if not locked_row:
        raise HTTPException(status_code=404, detail="Upload queue item not found")
    if not acquired:
        locked_status = str(locked_row.get("status") or "").lower()
        raise HTTPException(status_code=409, detail=f"Upload queue item is already {locked_status}")

    channel_code = str(locked_row.get("channel_code") or "").strip()
    account_key = _queue_account_key(locked_row)
    logger.info(
        "upload_queue_run_start queue_id=%s video_path=%s account_id=%s channel_code=%s",
        queue_id,
        str(video_path),
        locked_row.get("account_id") or "",
        channel_code,
    )

    try:
        if not channel_code:
            raise RuntimeError("channel_code is required")
        platform = str(locked_row.get("platform") or "tiktok").strip().lower()
        if platform != "tiktok":
            raise RuntimeError(f"platform '{platform}' is not supported by the manual queue worker yet")
        ensure_channel(channel_code)
        cfg = load_channel_config(channel_code, account_key=account_key)
        try:
            login_check = check_login_with_persistent_profile(channel_code, account_key=account_key)
        except Exception as login_exc:
            raise RuntimeError(f"account/login not ready: {login_exc}") from login_exc
        if not login_check.get("logged_in"):
            raise RuntimeError("account/login not ready")

        caption = str(locked_row.get("caption") or "").strip()
        if not caption:
            caption = video_path.stem.replace("_", " ").replace("-", " ").strip()
        scheduled_iso = datetime.now().astimezone().isoformat()
        attempts, detail = upload_one_video(
            cfg=cfg,
            video_path=video_path,
            scheduled_iso=scheduled_iso,
            caption=caption,
            use_schedule=False,
            retry_count=0,
            headless=False,
        )
        result = {
            "attempts": attempts,
            "detail": detail,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
        }
        final = mark_upload_queue_success(queue_id, result)
        logger.info("upload_queue_run_success queue_id=%s video_path=%s", queue_id, str(video_path))
        return {"status": "success", "queue_id": queue_id, "item": final}
    except Exception as exc:
        error = str(exc) or "Upload failed"
        final = mark_upload_queue_failed(queue_id, error)
        logger.error(
            "upload_queue_run_failed queue_id=%s video_path=%s error=%s",
            queue_id,
            str(video_path),
            error,
        )
        return {"status": "failed", "queue_id": queue_id, "item": final, "error": error}


@router.post("/queue/{queue_id}/cancel")
def cancel_upload_queue(queue_id: str):
    row = get_upload_queue_item(queue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload queue item not found")
    if str(row.get("status") or "").lower() == "uploading":
        raise HTTPException(status_code=409, detail="Uploading item cannot be cancelled in this phase")
    final, changed = cancel_upload_queue_item(queue_id)
    if not changed:
        raise HTTPException(status_code=409, detail=f"Upload queue item cannot be cancelled from status '{row.get('status')}'")
    return {"status": "cancelled", "queue_id": queue_id, "item": final}


@router.post("/schedule")
def schedule_upload(payload: UploadRequest):
    ensure_channel(payload.channel_code)
    return upload_schedule(
        channel_code=payload.channel_code,
        config_mode=payload.config_mode,
        dry_run=payload.dry_run,
        max_items=payload.max_items,
        include_hashtags=payload.include_hashtags,
        caption_prefix=payload.caption_prefix,
        use_schedule=payload.use_schedule,
        retry_count=payload.retry_count,
        headless=payload.headless,
        account_key=payload.account_key,
        network_mode=payload.network_mode,
        proxy_server=payload.proxy_server,
        proxy_username=payload.proxy_username,
        proxy_password=payload.proxy_password,
        proxy_bypass=payload.proxy_bypass,
        use_gpm=payload.use_gpm,
        gpm_profile_id=payload.gpm_profile_id,
        gpm_browser_ws=payload.gpm_browser_ws,
        browser_preference=payload.browser_preference,
        browser_executable=payload.browser_executable,
        login_username=payload.login_username,
        login_password=payload.login_password,
        tiktok_username=payload.tiktok_username,
        tiktok_password=payload.tiktok_password,
        mail_username=payload.mail_username,
        mail_password=payload.mail_password,
        video_input_dir=payload.video_input_dir,
        schedule_slot_1=payload.schedule_slot_1,
        schedule_slot_2=payload.schedule_slot_2,
        schedule_slots=payload.schedule_slots,
        schedule_use_local_tz=payload.schedule_use_local_tz,
        selected_files=payload.selected_files,
    )


@router.post("/schedule/start")
def schedule_upload_start(payload: UploadRequest, background_tasks: BackgroundTasks):
    ensure_channel(payload.channel_code)
    overrides = _resolve_upload_overrides(payload)
    check = check_login_with_persistent_profile(
        payload.channel_code,
        account_key=payload.account_key,
        overrides=overrides,
    )
    if not check.get("logged_in"):
        raise HTTPException(status_code=400, detail="Account session is not logged in. Please click TikTok Login first.")
    run_id = create_upload_run(payload.channel_code, payload.account_key)
    background_tasks.add_task(execute_upload_run, run_id, payload.model_dump())
    return {"run_id": run_id, "status": "queued"}


@router.get("/schedule/runs/{run_id}")
def upload_run_status(run_id: str):
    row = get_upload_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload run not found")
    return row


@router.websocket("/schedule/runs/{run_id}/ws")
async def ws_upload_run(websocket: WebSocket, run_id: str):
    """WebSocket — streams upload run status every 500 ms until terminal state."""
    await websocket.accept()
    try:
        while True:
            row = get_upload_run(run_id)
            if not row:
                await websocket.send_json({"error": "not_found"})
                break
            await websocket.send_json(row)
            if row.get("status") in ("completed", "failed", "done"):
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@router.post("/login/start")
def login_start(payload: UploadRequest):
    ensure_channel(payload.channel_code)
    overrides = _resolve_upload_overrides(payload)
    try:
        return login_with_persistent_profile(
            payload.channel_code,
            account_key=payload.account_key,
            overrides=overrides,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login/check")
def login_check(payload: UploadRequest):
    ensure_channel(payload.channel_code)
    overrides = _resolve_upload_overrides(payload)
    return check_login_with_persistent_profile(
        payload.channel_code,
        account_key=payload.account_key,
        overrides=overrides,
    )


@router.get("/accounts/{channel_code}")
def get_upload_accounts(channel_code: str):
    account = get_upload_account_row(channel_code)
    if account:
        return {"status": "ok", "item": account}
    ensure_channel(channel_code)
    items = list_upload_accounts(channel_code)
    return {"channel_code": channel_code, "items": items}


@router.post("/accounts/ensure")
def ensure_upload_account(payload: UploadRequest):
    ensure_channel(payload.channel_code)
    overrides = _resolve_upload_overrides(payload)
    cfg = ensure_upload_account_profile(
        payload.channel_code,
        account_key=payload.account_key,
        overrides=overrides,
    )
    return {
        "status": "ok",
        "channel_code": payload.channel_code,
        "account_key": cfg.get("account_key", payload.account_key),
        "user_data_dir": cfg.get("user_data_dir"),
    }


@router.get("/settings/{channel_code}")
def get_upload_settings(channel_code: str):
    ensure_channel(channel_code)
    return load_upload_settings(channel_code)


@router.get("/config/{channel_code}")
def get_upload_config(channel_code: str, account_key: str = "default"):
    ensure_channel(channel_code)
    settings = load_upload_settings(channel_code)
    profile = load_channel_config(channel_code, account_key=account_key)
    return {
        "status": "ok",
        "channel_code": channel_code,
        "account_key": profile.get("account_key", account_key),
        "settings": settings,
        "profile": profile,
    }


@router.post("/config/save")
def save_upload_config(payload: UploadRequest):
    ensure_channel(payload.channel_code)
    slots = []
    for s in payload.schedule_slots or []:
        text = str(s or "").strip()
        if text and len(text.split(":")) == 2:
            hh, mm = text.split(":")
            if hh.isdigit() and mm.isdigit():
                h = int(hh)
                m = int(mm)
                if 0 <= h <= 23 and 0 <= m <= 59:
                    slots.append(f"{h:02d}:{m:02d}")
    if not slots:
        slots = ["07:00", "17:00"]

    network_mode = (payload.network_mode or "direct").strip().lower()
    if network_mode not in {"direct", "proxy"}:
        network_mode = "direct"

    browser_preference = (payload.browser_preference or "chromeportable").strip().lower()
    if browser_preference not in {"chromeportable", "firefoxportable"}:
        browser_preference = "chromeportable"

    settings_updates = {
        "schedule_slots": slots,
        "network_mode": network_mode,
        "proxy_server": payload.proxy_server or "",
        "proxy_username": payload.proxy_username or "",
        "proxy_password": payload.proxy_password or "",
        "browser_preference": browser_preference,
        "browser_executable": payload.browser_executable or "",
    }
    if str(payload.video_input_dir or "").strip():
        settings_updates["default_video_input_dir"] = payload.video_input_dir.strip()

    settings = save_upload_settings(payload.channel_code, settings_updates)
    overrides = _resolve_upload_overrides(payload)
    profile = ensure_upload_account_profile(
        payload.channel_code,
        account_key=payload.account_key,
        overrides=overrides,
    )
    return {
        "status": "ok",
        "channel_code": payload.channel_code,
        "account_key": profile.get("account_key", payload.account_key),
        "settings": settings,
        "profile": profile,
    }


@router.get("/videos/{channel_code}")
def get_upload_videos(channel_code: str, max_items: int = 0, root_path: str = "", account_key: str = "default"):
    # Custom root path mode (for desktop folder chooser workflow)
    rp = Path(str(root_path or "").strip()) if str(root_path or "").strip() else None
    if rp and rp.is_dir():
        base = (rp / channel_code).resolve()
        if not base.is_dir():
            raise HTTPException(status_code=404, detail=f"Channel folder not found: {base}")

        candidates: list[Path] = []
        # Prefer channel-standard folders first
        candidates.append((base / "video_out").resolve())
        candidates.append((base / "upload" / "video_output").resolve())

        # Optional profile override if it points inside the same channel folder
        key = _safe_account_key(account_key)
        profile_cfg = base / "account" / "profiles" / key / "account.json"
        if profile_cfg.exists():
            try:
                profile_data = json.loads(profile_cfg.read_text(encoding="utf-8"))
                raw_input = str(profile_data.get("video_input_dir") or "").strip()
                if raw_input:
                    p = Path(raw_input)
                    if p.exists():
                        rp_abs = p.resolve()
                        # Safety: ignore stale paths pointing to other channels
                        if str(rp_abs).lower().startswith(str(base).lower()):
                            candidates.insert(0, rp_abs)
            except Exception:
                pass

        input_dir = None
        for c in candidates:
            if c.exists() and c.is_dir():
                input_dir = c
                break
        if input_dir is None:
            input_dir = candidates[0]

        exts = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
        files = [p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]
        files.sort(key=lambda p: (_extract_part_no_local(p.name), p.name.lower()))
        if max_items and max_items > 0:
            files = files[:max_items]
        return {
            "channel_code": channel_code,
            "count": len(files),
            "input_dir": str(input_dir),
            "items": [p.name for p in files],
        }

    # Default project channels mode
    ensure_channel(channel_code)
    files = list_ranked_videos(channel_code, max_items=max_items)
    cfg = load_channel_config(channel_code, account_key=account_key)
    input_dir = _resolve_video_input_dir(cfg)
    return {
        "channel_code": channel_code,
        "count": len(files),
        "input_dir": str(input_dir),
        "items": [p.name for p in files],
    }

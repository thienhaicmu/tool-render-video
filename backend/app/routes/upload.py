import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from app.models.schemas import (
    AddUploadVideoRequest,
    UpdateUploadVideoRequest,
    UploadAccountCreate,
    UploadAccountUpdate,
    UploadQueueAddRequest,
    UploadQueueUpdateRequest,
    UploadRequest,
)
from app.services.db import (
    UPLOAD_PROFILE_LOCK_TTL_MINUTES,
    add_upload_queue_item,
    acquire_upload_runtime_lock,
    build_default_upload_profile_path,
    cancel_upload_queue_item,
    create_upload_account_row,
    create_upload_video_row,
    disable_upload_video_row,
    disable_upload_account_row,
    find_upload_account_profile_conflict,
    get_upload_account_row,
    get_upload_queue_item,
    get_upload_video_row,
    normalize_profile_path_value,
    release_upload_runtime_locks_for_queue,
    set_upload_queue_last_error,
    insert_upload_history,
    list_upload_account_rows,
    list_upload_history,
    list_upload_queue,
    list_upload_video_rows,
    mark_upload_queue_failed,
    mark_upload_queue_success,
    mark_upload_queue_uploading,
    update_upload_account_row,
    update_upload_queue_item,
    update_upload_video_row,
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


def _probe_upload_video_path(video_path: str) -> tuple[str, int]:
    path_text = str(video_path or "").strip()
    file_name = Path(path_text).name or path_text.replace("\\", "/").split("/")[-1]
    file_size = 0
    try:
        p = Path(path_text)
        if p.exists() and p.is_file():
            file_size = p.stat().st_size
            file_name = p.name or file_name
    except Exception:
        pass
    return file_name, file_size


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _caption_with_hashtags(caption: str, hashtags: list[str] | None) -> str:
    base = str(caption or "").strip()
    tags = []
    for tag in hashtags or []:
        text = str(tag or "").strip()
        if not text:
            continue
        tags.append(text if text.startswith("#") else f"#{text}")
    if tags:
        merged = f"{base} {' '.join(tags)}".strip()
        return merged[:2200]
    return base[:2200]


def _build_queue_upload_cfg(account: dict, queue_item: dict) -> tuple[str, str, dict]:
    channel_code = str(account.get("channel_code") or queue_item.get("channel_code") or "").strip()
    account_key = str(account.get("account_key") or "default").strip() or "default"
    if not channel_code:
        raise RuntimeError("Upload account is missing channel_code; cannot resolve upload profile.")
    overrides = {}
    profile_path = str(account.get("profile_path") or "").strip()
    if profile_path:
        overrides["user_data_dir"] = profile_path
    proxy_id = str(account.get("proxy_id") or "").strip()
    if proxy_id:
        overrides["proxy_id"] = proxy_id
    proxy_config = account.get("proxy_config") or {}
    if isinstance(proxy_config, dict):
        for key in ("network_mode", "proxy_server", "proxy_username", "proxy_password", "proxy_bypass"):
            value = str(proxy_config.get(key) or "").strip()
            if value:
                overrides[key] = value
    cfg = load_channel_config(channel_code, account_key=account_key, overrides=overrides)
    return channel_code, account_key, cfg


def _account_profile_path(account: dict) -> str:
    explicit = str(account.get("profile_path") or "").strip()
    if explicit:
        return normalize_profile_path_value(explicit)
    return normalize_profile_path_value(
        build_default_upload_profile_path(
            str(account.get("platform") or "tiktok"),
            str(account.get("account_key") or "default"),
        )
    )


def _validate_account_profile_isolation(account_payload: dict, exclude_account_id: str = "") -> dict:
    profile_path = _account_profile_path(account_payload)
    account_payload["profile_path"] = profile_path
    conflict = find_upload_account_profile_conflict(
        normalized_profile_path=profile_path,
        exclude_account_id=exclude_account_id,
    )
    status = str(account_payload.get("status") or "active").strip().lower()
    if conflict and status in {"active", "warming"}:
        logger.warning(
            "profile_conflict account_id=%s profile_path=%s conflict_account_id=%s",
            exclude_account_id or "",
            profile_path,
            conflict.get("account_id") or "",
        )
        conflict_name = conflict.get("display_name") or conflict.get("account_key") or conflict.get("account_id") or "unknown"
        raise HTTPException(
            status_code=409,
            detail=f"profile_path already used by active account {conflict_name}",
        )
    return account_payload


@router.get("/accounts")
def list_upload_account_manager_accounts(include_disabled: bool = True):
    items = list_upload_account_rows(include_disabled=include_disabled)
    return {"status": "ok", "count": len(items), "items": items}


@router.post("/accounts")
def create_upload_account_manager_account(payload: UploadAccountCreate):
    data = _validate_account_profile_isolation(payload.model_dump())
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
    changes = _validate_account_profile_isolation({**current, **payload.model_dump(exclude_unset=True)}, exclude_account_id=account_id)
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


@router.post("/accounts/{account_id}/login-check")
def check_upload_account_login_state(account_id: str):
    account = get_upload_account_row(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Upload account not found")
    channel_code = str(account.get("channel_code") or "").strip()
    account_key = str(account.get("account_key") or "default").strip() or "default"
    profile_path = _account_profile_path(account)
    if not channel_code:
        response = {
            "status": "not_implemented",
            "account_id": account_id,
            "message": "not implemented for this adapter: account is missing channel_code",
        }
        update_upload_account_row(
            account_id,
            {
                "login_state": "unknown",
                "last_login_check_at": _utc_now_iso(),
                "health_json": response,
            },
        )
        return response
    try:
        result = check_login_with_persistent_profile(
            channel_code,
            account_key=account_key,
            overrides={"user_data_dir": profile_path},
        )
    except Exception as exc:
        error_result = {
            "status": "error",
            "account_id": account_id,
            "message": str(exc),
        }
        updated = update_upload_account_row(
            account_id,
            {
                "profile_path": profile_path,
                "login_state": "unknown",
                "last_login_check_at": _utc_now_iso(),
                "health_json": error_result,
            },
        )
        logger.warning(
            "login_check_result account_id=%s profile_path=%s login_state=unknown error=%s",
            account_id,
            profile_path,
            str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc))
    login_state = "logged_in" if result.get("logged_in") else "logged_out"
    updated = update_upload_account_row(
        account_id,
        {
            "profile_path": profile_path,
            "login_state": login_state,
            "last_login_check_at": _utc_now_iso(),
            "health_json": result,
        },
    )
    logger.info(
        "login_check_result account_id=%s profile_path=%s login_state=%s",
        account_id,
        profile_path,
        login_state,
    )
    return {"status": "ok", "item": updated, "result": result}


@router.post("/videos/add")
def add_upload_video_library_item(payload: AddUploadVideoRequest):
    video_path = str(payload.video_path or "").strip()
    if not video_path:
        raise HTTPException(status_code=400, detail="video_path is required")
    file_name, file_size = _probe_upload_video_path(video_path)
    item = create_upload_video_row(
        {
            "video_path": video_path,
            "file_name": file_name,
            "platform": payload.platform or "tiktok",
            "source_type": payload.source_type or "manual_file",
            "status": "ready",
            "caption": payload.caption or "",
            "hashtags": payload.hashtags or [],
            "cover_path": payload.cover_path or "",
            "note": payload.note or "",
            "duration_sec": 0,
            "file_size": file_size,
            "metadata": payload.metadata or {},
        }
    )
    logger.info(
        "upload_video_add video_id=%s platform=%s source_type=%s video_path=%s",
        item.get("video_id"),
        item.get("platform"),
        item.get("source_type"),
        video_path,
    )
    return {"status": "ok", "item": item}


@router.get("/videos")
def list_upload_video_library_items(
    platform: str = "",
    status: str = "",
    source_type: str = "",
    limit: int = 100,
):
    items = list_upload_video_rows(
        platform=str(platform or "").strip().lower(),
        status=str(status or "").strip().lower(),
        source_type=str(source_type or "").strip().lower(),
        limit=limit,
    )
    return {"status": "ok", "count": len(items), "items": items}


@router.patch("/videos/{video_id}")
def update_upload_video_library_item(video_id: str, payload: UpdateUploadVideoRequest):
    current = get_upload_video_row(video_id)
    if not current:
        raise HTTPException(status_code=404, detail="Upload video not found")
    changes = payload.model_dump(exclude_unset=True)
    item = update_upload_video_row(video_id, changes)
    return {"status": "ok", "item": item}


@router.delete("/videos/{video_id}")
def disable_upload_video_library_item(video_id: str):
    current = get_upload_video_row(video_id)
    if not current:
        raise HTTPException(status_code=404, detail="Upload video not found")
    item = disable_upload_video_row(video_id)
    logger.info("upload_video_disable video_id=%s", video_id)
    return {"status": "ok", "item": item}


@router.post("/queue/add")
def add_to_upload_queue(payload: UploadQueueAddRequest):
    video_id = str(payload.video_id or "").strip()
    account_id = str(payload.account_id or "").strip()
    video = get_upload_video_row(video_id) if video_id else None
    account = get_upload_account_row(account_id) if account_id else None

    if video_id and not video:
        raise HTTPException(status_code=404, detail="Upload video not found")
    if account_id and not account:
        raise HTTPException(status_code=404, detail="Upload account not found")
    if video and str(video.get("status") or "").lower() == "disabled":
        raise HTTPException(status_code=400, detail="Disabled video cannot be queued")
    if account and str(account.get("status") or "").lower() == "disabled":
        raise HTTPException(status_code=400, detail="Disabled account cannot be queued")
    if not video and not str(payload.video_path or "").strip():
        raise HTTPException(status_code=400, detail="video_id is required")
    if video and not account:
        raise HTTPException(status_code=400, detail="account_id is required")

    video_path = str((video or {}).get("video_path") or payload.video_path or "").strip()
    platform = str((account or {}).get("platform") or (video or {}).get("platform") or payload.platform or "tiktok").strip().lower() or "tiktok"
    caption_override = str(payload.caption or "").strip()
    hashtags_override = payload.hashtags if payload.hashtags else None
    caption = caption_override if caption_override else str((video or {}).get("caption") or "")
    hashtags = hashtags_override if hashtags_override is not None else ((video or {}).get("hashtags") or [])
    scheduled_at = str(payload.scheduled_at or "").strip()
    row = add_upload_queue_item(
        video_id=video_id,
        video_path=video_path,
        render_job_id=str(payload.render_job_id or "").strip(),
        part_no=int(payload.part_no or 0),
        channel_code=str(payload.channel_code or "").strip(),
        account_id=account_id,
        platform=platform,
        caption=caption,
        hashtags=hashtags,
        scheduled_at=scheduled_at,
        priority=int(payload.priority or 0),
        status='scheduled' if scheduled_at else 'pending',
        metadata={"source": "video_library" if video else "legacy"},
    )
    logger.info(
        "upload_queue_add queue_id=%s video_id=%s account_id=%s video_path=%s",
        row.get("queue_id"),
        video_id,
        account_id,
        video_path,
    )
    return {"status": "ok", "queue_id": row.get("queue_id"), "item": row}


@router.get("/queue")
def get_upload_queue(status: str = "", account_id: str = "", platform: str = "", limit: int = 100):
    items = list_upload_queue(
        limit=limit,
        status=str(status or "").strip().lower(),
        account_id=str(account_id or "").strip(),
        platform=str(platform or "").strip().lower(),
    )
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/history")
def get_upload_history(queue_id: str = "", limit: int = 50):
    items = list_upload_history(queue_id=str(queue_id or "").strip() or None, limit=limit)
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/queue/{queue_id}")
def get_upload_queue_detail(queue_id: str):
    row = get_upload_queue_item(queue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload queue item not found")
    return {"status": "ok", "item": row}


@router.get("/queue/{queue_id}/history")
def get_upload_queue_history(queue_id: str, limit: int = 50):
    row = get_upload_queue_item(queue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload queue item not found")
    items = list_upload_history(queue_id=queue_id, limit=limit)
    return {"status": "ok", "queue_id": queue_id, "count": len(items), "items": items}


@router.patch("/queue/{queue_id}")
def update_upload_queue_detail(queue_id: str, payload: UploadQueueUpdateRequest):
    current = get_upload_queue_item(queue_id)
    if not current:
        raise HTTPException(status_code=404, detail="Upload queue item not found")
    if str(current.get("status") or "").lower() not in {"pending", "scheduled", "held"}:
        raise HTTPException(status_code=409, detail=f"Upload queue item cannot be edited from status '{current.get('status')}'")
    changes = payload.model_dump(exclude_unset=True)
    if "account_id" in changes and changes["account_id"]:
        account = get_upload_account_row(str(changes["account_id"]).strip())
        if not account:
            raise HTTPException(status_code=404, detail="Upload account not found")
        if str(account.get("status") or "").lower() == "disabled":
            raise HTTPException(status_code=400, detail="Disabled account cannot be assigned")
    row = update_upload_queue_item(queue_id, changes)
    return {"status": "ok", "item": row}


@router.post("/queue/{queue_id}/hold")
def hold_upload_queue(queue_id: str):
    row = get_upload_queue_item(queue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload queue item not found")
    if str(row.get("status") or "").lower() not in {"pending", "scheduled", "failed"}:
        raise HTTPException(status_code=409, detail=f"Upload queue item cannot be held from status '{row.get('status')}'")
    final = update_upload_queue_item(queue_id, {"status": "held"})
    return {"status": "held", "queue_id": queue_id, "item": final}


@router.post("/queue/{queue_id}/resume")
def resume_upload_queue(queue_id: str):
    row = get_upload_queue_item(queue_id)
    if not row:
        raise HTTPException(status_code=404, detail="Upload queue item not found")
    if str(row.get("status") or "").lower() != "held":
        raise HTTPException(status_code=409, detail=f"Upload queue item cannot be resumed from status '{row.get('status')}'")
    next_status = "scheduled" if str(row.get("scheduled_at") or "").strip() else "pending"
    final = update_upload_queue_item(queue_id, {"status": next_status})
    return {"status": next_status, "queue_id": queue_id, "item": final}


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
    if current_status not in {"pending", "failed", "held", "scheduled"}:
        raise HTTPException(status_code=409, detail=f"Upload queue item cannot run from status '{current_status}'")

    account_id = str(row.get("account_id") or "").strip()
    if not account_id:
        raise HTTPException(status_code=400, detail="Upload queue item is missing account_id")
    account = get_upload_account_row(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Upload account not found")
    profile_path = _account_profile_path(account)
    account_status = str(account.get("status") or "").lower()
    if account_status in {"banned", "disabled", "limited"}:
        raise HTTPException(status_code=400, detail=f"Upload account status '{account_status}' cannot run uploads")
    login_state = str(account.get("login_state") or "unknown").lower()
    if login_state in {"logged_out", "expired", "challenge"}:
        raise HTTPException(status_code=400, detail=f"Upload account login_state '{login_state}' requires login check/login before upload")

    video_id = str(row.get("video_id") or "").strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="Upload queue item is missing video_id")
    video = get_upload_video_row(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Upload video not found")
    if str(video.get("status") or "").lower() == "disabled":
        raise HTTPException(status_code=400, detail="Disabled video cannot be uploaded")

    account_lock = acquire_upload_runtime_lock(
        lock_type="account_id",
        resource_key=account_id,
        account_id=account_id,
        queue_id=queue_id,
        profile_path=profile_path,
        metadata={"queue_id": queue_id, "video_id": video_id},
    )
    if not account_lock.get("acquired"):
        reason = "account/profile already busy"
        set_upload_queue_last_error(queue_id, reason)
        raise HTTPException(status_code=409, detail=reason)
    logger.info(
        "lock_acquired account_id=%s profile_path=%s queue_id=%s lock_type=account_id stale=%s",
        account_id,
        profile_path,
        queue_id,
        account_lock.get("stale_recovered"),
    )
    profile_lock = acquire_upload_runtime_lock(
        lock_type="profile_path",
        resource_key=profile_path,
        account_id=account_id,
        queue_id=queue_id,
        profile_path=profile_path,
        metadata={"queue_id": queue_id, "video_id": video_id},
    )
    if not profile_lock.get("acquired"):
        release_upload_runtime_locks_for_queue(queue_id)
        reason = "account/profile already busy"
        set_upload_queue_last_error(queue_id, reason)
        raise HTTPException(status_code=409, detail=reason)
    logger.info(
        "lock_acquired account_id=%s profile_path=%s queue_id=%s lock_type=profile_path stale=%s",
        account_id,
        profile_path,
        queue_id,
        profile_lock.get("stale_recovered"),
    )

    locked_row, acquired = mark_upload_queue_uploading(queue_id)
    if not locked_row:
        release_upload_runtime_locks_for_queue(queue_id)
        raise HTTPException(status_code=404, detail="Upload queue item not found")
    if not acquired:
        release_upload_runtime_locks_for_queue(queue_id)
        locked_status = str(locked_row.get("status") or "").lower()
        raise HTTPException(status_code=409, detail=f"Upload queue item is already {locked_status}")

    attempt_no = int(locked_row.get("attempt_count") or 0)
    video_path = Path(str(locked_row.get("video_path") or video.get("video_path") or "").strip())
    platform = str(locked_row.get("platform") or account.get("platform") or video.get("platform") or "tiktok").strip().lower()
    started_at = _utc_now_iso()
    started_dt = datetime.utcnow()

    logger.info(
        "upload_queue_run_start queue_id=%s video_path=%s account_id=%s platform=%s attempt_no=%s",
        queue_id,
        str(video_path),
        account_id,
        platform,
        attempt_no,
    )

    def _finish_failed(error: str, adapter_result: dict | None = None):
        finished_dt = datetime.utcnow()
        finished_at = finished_dt.isoformat() + "Z"
        duration = max(0.0, (finished_dt - started_dt).total_seconds())
        final = mark_upload_queue_failed(queue_id, error)
        history = insert_upload_history(
            queue_id=queue_id,
            account_id=account_id,
            video_id=video_id,
            platform=platform,
            video_path=str(video_path),
            status="failed",
            attempt_no=attempt_no,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration,
            error=error,
            adapter_result=adapter_result or {},
            metadata={"phase": "manual_worker"},
        )
        logger.error(
            "upload_queue_run_failed queue_id=%s video_path=%s account_id=%s platform=%s attempt_no=%s error=%s",
            queue_id,
            str(video_path),
            account_id,
            platform,
            attempt_no,
            error,
        )
        return {"status": "failed", "queue_id": queue_id, "item": final, "history": history, "error": error}

    if not video_path.exists() or not video_path.is_file():
        try:
            return _finish_failed(f"Video file not found: {video_path}")
        finally:
            released = release_upload_runtime_locks_for_queue(queue_id)
            for item in released:
                logger.info(
                    "lock_released account_id=%s profile_path=%s queue_id=%s lock_type=%s",
                    item.get("account_id") or "",
                    item.get("profile_path") or "",
                    queue_id,
                    item.get("lock_type") or "",
                )

    try:
        _, _, cfg = _build_queue_upload_cfg(account, locked_row)
        caption = _caption_with_hashtags(str(locked_row.get("caption") or ""), locked_row.get("hashtags") or [])
        adapter_attempts, detail = upload_one_video(
            cfg=cfg,
            video_path=video_path,
            scheduled_iso=datetime.now().astimezone().isoformat(),
            caption=caption,
            use_schedule=False,
            retry_count=0,
            headless=False,
        )
        result = {
            "adapter": "upload_one_video",
            "adapter_attempts": adapter_attempts,
            "detail": detail,
            "uploaded_at": _utc_now_iso(),
        }
        final = mark_upload_queue_success(queue_id, result)
        finished_dt = datetime.utcnow()
        finished_at = finished_dt.isoformat() + "Z"
        history = insert_upload_history(
            queue_id=queue_id,
            account_id=account_id,
            video_id=video_id,
            platform=platform,
            video_path=str(video_path),
            status="success",
            attempt_no=attempt_no,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=max(0.0, (finished_dt - started_dt).total_seconds()),
            error="",
            adapter_result=result,
            metadata={"phase": "manual_worker"},
        )
        logger.info(
            "upload_queue_run_success queue_id=%s video_path=%s account_id=%s platform=%s attempt_no=%s",
            queue_id,
            str(video_path),
            account_id,
            platform,
            attempt_no,
        )
        return {"status": "success", "queue_id": queue_id, "item": final, "history": history}
    except Exception as exc:
        return _finish_failed(str(exc) or "Upload failed", {"adapter": "upload_one_video"})
    finally:
        released = release_upload_runtime_locks_for_queue(queue_id)
        for item in released:
            logger.info(
                "lock_released account_id=%s profile_path=%s queue_id=%s lock_type=%s",
                item.get("account_id") or "",
                item.get("profile_path") or "",
                queue_id,
                item.get("lock_type") or "",
            )


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
    library_item = get_upload_video_row(channel_code)
    if library_item:
        return {"status": "ok", "item": library_item}

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

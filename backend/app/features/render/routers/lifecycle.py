"""Render lifecycle endpoints (audit FINDING-A03 lifecycle bucket).

Covers everything that submits, retries, resumes, cancels, or smoke-tests
a render: /process, /upload-local, /test-cloud-ai, /quick-process,
/resume/{id}, /retry/{id}, /{id}/cancel.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core import config as _cfg
from app.core.config import CHANNELS_DIR, TEMP_DIR
from app.core.naming import slugify
from app.features.render.engine.pipeline.render_pipeline import (
    _emit_render_event,
    _probe_video_duration,
    _validate_text_layers_or_400,
)
from app.features.render.engine.preview.ffmpeg_probers import (
    _detect_leading_black_duration,
    _run_ffmpeg_checked,
)
from app.models.schemas import (
    QuickProcessRequest,
    RenderRequest,
    RenderRequestStrict,
)
from app.models.render_public import RenderRequestPublic
from app.services.bin_paths import get_ffmpeg_bin
from app.services.channel_service import ensure_channel
from app.db.jobs_repo import get_job, list_job_parts, update_job_progress
from ._common import (
    _coerce_legacy_channel_payload,
    _emit_request_event,
    _queue_render_job,
    _validate_render_source,
)

router = APIRouter(tags=["render"])
logger = logging.getLogger("app.render")


@router.post("/process")
def create_render_job(public_payload: RenderRequestPublic):
    # Audit MT-3 phase 2 closure (Batch 10O, 2026-06-06): the wire surface
    # is now ``RenderRequestPublic`` — the explicit 88-field FE-facing
    # subset. A FE that sends a BE-only field (channel_code, resume_job_id,
    # ai_clip_*, ai_use_rag_memory, …) gets a 422 immediately instead of
    # silently sending an internal-surface field over the wire.
    #
    # Two-step validation:
    #   1. FastAPI deserializes the body into RenderRequestPublic
    #      (``extra='forbid'`` — structural gate at the boundary).
    #   2. Below we construct the full RenderRequest from the Public dump.
    #      That step applies RenderRequest's field validators (api-key
    #      strip per FINDING-F07, target_duration / output_count range
    #      bounds, render_profile / source_quality_mode allow-lists)
    #      AND fills in defaults for the 64 BE-only fields so the rest
    #      of the pipeline sees the same RenderRequest it always did.
    #
    # FINDING-C04 (the original Strict closure) stays satisfied because
    # Public is stricter than Strict on the FE-facing subset:
    # ``extra='forbid'`` plus an even smaller allowed field set.
    payload = RenderRequest(**public_payload.model_dump())
    _coerce_legacy_channel_payload(payload)
    # Apply server-wide LLM provider default to NEW jobs only.
    # Resume/retry: ai_provider stays as stored.
    if "ai_provider" not in public_payload.model_fields_set:
        payload.ai_provider = _cfg.AI_PROVIDER_DEFAULT
    try:
        _validate_render_source(payload)
        _validate_text_layers_or_400(payload)
    except HTTPException as exc:
        logger.warning("Render request rejected (HTTP %s): %s", exc.status_code, exc.detail)
        _emit_request_event(
            route="/api/render/process",
            status_code=exc.status_code,
            detail=str(exc.detail),
            channel_code=(payload.channel_code or "").strip(),
        )
        raise
    effective_channel = (payload.channel_code or "").strip() or "manual"
    # resume_job_id is BE-only by design (resume goes through /resume/{id}).
    # The full payload defaults it to None — fresh /process call always
    # creates a new job_id.
    job_id = payload.resume_job_id or str(uuid.uuid4())
    existing = get_job(job_id) if payload.resume_job_id else None
    resume_mode = bool(existing) and payload.resume_from_last
    _queue_render_job(job_id, effective_channel, payload, resume_mode=resume_mode, queued_message="Job queued")
    return {"job_id": job_id, "status": "queued", "resume_mode": resume_mode}


@router.post("/upload-local")
async def upload_local_video(
    file: UploadFile = File(...),
    channel_code: str = Form("T1"),
):
    """Accept a local video file upload from browser and save to channel source dir."""
    channel = (channel_code or "T1").strip()
    if not channel:
        raise HTTPException(status_code=400, detail="channel_code is required")
    ensure_channel(channel)
    source_dir = CHANNELS_DIR / channel / "upload" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "video.mp4"
    safe_name = slugify(Path(original_name).stem) or "video"
    ext = Path(original_name).suffix or ".mp4"
    dest = source_dir / f"{safe_name}{ext}"
    # Avoid overwriting.
    idx = 1
    while dest.exists():
        dest = source_dir / f"{safe_name}_{idx}{ext}"
        idx += 1

    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    return {"path": str(dest), "filename": dest.name, "size": dest.stat().st_size}


@router.post("/test-cloud-ai")
def test_cloud_ai(body: dict):
    """Validate cloud AI provider credentials.

    Sends a minimal prompt and returns latency. Never touches the render pipeline.
    Body: { provider: "gemini"|"openai"|"claude", api_key: str, model?: str }
    """
    import time
    provider = str(body.get("provider") or "gemini").lower()
    api_key  = str(body.get("api_key") or "").strip()
    model    = body.get("model") or None

    # If no API key in body, fall back to server env.
    if not api_key:
        _env_map = {
            "gemini": getattr(_cfg, "GEMINI_API_KEY", ""),
            "openai": getattr(_cfg, "OPENAI_API_KEY", ""),
            "claude": getattr(_cfg, "CLAUDE_API_KEY", ""),
        }
        api_key = (_env_map.get(provider) or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key for provider={provider} (not in body and "
                   f"{provider.upper()}_API_KEY env empty)",
        )

    _TEST_MESSAGES = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user",   "content": "Reply with the single word: ready"},
    ]

    t0 = time.monotonic()
    try:
        if provider == "openai":
            import openai as _openai
            resolved_model = model or "gpt-4o-mini"
            client = _openai.OpenAI(api_key=api_key, timeout=10)
            resp = client.chat.completions.create(
                model=resolved_model,
                messages=_TEST_MESSAGES,
                max_tokens=8,
                temperature=0.0,
            )
        elif provider == "gemini":
            from google import genai as _genai
            resolved_model = model or "gemini-2.0-flash"
            client = _genai.Client(api_key=api_key)
            _gem_resp = client.models.generate_content(
                model=resolved_model,
                contents="Reply with the single word: ready",
                config={"temperature": 0.0, "max_output_tokens": 8},
            )
            # Mock OpenAI-style response so the latency_ms path below works.
            class _R:
                pass
            resp = _R()
            resp.choices = [_R()]
            resp.choices[0].message = _R()
            resp.choices[0].message.content = (_gem_resp.text or "").strip()
        elif provider == "claude":
            try:
                from anthropic import Anthropic as _AnthClient
            except ImportError:
                raise HTTPException(status_code=501, detail="anthropic SDK not installed")
            resolved_model = model or "claude-haiku-4-5-20251001"
            client = _AnthClient(api_key=api_key, timeout=10)
            _claude_resp = client.messages.create(
                model=resolved_model,
                max_tokens=8,
                messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            )
            class _R:
                pass
            resp = _R()
            resp.choices = [_R()]
            resp.choices[0].message = _R()
            resp.choices[0].message.content = _claude_resp.content[0].text if _claude_resp.content else ""
        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"ok": True, "provider": provider, "model": resolved_model, "latency_ms": latency_ms}

    except HTTPException:
        raise
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        msg = str(exc)
        # Shorten verbose SDK error messages for the UI.
        if "invalid_api_key" in msg.lower() or "authentication" in msg.lower() or "401" in msg:
            msg = "Invalid API key"
        elif "model" in msg.lower() and ("not found" in msg.lower() or "does not exist" in msg.lower()):
            msg = f"Model not found: {resolved_model}"  # type: ignore[possibly-undefined]
        elif "connection" in msg.lower() or "timeout" in msg.lower():
            msg = "Connection failed — check network"
        logger.debug("test_cloud_ai_failed provider=%s: %s", provider, exc)
        return {"ok": False, "provider": provider, "error": msg, "latency_ms": latency_ms}


@router.post("/quick-process")
def quick_process(payload: QuickProcessRequest):
    """
    Simple one-shot flow over a local file:
    - Optionally apply resize/filter
    - Save to exact output file path
    """
    source = (payload.source or "local").strip().lower()
    local_path_raw = (payload.path or "").strip()
    output_raw = (payload.output or "").strip()

    quick_job_id = str(uuid.uuid4())
    _emit_render_event(
        channel_code="quick",
        job_id=quick_job_id,
        event="render.start",
        level="INFO",
        message="Quick render started",
        step="render.start",
        context={"source": source},
    )
    if source != "local":
        raise HTTPException(
            status_code=400,
            detail=(
                f"source='{source}' is not supported. "
                "Use the standalone Downloader to fetch remote sources, "
                "then call /api/render/quick-process with source='local'."
            ),
        )
    if not local_path_raw:
        raise HTTPException(status_code=400, detail="path is required when source='local'")
    if not output_raw:
        raise HTTPException(status_code=400, detail="output is required")
    if (payload.resize_width and not payload.resize_height) or (payload.resize_height and not payload.resize_width):
        raise HTTPException(status_code=400, detail="resize_width and resize_height must be provided together")
    if payload.resize_width is not None and payload.resize_width <= 0:
        raise HTTPException(status_code=400, detail="resize_width must be > 0")
    if payload.resize_width is not None and payload.resize_width > 7680:
        raise HTTPException(status_code=400, detail="resize_width must be <= 7680 (8K)")
    if payload.resize_height is not None and payload.resize_height <= 0:
        raise HTTPException(status_code=400, detail="resize_height must be > 0")
    if payload.resize_height is not None and payload.resize_height > 4320:
        raise HTTPException(status_code=400, detail="resize_height must be <= 4320 (8K)")
    if payload.black_min_duration <= 0:
        raise HTTPException(status_code=400, detail="black_min_duration must be > 0")
    if payload.black_threshold < 0 or payload.black_threshold > 1:
        raise HTTPException(status_code=400, detail="black_threshold must be between 0 and 1")

    output_path = Path(output_raw).expanduser()
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()
    if output_path.exists() and output_path.is_dir():
        raise HTTPException(status_code=400, detail="output must be a file path, not a directory")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid output path: {exc}") from exc

    job_id = str(uuid.uuid4())
    work_dir = TEMP_DIR / f"quick_{job_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        _emit_render_event(
            channel_code="quick",
            job_id=quick_job_id,
            event="render.input.validate.start",
            level="INFO",
            message="Validating quick render input",
            step="render.input.validate",
        )
        src_path = Path(local_path_raw).expanduser()
        if not src_path.is_absolute():
            src_path = (Path.cwd() / src_path).resolve()
        if not src_path.exists() or not src_path.is_file():
            raise HTTPException(status_code=400, detail=f"Local file not found: {src_path}")
        downloaded_title = src_path.stem
        duration = _probe_video_duration(src_path)

        vf_parts: list[str] = []
        if payload.resize_width and payload.resize_height:
            vf_parts.append(f"scale={int(payload.resize_width)}:{int(payload.resize_height)}")
        if (payload.video_filter or "").strip():
            _vf = (payload.video_filter or "").strip()
            # Security: allowlist prevents FFmpeg filter injection via crafted vf chains.
            # Filters like 'movie=', 'geq=', 'script=' can read files or run OS commands.
            _SAFE_VF_FILTERS = {
                "scale", "fps", "crop", "rotate", "transpose",
                "hflip", "vflip", "pad", "setsar", "setdar",
            }
            _vf_name = re.split(r"[=,\s]", _vf)[0].strip().lower()
            if _vf_name not in _SAFE_VF_FILTERS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported video filter '{_vf_name}'. "
                           f"Allowed filters: {sorted(_SAFE_VF_FILTERS)}",
                )
            vf_parts.append(_vf)

        overwrite_flag = "-y" if payload.overwrite else "-n"
        trim_start_sec = 0.0
        if payload.trim_black_intro:
            trim_start_sec = _detect_leading_black_duration(
                src_path,
                min_duration=float(payload.black_min_duration),
                threshold=float(payload.black_threshold),
            )

        _emit_render_event(
            channel_code="quick",
            job_id=quick_job_id,
            event="render.input.validate.success",
            level="INFO",
            message="Quick render input validated",
            step="render.input.validate",
            context={"source_path": str(src_path), "output": str(output_path)},
        )
        has_transform = bool(vf_parts) or (trim_start_sec > 0)

        if not has_transform:
            # Fast path: no transform requested and no leading black to trim.
            copy_cmd = [
                get_ffmpeg_bin(),
                overwrite_flag,
                "-i", str(src_path),
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_path),
            ]
            try:
                _run_ffmpeg_checked(copy_cmd, "FFmpeg copy failed")
            except Exception:
                has_transform = True

        if has_transform:
            # Single processing pass. Avoid intermediate temp files.
            _emit_render_event(
                channel_code="quick",
                job_id=quick_job_id,
                event="render.ffmpeg.start",
                level="INFO",
                message="Running ffmpeg quick process",
                step="render.ffmpeg",
                context={"trim_start_sec": round(trim_start_sec, 3), "filters": len(vf_parts)},
            )
            cmd = [
                get_ffmpeg_bin(),
                overwrite_flag,
            ]
            if trim_start_sec > 0:
                cmd += ["-ss", f"{trim_start_sec:.3f}"]
            cmd += ["-i", str(src_path)]
            if vf_parts:
                cmd += ["-vf", ",".join(vf_parts)]
            if trim_start_sec > 0 and not vf_parts:
                # Fast trim path with stream copy; fallback to encode for edge cases.
                trim_copy_cmd = [
                    *cmd,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
                try:
                    _run_ffmpeg_checked(trim_copy_cmd, "FFmpeg trim copy failed")
                except HTTPException:
                    trim_encode_cmd = [
                        *cmd,
                        "-c:v", "libx264",
                        "-preset", "medium",
                        "-crf", "20",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-movflags", "+faststart",
                        str(output_path),
                    ]
                    _run_ffmpeg_checked(trim_encode_cmd, "FFmpeg trim encode failed")
            else:
                cmd += [
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "20",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
                _run_ffmpeg_checked(cmd, "FFmpeg processing failed")
            _emit_render_event(
                channel_code="quick",
                job_id=quick_job_id,
                event="render.ffmpeg.success",
                level="INFO",
                message="Quick ffmpeg processing completed",
                step="render.ffmpeg",
            )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(f"Output file was not created: {output_path}")
        _emit_render_event(
            channel_code="quick",
            job_id=quick_job_id,
            event="render.complete",
            level="INFO",
            message="Quick render success",
            step="render.complete",
            context={"output": str(output_path)},
        )

        return {
            "status": "completed",
            "source": source,
            "url": "",
            "path": str(src_path),
            "output": str(output_path),
            "downloaded_title": downloaded_title,
            "duration": duration,
            "processed": has_transform,
            "trim_applied": trim_start_sec > 0,
            "trim_start_sec": round(trim_start_sec, 3),
        }
    except HTTPException:
        _emit_render_event(
            channel_code="quick",
            job_id=quick_job_id,
            event="render.error",
            level="ERROR",
            message="Quick render request failed",
            step="render.error",
        )
        raise
    except Exception as exc:
        _emit_render_event(
            channel_code="quick",
            job_id=quick_job_id,
            event="render.error",
            level="ERROR",
            message=f"Quick render failed: {exc}",
            step="render.error",
            exception=exc,
            traceback_text=traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


@router.post("/resume/{job_id}")
def resume_render_job(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    payload_json = row.get("payload_json") or "{}"
    try:
        payload_data = json.loads(payload_json)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot parse payload_json for job {job_id}: {e}") from e

    payload = RenderRequest(**payload_data)
    payload.resume_from_last = True
    _coerce_legacy_channel_payload(payload)
    _validate_render_source(payload)
    effective_channel = (payload.channel_code or "").strip() or "manual"
    _queue_render_job(job_id, effective_channel, payload, resume_mode=True, queued_message="Resume job queued")
    return {"job_id": job_id, "status": "queued", "resume_mode": True}


@router.post("/retry/{job_id}")
def retry_failed_parts(job_id: str):
    """Re-run only the failed parts of a completed or partially-failed render job.

    Done parts are preserved; only parts with status='failed' are re-processed.
    Equivalent to resume, but validated to have at least one failed part.

    Audit FINDING-BR13 closure (Batch 10B 2026-06-06): retry semantic is
    "fresh plan per retry". This handler does NOT touch ``render_plan_json``
    directly. The pipeline runs end-to-end (LLM Call 1 + Call 2) on retry
    just like a normal render, and ``update_render_plan(job_id, new_plan)``
    overwrites whatever blob was previously stored. This is the correct
    behaviour for creator-context updates between retries — the new plan
    reflects the current creator prefs. Done parts are still skipped by
    the per-part status check in ``part_renderer.py``, so the new plan
    only drives the re-rendering of failed parts.
    """
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if (row.get("status") or "").lower() in ("running", "queued"):
        raise HTTPException(status_code=409, detail="Job is already running or queued")

    parts = list_job_parts(job_id)
    failed = [p for p in parts if (p.get("status") or "").lower() == "failed"]
    if not failed:
        raise HTTPException(status_code=400, detail="No failed parts to retry")

    payload_json = row.get("payload_json") or "{}"
    try:
        payload_data = json.loads(payload_json)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot parse payload for job {job_id}: {e}") from e

    payload = RenderRequest(**payload_data)
    payload.resume_from_last = True
    _coerce_legacy_channel_payload(payload)
    _validate_render_source(payload)
    effective_channel = (payload.channel_code or "").strip() or "manual"
    _queue_render_job(
        job_id, effective_channel, payload,
        resume_mode=True,
        queued_message=f"Retrying {len(failed)} failed part(s)",
    )
    return {"job_id": job_id, "status": "queued", "failed_parts_count": len(failed)}


@router.post("/{job_id}/cancel")
def cancel_render_job(job_id: str):
    """Signal a running or queued render job to stop.

    Returns immediately with status='cancelling'. The job transitions to
    status='cancelled' asynchronously once the current FFmpeg call is
    terminated (within ~1 s of receiving the signal).
    """
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    status = (row.get("status") or "").lower()
    if status not in ("running", "queued"):
        raise HTTPException(status_code=409, detail=f"Job is not cancellable (status={status})")
    update_job_progress(job_id, "cancelling", 0, "Cancelling…", status="cancelling")
    from app.jobs import cancel as cancel_registry
    cancel_registry.request_cancel(job_id)
    return {"job_id": job_id, "status": "cancelling"}

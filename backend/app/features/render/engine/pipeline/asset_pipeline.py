from __future__ import annotations

import os
import time
from pathlib import Path

from app.models.schemas import RenderRequest
from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log, _safe_unlink
from app.features.render.engine.pipeline.remotion_adapter import (
    append_outro_clip,
    apply_logo_watermark,
    generate_hook_intro,
    prepend_intro_clip,
    resolve_intro_preset,
)


def _maybe_prepend_remotion_hook_intro(
    final_part: Path,
    payload: RenderRequest,
    *,
    effective_channel: str,
    job_id: str,
    part_no: int,
    headline_text: str | None = None,
    content_type: str = "vlog",
    hook_text: str | None = None,
    source_title: str | None = None,
) -> float:
    if not bool(getattr(payload, "remotion_hook_intro", False)):
        return 0.0

    _preset = resolve_intro_preset(
        content_type,
        override=str(getattr(payload, "intro_preset", "") or "").strip() or None,
    )
    # Per-preset duration â€” drives both the intro clip length and the return value
    # which feeds _expected_final_duration in the part timing calculation.
    _preset_durations = {
        "viral_pop": 1.0,
        "clean_creator": 1.2,
        "story_cinematic": 1.5,
        "gaming_energy": 1.0,
    }
    _duration = _preset_durations.get(_preset, 1.0)

    started = time.perf_counter()
    intro_path = final_part.with_name(f"{final_part.stem}.hook_intro.mp4")
    concat_path = final_part.with_name(f"{final_part.stem}.with_intro.mp4")
    _job_log(
        effective_channel,
        job_id,
        f"hook_intro_requested part={part_no} preset={_preset} duration_sec={_duration:.2f}",
    )
    try:
        intro = generate_hook_intro(
            str(intro_path),
            aspect_ratio=str(getattr(payload, "aspect_ratio", "3:4") or "3:4"),
            duration_sec=_duration,
            headline_text=headline_text,
            preset_id=_preset,
            hook_text=hook_text,
            source_title=source_title,
        )
        if not intro:
            _job_log(
                effective_channel,
                job_id,
                f"hook_intro_failed part={part_no} reason=intro_generation_failed",
                kind="warning",
            )
            return 0.0
        merged = prepend_intro_clip(str(final_part), intro, str(concat_path))
        if not merged:
            _job_log(
                effective_channel,
                job_id,
                f"hook_intro_failed part={part_no} reason=concat_failed",
                kind="warning",
            )
            return 0.0
        os.replace(merged, final_part)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _job_log(
            effective_channel,
            job_id,
            f"hook_intro_generated part={part_no} preset={_preset} intro_duration_ms={int(_duration * 1000)} elapsed_ms={elapsed_ms}",
        )
        return _duration
    except Exception as exc:
        _job_log(
            effective_channel,
            job_id,
            f"hook_intro_failed part={part_no} error={type(exc).__name__}: {exc}",
            kind="warning",
        )
        return 0.0
    finally:
        _safe_unlink(intro_path)
        _safe_unlink(concat_path)


# â”€â”€ UP27: Creator Asset Intelligence helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# All three are safe-skip: missing file â†’ log asset_missing_skip, continue.
# Never raise. Never fail the render.

def _maybe_prepend_asset_intro(
    final_part: Path,
    payload,
    *,
    effective_channel: str,
    job_id: str,
    part_no: int,
) -> None:
    intro_path_raw = str(getattr(payload, "asset_intro_path", None) or "").strip()
    if not intro_path_raw:
        return
    intro_path = Path(intro_path_raw)
    if not intro_path.exists() or intro_path.stat().st_size <= 0:
        _job_log(effective_channel, job_id,
                 f"asset_missing_skip type=intro path={intro_path_raw} part={part_no}", kind="warning")
        _emit_render_event(channel_code=effective_channel, job_id=job_id,
                           event="asset_missing", level="WARNING",
                           message=f"UP27 asset intro missing, skipped part={part_no}",
                           step="render.asset", context={"type": "intro", "part_no": part_no})
        return
    concat_path = final_part.with_name(f"{final_part.stem}.with_asset_intro.mp4")
    try:
        merged = prepend_intro_clip(str(final_part), str(intro_path), str(concat_path))
        if merged:
            os.replace(merged, final_part)
            _job_log(effective_channel, job_id,
                     f"asset_applied type=intro part={part_no} file={intro_path.name}")
            _emit_render_event(channel_code=effective_channel, job_id=job_id,
                               event="asset_applied", level="INFO",
                               message=f"UP27 creator intro sting applied part={part_no}",
                               step="render.asset", context={"type": "intro", "part_no": part_no})
        else:
            _job_log(effective_channel, job_id,
                     f"asset_skipped type=intro part={part_no} reason=concat_failed", kind="warning")
    except Exception as exc:
        _job_log(effective_channel, job_id,
                 f"asset_error type=intro part={part_no} error={exc}", kind="warning")
    finally:
        _safe_unlink(concat_path)


def _maybe_append_asset_outro(
    final_part: Path,
    payload,
    *,
    effective_channel: str,
    job_id: str,
    part_no: int,
) -> None:
    outro_path_raw = str(getattr(payload, "asset_outro_path", None) or "").strip()
    if not outro_path_raw:
        return
    outro_path = Path(outro_path_raw)
    if not outro_path.exists() or outro_path.stat().st_size <= 0:
        _job_log(effective_channel, job_id,
                 f"asset_missing_skip type=outro path={outro_path_raw} part={part_no}", kind="warning")
        _emit_render_event(channel_code=effective_channel, job_id=job_id,
                           event="asset_missing", level="WARNING",
                           message=f"UP27 asset outro missing, skipped part={part_no}",
                           step="render.asset", context={"type": "outro", "part_no": part_no})
        return
    concat_path = final_part.with_name(f"{final_part.stem}.with_asset_outro.mp4")
    try:
        merged = append_outro_clip(str(final_part), str(outro_path), str(concat_path))
        if merged:
            os.replace(merged, final_part)
            _job_log(effective_channel, job_id,
                     f"asset_applied type=outro part={part_no} file={outro_path.name}")
            _emit_render_event(channel_code=effective_channel, job_id=job_id,
                               event="asset_applied", level="INFO",
                               message=f"UP27 creator outro applied part={part_no}",
                               step="render.asset", context={"type": "outro", "part_no": part_no})
        else:
            _job_log(effective_channel, job_id,
                     f"asset_skipped type=outro part={part_no} reason=concat_failed", kind="warning")
    except Exception as exc:
        _job_log(effective_channel, job_id,
                 f"asset_error type=outro part={part_no} error={exc}", kind="warning")
    finally:
        _safe_unlink(concat_path)


def _maybe_apply_asset_logo(
    final_part: Path,
    payload,
    *,
    effective_channel: str,
    job_id: str,
    part_no: int,
) -> None:
    logo_path_raw = str(getattr(payload, "asset_logo_path", None) or "").strip()
    if not logo_path_raw:
        return
    logo_path = Path(logo_path_raw)
    if not logo_path.exists() or logo_path.stat().st_size <= 0:
        _job_log(effective_channel, job_id,
                 f"asset_missing_skip type=logo path={logo_path_raw} part={part_no}", kind="warning")
        _emit_render_event(channel_code=effective_channel, job_id=job_id,
                           event="asset_missing", level="WARNING",
                           message=f"UP27 asset logo missing, skipped part={part_no}",
                           step="render.asset", context={"type": "logo", "part_no": part_no})
        return
    watermarked = final_part.with_name(f"{final_part.stem}.with_logo.mp4")
    try:
        result = apply_logo_watermark(str(final_part), str(logo_path), str(watermarked),
                                      position="top-right", opacity=0.85)
        if result:
            os.replace(result, final_part)
            _job_log(effective_channel, job_id,
                     f"asset_applied type=logo part={part_no} file={logo_path.name}")
            _emit_render_event(channel_code=effective_channel, job_id=job_id,
                               event="asset_applied", level="INFO",
                               message=f"UP27 creator logo watermark applied part={part_no}",
                               step="render.asset", context={"type": "logo", "part_no": part_no})
        else:
            _job_log(effective_channel, job_id,
                     f"asset_skipped type=logo part={part_no} reason=overlay_failed", kind="warning")
    except Exception as exc:
        _job_log(effective_channel, job_id,
                 f"asset_error type=logo part={part_no} error={exc}", kind="warning")
    finally:
        _safe_unlink(watermarked)

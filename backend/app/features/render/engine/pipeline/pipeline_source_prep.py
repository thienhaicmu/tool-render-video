"""Render-pipeline source-preparation stage.

Sprint 6.D-1.3 â€” extracted verbatim from render_pipeline.py
(lines 373â€“591 of the pre-1.3 file). No logic changes; pure relocation.

Responsibilities (in order):
  1. Emit render.prepare_source.start + render.input.validate.start.
  2. Set stage = DOWNLOADING (progress 5) via the caller's _set_stage closure.
  3. Resolve edit_session_id; if present, load_session_fn -> editor session video.
  4. Otherwise validate payload.source_mode == "local" and resolve the local
     source file path.
  5. Emit prepare-paths + select-strategy events for whichever branch ran.
  6. Compute _output_stem via _smart_output_stem(hook_applied_text, title, job_id).
  7. Apply editor edits (trim_in/trim_out + volume) via FFmpeg subprocess
     when needed; mutate source dict + source_path to point at the edited file.
  8. Pre-render preflight: re-verify local source exists (catches files
     moved/deleted between validation and edits).
  9. Optional keep_source_copy: persist or move temp-origin sources into the
     output_dir/source/ tree; local-original sources are passed through
     without copying (avoids 10GB+ duplication).

This function executes inside the caller's outer try/except (the orchestrator
in render_pipeline.py). All RuntimeError / FFmpeg exceptions propagate up
unchanged â€” the caller's existing exception handler classifies them by
current_stage (set via set_stage callable).

Sacred Contracts honored:
  - #4 Frozen job stages: only JobStage.DOWNLOADING referenced (via set_stage).
  - #6 _emit_render_event signature: every call site preserves kwargs.
  - #7 No raw DB writes â€” only update_job_progress (via set_stage) and
       no upsert_job calls here.
  - #8 qa_pipeline not bypassed (not touched here).
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.models.schemas import RenderRequest
from app.core.config import TEMP_DIR
from app.core.stage import JobStage
from app.services.bin_paths import get_ffmpeg_bin, _summarize_ffmpeg_stderr
from app.features.download.engine.downloader import slugify
from app.features.render.engine.pipeline.pipeline_config import (
    _probe_video_duration,
    _reserve_source_path_in_dir,
)
from app.features.render.engine.pipeline.pipeline_segment_selection import _smart_output_stem
from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log


@dataclass
class SourcePrepResult:
    """Outputs of prepare_render_source consumed by the rest of run_render_pipeline."""
    source: dict
    source_path: Path
    edit_session_id: str
    detected_source_mode: str
    output_stem: str


def prepare_render_source(
    *,
    job_id: str,
    effective_channel: str,
    payload: RenderRequest,
    work_dir: Path,
    output_dir: Path,
    hook_applied_text: str,
    set_stage: Callable[[str, int, str], None],
    load_session_fn: Callable,
) -> SourcePrepResult:
    """Run the source-preparation block. Raises on any preflight failure;
    caller's outer try/except classifies the failure by current_stage.
    """
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.prepare_source.start",
        level="INFO",
        message="Preparing source",
        step="render.prepare_source",
        context={"source_mode": payload.source_mode},
    )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.input.validate.start",
        level="INFO",
        message="Validating render input",
        step="render.input.validate",
    )
    set_stage(JobStage.DOWNLOADING, 5, "Preparing source video")
    edit_session_id = (getattr(payload, "edit_session_id", None) or "").strip()
    sess = load_session_fn(edit_session_id) if edit_session_id else None
    if edit_session_id and not sess:
        raise RuntimeError(
            f"Editor session '{edit_session_id}' not found â€” "
            "the session may have expired or the server was restarted. "
            "Please re-open the editor to re-prepare the source."
        )
    detected_source_mode = "session" if sess else "local"
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.prepare_source.detect_input",
        level="INFO",
        message=f"Detecting source type: {detected_source_mode}",
        step="render.prepare_source.detect_input",
        context={"source_mode": detected_source_mode},
    )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.prepare_source.validate_input",
        level="INFO",
        message="Validating source input",
        step="render.prepare_source.validate_input",
    )
    if sess:
        source_path = Path(sess["video_path"])
        if not source_path.exists():
            raise RuntimeError(f"Editor session video not found: {source_path}")
        source = {
            "title": sess.get("title", source_path.stem),
            "slug": slugify(sess.get("title", source_path.stem)),
            "duration": sess.get("duration") or _probe_video_duration(source_path),
            "filepath": str(source_path),
        }
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.prepare_paths",
            level="INFO",
            message="Preparing source paths",
            step="render.prepare_source.prepare_paths",
            context={"source_path": str(source_path), "work_dir": str(work_dir)},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.select_strategy",
            level="INFO",
            message="Selecting editor-session source strategy",
            step="render.prepare_source.select_strategy",
            context={"strategy": "editor_session"},
        )
        _job_log(effective_channel, job_id, f"Reusing editor session video: {source_path}")
    else:
        if payload.source_mode and payload.source_mode.lower() not in ("local",):
            raise RuntimeError(
                f"Unsupported source_mode '{payload.source_mode}'. "
                "Only local video files are supported."
            )
        source_path = Path(payload.source_video_path or "").expanduser().resolve()
        if not source_path.exists() or not source_path.is_file():
            raise RuntimeError(
                f"Render stopped: the source video file was not found.\n"
                f"Path: {source_path}\n"
                f"Please reopen the editor and verify the file is still accessible."
            )
        source = {
            "title": source_path.stem.replace("_", " ").replace("-", " "),
            "slug": slugify(source_path.stem),
            "duration": _probe_video_duration(source_path),
            "filepath": str(source_path),
        }
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.prepare_paths",
            level="INFO",
            message="Preparing source paths",
            step="render.prepare_source.prepare_paths",
            context={"source_path": str(source_path), "work_dir": str(work_dir)},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.select_strategy",
            level="INFO",
            message="Selecting local source strategy",
            step="render.prepare_source.select_strategy",
            context={"strategy": "local_source"},
        )
        _job_log(effective_channel, job_id, f"Local source selected: {source_path}")
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.input.validate.success",
        level="INFO",
        message="Render input validated",
        step="render.input.validate",
        context={"source_path": str(source_path)},
    )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.prepare_source.success",
        level="INFO",
        message="Source prepared successfully",
        step="render.prepare_source.success",
        context={"source_mode": detected_source_mode, "source_path": str(source_path)},
    )

    # Compute once; captured by _process_one_part closure and auto_best_export
    _output_stem = _smart_output_stem(hook_applied_text, source.get("title", ""), job_id)

    # Apply editor edits: trim and/or volume adjustment
    trim_in = float(getattr(payload, "edit_trim_in", 0) or 0)
    trim_out = float(getattr(payload, "edit_trim_out", 0) or 0)
    edit_volume = float(getattr(payload, "edit_volume", 1.0) or 1.0)
    needs_trim = trim_in > 0.5 or (trim_out > 0.5 and trim_out < source["duration"] - 0.5)
    needs_volume = abs(edit_volume - 1.0) > 0.005
    if needs_trim or needs_volume:
        edited_path = work_dir / f"edited_{source_path.stem}.mp4"
        cmd = [get_ffmpeg_bin(), "-y"]
        if trim_in > 0.5:
            cmd += ["-ss", f"{trim_in:.3f}"]
        cmd += ["-i", str(source_path)]
        if needs_trim and trim_out > 0.5 and trim_out < source["duration"] - 0.5:
            duration_t = trim_out - (trim_in if trim_in > 0.5 else 0)
            cmd += ["-t", f"{max(1.0, duration_t):.3f}"]
        if needs_volume:
            cmd += ["-af", f"volume={edit_volume:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k"]
        else:
            cmd += ["-c:v", "copy", "-c:a", "copy"]
        cmd += ["-avoid_negative_ts", "make_zero", str(edited_path)]
        _job_log(effective_channel, job_id, f"Applying edits: trim_in={trim_in:.1f}s trim_out={trim_out:.1f}s volume={edit_volume:.2f}")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as _preprocess_exc:
            _pp_stderr = _preprocess_exc.stderr or ""
            _pp_diag = _summarize_ffmpeg_stderr(_pp_stderr)
            _pp_tail = _pp_stderr[-2000:].strip()
            _job_log(
                effective_channel, job_id,
                f"FFmpeg preprocess failed exit={_preprocess_exc.returncode} diag={_pp_diag!r}",
                kind="warning",
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.ffmpeg.preprocess.error",
                level="ERROR",
                message=f"FFmpeg preprocess failed: {_pp_diag}",
                step="render.preprocess",
                context={
                    "exit_code": _preprocess_exc.returncode,
                    "diagnostic": _pp_diag,
                    "stderr_tail": _pp_tail,
                    "input_path": str(source_path),
                    "output_path": str(edited_path),
                },
            )
            raise RuntimeError(f"FFmpeg preprocess failed: {_pp_diag}") from _preprocess_exc
        new_dur = _probe_video_duration(edited_path)
        source["duration"] = new_dur or max(1, source["duration"] - trim_in)
        source_path = edited_path
        source["filepath"] = str(edited_path)
        _job_log(effective_channel, job_id, f"Edits applied â†’ {edited_path} | new_duration={source['duration']}s")

    # Pre-render source preflight: catch local files moved/deleted after initial validation
    if detected_source_mode == "local" and not source_path.exists():
        raise RuntimeError(
            f"Render stopped: the source video file was moved or deleted.\n"
            f"Path: {source_path}\n"
            f"Please reopen the editor and confirm the file is still accessible."
        )

    if payload.keep_source_copy:
        ext = source_path.suffix or ".mp4"
        keep_source_dir = output_dir / "source"
        # If output is a typical "video_output/video_out" folder, keep source as sibling under upload/source.
        if output_dir.name.lower() in ("video_output", "video_out"):
            keep_source_dir = output_dir.parent / "source"
        # Only temp-origin files (YouTube downloads, edited locals) need to be
        # persisted into source/. A user's original local file is already permanent â€”
        # copying it would waste disk space (10 GB+) and slow render startup.
        is_temp_source = str(source_path).startswith(str(TEMP_DIR))
        if is_temp_source:
            keep_path = _reserve_source_path_in_dir(keep_source_dir, source["slug"], ext=ext)
            if not keep_path.exists():
                # Move instead of copy when source is in temp dir (instant on same drive, saves I/O + disk)
                try:
                    shutil.move(str(source_path), str(keep_path))
                    _job_log(effective_channel, job_id, f"Source moved (zero-copy) to: {keep_path}")
                except Exception:
                    shutil.copy2(source_path, keep_path)
                    _job_log(effective_channel, job_id, f"Source copied to: {keep_path}")
            source_path = keep_path
        else:
            # Local original (not temp): render directly from user's file â€” no copy, no hardlink.
            _job_log(effective_channel, job_id, f"local_source.passthrough path={source_path} (source copy skipped)")

    return SourcePrepResult(
        source=source,
        source_path=source_path,
        edit_session_id=edit_session_id,
        detected_source_mode=detected_source_mode,
        output_stem=_output_stem,
    )

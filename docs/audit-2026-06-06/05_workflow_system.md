# 05 — System Sequence (render)

End-to-end trace of one render job, from the FE click through pipeline completion. Every node cites file:line evidence.

> Two earlier docs feed this one: [04_workflow_user.md](04_workflow_user.md) (UI per step) and [07_workflow_render.md](07_workflow_render.md) (deep render pipeline). This file is the **single canonical sequence map**.

---

## Diagram (ASCII)

```
USER clicks "Start Render"
│
▼  RenderWorkflow.tsx:199  handleStartRender()
   assembles  RenderRequest  from  cfg + prepareResult + sources
│
▼  HTTP POST /api/render/process       (api/render.ts:11)
│
├──────────────  BACKEND  ──────────────
│
│  features/render/router.py:584  create_render_job(req)
│    ├─ _coerce_legacy_channel_payload
│    ├─ _validate_render_source         (file exists, output_dir)
│    ├─ _validate_text_layers_or_400
│    ├─ effective_channel = req.channel_code or "manual"
│    ├─ job_id = req.resume_job_id or uuid.uuid4()
│    └─ _queue_render_job(...)          [router.py:542]
│         ├─ if is_running(job_id): raise HTTPException(409)
│         ├─ DB-WRITE #1
│         │    db/jobs_repo.py:12  upsert_job(job_id, "render", channel,
│         │      status="queued", stage=QUEUED, progress_percent=0,
│         │      payload_json=..., result_json="{}")
│         └─ submit_job(job_id, process_render, job_id, payload, resume_mode)
│              jobs/manager.py:~52  heappush(_pending, (-prio, seq, job_id, fn))
│              _cond.notify_all()
│
▼  HTTP 200 { job_id, status:"queued" }
│
│  FE:
│    setJobId(); setStep(3);  useRenderSocket(jobId) → opens WS
│
═════════════════════════════════════════════════════════════
SCHEDULER  (daemon, jobs/manager.py:95 _scheduler_loop)
═════════════════════════════════════════════════════════════
│
│  wait _cond  until  pending && active < MAX_CONCURRENT_JOBS
│  job = heappop(_pending);  _active_job_ids.add(job_id)
│
│  DB-WRITE #2
│    db/jobs_repo.py:36  update_job_progress(job_id, "starting", 0,
│      status="running")
│
│  executor.submit(_run, fn=process_render, args=(job_id, payload, resume))
│
═════════════════════════════════════════════════════════════
WORKER THREAD                router.py:497  process_render()
═════════════════════════════════════════════════════════════
│
│  cancel_registry.register(job_id) → threading.Event
│  start_monotonic = time.monotonic()
│
│  run_render_pipeline(job_id, payload, resume_mode,
│      load_session_fn=_load_session,
│      cleanup_session_fn=_cleanup_preview_session)
│
═════════════════════════════════════════════════════════════
PIPELINE                     features/render/engine/pipeline/
                             render_pipeline.py:299 run_render_pipeline
═════════════════════════════════════════════════════════════
│
│  setup_render_pipeline(payload)
│  prepare_output_dir(job_id, channel, output_dir)
│  DB-WRITE #3  upsert_job(stage=STARTING, progress=1, message="Initializing")
│
│  TRY:
│  ┌── Phase 1  prepare_render_source()          pipeline_source_prep.py:65
│  │    local-file branch  OR  editor-session branch
│  │    probe duration via ffprobe; optionally trim/re-encode
│  │    returns source dict + path
│  │
│  ├── Phase 2  run_manual_voice_tts() (if narration_enabled)
│  │                                              pipeline_narration.py
│  │    edge-tts or XTTS → voice_audio_path.wav
│  │
│  ├── Phase 3  run_llm_pre_render()              llm_pipeline.py:68
│  │    1. Whisper transcribe (cached) → full_srt
│  │       cache key SHA based on (path, mtime, size, model, lang)
│  │       cache TTL 72 h
│  │    2. select_segments(provider, srt, …)     llm/__init__.py
│  │       Claude / OpenAI / Gemini  →  scored[]
│  │    HARD-FAIL if no API key / no audio / Whisper fails / empty SRT /
│  │              empty LLM result / segments out of bounds
│  │    DB-WRITE  update_job_progress(stage=TRANSCRIBING_FULL, progress=28)
│  │
│  ├── Phase 4  RenderPlan emission (LLM_EMIT_RENDER_PLAN=1, default ON)
│  │                                              render_pipeline.py:533–652
│  │    select_render_plan()                     llm/__init__.py
│  │    on success:
│  │      DB-WRITE #4  update_render_plan(job_id, plan_json)
│  │                      db/jobs_repo.py:61
│  │      WS event "render.plan.persisted"
│  │    on failure:
│  │      _render_plan = None; legacy path silently engages
│  │      WS event "render.plan.ai_fallback"
│  │    if _render_plan present, derive scored[] from RenderPlan.clips
│  │
│  ├── Phase 5  Subtitle pre-processing
│  │    subtitle_enabled_by_idx (gating by viral score)
│  │    if add_subtitle and need full-srt: TRANSCRIBING_FULL
│  │    (reuse if available)
│  │
│  ├── Phase 6  run_render_loop(...)             pipeline_render_loop.py:43
│  │    JOB_SEMAPHORE.acquire() — concurrent encode throttle
│  │    resolve max_workers, ffmpeg_threads
│  │    DB-WRITE  update_job_progress(stage=RENDERING_PARALLEL, progress=30)
│  │
│  │    foreach scored seg in scored[]:
│  │       process_one_part(ctx, idx, seg)       stages/part_renderer.py:91
│  │         ├─ asset_planner → SRT/ASS, camera strategy
│  │         ├─ part_cut       → raw_part.mp4 (or skip if RAW_PART_SKIP)
│  │         ├─ part_render_setup → encode params + progress timer
│  │         ├─ part_render_encode → FFmpeg (NVENC sem-protected)
│  │         ├─ part_voice_mix → narration mix
│  │         ├─ part_render_finalize → qa_pipeline._validate_render_output
│  │         └─ part_done → upsert_job_part(stage=DONE)
│  │       DB-WRITE (multiple) upsert_job_part at every stage
│  │
│  └── Phase 7  run_render_finalize(...)          pipeline_finalize.py:76
│       result_json assembly (output_rank_score / is_best_clip / is_best_output)
│       optional best-export copy (P5-2)
│       DB-WRITE #5  upsert_job(status="completed", result_json=...)
│       db_backup snapshot (optional)
│       WS event "render.complete" + "render.ffmpeg.success"
│
│  EXCEPT  Exception:
│       _emit_render_event(level=error, stage=…)
│       DB-WRITE #6  upsert_job(status="failed", result_json={"error":…})
│
│  EXCEPT  cancel_registry.JobCancelledError:
│       DB-WRITE #7  update_job_progress(stage=CANCELLED, status="cancelled")
│
│  FINALLY:
│       cleanup_temp_files (rm -rf work_dir if requested)
│       cleanup_session_fn(edit_session_id) if any
│       unregister_job_log_dir(job_id)
│
═════════════════════════════════════════════════════════════
WORKER cleanup           router.py:517 process_render() finally
═════════════════════════════════════════════════════════════
│  metrics:
│    RENDER_JOBS_TOTAL.labels(status=final).inc()
│    RENDER_JOB_DURATION.labels(status=final).observe(elapsed)
│  cancel_registry.unregister(job_id)
│
═════════════════════════════════════════════════════════════
WEBSOCKET PROGRESS  (in parallel, throughout pipeline)
═════════════════════════════════════════════════════════════
FE  RenderSocketClient    websocket/RenderSocketClient.ts
│   onmessage → ignore "ping"; on isProgressEvent:
│     setStage, setProgress, setLiveParts, setJobStatus
│
BE  routes/jobs.py:644  ws_job_progress(websocket, job_id)
│   await websocket.accept()
│   loop:
│     job   = get_job(job_id)            db/jobs_repo.py:141
│     parts = list_job_parts(job_id)     db/jobs_repo.py:151
│     summary = _compute_progress_summary(parts)
│     fp = _ws_fingerprint(job, parts, summary)
│     if fp changed or terminal:
│        if failed: save_error_kind(job_id, _classify_error_kind(job))
│        await websocket.send_json({"job":job, "parts":parts, "summary":summary})
│     elif elapsed_since_send >= 25 s:
│        await websocket.send_json({"type":"ping"})
│     if terminal: break
│     await asyncio.sleep(0.5)
```

---

## Critical paths summarised

| Concern | Where it actually happens |
|---|---|
| Job state authority | `data/app.db` only (Sacred Contract #7); writes via `db/jobs_repo.py` |
| Backpressure | `MAX_CONCURRENT_JOBS` (jobs/manager.py) + `JOB_SEMAPHORE` (pipeline_render_loop.py:64) + `NVENC_SEMAPHORE` (encoder/ffmpeg_helpers.py:27-28) |
| Cancellation | `cancel_registry` (`jobs/cancel.py`) — threading.Event polled at safe checkpoints in pipeline + ffmpeg subprocess loop |
| Progress emission | `update_job_progress` + WS handler diffing fingerprints. **No push from pipeline to WS handler.** |
| Event log (separate from WS) | `_emit_render_event` writes JSON lines to per-job log file; not sent on the WS frame |
| Resume | `payload.resume_job_id` + `resume_from_last` reuses existing DB row + cached source files |
| QA gate | `qa_pipeline._validate_render_output` in `part_render_finalize` (Sacred Contract #8) |
| Sacred Contract #1 keys | written by `pipeline_ranking.py:230, 237-238` and copied through finalize |
| Sacred Contract #6 WS shape | `{job, parts, summary}` — only emitted by `routes/jobs.py:644-696` handler |

---

## DB writes timeline (typical successful render)

```
#1  jobs            INSERT (status=queued)            router._queue_render_job
#2  jobs            UPDATE (status=running)           jobs/manager._mark_job_running
#3  jobs            UPDATE (stage=STARTING)           render_pipeline (init)
… periodic        update_job_progress                _set_stage closure
#4  jobs            UPDATE (render_plan_json)         after LLM Phase 4
#5  job_parts       INSERT per part                   part_renderer (per stage)
#6  job_parts       UPDATE per part                   per-stage transitions
#7  jobs            UPDATE (result_json, completed)   pipeline_finalize
#8  jobs            UPDATE (error_kind)               routes/jobs._classify on terminal failed
```

Roughly **12–14 writes for a successful render**, plus 4–6 per clip — dominated by `upsert_job_part` and per-frame `update_job_progress` writes from the progress timer thread (3 s cadence). The thread-local `_thread_conn` model exists specifically to make these cheap (Phase 1 / `03_database_inventory.md`).

---

## Findings

**FINDING-S01 (HIGH if surface ever expands beyond localhost):** No auth anywhere. See [04_workflow_user.md](04_workflow_user.md) FINDING-U01.

**FINDING-S02 (LOW):** WS is poll-then-push. `_emit_render_event` JSON lines go to log files, never reach the FE. The FE state model is "DB poll over a WS frame". Acceptable but worth documenting because it explains why event-log timestamps don't match WS timestamps.

**FINDING-S03 (MED):** Feature-flag explosion in `render_pipeline.py:109-161` — 4 active flags plus 2 recently retired. Each flag multiplies the test matrix. Phase 11 roadmap should retire flags whose "settling window" has expired (per top-of-file comments).

**FINDING-S04 (MED):** Sacred Contracts referenced by number throughout the codebase (Contract #1, #2, #3, #5, #6, #7, #8) but documented only in `CLAUDE.md` (now partly stale, see Phase 1). Risk: a future refactor breaks one silently. Phase 10 will produce a clean `08_api_reference.md`-style canonical document.

**FINDING-S05 (LOW):** RenderPlan emission is non-fatal by design — when the LLM fails, the job continues on legacy `scored[]`. The FE sees no error. Reasonable, but the WS event `render.plan.ai_fallback` is **not displayed in the FE**. The user has no idea AI fell back. Phase 7 should propose surfacing this.

**FINDING-S06 (LOW):** Two progress percent computations: pipeline writes a single `progress_percent` to `jobs`; WS handler also computes `overall_progress_percent` from per-part states. They can disagree mid-flight. Cosmetic.

**FINDING-S07 (HIGH):** Per Phase 1 FINDING-B05, `llm_pipeline.py` **raises** `LLMPipelineError` when no provider works. That exception propagates up to `run_render_pipeline`'s outer try, kills the job, sets status `failed`. **This is the only path in the whole system where a single missing API key takes the whole job down**, and it's silent in the FE (just shows a failed status). Phase 11 should propose either (a) a legacy fallback path, or (b) a clearer FE-visible error code.

End of 05_workflow_system.md.

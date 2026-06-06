# 19 — Backend Reference

Rebuilt from code on 2026-06-06. For deep tracing see [02_backend_inventory.md](02_backend_inventory.md), [05_workflow_system.md](05_workflow_system.md), [07_workflow_render.md](07_workflow_render.md).

## Entry point

[backend/app/main.py](../../backend/app/main.py) (369 LOC). FastAPI app with 11 main routers + 2 conditional V2 routers, CSP middleware, 3 startup daemons, graceful shutdown.

## Layout

```
backend/app/
├── main.py                          # entry: routers + startup + middleware
├── core/                            # config, logging, stage, ui_gate, devtools_safety
├── domain/                          # render_plan, creator_context, manifests, timeline (pure dataclasses)
├── db/                              # SQLite connection + per-table repos + migrations
│   ├── connection.py                # db_conn ctxmgr + _thread_conn (hot path)
│   ├── jobs_repo.py                 # jobs + job_parts
│   ├── creator_repo.py              # creator_prefs singleton
│   ├── feedback_repo.py             # clip_feedback
│   ├── download_repo.py             # download_jobs
│   └── migration_steps/             # 0001 add render_plan_json, 0002 groq→llm rewrite
├── jobs/
│   ├── manager.py                   # priority heap + ThreadPoolExecutor
│   └── cancel.py                    # per-job threading.Event
├── models/schemas.py                # 26+ Pydantic models (892 LOC)
├── routes/                          # legacy routers
│   ├── channels.py, jobs.py, feedback.py, files.py,
│   ├── settings.py, voice.py, metrics.py, devtools.py
├── services/                        # non-feature services + facade
│   ├── bin_paths.py                 # ffmpeg/ffprobe path resolution
│   ├── channel_service.py
│   ├── db.py                        # 49-line re-export facade
│   ├── maintenance.py               # disk cleanup helpers
│   ├── metrics.py                   # Prometheus gauges
│   ├── warmup.py                    # startup warmup tasks
│   └── qa_runner.py
└── features/
    ├── download/                    # yt-dlp + per-platform adapters
    │   ├── router.py
    │   ├── service.py
    │   ├── engine/                  # downloader, platform_detect, cookie_extractor, ...
    │   └── adapters/                # youtube, tiktok, instagram, facebook, douyin, generic
    └── render/                      # main feature
        ├── router.py                # /api/render (15+ endpoints, 1195 LOC)
        ├── editing/                 # trim/rerender/export
        ├── ai/                      # LLM dispatch + analysis + creator context + visibility
        │   ├── analysis/            # hybrid + local + cloud variants
        │   ├── llm/                 # providers, prompts, parser, dispatch
        │   ├── context/builder.py
        │   ├── visibility/ai_visibility_summary.py
        │   ├── dependencies.py      # optional-import gates
        │   ├── diagnostics.py
        │   └── tracing.py
        └── engine/                  # render engine
            ├── audio/               # mixer, tts (edge), tts_xtts
            ├── encoder/             # ffmpeg_helpers, clip_renderer, clip_ops, overlay_compositor
            ├── motion/              # detection, crop, cache, path, tracker, trackerless, ...
            ├── overlay/text_overlay.py
            ├── pipeline/            # render_pipeline + 15 stage helpers + qa_pipeline + db_backup
            ├── preview/             # session_service + media_streaming + ffmpeg_probers
            ├── quality/             # assessor + models + report_summary
            ├── stages/              # part_renderer skeleton + 8 part_* helpers
            ├── subtitle/            # transcription/ + generator/ + processing/ + translation
            └── thumbnail/thumbnail_quality.py
```

Ghost dirs (zero `.py`): `backend/app/{ai,orchestration,quality}/` — delete per Phase 4 DC03.

## Routers + URL prefixes

| File | Prefix | Endpoints | Notes |
|---|---|---|---|
| `routes/channels.py` | `/api/channels` | 6 | all UNCALLED (Phase 6 API05) |
| `features/render/router.py` | `/api/render` | 19 | god controller (Phase 3 A03); 8 USED, 11 UNCALLED |
| `routes/jobs.py` | `/api/jobs` | 13 (+ WS) | 9 USED, 4 internal/deprecated |
| `features/render/editing/router.py` | `/api/jobs` | 3 | trim/rerender/export — all USED |
| `routes/feedback.py` | `/api/feedback` | 4 | 3 USED, 1 UNCALLED |
| `features/download/router.py` | `/api/downloader` | 10 (+ WS) | 7 USED, 3 UNCALLED |
| `routes/files.py` | `/api/upload-file` | 1 | USED |
| `routes/settings.py` | `/api/settings` | 2 | both USED |
| `routes/voice.py` | `/api/voice` | 1 | UNCALLED |
| `routes/metrics.py` | `/metrics` | 1 | Prometheus scrape |
| `routes/devtools.py` | `/api/dev` | 1 | env-gated shell exec |

70 total (excluding V2). Catalog: [13_api_catalog.md](13_api_catalog.md).

## Startup sequence

[main.py:227-280](../../backend/app/main.py) `@app.on_event("startup")`:

1. `init_db()` — schema + migrations.
2. DB fallback path probe.
3. Default channel `"k1"` ensure.
4. Log/preview/render-temp/cache prune.
5. `recover_pending_render_jobs()` — marks orphan jobs as `interrupted`.
6. `start_warmup()`.
7. Spawn 3 daemons: Whisper warmup, periodic cleanup, cookie extraction.

## Shutdown sequence

[main.py:333](../../backend/app/main.py) `@app.on_event("shutdown")`: graceful job manager drain with `SHUTDOWN_TIMEOUT_SEC` (default 30 s).

## Services facade

`services/db.py` (49 LOC) re-exports `db.connection`, `db.jobs_repo`, etc. 18 callers depend on it. See Phase 3 A14 for cleanup plan.

End of 19_backend.md.

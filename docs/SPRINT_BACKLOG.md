# Sprint Backlog — Phases C–T

> Last updated: 2026-06-13
> Branch: `feature/phases-c-to-l` (commit `3375850f`)
> Pytest baseline: 1087 passed, 1 pre-existing failure (test_render_pipeline_integration)
> Post-sprint: 1319 passed, 1 pre-existing failure — all 16 phases DONE

---

## Completed ✓

| Phase | Tên | Files chính | Commit |
|-------|-----|-------------|--------|
| C | Asset Library | `db/assets_repo.py`, `domain/asset.py`, `features/download/engine/enrichment.py`, `routes/assets.py`, migration `0007` | `3375850f` |
| D | Creator Feedback Loop | `db/feedback_repo.py` → `get_feedback_signals()`, `features/render/ai/feedback/signals.py`, `llm_stage.py` | `3375850f` |
| E | Smart Render Presets | `db/presets_repo.py`, `domain/render_preset.py`, `routes/presets.py`, `services/preset_seeder.py`, migration `0008` | `3375850f` |
| F | Multi-Output Compare & Export | `db/ab_scores_repo.py` → `list_ab_scores_for_job()`, `routes/outputs.py` | `3375850f` |
| G | Analytics Dashboard API | `routes/analytics.py` — overview / scores trend / feedback by-hook / jobs trend | `3375850f` |
| H | Whisper Speed Optimization | `adapters.py` → `WHISPER_BATCH_SIZE`, `pipeline_cache.py` → content-hash cache (`WHISPER_CONTENT_HASH_CACHE`) | `3375850f` |
| I | Per-Channel Creator Context API | `routes/channels_context.py` — `GET/PUT/DELETE /api/channels/{code}/context` | `3375850f` |
| J | Output Thumbnail API | `routes/thumbnails.py` — `GET /api/jobs/{id}/outputs/{part_no}/thumbnail` | `3375850f` |
| K | Batch Render from Asset Library | `routes/batch_render.py` — `POST /api/render/batch` (max 20 assets + preset) | `3375850f` |
| L | Disk Usage & Cleanup API | `routes/storage.py` — summary / per-job delete / bulk cleanup | `3375850f` |
| P | Job Snapshot Endpoint | `routes/snapshot.py` (NEW), `main.py` | 2026-06-13 |
| Q | Asset Search & Filter API | `db/assets_repo.py` (extended), `routes/assets.py` (query params + `filters` key) | 2026-06-13 |
| M | Job Clone / Re-render API | `routes/job_clone.py` (NEW), `main.py` | 2026-06-13 |
| R | LLM Prompt Preview | `routes/prompt_preview.py` (NEW), `main.py` | 2026-06-13 |
| S | Job Export Report | `routes/job_report.py` (NEW), `main.py` | 2026-06-13 |
| T | Output File Archive | `routes/storage.py` (archive endpoint), `db/jobs_repo.py` (`update_part_output_path`) | 2026-06-13 |

---

## All phases complete — no remaining items

## Env vars mới (Phase H)

| Var | Default | Mô tả |
|-----|---------|--------|
| `WHISPER_BATCH_SIZE` | `8` (CUDA) / `4` (CPU) | WhisperX batch size |
| `WHISPER_CONTENT_HASH_CACHE` | `0` | `1` = enable content-hash transcription cache |

## API endpoints mới (Phases C–L)

| Method | Path | Phase |
|--------|------|-------|
| GET | `/api/assets` | C |
| GET | `/api/assets/{asset_id}` | C |
| DELETE | `/api/assets/{asset_id}` | C |
| GET | `/api/jobs/{id}/outputs` | F |
| GET | `/api/jobs/{id}/outputs/best` | F |
| GET | `/api/jobs/{id}/outputs/export` | F |
| GET | `/api/jobs/{id}/outputs/{part_no}/thumbnail` | J |
| DELETE | `/api/jobs/{id}/outputs` | L |
| GET | `/api/analytics/overview` | G |
| GET | `/api/analytics/scores/trend` | G |
| GET | `/api/analytics/feedback/by-hook` | G |
| GET | `/api/analytics/jobs/trend` | G |
| GET | `/api/presets` | E |
| POST | `/api/presets` | E |
| PUT | `/api/presets/{id}` | E |
| DELETE | `/api/presets/{id}` | E |
| GET | `/api/channels/{code}/context` | I |
| PUT | `/api/channels/{code}/context` | I |
| DELETE | `/api/channels/{code}/context` | I |
| POST | `/api/render/batch` | K |
| GET | `/api/storage/summary` | L |
| POST | `/api/storage/cleanup` | L |
| GET | `/api/jobs/{id}/snapshot` | P |
| POST | `/api/jobs/{id}/clone` | M |
| POST | `/api/render/preview-prompt` | R |
| GET | `/api/jobs/{id}/report` | S |
| POST | `/api/jobs/{id}/outputs/archive` | T |

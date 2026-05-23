# Render Rules

## Reality Check

`render_pipeline.py` = **5,816 lines**. All render stages in one file.
Every render stage, part update, event emission, and result write is here.
Never touch casually. Full pytest required — not optional.

## Sacred — Never Break

| Contract | File | What must stay intact |
|----------|------|-----------------------|
| Stage transitions: `QUEUED→DOWNLOADING→RENDERING→DONE` | `render_pipeline.py` | Order and names |
| Part status: `QUEUED→WAITING→CUTTING→TRANSCRIBING→RENDERING→DONE` | `render_pipeline.py` | Order and names |
| `_emit_render_event` signature | `render_pipeline.py` | Event shape consumed by WS + UI |
| `result_json` backward-compat aliases | `render_pipeline.py` | `output_rank_score`, `is_best_output`, `is_best_clip` |
| NVENC semaphore | `render_engine.py` | `NVENC_MAX_SESSIONS` — protects GPU |
| FFmpeg path escaping | `render_engine.py` | Use `safe_filter_path`, `get_ffmpeg_bin`, `get_ffprobe_bin` |
| Output validation | `qa_pipeline.py` | Never bypass — failed renders must stay visible |

## Before Any Render Edit (mandatory flow)

1. Read `docs/RENDER_PIPELINE.md`
2. Read `docs/ARCHITECTURE.md`
3. Planner produces analysis with explicit file list
4. Get **explicit user approval** (not implicit)
5. Run full pytest → record baseline
6. Make minimal patch
7. Run full pytest → verify no regression

## Concurrency — Never Change Casually

- `MAX_CONCURRENT_JOBS` — protects local machine from overload
- `MAX_RENDER_JOBS` — render-specific parallelism cap
- `NVENC_MAX_SESSIONS` — GPU encoder protection

Only change with explicit request + reasoning.

## Never Do

- Bypass `qa_pipeline.py` to make a render "succeed"
- Remove partial-success handling (partial renders must stay visible)
- Change `_emit_render_event` call signature without updating all consumers
- Remove resume/retry behavior from `render_pipeline.py`
- Skip source cleanup on failure paths

## Render-adjacent (HIGH risk, plan first)

- `backend/app/orchestration/qa_pipeline.py` — output validation
- `backend/app/orchestration/asset_pipeline.py` — asset injection
- `backend/app/orchestration/render_events.py` — error classification
- `backend/app/services/segment_builder.py` — clip boundary builder

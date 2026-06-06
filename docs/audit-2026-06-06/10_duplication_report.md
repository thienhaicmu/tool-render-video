# 10 — Duplication Report

Each finding needs ≥2 file:line citations doing the same thing. Source code only.

---

## HIGH

### FINDING-DUP01 — Job ID regex/validator triplicated

Same regex `^[A-Za-z0-9_-]{1,128}$` compiled and `_validate_job_id` implemented independently in three files:

| File:line | Returns |
|---|---|
| [backend/app/features/render/editing/editing_service.py:27, 45](../../backend/app/features/render/editing/editing_service.py) | `bool` |
| [backend/app/features/render/editing/router.py:28, 31](../../backend/app/features/render/editing/router.py) | raises `HTTPException` |
| [backend/app/features/render/engine/quality/report_locator.py:20, 23](../../backend/app/features/render/engine/quality/report_locator.py) | `bool` |

**Risk:** if the format changes (e.g., to support `uuid` form), all three must be updated — likely one will drift and silently accept invalid IDs.

**Action:** introduce `app/core/identifiers.py::JobId.parse(raw) -> str | None`. All callers consume one helper; tests live in one place.

---

## MEDIUM

### FINDING-DUP02 — 72-hour TTL hardcoded in two cache systems

| File:line | Constant |
|---|---|
| [backend/app/features/render/engine/motion/cache.py:22](../../backend/app/features/render/engine/motion/cache.py) | `_MOTION_CACHE_TTL_SEC = 72 * 3600` |
| [backend/app/services/maintenance.py:76](../../backend/app/services/maintenance.py) | `max_age_hours=72` default |
| [backend/app/main.py:210, 241](../../backend/app/main.py) | passes `max_age_hours=72` |

Drift would mean a cache that lives beyond pruning, leaking disk indefinitely.

**Action:** `app/core/cache_policy.py::DEFAULT_TTL_SEC = 72 * 3600`. Import everywhere.

### FINDING-DUP03 — Render output / source validation re-done in pipeline

Two layers of `output_dir` validation:

- [features/render/router.py:201-260](../../backend/app/features/render/router.py): `_validate_output_dir`, `_validate_render_source`.
- [features/render/engine/pipeline/pipeline_setup.py:54-111](../../backend/app/features/render/engine/pipeline/pipeline_setup.py): re-derives + re-validates output_path (lines 90-98).

Both should agree on what's valid. Already exact today, but a future fix to one is easy to miss.

**Action:** make pipeline assume the API already validated; or extract a shared `RenderRequestValidator`.

### FINDING-DUP04 — Legacy channel-mode coercion split

- [features/render/router.py:207-215](../../backend/app/features/render/router.py): `_coerce_legacy_channel_payload`.
- [features/render/engine/pipeline/pipeline_setup.py:~66](../../backend/app/features/render/engine/pipeline/pipeline_setup.py): re-infers `output_mode = (payload.output_mode or "channel").strip().lower()`.

Two places interpret the same legacy semantics. **Action:** coerce once at the API boundary; pipeline trusts the input.

### FINDING-DUP05 — Two progress percent formulas

- [features/render/engine/pipeline/render_events.py:203](../../backend/app/features/render/engine/pipeline/render_events.py): timer thread `progress = min(99, 70 + int(30 * elapsed / expected_duration))`.
- [features/render/engine/pipeline/render_pipeline.py:1337](../../backend/app/features/render/engine/pipeline/render_pipeline.py): `progress_percent = max(0, min(99, int(current_progress)))`.
- [routes/jobs.py:525+](../../backend/app/routes/jobs.py): `_compute_progress_summary` recomputes `overall_progress_percent` from per-part states.

Three computations for one UX number. They will not always agree mid-flight (FE may see WS-computed `overall_progress_percent` flicker against the part-store `progress` of the active part).

**Action:** decide which is authoritative (vote: the pipeline write to `jobs.progress_percent`), the WS handler echoes it, the FE renders one.

---

## LOW

### FINDING-DUP06 — FFmpeg AAC argv pair inlined 11+ times

`["-c:a", "aac", "-b:a", "<bitrate>"]` constructed inline at:

- [features/render/engine/encoder/clip_ops.py:98, 381](../../backend/app/features/render/engine/encoder/clip_ops.py) (2 sites)
- [features/render/engine/encoder/clip_renderer.py:222, 505, 568](../../backend/app/features/render/engine/encoder/clip_renderer.py) (3 sites)
- [features/render/engine/audio/mixer.py:86, 96, 109, 120, 131, 141](../../backend/app/features/render/engine/audio/mixer.py) (6 sites)
- [features/render/router.py:908, 919](../../backend/app/features/render/router.py) (2 sites)

If the codec is changed to Opus or AAC bitrate is parametrized centrally, all 13 sites move together. **Action:** `app/features/render/engine/encoder/audio_args.py::aac_args(bitrate)`.

### FINDING-DUP07 — SRT timestamp parsing in two files

- [features/render/engine/subtitle/generator/srt.py:58-95](../../backend/app/features/render/engine/subtitle/generator/srt.py) — `parse_srt_timestamp`, `_parse_srt_blocks`, `parse_srt_blocks` for ASS generation.
- [features/render/ai/llm/prompts.py:13-43](../../backend/app/features/render/ai/llm/prompts.py) — `_srt_to_seconds_format` parses timestamps too for token-compressed prompt.

The regex is simple and each consumer has a different output format, so risk is genuinely low — but a shared `SrtTime.parse(line) -> float` would cost nothing.

### FINDING-DUP08 — Whisper model default chosen by 3 different rules

- [features/render/router.py:471](../../backend/app/features/render/router.py): preview hard-codes `"tiny"`.
- [features/render/engine/pipeline/llm_pipeline.py:175](../../backend/app/features/render/engine/pipeline/llm_pipeline.py): env `LLM_WHISPER_MODEL` or `tuned["whisper_model"]`.
- [features/render/engine/pipeline/pipeline_config.py:23-38](../../backend/app/features/render/engine/pipeline/pipeline_config.py): profile-based (`"base"`, `"small"`, `"large-v3"`).

Three places pick the model with different rules. **Intentional** (preview must be fast; main must be accurate; LLM call may want different) — but the rule should be documented in one comment.

### FINDING-DUP09 — `slugify` imported across feature boundary

- Defined in [features/download/engine/downloader.py](../../backend/app/features/download/engine/downloader.py).
- Imported by [features/render/router.py:25](../../backend/app/features/render/router.py).
- Imported by [features/render/engine/pipeline/pipeline_source_prep.py:46](../../backend/app/features/render/engine/pipeline/pipeline_source_prep.py).

A render feature importing a downloader feature is wrong-direction. Phase 3 FINDING-A08 already flagged the cross-feature coupling. **Action:** move to `app/core/naming.py`.

### FINDING-DUP10 — FE Job state in store + hook (architectural, not a bug)

- Global `useRenderStore.jobs{}` ([renderStore.ts:9-11](../../frontend/src/stores/renderStore.ts))
- Local `useRenderSocket` state (`stage`, `progress`, `liveParts`, `jobStatus`)

The two converge on terminal events ([useRenderSocket.ts:76](../../frontend/src/hooks/useRenderSocket.ts)). By design (live WS stream + global persistence) — not duplication in the harmful sense.

---

## Summary

| # | Severity | Pattern | Action |
|---|---|---|---|
| DUP01 | HIGH | JobId validator x3 | Extract to `core/identifiers.py` |
| DUP02 | MED | 72 h TTL constant x3 | Shared `cache_policy.DEFAULT_TTL_SEC` |
| DUP03 | MED | RenderRequest validation x2 | One validator at API boundary |
| DUP04 | MED | Legacy channel coercion x2 | Coerce once |
| DUP05 | MED | Progress formula x3 | One authoritative source |
| DUP06 | LOW | AAC argv x11 | Helper `aac_args()` |
| DUP07 | LOW | SRT parsing x2 | Shared `SrtTime.parse` |
| DUP08 | LOW | Whisper model defaults x3 | Document the policy |
| DUP09 | LOW | `slugify` cross-feature | Move to `core/naming.py` |
| DUP10 | — | FE state | by design |

End of 10_duplication_report.md.

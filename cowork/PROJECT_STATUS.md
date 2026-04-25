# Project Status — Render Studio

Last updated: 2026-04-25

---

## Current Architecture

Architecture V2 is active and stable.

```
routes/ → orchestration/render_pipeline.py → services/ → core/
```

- All render pipeline logic lives in `orchestration/render_pipeline.py`
- `routes/render.py` is an HTTP boundary only
- Session callbacks are passed as arguments to avoid circular imports

---

## Phase Stability

| Phase | Description | Status |
|---|---|---|
| Phase 0 | Core stability — SQLite persistence, job queue, channel structure | Stable |
| Phase 1 | Preview/render trust — editor session flow, prepare-source, session reuse | Stable |
| Phase 2 | Failure visibility — structured logs, error classification, request.log | Stable |
| Phase 3 | Narration hardening — Edge TTS, audio mix modes, BGM filter_complex fix | Stable |
| Phase 4 | Cowork hardening — COWORK_SYSTEM_DEFINITION, prompts, task templates | Stable |
| Phase 5 | Scale work — parallel render, adaptive workers, motion crop | Active — Treat Carefully |

---

## Current Caution Areas

### Phase 5 Scale Work
- Parallel part rendering uses adaptive worker cap based on hardware detection
- NVENC probe uses a null-encode test — GPU driver state can affect this
- Motion-aware crop (OpenCV) is active in the render path — CPU-intensive
- **No additional scale or parallelism changes without review**

### Editor Session Flow
- Session reuse is working and well-tested
- The `edit_session_id` check MUST come before `source_mode` dispatch
- If session is missing when `edit_session_id` is set: raise, do not re-download
- Session expiry: 6 hours after creation or after server restart

### Frontend
- `render-ui.js` and `render-engine.js` have complex state machines
- The `_ev` state object (editor session state) is the critical bridge between editor and render
- Text layer normalizers (`_toOutline`, `_toShadow`, `_toBg`) must run before payload submission
- `evTxtFont` options must stay in sync with `VALID_FONTS` in `text_overlay.py`

---

## Safe Work Right Now

These tasks are safe to do without extra review:
- Documentation cleanup (`cowork/`, `docs/`, `prompts/`)
- Cowork command clarity (this file, COMMANDS.md, FIX_PROMPT.md)
- Test checklist updates
- Log analysis and error investigation
- Single-service bug fixes with `/test` verification

---

## Tasks That Require Review Before Starting

- Any change to `orchestration/render_pipeline.py`
- Any change to `routes/render.py`
- Any change to frontend JS files
- Parallelism or worker count changes
- New API fields or status enums
- Database schema changes
- Electron shell changes

Protocol: produce a plan, get explicit approval, then implement.

---

## What Is Known Fragile (External Dependencies)

| Component | Why Fragile |
|---|---|
| YouTube format availability | yt-dlp client list may need updating when formats are blocked |
| TikTok upload selectors | Playwright selectors drift when TikTok updates its UI |
| NVENC availability | Depends on GPU driver state — varies across machines |

These are not bugs to fix with /fix. They require targeted investigation.

---

## Stable Interfaces (Do Not Break)

- SQLite job/part schema
- Channel folder structure (`video_out/`, `upload/source|uploaded|failed/`, `logs/`)
- `run_render_pipeline()` callback interface (`load_session_fn`, `cleanup_session_fn`)
- `VALID_FONTS` set in `text_overlay.py`
- `JobStage` and `JobPartStage` enum values
- `STAGE_TO_EVENT` mapping
- Session in-memory + disk fallback

---

## Merge Recommendation

Do NOT merge the `refactor/project-structure-cowork` branch until the user manually verifies:
- [ ] App starts cleanly
- [ ] Render flow completes at least one job
- [ ] `/fix`, `/test`, `/error`, `/status` docs are clear and accurate
- [ ] No runtime files were changed

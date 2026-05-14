# PRODUCT-ARCHITECTURE-REVIEW-3

Creator-first frontend rebuild contract.

This document defines how the frontend should be rebuilt before any Figma or implementation work begins. It is not a redesign, wireframe, visual direction, or implementation patch. It preserves only implemented workflow, capability, runtime dependencies, and user task flow.

The current frontend is a workflow reference only. Do not preserve its layout, page organization, panel organization, DOM structure, CSS architecture, JavaScript organization, or visual hierarchy.

## 1. Creator Mental Model

The creator should understand the product as:

```text
Bring in a source
  -> let the system find and improve publishable clips
  -> review ranked outputs
  -> export or continue to download/upload workflows
```

The product should not feel like an FFmpeg control panel. The creator should believe the product does four things:

1. Prepares source video for short-form production.
2. Helps decide which moments are worth turning into clips.
3. Applies creator-controlled enhancements: subtitles, voice, crop, text, market/hook settings, and render profile.
4. Produces ranked output packages with explanations, warnings, and recovery paths.

The creator-facing mental model should be:

```text
Create
  -> Optimize
  -> Render
  -> Review
  -> Reuse
```

### Create

The creator starts with a YouTube URL or local file and turns it into a prepared preview session. This maps to `/api/render/prepare-source`, preview video serving, source validation, and preview transcript support.

Create does not mean a blank canvas or full timeline editor. Arbitrary multi-track nonlinear editing is not implemented.

### Optimize

The creator configures how clips should be generated and improved: clip duration, order, aspect ratio, subtitles, translation, voice narration, text layers, motion crop/reframe, market scoring, hook settings, and AI flags.

Optimize means "guide the rendering intelligence." It does not mean unrestricted AI editing.

### Render

The creator submits a render request and watches job/part progress. The system queues work locally, runs the render pipeline, and preserves partial results when possible.

Render is a long-running local job, not an instant cloud task.

### Review

The creator receives a render package: clips, scores, best clip, warnings, failed parts, subtitle/voice summaries, and AI metadata when available.

Review is the most important product moment. The product should help answer: "Which clip should I use, and why?"

### Reuse

The creator can revisit history, retry failures, open/download outputs, run standalone downloads, manage channels, and optionally use upload automation.

Reuse does not imply cloud libraries, collaboration, or campaign analytics.

## 2. Product Navigation Model

Navigation must be based on real workflow ownership, not current frontend panels.

### 2.1 Source

Purpose:

- Own source selection and source readiness.
- Create or restore preview sessions.
- Make source problems visible before the creator reaches render.

Belongs here:

- YouTube URL source.
- Local file source.
- Output destination/channel selection when required before preview.
- Source validation.
- Download/source health checks.
- Preview session creation.
- Preview transcript readiness.

Must not belong here:

- Final output ranking.
- Render logs except source preparation errors.
- Upload queue/account management.
- Raw FFmpeg settings beyond source quality choice.

Primary implementation mapping:

- `backend/app/routes/render.py`
- `/api/render/prepare-source`
- `/api/render/preview-video/{session_id}`
- `/api/render/preview-transcript/{session_id}`
- `/api/render/download-health`
- `RenderRequest.source_mode`, `youtube_url`, `source_video_path`, `source_quality_mode`, `edit_session_id`

### 2.2 Studio

Purpose:

- Own the creator's render draft.
- Let the creator preview and configure how clips should be generated.
- Keep manual controls and AI-assisted controls distinct.

Belongs here:

- Preview video.
- Trim and volume.
- Clip duration and max export count.
- Aspect ratio, render profile, output FPS, codec/profile options.
- Subtitle style, translation, subtitle edits, preview.
- Voice narration setup.
- Text layers.
- Motion-aware crop and reframe mode.
- Market/hook/scoring controls.
- AI opt-in controls that affect the draft.

Must not belong here:

- Historical job list.
- Completed output package review.
- Upload scheduler.
- Low-level logs as primary UI.

Primary implementation mapping:

- `backend/static/js/editor-view.js` as workflow reference only.
- `backend/app/models/schemas.py::RenderRequest`
- `/api/subtitle/preview`
- `/api/voice/profiles`
- `/api/viral/score` and `/api/viral/score/all`

### 2.3 Monitor

Purpose:

- Own live job state.
- Make long-running local work understandable.
- Keep failure and partial-success states recoverable.

Belongs here:

- Active job.
- Queue status.
- Current stage.
- Part progress.
- WebSocket status.
- Polling fallback status.
- Job logs and structured render events.
- Retry/resume actions where implemented.

Must not belong here:

- Source setup form.
- Full editor controls.
- Upload account setup.
- Result ranking explanation after the job is complete, except as a transition to Results.

Primary implementation mapping:

- `/api/jobs/{job_id}`
- `/api/jobs/{job_id}/parts`
- `/api/jobs/{job_id}/logs`
- `/api/jobs/{job_id}/ws`
- `/api/render/resume/{job_id}`
- `/api/render/retry/{job_id}`
- `backend/app/services/job_manager.py`
- `backend/app/services/db.py`

### 2.4 Results

Purpose:

- Own the completed render package.
- Help the creator choose outputs.
- Explain ranking, warnings, and failures.

Belongs here:

- Output clips.
- Best clip.
- Ranked clip list.
- Score components and reasons.
- Failed parts and partial success details.
- Subtitle translation summary.
- Voice summary.
- AI Director metadata.
- AI render influence report.
- AI output ranking.
- AI UX/explainability metadata.
- Export/download/open-folder actions.

Must not belong here:

- Source import controls.
- Full render configuration editing.
- Raw diagnostics as the default experience.
- Claims about unavailable social performance analytics.

Primary implementation mapping:

- `jobs.result_json`
- `job_parts`
- `/api/jobs/{job_id}/parts/{part_no}/stream`
- `/api/render/jobs/{job_id}/parts/{part_no}/media`
- `result_json.outputs`
- `result_json.output_ranking`
- `result_json.best_clip`
- `result_json.best_exports`
- `result_json.failed_parts`
- `result_json.failed_parts_detail`
- `result_json.ai_*`

### 2.5 Library

Purpose:

- Own previously created render and download packages.
- Support recovery, retry, and re-entry.

Belongs here:

- Render job history.
- Download job history where applicable.
- Status filters.
- Completed, failed, interrupted, and partial jobs.
- Rerun/retry/open output actions.

Must not belong here:

- Upload queue history unless the data model is clearly separated.
- Cloud project management.
- Team collaboration.

Primary implementation mapping:

- `/api/jobs/history`
- `/api/jobs/{job_id}`
- `/api/jobs/{job_id}/parts`
- `jobs.result_json`

Important boundary:

Upload history is separate and lives under `/api/upload/history`. Do not collapse it into render history unless the backend contract is intentionally unified later.

### 2.6 Downloads

Purpose:

- Own standalone public video downloads.
- Keep source acquisition separate from render preview sessions.

Belongs here:

- Batch URL input.
- Download queue progress.
- Per-item statuses.
- Retry failed or selected items.
- Download output location.

Must not belong here:

- Render editor session.
- Clip scoring.
- Subtitle/voice/crop controls.

Primary implementation mapping:

- `backend/app/routes/download.py`
- `/api/download/process`
- `/api/download/retry/{job_id}`

### 2.7 Publish

Purpose:

- Own implemented upload automation if included in rebuild scope.
- Keep publishing operationally separate from rendering.

Belongs here:

- Upload accounts.
- Videos available for upload.
- Upload queue.
- Scheduler.
- Proxy pool.
- Login/profile checks.
- Worker/run status.

Must not belong here:

- Fake one-click publishing.
- Guaranteed social upload success.
- Official platform analytics.
- Campaign management.

Primary implementation mapping:

- `backend/app/routes/upload.py`
- `backend/static/js/upload-*` as workflow reference only.
- Upload tables in `backend/app/services/db.py`

Scope warning:

Publish is real but complex. If the first rebuild phase is not explicitly publishing-focused, Publish should be mounted as an advanced module after Source, Studio, Monitor, Results, Library, and Downloads are stable.

### 2.8 System

Purpose:

- Own local runtime readiness and diagnostics.
- Explain whether the workstation can render reliably.

Belongs here:

- Warmup status.
- FFmpeg/ffprobe readiness.
- yt-dlp readiness.
- Whisper/Ollama/AI diagnostics.
- Backend health.
- Log cleanup/maintenance if exposed.

Must not belong here:

- Creator-facing ranking decisions.
- Upload campaign controls.
- Main render settings.

Primary implementation mapping:

- `/api/warmup/status`
- `/api/render/ai-diagnostics`
- `/health`
- `backend/app/services/warmup.py`

## 3. Workflow Contract

The canonical workflow is:

```text
Entry
  -> Source inputs
  -> Source preparation
  -> Preview session
  -> Studio draft
  -> Optional analysis/AI setup
  -> Render submission
  -> Monitor
  -> Results
  -> Library / Downloads / Publish
```

### 3.1 Entry

Entry may start from:

- New render from YouTube URL.
- New render from local file.
- Existing job from Library.
- Standalone download.
- Upload automation module.

Entry ownership:

- Navigation decides the product area.
- Product areas decide their own data contracts.
- No page should mutate another page's state except through a typed store or explicit navigation action.

### 3.2 Inputs

Render inputs are owned by Source and Studio.

Source owns:

- Source mode.
- Source URL/path.
- Source quality mode.
- Output/channel destination needed to create a session.

Studio owns:

- Render draft fields from `RenderRequest`.
- Editor session ID.
- Subtitle/voice/crop/text/market/AI settings.
- Render submission validation.

Constraint:

The DOM must never be the source of truth. Form state should produce a validated `RenderRequest` draft.

### 3.3 Preview

Preview is owned by Source until a preview session exists, then by Studio.

Preview must use backend media endpoints, not raw local file paths, for browser playback.

Preview session data must preserve the distinction between:

- Original source path used for rendering.
- Browser-safe preview path used for playback.
- `edit_session_id` used by render submission.

### 3.4 Editor / Studio Draft

Studio owns the draft render configuration.

Studio must support these implemented configuration groups:

- Clip generation: trim, min/max part duration, max exports, part order.
- Render profile: aspect ratio, source quality, render profile, FPS, codec/profile where exposed.
- Subtitle: enable, style, font, color, size, highlight, outline, margins/position, preview, edits.
- Translation: enable and target language.
- Voice: enable, source, language, gender, voice ID/profile, speed/rate, mix mode, text.
- Text layers: timing, text, position, style, shadow/outline/background where implemented.
- Camera/crop: motion-aware crop, reframe mode, scale/frame controls.
- Market/hook: market viral config, hook score/application, combined/adaptive scoring, auto-best export.
- AI: AI Director, render influence, beat execution, timing mutation, variant planning, clip discovery/selection/batch planning where implemented.

Studio must not promise:

- Arbitrary timeline editing.
- Multiple video/audio tracks.
- Manual keyframe animation.
- Guaranteed cinematic reframing.
- New subtitle styles not supported by backend.

### 3.5 AI Enhancement

AI enhancement is not one feature. It is a set of implemented advisory and bounded-execution systems.

Ownership:

- Studio owns AI opt-in settings before render.
- Results owns AI explanations after render.
- System owns AI readiness diagnostics.

The future frontend must not flatten all AI into a generic "AI magic" control.

### 3.6 Render

Render submission posts a `RenderRequest` to `/api/render/process`.

Batch behavior must be treated carefully:

- Backend `/api/render/process/batch` exists.
- Current main editor batch flow may submit individual `/api/render/process` jobs.
- A rebuild must choose one canonical batch behavior and verify it against backend code before designing around it.

Render state is owned by Monitor.

Monitor must support:

- Queued state.
- Running state.
- Stage progress.
- Part progress.
- Completed.
- Completed with errors.
- Failed.
- Interrupted.
- Retry/resume where implemented.

### 3.7 Results

Results owns completed job interpretation.

Results must parse:

- Job row.
- Part rows.
- `result_json`.
- Output ranking aliases.
- Failed part details.
- AI metadata when present.

Results must distinguish:

- Clean success.
- Partial success.
- Complete failure.
- Missing output.
- Validation warning.
- AI advisory metadata.
- AI execution influence metadata.

### 3.8 History

Library owns history.

Library must let creators recover context:

- What source was used.
- What status the job ended with.
- Where outputs are.
- Which clips were best.
- Whether there were failed parts.
- Whether retry/reopen actions are available.

History must not become a dumping ground for every runtime table. Upload history has its own route and should remain separate unless deliberately unified.

## 4. AI Surfacing Strategy

Creators should experience AI as:

```text
The system helps choose, improve, rank, and explain clips.
You control when AI can influence the actual render.
```

AI must be visible where it creates creator value, passive where it is implementation support, explainable where it affects trust, and advanced-only where it can confuse or destabilize workflow.

### 4.1 Visible To Creator

These should become creator-visible because they directly affect output choice or confidence.

| Capability | Real implementation | Creator-facing meaning |
|---|---|---|
| Output ranking and best clip | `render_pipeline.py`, `backend/app/ai/output/*`, `result_json.output_ranking`, `best_clip` | "These clips are ranked; this one is strongest." |
| Score reasons/components | `render_pipeline.py` ranking entries | "This clip scored well because of hook, retention, market fit, duration, speech density, quality." |
| Partial success | `result_json.failed_parts`, `failed_parts_detail`, `completed_with_errors` | "Some clips succeeded; some need attention." |
| Subtitle intelligence | `subtitle_engine.py`, market subtitle policy, AI subtitle phases | "Subtitles were generated, styled, translated, or adapted for readability." |
| Motion/camera strategy | `motion_crop.py`, camera quality, camera promotion | "Framing was centered/subject/motion-aware and may have been quality-gated." |
| Voice narration summary | `tts_service.py`, `audio_mix_service.py`, `voice_summary` | "Narration was generated/mixed, or safely skipped/fell back." |
| Market/hook scoring | `viral_scoring.py`, `/api/viral/*`, market AI | "The clip fits this market/hook strategy." |
| AI explanations | `ai_ux`, explainability modules, render decision preview | "Why the system made this recommendation." |
| Quality warnings | output validation, quality evaluators | "The clip is valid but may have quality concerns." |

Visibility rule:

Show conclusions first, details second. Do not expose raw JSON as the product surface.

### 4.2 Passive / Automatic

These should generally work in the background unless they fail or need setup.

| Capability | Real implementation | Surfacing rule |
|---|---|---|
| Source probing | render routes, FFmpeg/ffprobe | Show readiness/errors, not probe internals. |
| Browser-safe preview generation | `_ensure_h264_preview()` | Show preview availability, not transcoding details. |
| Full-source transcription reuse | `subtitle_engine.py` | Show transcript/subtitle readiness. |
| Segment generation | `segment_builder.py` | Show selected clips and rationale, not raw segment lists by default. |
| FFmpeg codec fallback | `render_engine.py` | Show only when fallback affects outcome or speed. |
| Polling fallback | jobs API/frontend runtime | Never make creators manage it. |
| Warmup checks | `warmup.py` | Show system readiness and actionable missing dependencies. |

Passive rule:

Do not turn implementation mechanics into primary navigation.

### 4.3 Explainable

These need explicit explanations because they affect trust or output selection.

| Capability | Real implementation | Required explanation |
|---|---|---|
| AI Director plan | `ai_director.py`, `AIEditPlan` | What was analyzed, what confidence exists, what stayed advisory. |
| AI render influence | `render_influence.py` | What was allowed to change, what was skipped, why. |
| Subtitle promotion | `subtitle_promotion_engine.py` | Whether style/highlight was promoted, user override status, confidence. |
| Camera promotion | `camera_promotion_engine.py` | Whether reframe/motion crop was promoted, quality gates, confidence. |
| Segment promotion | `segment_promotion_engine.py` | Whether existing segments were reordered; must state no new timestamps were invented. |
| Quality gate | `quality_gate_engine.py` | What risky influence was blocked or downgraded. |
| Platform strategy | `backend/app/ai/knowledge/*` | How platform guidance affected subtitle/camera/hook/ranking strategy. |
| Creator intelligence | `creator_*`, `rag`, adaptive/feedback modules | What preference signal was used and whether it was strong enough. |
| Multivariant planning | `variants`, `strategy_variants`, `multivariant` | Treat as planning/evaluation unless execution is actually wired. |

Explainability rule:

Every AI control that can affect output must have a visible "what changed" report after render.

### 4.4 Advanced-Only

These should not be prominent in default creator workflow.

| Capability | Real implementation | Why advanced |
|---|---|---|
| AI diagnostics | `/api/render/ai-diagnostics` | Runtime readiness/debug context. |
| Raw logs | `/api/jobs/{job_id}/logs` | Support/recovery, not creator decision-making. |
| Warmup internals | `/api/warmup/status` | Useful when troubleshooting. |
| Deep phase metadata | `AIEditPlan` fields | Too noisy unless summarized. |
| Upload proxy pool | upload APIs | Operational/publishing setup complexity. |
| Devtools/QA routes | devtools/QA services | Internal or support-oriented. |
| Caption generation modes | `caption_engine.py` | Useful for Publish, but template/Ollama/Claude modes are setup-dependent. |

Advanced rule:

Advanced panels may exist, but they must not define the default mental model.

### 4.5 AI Surface Boundaries

Hard boundaries:

- Do not show AI as autonomous publishing.
- Do not imply every AI insight changes the render.
- Do not expose an execution toggle unless a real `RenderRequest` field or pipeline path exists.
- Do not design "AI rewrite timeline" or "AI edit arbitrary video" controls.
- Do not hide user override locks for subtitle/camera promotion.
- Do not hide quality-gate blocks; they are trust-building information.

## 5. Information Priority Model

The rebuild must prioritize creator decisions over engineering internals.

### HIGH Priority

These deserve primary placement in the product architecture.

| Information | Why creators care |
|---|---|
| Source readiness | They need to know the input can be used. |
| Preview playback | They need confidence before rendering. |
| Render draft readiness | They need to know required settings are complete. |
| Active job status | Local renders can take time. |
| Part progress | Multi-clip renders need per-output visibility. |
| Completed outputs | The product exists to produce clips. |
| Best clip / ranked clips | The creator needs a publishing decision. |
| Score reasons | Ranking must be trusted, not mysterious. |
| Failed parts / partial success | Creators need to salvage successful work. |
| Export/open/download actions | Outputs must be easy to use. |
| Subtitle/voice/crop active state | These visibly change the final clip. |

### MEDIUM Priority

These support confidence and refinement but should not dominate.

| Information | Why it matters |
|---|---|
| Market fit | Useful for choosing/editing clips. |
| Hook score | Useful when deciding best output. |
| Quality warnings | Important after render, less important before every action. |
| AI explanation summary | Useful when concise. |
| Voice summary | Important when narration is enabled. |
| Subtitle translation summary | Important when translation is enabled. |
| System readiness | Important when there is a problem or first run. |
| Queue position | Useful when multiple jobs exist. |
| History filters | Useful for returning creators. |
| Channel/output destination | Important, but not the core value moment. |

### LOW Priority

These should be available but not foregrounded.

| Information | Why lower priority |
|---|---|
| Raw logs | Needed for troubleshooting, not everyday decisions. |
| Raw `result_json` | Developer/support artifact. |
| FFmpeg command details | Backend execution detail. |
| Internal AI phase names | Too technical unless troubleshooting. |
| Warmup check internals | Only useful when failing. |
| Upload proxy details | Advanced operational setup. |
| Devtools diagnostics | Internal/support use. |
| Exact fallback mechanics | Show outcome and action, not every branch. |

Anti-dashboard rule:

The default creator experience should not look like logs plus JSON plus toggles. It should lead with source, preview, render package, ranked outputs, and recoverable issues.

## 6. Frontend Ownership Architecture

The rebuild must be modular by workflow and API contract. It must not recreate `render-ui.js` as a new mega-file.

### 6.1 Suggested Folder Ownership

```text
frontend/
  app/
    routes/
    shell/
    providers/
  features/
    source/
    studio/
    monitor/
    results/
    library/
    downloads/
    publish/
    system/
  entities/
    render-request/
    job/
    job-part/
    result-package/
    source-session/
    channel/
    upload/
  shared/
    api/
    components/
    state/
    desktop/
    utils/
    tokens/
```

This is a contract shape, not a mandate for a specific framework.

### 6.2 Page Ownership

Pages own workflow composition only.

Pages may:

- Load route-level data.
- Compose feature modules.
- Decide navigation transitions.
- Pass IDs into feature components.

Pages must not:

- Build raw API payloads directly.
- Parse `result_json` ad hoc.
- Own WebSocket implementation details.
- Reach into another feature's store.
- Contain large domain logic.

### 6.3 Feature Ownership

Each feature owns one workflow area.

| Feature | Owns | Does not own |
|---|---|---|
| `source` | Source selection, prepare-source, preview session metadata | Render result interpretation |
| `studio` | Render draft, editor preview, draft validation | Live job subscription |
| `monitor` | Active job, parts, logs, WebSocket/polling | Render draft controls |
| `results` | Result package parsing and output review | Source preparation |
| `library` | History and recovery entry points | Active render execution |
| `downloads` | Standalone download jobs | Render editor sessions |
| `publish` | Upload automation | Core render result ranking |
| `system` | Readiness, diagnostics, maintenance | Creator clip decisions |

### 6.4 Entity Ownership

Entities should hold contracts and parsers.

Required entities:

- `RenderRequestDraft`: maps Studio controls to backend `RenderRequest`.
- `SourceSession`: maps prepare-source response and preview URLs.
- `Job`: maps `/api/jobs/{job_id}`.
- `JobPart`: maps `/api/jobs/{job_id}/parts`.
- `ResultPackage`: parses `result_json`.
- `OutputRanking`: normalizes ranking aliases.
- `AIInsightSummary`: summarizes AI metadata without exposing raw phase data by default.
- `UploadQueueItem`: maps upload automation only inside Publish.

Entity rule:

Every backend response with compatibility risk needs one parser/normalizer. Do not parse the same JSON shape differently across pages.

### 6.5 State Ownership

State should be split by durable domain.

| Store | Owns |
|---|---|
| `sourceSessionStore` | Current session ID, source metadata, preview URL, transcript readiness |
| `renderDraftStore` | Draft `RenderRequest`, validation, dirty state |
| `jobStore` | Active job row, parts, summary, terminal state |
| `jobTransportStore` | WebSocket status, polling status, last update time |
| `resultStore` | Parsed result package, selected output, ranking map |
| `historyStore` | History list, filters, selected history item |
| `downloadStore` | Download jobs and item statuses |
| `publishStore` | Upload accounts/videos/queue/scheduler/proxy state |
| `systemStore` | Warmup, diagnostics, health |
| `desktopStore` | Electron capability checks and desktop actions |

State rules:

- Backend job/part rows are authoritative.
- WebSocket updates may accelerate state but must not replace polling fallback.
- DOM state is display state only.
- Local storage may cache user convenience preferences, not authoritative job data.
- Result parsing must be deterministic and repeatable after refresh.

### 6.6 API Client Ownership

API clients should be grouped by route contract.

Required clients:

- `renderApi`: prepare source, process, batch process if used, quick process, resume, retry, download health, AI diagnostics.
- `jobsApi`: job, parts, logs, history, queue status, stream/media URL builders.
- `downloadApi`: process and retry.
- `subtitleApi`: preview.
- `voiceApi`: profiles.
- `viralApi`: score and score all.
- `channelsApi`: root, scan, create/config/info.
- `uploadApi`: accounts, videos, queue, history, scheduler, proxies, workers.
- `systemApi`: health and warmup.

API client rules:

- API clients return typed/normalized data or explicit errors.
- Components do not hardcode endpoint strings.
- Media URL builders live with API clients, not result cards.
- Batch render behavior must be verified before it becomes a primary client abstraction.

### 6.7 Component Ownership

Components should be categorized:

- Product components: feature-specific and allowed to know domain language.
- Shared components: visual and interaction primitives only.
- Runtime components: media player, job progress, file/folder capability wrappers.

Shared components must not:

- Fetch data.
- Know `RenderRequest` fields.
- Parse result JSON.
- Own business rules.
- Depend on Electron directly.

Feature components must:

- Receive normalized entity data.
- Emit domain events.
- Keep local UI state small.
- Be replaceable without changing backend contracts.

### 6.8 Design Token Ownership

Design tokens are allowed in the rebuild, but they must be implementation-neutral.

Token ownership:

- `shared/tokens` owns spacing, type scale, color roles, status roles, elevation, radius, motion durations.
- Feature modules may consume tokens but may not define global visual language.
- Status colors must map to job/part states consistently.

Do not derive tokens from current CSS. The current CSS is not a design system.

### 6.9 Desktop Runtime Boundary

Desktop-specific behavior must be behind an adapter.

Adapter owns:

- Folder picker.
- Open path.
- Shell open.
- Desktop capability detection.
- Packaged/runtime path awareness where surfaced.

Browser fallback owns:

- Disabled desktop-only actions.
- Copy path/link alternatives.
- Media endpoint playback.

No feature module should call Electron APIs directly.

## 7. Maintainability Rules

These rules are hard constraints for the rebuild.

### 7.1 Page Rules

- A page may compose features.
- A page may not contain render payload construction.
- A page may not parse `result_json`.
- A page may not own WebSocket/polling logic.
- A page may not directly mutate another page's store.

### 7.2 Feature Rules

- One feature owns one workflow area.
- Feature code may call only its own store, entity parsers, and API clients.
- Cross-feature communication must use IDs, route transitions, or explicit domain events.
- Feature modules must not import each other's internal components.

### 7.3 State Rules

- One source of truth per domain.
- Job state comes from backend job/part routes.
- Render draft state produces a `RenderRequest`; it is not reconstructed from DOM.
- Result package state comes from `result_json` parser.
- Polling remains available even when WebSocket works.
- Terminal states must include `completed`, `completed_with_errors`, `failed`, and `interrupted`.

### 7.4 API Rules

- No component hardcodes API route strings.
- No component builds media stream URLs by string concatenation.
- No feature invents fields outside backend contracts.
- Request builders must preserve backend defaults unless explicitly changed by the user.
- Optional AI fields stay optional.
- Unsupported backend errors must surface as recoverable UI states.

### 7.5 Result JSON Rules

- Parse `result_json` once through a shared entity.
- Preserve aliases such as `output_rank_score`, `is_best_output`, and `is_best_clip`.
- Treat missing optional AI metadata as unavailable, not failed.
- Treat malformed result JSON as a recoverable diagnostics state.
- Never hide `failed_parts` when successful outputs exist.

### 7.6 AI Rules

- Separate advisory AI from execution AI.
- AI execution controls must map to existing schema fields or implemented promotion paths.
- AI explanations must state what changed, what did not change, and what was blocked/skipped.
- Quality gates must be visible when they block or downgrade influence.
- AI readiness belongs in System, not the primary Studio path unless unavailable dependencies block a selected feature.

### 7.7 DOM and Runtime Rules

- DOM IDs from the current frontend are not design inspiration.
- If rebuilding incrementally inside the legacy shell, preserve IDs until all legacy callers are removed.
- If rebuilding as a new frontend entry, replace old DOM/JS contracts together rather than mixing ownership.
- Do not attach business logic to CSS classes.
- Do not use inline event handlers in the rebuilt architecture.

### 7.8 File Size and Complexity Rules

- No new mega-file equivalent to `render-ui.js`.
- Feature files should stay focused on one responsibility.
- Large components must be split by domain behavior, not by arbitrary visual sections.
- API parsing, state, and rendering should live in separate files.
- Complex render/result mappings need tests.

### 7.9 Naming Rules

- Use product names for product modules: `source`, `studio`, `results`, `library`.
- Use backend names for contract entities: `RenderRequest`, `JobPart`, `ResultPackage`.
- Avoid generic names such as `utils2`, `renderHelpersFinal`, `newUi`, `panelManager`.
- AI names must clarify advisory vs execution: `AIInsightSummary`, `AIRenderInfluenceReport`, `AIQualityGateReport`.

### 7.10 Anti-Patterns To Avoid

- Recreating the current all-in-one render page.
- Treating logs as the primary product surface.
- Hiding ranked outputs behind progress UI.
- Designing AI as a single magic button.
- Combining upload automation with core render settings.
- Parsing result JSON in multiple places.
- Letting WebSocket be the only progress source.
- Using current CSS as a token source.
- Designing unimplemented cloud/team/campaign features.
- Turning every backend field into a visible control.

## 8. Rebuild Constraints

### 8.1 Figma Constraints

Figma generation must:

- Preserve workflow, not visuals.
- Map every visible feature to real implementation.
- Annotate controls with backend ownership where possible.
- Treat Source, Studio, Monitor, Results, Library, Downloads, Publish, and System as separate responsibility zones.
- Represent partial success and failed parts.
- Represent ranked output review as first-class.
- Represent AI advisory vs AI execution clearly.
- Represent desktop/local constraints.

Figma generation must not:

- Create landing pages.
- Imitate the current UI.
- Imitate CapCut.
- Invent collaboration, cloud storage, billing, social analytics, campaign dashboards, or official platform API publishing.
- Add fake autonomous AI editing.
- Hide local runtime readiness/failure states.

### 8.2 Frontend Constraints

Frontend implementation must:

- Use API/data contracts as the architecture source.
- Keep source preparation, studio draft, job monitor, and result parsing separate.
- Preserve WebSocket plus polling fallback.
- Preserve media streaming endpoints.
- Preserve local desktop capability checks.
- Preserve optional AI defaults.
- Preserve partial-success behavior.
- Preserve history recovery behavior.
- Keep upload automation separate unless intentionally integrated.

Frontend implementation must not:

- Depend on raw filesystem paths for media playback.
- Let the DOM be the source of truth.
- Mix upload scheduler state into render draft state.
- Require cloud/network AI dependencies for normal startup.
- Assume packaged desktop behavior is fully verified.

### 8.3 Backend Contract Constraints

The rebuild must not assume backend redesign.

Stable contracts to preserve:

- `RenderRequest` fields and defaults.
- `/api/render/process`.
- `/api/render/prepare-source`.
- `/api/jobs/*`.
- `/api/download/*`.
- `/api/subtitle/preview`.
- `/api/voice/profiles`.
- `/api/viral/*`.
- `/api/upload/*` if Publish is included.
- Job status and stage semantics.
- Part status semantics.
- `result_json` keys and aliases.
- AI metadata optionality.

If a frontend concept requires backend changes, it must be marked out of scope until a separate backend architecture task approves and tests it.

### 8.4 Desktop Constraints

The rebuilt frontend must be desktop-first and local-first.

Required assumptions:

- Large desktop viewport is primary.
- Local source files and output folders are normal.
- Long jobs must survive navigation and reload.
- Electron IPC may be available, but browser fallback must exist.
- FFmpeg, yt-dlp, Whisper, Ollama, and GPU readiness vary by machine.
- Packaged desktop runtime needs verification.

Desktop must not be treated as a thin responsive website wrapper only.

### 8.5 Unsupported Features

Do not include these in Figma or implementation as existing capabilities:

- Cloud render farm.
- Multi-user collaboration.
- Teams, roles, permissions.
- Billing/subscription.
- Cloud asset library.
- Browser-native full multi-track timeline editor.
- Arbitrary drag-and-drop clip sequencing.
- Official TikTok/YouTube/Instagram API publishing.
- Guaranteed upload success.
- Social performance analytics.
- Campaign management.
- Real-time comments/approvals.
- Fully autonomous AI editor.
- AI arbitrary FFmpeg command rewriting.
- AI arbitrary subtitle timing rewrite.
- AI arbitrary clip timestamp invention.
- Guaranteed perfect translation.
- Guaranteed professional mastering.
- Guaranteed cinematic subject tracking.
- Fully verified packaged offline desktop distribution.

## 9. Rebuild Success Criteria

### 9.1 UX Quality

The rebuild succeeds when:

- A creator can understand the product without knowing FFmpeg.
- The main flow is obvious: Source -> Studio -> Monitor -> Results -> Library.
- Ranked outputs are easier to evaluate than raw output files.
- Partial success feels recoverable, not broken.
- AI explanations improve trust without overwhelming the creator.
- Advanced diagnostics are available without dominating the default workflow.

### 9.2 Maintainability

The rebuild succeeds when:

- No single file owns source, editor, monitor, results, logs, and history together.
- API clients are centralized.
- `result_json` parsing is centralized.
- Stores have clear domain ownership.
- Feature modules can be changed without unrelated workflow regressions.
- Desktop capabilities are isolated behind an adapter.
- Tests can target request building, result parsing, job transport, and feature behavior independently.

### 9.3 Capability Visibility

The rebuild succeeds when these real capabilities are visible at the right level:

- Source preparation and preview sessions.
- Subtitle generation, styling, translation, and preview.
- Voice narration and mix state.
- Motion crop/reframe state.
- Market/hook scoring.
- Output ranking and best clip.
- Partial success and failed part recovery.
- AI Director summaries and explainability.
- AI render influence/promotion reports when enabled.
- System readiness and diagnostics.

### 9.4 Creator Clarity

The rebuild succeeds when creators can answer:

- What source am I working from?
- Is it ready to render?
- What will the system generate?
- Which enhancements are enabled?
- Is AI only advising or also influencing the render?
- What is rendering right now?
- Which output is best?
- Why is it best?
- What failed, if anything?
- What can I do next?

### 9.5 Implementation Safety

The rebuild succeeds when:

- Existing backend routes continue to work unchanged.
- Existing job/result contracts remain parseable.
- WebSocket and polling fallback both work.
- Interrupted and partial jobs remain visible.
- Optional AI metadata absence does not crash UI.
- Unsupported features are not represented as available.
- Legacy frontend can be retired or isolated cleanly.

## 10. Recommended Next Step

Before Figma, create a frontend API and entity contract packet:

1. `RenderRequest` field groups by workflow.
2. Prepare-source response contract.
3. Job, part, and progress response contract.
4. `result_json` parser contract with aliases.
5. AI metadata summary contract.
6. Upload automation contract if Publish is in v1 scope.
7. Desktop capability adapter contract.

Then run the Figma phase against this rebuild contract, not against the current UI.


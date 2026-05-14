# PRODUCT-ARCHITECTURE-REVIEW-1

Real capability review before full frontend rebuild.

This document is not a UI redesign, Figma brief, or mockup plan. It reviews the implemented product and extracts the workflow and architecture constraints needed for a complete frontend rebuild.

## 1. Executive Summary

The product is a local AI rendering intelligence platform for creator video production. FFmpeg is the execution backend, but the implemented product value is broader: source preparation, preview/edit sessions, scene and segment generation, scoring, subtitles, translation, motion-aware reframing, narration, output validation, ranking, history, and optional metadata-first AI Director phases.

The current frontend should be treated only as a workflow reference. It is not a design system, not a layout reference, and not a component architecture to preserve. Its value for the rebuild is in the journey it exposes: source import, preview, editing, render submission, progress monitoring, result review, and history/retry.

The strongest implemented capabilities are hidden in backend contracts and result metadata: output ranking, AI explanation metadata, subtitle intelligence, market scoring, partial-success diagnostics, voice summaries, and bounded AI execution promotion. These should become first-class product surfaces in the future architecture, but only where the backend already emits real data.

The biggest product-structure problem is not missing rendering technology. It is information architecture. The current frontend compresses source setup, editor controls, render monitor, output gallery, AI metadata, downloads, history, channel setup, and upload automation into one static global-state shell. A complete rebuild should split product areas by workflow ownership and API contract ownership, not by the current DOM or CSS structure.

Source gap: `docs/review/audit_ui.md` was requested but does not exist in this repository. Only `docs/review/render_audit.md` and `backend/docs/review/render_audit.md` were available.

## 2. Product Reality

This product actually is:

- A local desktop/browser creator-video production platform.
- A FastAPI backend with a static frontend and optional Electron shell.
- A SQLite-backed local job system with an in-process priority queue.
- A render orchestration pipeline that uses FFmpeg, ffprobe, Whisper, yt-dlp, OpenCV, Edge TTS, and local AI metadata modules.
- A metadata-first AI system where most phases plan, score, rank, explain, or recommend rather than directly mutating renders.
- A creator workflow tool for producing multiple short clips from YouTube or local source video, then reviewing and exporting ranked results.
- An adjacent upload automation system for channels/accounts/proxies/queues/scheduling, implemented under `/api/upload` and `backend/static/js/upload-*`.

This product is not currently:

- A cloud SaaS editor.
- A multi-user collaboration system.
- A full non-linear timeline editor.
- A Figma/design-first application.
- A generic FFmpeg wrapper.
- A fully verified packaged desktop product.
- A fully autonomous AI editor that can safely rewrite arbitrary render commands or publish content without user-controlled setup.

Primary implementation anchors:

- App bootstrap: `backend/app/main.py`
- Render API: `backend/app/routes/render.py`
- Job/history API: `backend/app/routes/jobs.py`
- Download API: `backend/app/routes/download.py`
- Upload automation API: `backend/app/routes/upload.py`
- Request contracts: `backend/app/models/schemas.py`
- Job persistence: `backend/app/services/db.py`
- Queue: `backend/app/services/job_manager.py`
- Render spine: `backend/app/orchestration/render_pipeline.py`
- FFmpeg engine: `backend/app/services/render_engine.py`
- Subtitle engine: `backend/app/services/subtitle_engine.py`
- Motion crop: `backend/app/services/motion_crop.py`
- Voice/TTS: `backend/app/services/tts_service.py`, `backend/app/services/audio_mix_service.py`
- AI Director: `backend/app/ai/director/ai_director.py`, `backend/app/ai/director/edit_plan_schema.py`
- Current workflow frontend: `backend/static/index.html`, `backend/static/js/*.js`
- Desktop shell: `desktop-shell/main.js`, `desktop-shell/preload.js`

## 3. Existing Capability Matrix

| Capability | File/module | What it actually does | User value | Current exposure | Priority |
|---|---|---|---|---|---|
| App shell and backend startup | `backend/app/main.py` | Registers routes, mounts static UI, initializes DB, ensures default channel, prunes runtime files, recovers interrupted jobs, starts warmup. | Makes the local platform bootable and recoverable. | Indirect, mostly invisible except health/warmup UI. | P0 |
| Render source preparation | `backend/app/routes/render.py`, `/api/render/prepare-source` | Downloads YouTube or validates local file, creates preview session, probes duration, may generate browser-safe H.264 preview. | Lets creators inspect and configure before rendering. | Exposed through "Open Editor" flow. | P0 |
| Preview video serving | `backend/app/routes/render.py`, `/api/render/preview-video/{session_id}` | Serves preview media with range support, preferring H.264 preview path. | Reliable editor playback. | Exposed in editor preview. | P0 |
| Preview transcript | `backend/app/routes/render.py`, `/api/render/preview-transcript/{session_id}` | Runs Whisper tiny on preview media and caches transcript JSON. | Enables real subtitle preview before render. | Exposed but secondary. | P1 |
| Render request schema | `backend/app/models/schemas.py::RenderRequest` | Defines render/source/output/subtitle/voice/crop/reup/scoring/AI fields and validation. | Backend contract for all render flows. | Hidden behind current form controls. | P0 |
| Render queue | `backend/app/services/job_manager.py` | In-process priority queue with thread pool, concurrency limit, duplicate prevention, startup interruption marking. | Allows background rendering without Celery/Redis. | Exposed through monitor and queue status. | P0 |
| Job persistence | `backend/app/services/db.py` | Stores `jobs`, `job_parts`, payload/result JSON, upload tables, scheduler state, proxy pool. | Durable local history and recovery. | Partially exposed through history and monitor. | P0 |
| Render orchestration | `backend/app/orchestration/render_pipeline.py` | Source resolution, trim/volume, scene detection, segment scoring, subtitles, AI planning, render, voice mix, validation, report, result JSON. | Core creator output generation. | Exposed as one "render" action; internals under-exposed. | P0 |
| Scene detection | `backend/app/services/scene_detector.py` | Detects scene boundaries and transition scores. | Better candidate segments. | Hidden, controlled by `auto_detect_scene`. | P1 |
| Segment building | `backend/app/services/segment_builder.py` | Builds candidate segments respecting duration limits and scoring inputs. | Produces useful clip candidates automatically. | Mostly hidden behind min/max clip settings and order. | P0 |
| Viral scoring | `backend/app/services/viral_scorer.py` | Scores segment features using heuristic/optional ML feedback path. | Ranks likely stronger clips. | Partially exposed as clip scores/ranking. | P0 |
| Market scoring | `backend/app/services/viral_scoring.py`, `backend/app/routes/viral.py` | Scores hook, keywords, duration, tone, readability for US/EU/JP-like market profiles. | Market-aware optimization and hook guidance. | Exposed in editor market analysis, but not as a coherent intelligence layer. | P1 |
| FFmpeg rendering | `backend/app/services/render_engine.py` | Builds FFmpeg commands for crop/scale/effects/subtitles/text/audio/codec/fps/reup/loudnorm; handles NVENC fallback and probe cache. | Reliable clip rendering across local machines. | Exposed as render profiles/device settings, not command details. | P0 |
| Output validation | `backend/app/orchestration/render_pipeline.py` | Checks file existence, size, ffprobe readability, video stream, plausible duration, quality warnings. | Prevents false successful renders. | Mostly hidden except failed/partial state. | P0 |
| Partial success handling | `backend/app/orchestration/render_pipeline.py`, `backend/app/routes/jobs.py` | Allows successful outputs to remain available when some parts fail; stores failed part details. | Saves work and makes failures actionable. | Exposed in monitor/output/history but not productized enough. | P0 |
| Output ranking and best clip | `backend/app/orchestration/render_pipeline.py`, `backend/app/ai/output/output_ranker.py` | Writes `output_ranking`, `best_clip`, aliases, best exports, AI ranking recommendations. | Helps creator choose what to publish. | Exposed with badges/score, under-explained. | P0 |
| Auto best export | `RenderRequest.auto_best_export_enabled`, pipeline result JSON | Copies selected top outputs to best-export path when enabled. | Reduces manual sorting after a batch. | Exposed in editor market/best export controls. | P1 |
| Report generation | `backend/app/services/report_service.py` | Writes render report rows to XLSX. | Operational record of outputs. | Mostly hidden or folder-based. | P2 |
| Subtitle transcription | `backend/app/services/subtitle_engine.py` | Full-source Whisper SRT generation, per-part slicing/rebasing. | Produces subtitles for all selected clips. | Exposed through editor subtitle controls. | P0 |
| WhisperX adapter | `backend/app/services/subtitle_transcription_adapters.py`, schema field | Optional word-level transcription adapter with fallback to default. | Better word-level subtitle timing when available. | Mostly hidden. | P2 |
| Subtitle styling | `backend/app/services/subtitle_engine.py` | ASS bounce/karaoke generation, style aliases, margins, fonts, color, highlight, preview rendering. | Creator-facing perceived quality. | Exposed in editor controls and preview. | P0 |
| Subtitle preview image | `backend/app/routes/subtitle.py`, `/api/subtitle/preview` | Renders one PNG subtitle preview; returns base64. | Fast visual check of style. | Exposed in editor preview pane. | P1 |
| Subtitle translation | `backend/app/services/translation_service.py`, `RenderRequest.subtitle_translate_enabled` | Block-based SRT translation to `vi`, `en`, `ja` with original-text fallback. | Localizes clips and supports translated narration. | Exposed but not deeply explained. | P1 |
| Market subtitle policy | `backend/app/services/market_subtitle_policy.py`, `subtitle_engine.py` | Applies market line breaks/hook text/emphasis behavior. | Better market-specific readability. | Under-exposed. | P1 |
| Subtitle edits/hook edits | `editor-view.js`, pipeline `_apply_subtitle_edits_to_srt` | Lets edited subtitle blocks be applied before render. | User control over hook wording. | Exposed in current editor workflow. | P1 |
| Voice narration | `backend/app/services/tts_service.py`, `audio_mix_service.py`, `voice_profiles.py` | Generates Edge TTS from manual/subtitle/translated subtitle and mixes audio. | Converts clips into narrated localized outputs. | Exposed in editor but not positioned as a workflow. | P1 |
| Voice profiles API | `backend/app/routes/voice.py`, `/api/voice/profiles` | Returns available voice profiles by language/gender/use. | Voice selection. | Partially exposed; frontend also has hardcoded presets. | P2 |
| Audio mix modes | `backend/app/services/audio_mix_service.py` | `replace_original` or `keep_original_low`; preserves original clip on mix failure. | Safe narration integration. | Exposed in editor. | P1 |
| Loudness/audio cleanup | `render_engine.py`, `audio_cleanup_adapters.py` | Loudnorm filter path and optional DeepFilterNet cleanup adapter. | Better technical audio quality. | Lightly exposed, not well framed. | P2 |
| Motion-aware crop/reframe | `backend/app/services/motion_crop.py`, `render_engine.py::render_part_smart` | OpenCV subject/face/body/motion tracking, subtitle-safe crop, fallback rendering. | Better vertical/social framing. | Exposed as reframe strategy, but risks/quality not explained. | P0 |
| Text overlays | `backend/app/services/text_overlay.py`, `TextLayerConfig`, `editor-view.js` | Multi-layer drawtext overlays with font/color/position/timing/background/outline/shadow. | Manual creator annotations. | Exposed in editor. | P1 |
| Title overlay | `RenderRequest.add_title_overlay`, `render_engine.py` | Simple top title overlay for opening seconds. | Basic hook/title support. | Exposed, basic. | P2 |
| Reup transform mode | `RenderRequest.reup_*`, `render_engine.py` | Overlay opacity, BGM mix, speed/effect changes for transformed output. | Repackaging source content. | Exposed in editor performance/audio controls. | P2 |
| Remotion hook intro | `backend/app/services/remotion_adapter.py`, pipeline hook | Optional intro generation/concat fallback path. | Potential hook packaging. | Schema field exists; current UI exposure appears weak. | P2 |
| Quick process | `backend/app/routes/render.py`, `/api/render/quick-process` | One-shot download/local process to exact file with optional resize/filter/black intro trim. | Utility/API workflow. | Not visible as primary frontend workflow. | P2 |
| Download batch | `backend/app/routes/download.py`, `/api/download/process` | Batch public video downloads with per-item parts, retry, unsupported link states. | Saves source videos separately from render. | Exposed in Download tab. | P1 |
| Download health check | `backend/app/routes/render.py`, `/api/render/download-health` | Probes YouTube availability/title/format health. | Preflight source confidence. | Under-exposed. | P2 |
| Jobs/history | `backend/app/routes/jobs.py`, `history-ui.js` | Lists jobs, normalizes history, streams parts/logs, computes progress summary. | Recovery, retry, review. | Exposed but split between monitor/history/output. | P0 |
| WebSocket progress with polling fallback | `backend/app/routes/jobs.py`, `render-engine.js` | `/api/jobs/{job_id}/ws` streams job/parts/summary; HTTP polling continues as fallback. | Robust progress monitoring. | Exposed operationally. | P0 |
| Logs and diagnostics | `jobs.py`, `render_pipeline.py`, `render-ui.js` | Per-job logs, structured render events, request rejection logs, copy diagnostics. | Support/debuggability. | Exposed but feels like debug, not recovery workflow. | P1 |
| AI diagnostics | `backend/app/routes/render.py`, `/api/render/ai-diagnostics` | Read-only AI runtime dependency diagnostics. | Explains local AI readiness. | Under-exposed. | P2 |
| AI Director plan | `backend/app/ai/director/ai_director.py`, `edit_plan_schema.py` | Builds `AIEditPlan` with many phase metadata fields; never blocks render on failure. | Intelligence spine for selection/explanation. | Mostly hidden in result JSON/logs. | P0 |
| AI render influence | `backend/app/ai/director/render_influence.py` | Opt-in bounded payload influence and reporting. | Lets safe AI decisions affect actual render. | Under-exposed; flags not clearly surfaced. | P1 |
| Subtitle execution promotion | `backend/app/ai/subtitle_promotion/subtitle_promotion_engine.py` | Opt-in promotion of subtitle preset/highlight only, confidence/user-override gated. | Converts advisory subtitle intelligence into safe execution. | Hidden/under-exposed. | P1 |
| Camera execution promotion | `backend/app/ai/camera_promotion/camera_promotion_engine.py` | Opt-in promotion of `reframe_mode` and `motion_aware_crop`, quality gated. | Safer AI-assisted reframing. | Hidden/under-exposed. | P1 |
| Segment selection promotion | `backend/app/ai/segment_promotion/segment_promotion_engine.py` | Opt-in reorders existing scored segments by overlap with AI selections; does not invent timestamps. | Lets AI influence which clips render. | Hidden/under-exposed. | P1 |
| AI quality gate | `backend/app/ai/quality_gate/quality_gate_engine.py`, pipeline integration | Applies safety checks around influence changes. | Prevents risky AI promotions. | Hidden. | P1 |
| AI UX metadata | `backend/app/ai/ux/ai_ux_metadata.py`, `render-ui.js` | Builds displayable AI explanation metadata when available. | Makes AI decisions understandable. | Partially exposed in output cards; under-developed. | P1 |
| Local knowledge/platform intelligence | `backend/app/ai/knowledge/**`, `backend/knowledge/**` | Local platform/subtitle/camera/hook/strategy/quality context; no live scraping. | Platform-aware guidance without cloud dependency. | Mostly hidden. | P1 |
| Creator memory/RAG | `backend/app/ai/rag/**`, AI Director flags | Optional local memory/retrieval context. | Personalization over time. | Backend implemented, UI unclear/under-exposed. | P2 |
| Strategy variants/planning | `backend/app/ai/variants/**`, `strategy_variants/**`, `multivariant/**` | Plans/evaluates variants; mostly advisory unless explicitly wired. | Future decision support. | Hidden; should not be presented as full multi-render automation unless wired. | P2 |
| Channel management | `backend/app/routes/channels.py`, `channel_service.py`, `channels.js` | Creates/scans channel folders, writes settings/profile files. | Organizes local creator accounts/output folders. | Exposed in settings/setup areas. | P1 |
| Upload automation | `backend/app/routes/upload.py`, `upload_engine.py`, `upload-manager.js` | Accounts, videos, queue, scheduler, proxy pool, login checks, Playwright upload runs. | Post-render publishing workflow. | Implemented but complex and adjacent to render core. | P1/P2 |
| Desktop shell | `desktop-shell/main.js`, `preload.js` | Electron startup, single instance, backend health/spawn, packaged env paths, IPC folder/profile open. | Desktop product packaging and local file access. | Present; packaged stability needs verification. | P1 |
| Warmup status | `backend/app/services/warmup.py`, `/api/warmup/status`, `warmup.js` | Checks FFmpeg/GPU/yt-dlp/cascades/Whisper/Ollama readiness in background. | Reduces surprise failures and informs readiness. | Exposed as a chip/panel. | P1 |

## 4. Workflow Analysis

The real creator render workflow is:

```text
Choose source
  -> prepare source
  -> open editor preview
  -> configure clip/render/subtitle/voice/crop/market settings
  -> submit render
  -> monitor queued/running parts
  -> review output gallery
  -> inspect best/ranked clips and failures
  -> download/open/export
  -> revisit from history
```

### 4.1 Source Import

Implemented paths:

- YouTube URL input through `startRender()` and `/api/render/prepare-source`.
- Local file input through local picker/upload/validation and `/api/render/prepare-source`.
- Standalone batch download through `/api/download/process`, separate from render source preparation.
- Batch render paths exist in backend `/api/render/process/batch`, while the current editor also queues multiple `/api/render/process` requests one by one for batch URLs.

Important dependencies:

- `edit_session_id` is the bridge from preview/editor to render pipeline.
- Preview sessions store original render path separately from browser-safe preview path.
- Output folder is required before editor/render.

### 4.2 Analyze / Preview

Implemented paths:

- Browser-safe preview video via `/api/render/preview-video/{session_id}`.
- Preview transcript via `/api/render/preview-transcript/{session_id}`.
- Subtitle visual preview via `/api/subtitle/preview`.
- Market/hook analysis via `/api/viral/score/all`.

What exists is useful but fragmented. The backend can supply source metadata, preview transcript, subtitle preview, and market scoring. The future frontend should treat this as an "analysis readiness" layer rather than scattered controls.

### 4.3 Edit / Configure

The current editor configures:

- Trim in/out and volume.
- Aspect ratio, playback speed, clip length, max export count, part order.
- Render profile, source quality, encoder mode, output FPS.
- Subtitle on/off, style, font, size, color, highlight, outline, X/Y position.
- Subtitle translation target.
- Text layers with timing and styling.
- Motion-aware crop/reframe mode.
- Reup mode, transform preset, BGM, loudnorm.
- Voice narration source/language/preset/speed/mix/text.
- Market viral settings, hook application, combined/adaptive scoring, best export.

This is real workflow functionality. The future rebuild should preserve the inputs and dependencies, but should not preserve the current inspector tabs, layout, or control grouping.

### 4.4 Render

Render submission posts a `RenderRequest` to `/api/render/process`. The job manager queues it, the render pipeline executes it, and state is persisted in SQLite.

Runtime flow:

```text
queued
  -> starting/downloading
  -> scene_detection
  -> segment_building
  -> transcribing_full when subtitles need it
  -> optional AI Director/influence
  -> rendering or rendering_parallel
  -> writing_report
  -> completed/completed_with_errors/failed
```

Part flow includes waiting/cutting/transcribing/rendering/done/failed. The frontend must retain a WebSocket-first plus polling-fallback progress model because the backend explicitly supports both.

### 4.5 Review Result

Implemented review surfaces:

- `job_parts` with per-part output files and statuses.
- `result_json.outputs`.
- `result_json.output_ranking`.
- `result_json.best_clip`.
- `result_json.best_exports`.
- `failed_parts` and `failed_parts_detail`.
- Voice and subtitle translation summaries.
- AI Director, AI influence, AI output ranking, AI quality evaluation, and AI UX metadata.

The future frontend should treat result review as a primary product area, not a side panel. The important object is not simply "a list of MP4 files"; it is "a ranked render package with explanations and recoverable failures."

### 4.6 Export / Continue

Implemented paths:

- Download/stream rendered part: `/api/jobs/{job_id}/parts/{part_no}/stream`.
- Preview media: `/api/render/jobs/{job_id}/parts/{part_no}/media`.
- Open output folder through Electron IPC when desktop is available.
- Auto best export when enabled.
- History rerun/retry actions.
- Upload automation exists as a separate post-render pipeline but is not tightly integrated as a clean end-to-end publish flow.

## 5. Hidden Strengths

1. Output ranking is a core product asset.

   `render_pipeline.py` builds ranking entries with score components, reasons, best flags, and aliases. The UI currently shows some ranking information, but the future product should make ranking explanation central to result review.

2. AI metadata is much richer than the UI suggests.

   `AIEditPlan` carries story, retention, creator style, creator feedback, market optimization, strategy variants, quality, platform strategy, platform feedback, subtitle/camera promotions, segment promotion, and more. Much of this is metadata-only, but it is real and tested. The UI should not fake execution, but it should surface available reasoning.

3. Partial success is handled correctly.

   The pipeline preserves successful outputs even when some parts fail, stores failed part detail, and can complete with `completed_with_errors`. This is high-value for long local renders and should become an explicit recovery/review workflow.

4. Subtitle intelligence is product-grade relative to the rest of the app.

   Full-source transcription, SRT slicing/rebasing, translation fallback, ASS styles, karaoke/bounce, market line breaks, hook formatting, and preview rendering are all implemented. The current UI exposes controls but under-communicates the workflow value.

5. Motion crop has safety-oriented architecture.

   Motion-aware crop has subject/face/body/motion paths, smoothing, subtitle-safe assumptions, and fallback through `render_part_smart()`. Future UI should expose it as a capability with confidence/risk framing, not just a raw toggle.

6. Voice narration is a real creator workflow.

   Manual, subtitle-derived, and translated-subtitle narration are implemented. Mix failure is designed to preserve valid clips. The current UI exposes it, but not as a structured "localization/narration" workflow.

7. Local-first AI is a strong product position.

   AI phases are designed to avoid startup-breaking optional dependencies and to fail soft. Knowledge packs and advisory strategy reduce dependence on network AI.

8. Desktop shell enables local creator ergonomics.

   Folder pickers, open path actions, backend spawn, FFmpeg path injection, and packaged runtime paths are real. This supports a desktop-first architecture if verified.

9. Upload automation is implemented but structurally separate.

   Accounts, videos, queue, scheduler, proxies, login/profile checks, worker endpoints, and upload runs exist. This can become a post-render publishing module, but only if future product scope chooses to include it.

## 6. Structural Product Weaknesses

These are product and architecture problems, not visual criticism.

1. Capability discoverability is poor.

   Backend capabilities such as AI ranking, platform strategy, quality feedback, subtitle promotion, camera promotion, partial success detail, and voice summaries exist but are not organized into a clear product mental model.

2. Workflow boundaries are blurred.

   Render source preparation, standalone download, editor configuration, render monitoring, output review, history, channel setup, and upload automation coexist in one static app shell. The user journey is real, but ownership boundaries are weak.

3. AI execution vs AI advisory is not clear enough.

   The backend carefully separates metadata-only phases from bounded execution promotion. The frontend should make this distinction explicit in future architecture so users do not assume every AI insight changes the render.

4. Result review is under-prioritized.

   The most valuable output is a ranked set of clips with reasons, warnings, summaries, and failures. Current workflow still treats the result mostly as output cards plus logs.

5. History is operational, not creator-oriented.

   History normalizes jobs well, but it does not yet behave like a creator library of render packages, best clips, failed parts, and reusable configurations.

6. Upload automation is powerful but product-isolated.

   Upload modules are implemented and large, but they are not cleanly integrated into the render package lifecycle. A future frontend must decide whether "Publish" is a first-class top-level domain or an advanced automation module.

7. State ownership is fragile.

   Current frontend state is global across `globals.js`, `render-engine.js`, `render-ui.js`, `editor-view.js`, localStorage, DOM attributes, WebSocket responses, and polling responses. A rebuild should not inherit this model.

8. API response contracts are stronger than UI contracts.

   `RenderRequest`, job rows, part rows, and `result_json` have clearer boundaries than the frontend. The rebuild should start from API/data models, not current DOM sections.

9. Desktop packaging remains a verification risk.

   The desktop shell is implemented, but docs mark packaged behavior as experimental/needs verification. Future architecture must design for desktop-first use without overpromising packaging stability.

10. No formal frontend module architecture exists.

   The current frontend uses static global scripts and inline handlers. That is adequate as legacy shell behavior, but unsuitable for a maintainable premium creator product.

## 7. Frontend Rebuild Architecture Recommendation

The rebuild should be architecture-first and data-contract-first. Do not preserve current layout, CSS, DOM structure, panel organization, or visual hierarchy.

### 7.1 Information Architecture

Recommended top-level product areas:

1. Project / Source
   - Source selection: YouTube/local.
   - Source health/preflight.
   - Preview session status.
   - Source metadata and transcript readiness.

2. Studio
   - Video preview.
   - Trim, clip-generation constraints, aspect/profile.
   - Subtitle, text, voice, motion crop, market/hook settings.
   - Clear separation between manual controls and AI-assisted settings.

3. Render Monitor
   - Queue state.
   - Current job.
   - Part progress.
   - Stage timeline.
   - Diagnostics/logs.
   - Must keep polling fallback as a first-class state source.

4. Results
   - Ranked clips.
   - Best clip.
   - Warnings/failed parts.
   - AI explanations.
   - Voice/subtitle summaries.
   - Export/download/open-folder actions.

5. Library / History
   - Past render packages and downloads.
   - Rerun/retry.
   - Output folder and source hints.
   - Status filters.

6. Downloads
   - Standalone public video download workflow.
   - Separate from render source preparation.

7. Channels / Publishing
   - Channel folder management.
   - Upload accounts/videos/queue/scheduler/proxy management if included.
   - Should be modular and separable from render core.

8. System
   - Warmup/readiness.
   - AI diagnostics.
   - FFmpeg/Whisper/Ollama/yt-dlp readiness.
   - Maintenance/log cleanup.

### 7.2 Page Ownership

Each page/module should own one workflow and one data boundary:

- `SourcePage`: prepares sessions and owns source preflight.
- `StudioPage`: owns draft render configuration and editor preview state.
- `RenderMonitorPage` or persistent monitor service: owns live job subscription.
- `ResultsPage`: owns result package parsing from `job.result_json` and `job_parts`.
- `HistoryPage`: owns normalized `/api/jobs/history` data and job actions.
- `DownloadsPage`: owns `/api/download/*` jobs.
- `PublishPage`: owns `/api/upload/*` if retained in the rebuilt product.
- `SystemPage`: owns `/api/warmup/status`, `/api/render/ai-diagnostics`, maintenance.

### 7.3 State Ownership

Use explicit stores by domain:

- `sourceSessionStore`: `session_id`, source metadata, preview URLs, transcript status.
- `renderDraftStore`: `RenderRequest` draft, validation, dirty state.
- `jobStore`: active job ID, job row, parts, summary, logs, WebSocket status, polling fallback.
- `resultStore`: parsed result JSON, ranking map, best clip, failed parts, AI metadata.
- `historyStore`: normalized history items and filters.
- `downloadStore`: current download job and batch items.
- `publishStore`: upload accounts/videos/queue/scheduler if included.
- `systemStore`: warmup and diagnostics.

Do not let the DOM be the source of truth. Do not let WebSocket state replace polling state. Backend job/part rows remain authoritative.

### 7.4 Component Boundaries

Recommended component families:

- Source components: `SourcePicker`, `SourceHealth`, `PreviewSessionStatus`.
- Studio components: `VideoPreview`, `TrimControls`, `ClipGenerationControls`, `SubtitleControls`, `VoiceControls`, `MotionControls`, `MarketHookControls`, `TextLayerControls`, `RenderProfileControls`.
- Monitor components: `JobStageTimeline`, `PartProgressTable`, `QueueStatus`, `RenderLogPanel`, `FailureDiagnostics`.
- Result components: `RankedClipList`, `ClipPreview`, `BestClipSummary`, `AIReasonPanel`, `QualityWarnings`, `ExportActions`.
- History components: `RenderPackageCard`, `DownloadJobCard`, `HistoryFilters`.
- Publish components: `ChannelSelector`, `UploadAccountManager`, `UploadQueue`, `SchedulerStatus`, `ProxyPool`.
- System components: `WarmupPanel`, `AIDiagnosticsPanel`, `RuntimeDependencyStatus`.

### 7.5 API Client Boundaries

Create typed client modules around existing routes:

- `renderApi`: prepare source, process, resume, retry, quick-process, download-health.
- `jobsApi`: jobs, history, parts, logs, media/stream URLs, cleanup logs.
- `downloadApi`: process and retry.
- `subtitleApi`: preview.
- `voiceApi`: profiles.
- `viralApi`: scoring.
- `channelsApi`: scan/create/config.
- `uploadApi`: accounts/videos/queue/scheduler/proxy/run endpoints.
- `systemApi`: warmup and health/diagnostics.

The rebuild must preserve backend payload and response contracts unless backend changes are separately planned and tested.

### 7.6 Desktop-First Structure

The future frontend should assume:

- Large-screen creator workstation as primary.
- Local files and folders are normal workflows.
- Electron APIs may be available but browser fallback should remain possible.
- Long-running jobs need resilient monitor state.
- Logs and diagnostics are part of support UX, not developer-only afterthoughts.
- Packaging paths and FFmpeg availability can vary by machine.

Desktop constraints:

- Never depend solely on raw filesystem paths for media preview; use media endpoints.
- Use Electron IPC only behind capability checks.
- Treat local path opening and folder picking as optional platform services.
- Keep render progress resilient if the window reloads.

## 8. Unsupported Features

Do not design or claim these as implemented product capabilities unless code is added later:

- Cloud SaaS rendering.
- Multi-user accounts, teams, roles, permissions, or collaboration.
- Browser-based full NLE timeline editing with arbitrary clips/tracks/transitions.
- Drag-and-drop multi-track video/audio timeline.
- Automatic publishing directly from render completion without upload module setup.
- Guaranteed TikTok/YouTube/Instagram upload success.
- Platform API publishing through official APIs.
- Live internet AI research/scraping during render.
- Fine-tuned model training.
- Guaranteed professional audio mastering.
- Guaranteed perfect translation.
- Guaranteed perfect subject tracking/cinematic camera movement.
- AI rewriting arbitrary FFmpeg commands.
- AI rewriting subtitle timing as a general behavior.
- AI inventing new segment timestamps during Phase 59C segment promotion.
- AI deleting outputs or overriding validation.
- General plugin marketplace architecture.
- Cloud asset library.
- Collaborative comments/approvals.
- Real-time multiplayer review.
- In-app payment/subscription features.
- Fully verified offline packaged desktop distribution.
- Mobile-first creator app.
- Figma-generated UI implementation.
- Current visual design or CSS architecture as a reusable design system.

## 9. Hard Constraints For Future Figma Phase

Future Figma generation must follow these rules:

1. Preserve workflow, not visuals.

   Use the real flow: source -> analysis/preview -> studio configuration -> render monitor -> ranked results -> history/export. Do not copy current panels, current navigation, current CSS, or current component structure.

2. Map every visible feature to implemented backend capability.

   Any UI control must map to `RenderRequest`, route parameters, job/part/result fields, or implemented frontend workflow. If no backend contract exists, label it unsupported and exclude it.

3. Separate advisory AI from execution AI.

   AI insight panels may show metadata. Execution controls must only represent real opt-in fields such as `ai_director_enabled`, `ai_render_influence_enabled`, `ai_beat_execution_enabled`, and current bounded promotion behavior.

4. Treat result review as a first-class product area.

   Designs must include ranked outputs, best clip, warnings, failed parts, summaries, and AI explanations where available.

5. Preserve local desktop constraints.

   Designs must support local folder selection, local paths, long-running jobs, logs, interrupted jobs, and offline/dependency readiness states.

6. Preserve WebSocket plus polling fallback semantics.

   The UI may present a clean progress experience, but architecture must not assume WebSocket is the only source of truth.

7. Do not fake platform publishing.

   Upload automation exists, but it is complex and setup-dependent. If included, design it as a separate publishing/automation module with account/profile/scheduler states, not a magical "Publish now" button.

8. Do not hide failure states.

   Failed parts, partial success, validation failures, download failures, TTS failures, subtitle translation fallback, and motion crop fallback must be representable.

9. Keep API contracts visible to implementation.

   Future designs should be annotated with owning API fields: `RenderRequest`, `job`, `job_parts`, `result_json`, `upload_queue`, etc.

10. Design for modular implementation.

   Figma sections should align with future frontend modules: Source, Studio, Monitor, Results, History, Downloads, Publish, System.

11. Do not include unimplemented SaaS/admin concepts.

   No team dashboard, cloud storage, billing, roles, analytics suite, campaign manager, or collaboration unless backend support is built first.

12. Keep desktop density appropriate.

   This is a production creator workstation tool. It should support scanning, comparison, multi-clip review, and repeated jobs. Avoid landing-page composition and marketing-page hierarchy.

## 10. Recommended Next Step

Before Figma, define the rebuild contract package:

1. Freeze a frontend-readable API map:
   - `RenderRequest` fields grouped by workflow.
   - Job and part response shapes.
   - `result_json` fields and aliases.
   - Upload automation data shapes if included.

2. Decide product scope for v1 rebuild:
   - Core render only, or render plus standalone downloads, or render plus publishing.
   - Recommendation: rebuild core render/download/history/results first; keep upload automation as a separately mounted advanced module unless publishing is a hard v1 requirement.

3. Create a frontend module plan:
   - Routes/pages.
   - Stores.
   - API clients.
   - Result JSON parser.
   - Job subscription service.
   - Desktop capability adapter.

4. Only then run a Figma phase:
   - Figma should express the new information architecture.
   - Figma should not inherit the current UI.
   - Every screen should include implementation annotations mapping controls to real backend fields.


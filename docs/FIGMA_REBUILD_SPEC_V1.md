# FIGMA_REBUILD_SPEC_V1

Premium creator product Figma specification.

This document is the design specification for MCP Figma generation. It is not frontend implementation, not backend redesign, and not a request to copy the current UI. The current UI is workflow reference only.

The Figma output must express a new desktop-native creator workstation that maps only to implemented backend capabilities documented in:

- `docs/PRODUCT_ARCHITECTURE_REVIEW_1.md`
- `docs/PRODUCT_ARCHITECTURE_REVIEW_3.md`
- `docs/FRONTEND_CONTRACT_PACKET_V1.md`

## 1. Product Design Philosophy

The product should feel like a focused creator workstation for turning source video into ranked, ready-to-review short-form outputs.

The creator should feel:

```text
I import content.
The system prepares and understands it.
I guide the creative strategy.
The render runs locally.
I review ranked outputs and know what to trust.
```

The product must not feel like:

- An engineering dashboard.
- A raw FFmpeg frontend.
- A generic SaaS admin tool.
- A fake AI editor.
- A social media analytics suite.
- A CapCut clone.
- A full nonlinear timeline editor.

### 1.1 Emotional Outcomes

The target emotional outcomes are:

- Confidence: the creator understands whether the source, render, and outputs are usable.
- Momentum: the creator can move from source to render without fighting settings.
- Control: advanced configuration exists but does not dominate the default path.
- Trust: AI explains what it did, what it only recommended, and what it refused to change.
- Recovery: partial success and failed parts are handled as salvageable work, not dead ends.
- Craft: subtitle, voice, crop, market, and ranking surfaces feel like production tools rather than debug flags.

### 1.2 Experience Principle

The hierarchy is:

```text
Results > configuration
Confidence > complexity
Workflow > settings
AI assistance > AI magic
```

The main design posture:

- Start with the creator's task.
- Reveal system intelligence as useful confidence.
- Keep operational detail available but secondary.
- Never imply capabilities that do not exist.

### 1.3 Product Identity

The product identity is:

```text
AI-assisted local rendering intelligence for creator clips.
```

FFmpeg, Whisper, queues, logs, and AI phases are implementation power. They should support the experience but not become the primary mental model.

## 2. Information Architecture

The product areas are:

1. Source
2. Studio
3. Monitor
4. Results
5. Library
6. Downloads
7. Publish, advanced-module-only
8. System

This IA is based only on implemented capability. It intentionally does not preserve current navigation.

### 2.1 Source

Purpose:

- Start a creator job from YouTube or local video.
- Prepare a preview session.
- Confirm source readiness before editing.

Ownership:

- Source input.
- Source validation.
- Preview session creation.
- Browser-safe preview availability.
- Preview transcript readiness.
- Output destination requirement when needed before render.

Belongs:

- YouTube URL.
- Local file path.
- Source quality mode.
- Output location/channel selection.
- Source health/check states.
- Prepared session summary.

Must not belong:

- Full render settings.
- Output ranking.
- Upload automation.
- Raw job logs.
- Full AI phase metadata.

Navigation behavior:

- Default entry for new work.
- Successful prepare-source transitions into Studio with `edit_session_id`.
- Failure keeps creator in Source with actionable source error.

### 2.2 Studio

Purpose:

- Let creators guide how clips will be generated and improved.
- Own the `RenderRequest` draft.

Ownership:

- Preview playback.
- Trim and volume.
- Clip generation settings.
- Subtitle styling, translation, and subtitle edits.
- Voice narration.
- Text layers.
- Camera/reframe.
- Market/hook scoring settings.
- Render profile.
- AI opt-in settings.

Belongs:

- Preview video.
- Essential render controls.
- Enhancement controls.
- AI assistance controls.
- Render readiness summary.

Must not belong:

- Completed output package review.
- Historical jobs list.
- Upload scheduler.
- Debug log stream as default surface.

Navigation behavior:

- Entry from Source prepared session.
- Can return to Source without losing draft.
- Render submission transitions to Monitor.
- If validation fails, stays in Studio and highlights required fixes.

### 2.3 Monitor

Purpose:

- Track a long-running local job.
- Keep the creator informed without making them read logs.

Ownership:

- Active job status.
- Stage progress.
- Part progress.
- Queue status.
- WebSocket/polling transport status.
- Recoverable failure and retry/resume actions.
- Logs as secondary diagnostics.

Belongs:

- Current job state.
- Part table/list.
- Progress summary.
- Active/stuck part indicators.
- Partial failure messages.
- Diagnostics drawer.

Must not belong:

- Source import.
- Full Studio configuration.
- Final ranked output review except a transition state.

Navigation behavior:

- Entry after render submit or from Library active job.
- Completion transitions or prompts into Results.
- Failed/interrupted jobs allow Library/Retry/Resume pathways where backend supports them.

### 2.4 Results

Purpose:

- Make outputs easy to review, compare, trust, and export.

Ownership:

- `ResultPackage`.
- Output clips.
- Ranking and best clip.
- Score reasons.
- Failed parts.
- Partial success.
- Voice/subtitle summaries.
- AI summaries.
- Export/download/open-folder actions.

Belongs:

- Clip preview.
- Ranked clip list.
- Best clip summary.
- Confidence and warnings.
- AI explanation summary.
- Failure recovery panel.

Must not belong:

- Full source setup.
- Full editor configuration.
- Fake social analytics.
- Raw JSON as primary UI.

Navigation behavior:

- Entry after job completion or from Library.
- Can open output, download/stream parts, retry failures, or start another source.
- Can optionally send eligible rendered files into Publish if Publish module is in scope and the user chooses it.

### 2.5 Library

Purpose:

- Re-enter previous render/download work safely.

Ownership:

- `/api/jobs/history`.
- Render and download history cards.
- Status filtering.
- Rerun/retry/open-folder actions.

Belongs:

- Past render packages.
- Past download jobs.
- Interrupted/partial/failed jobs.
- Source/output hints.

Must not belong:

- Upload queue history unless clearly separated.
- Cloud project library.
- Collaboration artifacts.

Navigation behavior:

- Opens render jobs into Results or Monitor depending on status.
- Opens download jobs into Downloads history/detail.
- Does not mutate Studio draft unless explicit rerun action is taken.

### 2.6 Downloads

Purpose:

- Standalone public video download workflow.

Ownership:

- `/api/download/process`.
- `/api/download/retry/{job_id}`.
- Download job states and item statuses.

Belongs:

- Batch URL input.
- Output folder.
- Download progress.
- Unsupported/failed item recovery.

Must not belong:

- Render preview sessions.
- Studio editing.
- Clip ranking.

Navigation behavior:

- Separate entry from render Source.
- Download jobs appear in Library/history but remain distinct from render packages.

### 2.7 Publish

Scope:

- Advanced-module-only.
- Include in Figma as a clearly separated optional module only if the design set includes advanced operations.

Purpose:

- Manage implemented upload automation.

Ownership:

- Accounts.
- Videos.
- Upload queue.
- Scheduler.
- Proxy pool.
- Login/profile checks.
- Worker/run state.

Belongs:

- `/api/upload/*` workflows.
- Account health.
- Queue eligibility.
- Scheduler status.

Must not belong:

- Fake "publish everywhere" button.
- Guaranteed social upload success.
- Official API publishing.
- Analytics dashboard.
- Campaign management.

Navigation behavior:

- Separate advanced area.
- Can receive a rendered file reference only through an explicit action.
- Does not sit inside Studio or Results as a magical final step.

### 2.8 System

Purpose:

- Explain local runtime readiness.

Ownership:

- Warmup status.
- AI diagnostics.
- Backend health.
- Desktop capability state.
- Dependency readiness.
- Log cleanup/maintenance if exposed.

Belongs:

- FFmpeg/ffprobe readiness.
- yt-dlp readiness.
- Whisper/Ollama/AI diagnostics.
- Desktop/Electron capability status.

Must not belong:

- Creator ranking decisions.
- Main render configuration.
- Upload scheduling.

Navigation behavior:

- Secondary area.
- Warning states may appear contextually in Source, Studio, or Monitor, with detail linking to System.

## 3. Screen Responsibility Matrix

| Screen | Primary responsibility | Data owner | Must not own |
|---|---|---|---|
| Source | Start and prepare a source session | `SourceSession`, source fields from `RenderRequest` | Render package parsing, job monitor, upload scheduler |
| Studio | Build a valid render draft | `RenderDraft`, `RenderRequest` builder | Job transport, result parsing, history list |
| Monitor | Observe active job execution | `Job`, `JobPart`, transport summary, logs | Studio draft editing, final ranking UX |
| Results | Review completed render package | `ResultPackage`, `OutputClip`, `AIInsightSummary` | Source import, full settings editing |
| Library | Re-enter past work | History item normalization, job lookup | Upload queue internals, active draft state |
| Downloads | Run standalone downloads | Download job and download parts | Render preview sessions, clip scoring |
| Publish | Advanced upload automation | Upload accounts/videos/queue/scheduler/proxy | Core render settings, fake publish success |
| System | Runtime readiness and diagnostics | System readiness, AI diagnostics, desktop capability | Creator clip choice, upload queue decisions |

Responsibility rule:

Every screen must have one primary entity and one primary workflow. If a screen needs another domain's data, it receives a normalized reference, not raw ownership.

## 4. Screen Blueprint

This section defines screen architecture, not visual mockups.

### 4.1 Source Screen

Purpose:

- Start new creator work.

Primary goal:

- Create a prepared source session.

Secondary goal:

- Explain why a source cannot be prepared.

Supported backend capabilities:

- `/api/render/prepare-source`
- `/api/render/download-health`
- `PrepareSourceRequest`
- local source path through desktop/browser input

AI visibility:

- None by default.
- System readiness may note AI availability only as contextual readiness, not as a Source decision.

Entry points:

- App start.
- New render action.
- Rerun from Library.

Exit points:

- Studio with prepared `session_id`.
- Downloads for standalone downloading.
- System for missing runtime dependency.

Success state:

- Source prepared.
- Duration/title visible.
- Preview session ready.
- Continue to Studio.

Failure state:

- Missing URL/path.
- Local file not found.
- Download/source preparation failure.
- Preview file missing.

Empty state:

- Clear source choice: YouTube or local file.
- Output destination requirement visible but not overwhelming.

Loading state:

- Preparing source.
- Downloading/probing/transcoding preview when needed.
- Keep source action locked while in flight.

Desktop layout behavior:

- Two-column workstation layout is allowed: source inputs and readiness summary.
- Must not resemble a marketing landing page.

Panel ownership:

- Source input panel.
- Source readiness panel.
- Recent source/library shortcut panel, optional.

Scroll ownership:

- Source screen scrolls as a page.
- Readiness summary should stay visible on desktop if practical.

Hierarchy:

1. Source type and source value.
2. Output destination.
3. Prepare action.
4. Readiness details.
5. Recent/recovery affordances.

### 4.2 Studio Screen

Purpose:

- Configure the render draft around a live preview.

Primary goal:

- Submit a valid `RenderRequest`.

Secondary goal:

- Let creators refine key production choices without drowning in every backend field.

Supported backend capabilities:

- Preview video endpoint.
- Preview transcript endpoint.
- `/api/subtitle/preview`
- `/api/voice/profiles`
- `/api/viral/score` and `/api/viral/score/all`
- `RenderRequest` fields.

AI visibility:

- AI assistance as a contained Studio section.
- Clear labels for advisory vs render influence.
- Disabled/fallback states if AI diagnostics indicate missing readiness.

Entry points:

- Source prepared session.
- Rerun job from Library.

Exit points:

- Monitor after render submit.
- Source to change input.
- System for diagnostics.

Success state:

- Draft valid.
- Preview usable.
- Render action enabled.

Failure state:

- Required output missing.
- Invalid voice config.
- Invalid local path.
- Unsupported values.
- Subtitle preview or transcript failure as non-blocking unless required by chosen setting.

Empty state:

- Studio should not be empty without a source session.
- If opened directly, prompt creator to prepare a source.

Loading state:

- Loading preview media.
- Loading transcript.
- Loading subtitle preview.
- Loading voice profiles.
- Validating market score.

Desktop layout behavior:

- Preview should be central and persistent.
- Controls should be grouped by creator intent, not by backend file.
- Advanced controls are progressive disclosure.

Panel ownership:

- Preview/work canvas.
- Essential settings.
- Enhancement settings.
- AI assistance.
- Render readiness/action.

Scroll ownership:

- Preview area should not scroll with long settings on desktop.
- Control rail/panel owns its own scroll.
- Advanced settings sections should not expand the whole page unpredictably.

Hierarchy:

1. Preview and source context.
2. Essential clip/render choices.
3. Creator enhancements: subtitles, voice, camera, text.
4. Market/hook optimization.
5. AI assistance.
6. Advanced render/system settings.
7. Render action.

### 4.3 Monitor Screen

Purpose:

- Track render/download job execution.

Primary goal:

- Tell creator what is happening and whether action is needed.

Secondary goal:

- Provide diagnostics without making logs primary.

Supported backend capabilities:

- `/api/jobs/{job_id}`
- `/api/jobs/{job_id}/parts`
- `/api/jobs/{job_id}/logs`
- `/api/jobs/{job_id}/ws`
- `/api/jobs/queue/status`
- `/api/render/retry/{job_id}`
- `/api/render/resume/{job_id}`

AI visibility:

- If AI planning/influence is active, show concise status such as "AI planning included" only when backed by job/result data.
- Full AI explanation belongs in Results.

Entry points:

- Render submit.
- Active job from Library.
- Download job from Downloads/Library.

Exit points:

- Results on completion.
- Library after interruption/failure.
- Studio only through explicit rerun/edit action.

Success state:

- Job completed or completed with errors.
- Results CTA is available.

Failure state:

- Failed job.
- Interrupted job.
- Stuck part detected.
- Missing logs or transport disconnect.

Empty state:

- No active job. Offer Source and Library entry points.

Loading state:

- Initial job lookup.
- Connecting WebSocket.
- Polling fallback active.

Desktop layout behavior:

- Progress overview high.
- Part list/table dominant.
- Logs collapsed or secondary by default.

Panel ownership:

- Job summary.
- Part progress.
- Transport/readiness.
- Diagnostics/logs.
- Actions.

Scroll ownership:

- Part list owns scroll.
- Logs drawer owns independent scroll.

Hierarchy:

1. Job status and stage.
2. Overall and part progress.
3. Active/stuck/failed parts.
4. Recovery actions.
5. Diagnostics/logs.

### 4.4 Results Screen

Purpose:

- Help the creator choose and export clips.

Primary goal:

- Present ranked outputs and explain the best choices.

Secondary goal:

- Make failures, partial success, and AI influence understandable.

Supported backend capabilities:

- `result_json.outputs`
- `result_json.output_ranking`
- `result_json.best_clip`
- `result_json.best_exports`
- `failed_parts`
- `failed_parts_detail`
- `voice_summary`
- `subtitle_translate_summary`
- `ai_director`
- `ai_render_influence`
- `ai_output_ranking`
- `ai_render_quality_evaluation`
- `ai_ux`
- part stream/media endpoints

AI visibility:

- Explain ranking and AI influence when present.
- Clearly mark AI disabled/unavailable.
- Do not show fake AI cards if metadata is absent.

Entry points:

- Completed Monitor job.
- Library item.

Exit points:

- Export/download/open folder.
- Retry failed parts.
- Start new Source.
- Publish advanced module, explicit only.

Success state:

- Ranked clips visible.
- Best clip clearly identified.
- Preview and actions available.

Failure state:

- No successful outputs.
- Malformed result JSON.
- Missing media file for a part.
- All parts failed.

Empty state:

- No result package selected. Offer Library or Source.

Loading state:

- Loading job.
- Loading parts.
- Parsing result package.
- Loading selected clip media.

Desktop layout behavior:

- Results should be more important than logs.
- Large selected clip preview and ranked list are primary.
- Summary/insight panels are secondary but visible.

Panel ownership:

- Selected output preview.
- Ranked output list.
- Best clip summary.
- AI/quality explanation.
- Failure recovery.
- Export actions.

Scroll ownership:

- Ranked list scrolls independently.
- Explanation panel scrolls independently if needed.
- Selected preview should remain stable.

Hierarchy:

1. Best clip and ranked outputs.
2. Clip preview and playback.
3. Score reasons and confidence.
4. Warnings/partial success.
5. Voice/subtitle summaries.
6. AI explanation.
7. Logs/advanced diagnostics.

### 4.5 Library Screen

Purpose:

- Re-enter prior work safely.

Primary goal:

- Find a render/download job and continue from its real status.

Secondary goal:

- Support retry/rerun/open results.

Supported backend capabilities:

- `/api/jobs/history`
- `/api/jobs/{job_id}`
- `/api/jobs/{job_id}/parts`

AI visibility:

- Lightweight indicators only when result package has AI metadata.
- Full AI detail belongs in Results.

Entry points:

- Main navigation.
- Empty Monitor/Results recovery.

Exit points:

- Results for completed/partial render.
- Monitor for running/queued job.
- Downloads for download job detail.
- Studio through explicit rerun.

Success state:

- History items grouped and filterable by state/kind.

Failure state:

- History fetch fails.
- Job no longer exists.
- Result references missing output files.

Empty state:

- No jobs yet. Offer new Source and Downloads.

Loading state:

- Loading history.

Desktop layout behavior:

- Dense but calm list/card table hybrid is appropriate.
- Must support scanning status, source, counts, and next action.

Panel ownership:

- Filters.
- History list.
- Selected job summary/detail.

Scroll ownership:

- History list owns page scroll.
- Detail pane optional desktop side panel.

Hierarchy:

1. Recent recoverable work.
2. Status and kind filters.
3. Job summaries.
4. Actions.

### 4.6 Downloads Screen

Purpose:

- Download public videos separately from render prep.

Primary goal:

- Queue and track standalone downloads.

Secondary goal:

- Retry failed/unsupported items where applicable.

Supported backend capabilities:

- `/api/download/process`
- `/api/download/retry/{job_id}`
- jobs/parts monitoring for download jobs

AI visibility:

- None. Do not introduce AI download intelligence.

Entry points:

- Main navigation.
- Source screen link when user wants to save sources first.

Exit points:

- Library.
- Source with downloaded local file only if the user explicitly chooses a local file path later.

Success state:

- Saved items visible with output folder.

Failure state:

- Invalid URL.
- Unsupported source.
- Per-item failed download.

Empty state:

- Batch URL input and output destination.

Loading state:

- Queueing/downloading with item progress.

Desktop layout behavior:

- Operational but not admin-heavy.
- Item statuses clear.

Panel ownership:

- Batch input.
- Download job monitor.
- Download history shortcut.

Scroll ownership:

- Download item list owns scroll.

Hierarchy:

1. URLs and output destination.
2. Queue action.
3. Current job/item status.
4. Retry failed.

### 4.7 Publish Screen

Scope:

- Advanced-module-only.

Purpose:

- Operate implemented upload automation.

Primary goal:

- Manage accounts, videos, queue, scheduler, and proxy state.

Secondary goal:

- Run and recover upload queue items.

Supported backend capabilities:

- `/api/upload/accounts`
- `/api/upload/videos`
- `/api/upload/queue`
- `/api/upload/scheduler/status`
- `/api/upload/proxies`
- `/api/upload/workers/*`
- login/proxy checks

AI visibility:

- Caption generation modes are implemented but setup-dependent. If surfaced, mark as advanced and configuration-dependent.
- No fake social optimization or analytics.

Entry points:

- Advanced navigation.
- Explicit "send to Publish" from Results only if upload queue creation is wired in implementation.

Exit points:

- Account setup.
- Queue detail.
- Scheduler status.
- Results/Library.

Success state:

- Queue item successful or scheduled.

Failure state:

- Login required.
- Profile locked.
- Proxy failed.
- Upload failed.
- Browser/Playwright missing.

Empty state:

- No accounts/videos/queue items. Prompt setup, not fake publishing.

Loading state:

- Account list, queue list, scheduler status.
- Login/proxy check in progress.

Desktop layout behavior:

- Advanced operational console, but visually consistent with premium workstation.
- More density acceptable here than core render flow.

Panel ownership:

- Accounts.
- Video library.
- Queue.
- Scheduler.
- Proxy/status.

Scroll ownership:

- Each operational list owns its own scroll in desktop layout.

Hierarchy:

1. Blocking health state.
2. Queue status.
3. Accounts/videos.
4. Scheduler/proxies.
5. History/diagnostics.

### 4.8 System Screen

Purpose:

- Surface local readiness and diagnostics.

Primary goal:

- Explain whether the machine can render and why something may fail.

Secondary goal:

- Provide advanced details for support.

Supported backend capabilities:

- `/api/warmup/status`
- `/api/render/ai-diagnostics`
- `/health`
- Electron capability checks

AI visibility:

- AI readiness and diagnostics only.
- Do not present AI creation controls here.

Entry points:

- Main/secondary navigation.
- Contextual warning links from Source, Studio, Monitor.

Exit points:

- Return to prior workflow.

Success state:

- Runtime dependencies ready or understandable.

Failure state:

- Missing FFmpeg/ffprobe/yt-dlp/Whisper/Ollama/browser capability.

Empty state:

- Loading readiness status.

Loading state:

- Warmup in progress.

Desktop layout behavior:

- Clear readiness groups.
- Details available but not visually louder than core product.

Panel ownership:

- Runtime readiness.
- AI diagnostics.
- Desktop capabilities.
- Maintenance/diagnostics.

Scroll ownership:

- Page scroll is acceptable.

Hierarchy:

1. Overall readiness.
2. Blocking issues.
3. Dependency groups.
4. Details/log maintenance.

## 5. Render Studio Experience

The Studio experience should make rendering feel like guided production, not settings administration.

### 5.1 Canonical Studio Flow

```text
Prepared source
  -> Preview
  -> Choose output intent
  -> Set clip generation
  -> Choose enhancements
  -> Optional AI assistance
  -> Confirm render readiness
  -> Submit render
  -> Monitor
  -> Results
```

### 5.2 Source Prep

The creator should see Source prep as the product taking custody of the input:

- URL or local path is validated.
- Duration/title are found.
- Preview media is prepared.
- Transcript may be prepared.

Design implication:

- Source prep status should feel like "ready to edit", not "technical task completed."

### 5.3 Preview

Preview is the anchor of Studio.

It should support:

- Video playback from preview endpoint.
- Trim context.
- Subtitle/text overlay preview states where available.
- Media loading/failure states.

Do not design:

- Multi-track editing timeline.
- Arbitrary clip sequencing.
- Keyframe animation surface.

### 5.4 Clip Generation

Clip generation controls should be simple first:

- Clip duration range.
- Max outputs.
- Order strategy.
- Scene detection on/off.

Advanced:

- Parallel parts.
- Retry count.
- Fine render profile details.

Creator wording should express outcomes:

- "Find strong clips between 15 and 60 seconds"
- "Limit to 5 outputs"
- "Rank by strongest moments"

Avoid exposing backend labels as the only language.

### 5.5 Subtitle System

Subtitle controls are high-value and should be prominent.

Implemented capabilities:

- Enable/disable subtitles.
- Transcription engine.
- Style.
- Font, size, color, highlight, outline, position.
- Preview PNG endpoint.
- Subtitle edits.
- Translation.
- Market/hook policy effects.

Design behavior:

- Default subtitle controls show only essential style and readability.
- Detailed typography and positioning live under an expanded section.
- Translation is a dedicated subsection tied to target language and voice source.

### 5.6 Voice

Voice narration is a workflow, not a checkbox.

Implemented capabilities:

- Manual text.
- Subtitle-derived voice.
- Translated-subtitle voice.
- Language/gender/profile.
- Rate.
- Mix mode.
- Voice summary in results.

Design behavior:

- Voice source choice drives required fields.
- Manual source requires text.
- Translated subtitle source should clearly depend on translation settings.
- Mix failure should be explained in Results, not hidden.

### 5.7 Camera / Reframe

Implemented capabilities:

- Aspect ratio.
- Frame scale.
- Reframe mode.
- Motion-aware crop.
- AI camera promotion under opt-in influence.

Design behavior:

- Camera choices should be described as framing behavior.
- Motion-aware crop should carry a "may fall back safely" expectation.
- AI camera changes must be explainable after render.

### 5.8 Market / Hook

Implemented capabilities:

- `/api/viral/score`
- `/api/viral/score/all`
- market/hook settings in `RenderRequest`
- combined/adaptive scoring
- output ranking components

Design behavior:

- Market/hook should feel like optimization guidance.
- Show score as confidence input, not guaranteed virality.
- Avoid social analytics language.

### 5.9 AI Director

Implemented capabilities:

- `ai_director_enabled`
- `ai_render_influence_enabled`
- beat execution
- timing mutation opt-in
- variant planning
- clip discovery/selection/batch planning
- AI metadata and promotion reports in results

Design behavior:

- Default AI section: "Analyze and explain recommendations."
- Execution influence must be a separate advanced opt-in.
- Each AI execution option needs plain consequence text and result report mapping.
- Disabled/unavailable AI should not block non-AI rendering.

### 5.10 Render Execution

Render action should be a readiness checkpoint.

Readiness should summarize:

- Source prepared.
- Output destination set.
- Required voice fields valid.
- Subtitle/translation dependencies clear.
- AI state clear.
- Expected outputs/clip constraints clear.

Render starts Monitor. Studio should not remain the live job owner.

### 5.11 Result Transition

When render completes:

- Clean success: move to Results with ranked outputs.
- Partial success: move to Results with a recoverable warning.
- Failed: stay in Monitor with failure summary and Library/retry options.
- Interrupted: show recovery state, not a generic failure.

## 6. AI Surfacing Spec

AI must be presented as assistance with explicit boundaries.

### 6.1 Visible AI

Visible AI should appear when it helps creator decisions.

Capabilities:

- Output ranking.
- Best clip.
- Ranking reasons.
- AI UX metadata.
- Market fit.
- Quality warnings.
- Subtitle/camera/segment promotion reports when enabled.

When visible:

- Results screen by default.
- Studio only for opt-in configuration and readiness.

How visible:

- Summary cards.
- Reason lines.
- Confidence/status chips.
- "Changed / suggested / blocked" distinction.

Confidence behavior:

- Show confidence only when backend provides it.
- Do not fabricate confidence values.

Failure behavior:

- AI unavailable should degrade to non-AI render experience.
- AI failure should not invalidate successful outputs.

Disabled behavior:

- If AI Director disabled, show "AI analysis was not enabled" only where relevant.

Trust messaging:

- "Recommended" for advisory.
- "Applied" for actual influence.
- "Blocked" or "Skipped" for quality gate or user override.

### 6.2 Passive AI

Passive AI or intelligence includes:

- Segment scoring.
- Viral/hook/motion/market scoring.
- Output ranking.
- Quality evaluation when available.
- Knowledge/platform context when AI enabled.

When visible:

- As result explanations, not as constant controls.

How visible:

- Score reasons.
- Best-clip rationale.
- Warnings.

Failure behavior:

- Missing passive metadata falls back to basic output/part information.

### 6.3 Explainable AI

Explainable AI includes:

- AI Director plan.
- Render decision preview.
- Render influence report.
- Promotion reports.
- Quality gate.
- AI execution summary/metrics when available.

When visible:

- Results primary explanation area.
- Monitor only as status hint.
- Studio only as opt-in description.

How visible:

- "What AI analyzed"
- "What AI changed"
- "What AI skipped"
- "What was blocked for safety"

Failure behavior:

- Explanation absent should show unavailable state, not empty panels.

### 6.4 Advanced AI

Advanced AI includes:

- Timing mutation.
- Variant planning.
- Clip discovery/selection/batch planning.
- RAG memory.
- Deep phase metadata.
- AI diagnostics.

When visible:

- Advanced Studio section.
- System diagnostics.
- Advanced Results details.

How visible:

- Collapsed by default.
- Each option must map to real `RenderRequest` field or result metadata.

Disabled behavior:

- Default disabled.
- No pressure to enable for basic render.

Trust messaging:

- Use "experimental", "planning-only", or "execution opt-in" only where true from implementation.

### 6.5 AI Prohibitions

Do not design:

- AI publish button.
- AI arbitrary timeline editor.
- AI social analytics predictor.
- AI cloud research.
- AI prompt box that implies arbitrary editing.
- AI rewrite FFmpeg command control.
- AI generate non-implemented subtitle styles.

## 7. Results Experience Spec

Results is the product's main value moment.

### 7.1 Results Mental Model

The creator should experience Results as:

```text
Here are the clips.
This one is strongest.
Here is why.
Here is what failed or needs review.
Here is what to do next.
```

### 7.2 Required Result Surfaces

Use only real data:

- `outputs`
- `output_ranking`
- `best_clip`
- `best_exports`
- `failed_parts`
- `failed_parts_detail`
- `voice_summary`
- `subtitle_translate_summary`
- `ai_director`
- `ai_render_influence`
- `ai_output_ranking`
- `ai_render_quality_evaluation`
- `ai_ux`
- job parts
- media/stream endpoints

### 7.3 Output Review

Primary content:

- Selected clip preview.
- Ranked clip list.
- Best clip designation.
- Part number and status.
- Score and reason.
- Download/stream/open actions.

Behavior:

- Ranking list drives selected preview.
- Missing media should show a recoverable file unavailable state.
- Output actions must not assume raw local path is playable.

### 7.4 Ranking

Ranking must be creator-readable.

Show:

- Rank.
- Score.
- Primary reason.
- Component details on demand.

Do not show:

- Raw score formula as primary UI.
- Raw JSON.
- Claims of guaranteed performance.

### 7.5 Partial Success

Partial success must feel salvageable.

Show:

- Successful outputs first.
- Clear partial warning.
- Failed part count.
- Failed part details in a recovery panel.
- Retry/recover action where backend supports it.

Do not:

- Collapse the whole job into a failed state when outputs exist.
- Hide failed parts.

### 7.6 Voice and Subtitle Summary

Show concise status:

- Voice: not used/applied/failed.
- Translation: not used/applied/partial/failed.

If failed:

- Explain that output video may still be valid.
- Link to diagnostics/logs if needed.

### 7.7 AI Summary

Show only backed data:

- AI enabled/disabled.
- Advisory summary.
- Applied changes.
- Skipped/blocked changes.
- Quality warnings.
- Confidence if present.

Do not create empty AI cards just to fill layout.

### 7.8 Logs and Diagnostics

Logs are available but not primary.

Default:

- Human-readable warnings and recovery.

Advanced:

- Raw logs.
- Raw result diagnostics.
- AI phase raw detail.

## 8. Maintainability Design Rules

### 8.1 Screen Ownership

- Source owns source prep only.
- Studio owns render draft only.
- Monitor owns active job only.
- Results owns result package only.
- Library owns history only.
- Downloads owns standalone downloads only.
- Publish owns upload automation only.
- System owns readiness only.

No screen may become an all-purpose dashboard.

### 8.2 Component Ownership

Component families:

- Source components.
- Studio controls.
- Monitor components.
- Result components.
- Library components.
- Download components.
- Publish components.
- System components.
- Shared primitives.

Shared primitives may not know backend fields.

### 8.3 Token Ownership

Tokens belong to the design system foundation:

- Spacing.
- Type scale.
- Color roles.
- Status roles.
- Surface roles.
- Radius.
- Motion.

Feature screens consume tokens; they do not define new global language.

### 8.4 Interaction Ownership

- Source interactions produce `SourceSession`.
- Studio interactions produce `RenderDraft`.
- Monitor interactions read `Job`/`JobPart`.
- Results interactions read `ResultPackage`.
- Desktop interactions go through adapter.

### 8.5 Anti-Patterns

Avoid:

- Nested cards inside cards.
- Giant settings walls.
- Logs-first layouts.
- Raw JSON panels as primary UI.
- One mega "Render" screen that owns everything.
- Generic "AI Magic" actions.
- Hiding terminal states.
- Overusing modal dialogs for core workflow.
- Designing every backend field as a top-level visible control.

## 9. Design System Foundation

This section gives direction for Figma generation. It does not prescribe exact hex values.

### 9.1 Spacing Philosophy

- Desktop workstation density.
- Spacious enough for confidence, dense enough for repeated use.
- Use consistent spacing steps.
- Avoid decorative whitespace that makes production tasks slower.
- Preserve stable dimensions for preview, ranked lists, progress rows, and controls.

### 9.2 Density Philosophy

- Core workflow: medium density.
- Results review: medium-high density with strong hierarchy.
- Publish/System: higher density acceptable.
- Advanced settings: compact but readable.

Avoid both extremes:

- Not a marketing landing page.
- Not a spreadsheet of controls.

### 9.3 Surface Hierarchy

Use surfaces to clarify responsibility:

1. Workspace background.
2. Primary working surface.
3. Secondary panels.
4. Inline controls.
5. Diagnostics/advanced drawers.

Cards should be used for repeated items and framed tools, not every section.

### 9.4 Motion Philosophy

Motion should communicate state:

- Source preparing.
- Render running.
- Part progress.
- Result transition.
- Drawer expansion.
- Error recovery.

Avoid decorative motion. Avoid motion that implies real-time AI work where none exists.

### 9.5 Color Direction

Color should feel premium, focused, and trustworthy.

Guidance:

- Neutral foundation with restrained accent.
- Distinct semantic colors for success, warning, failed, interrupted, active.
- AI accent should be subtle and not dominate product identity.
- Avoid gamer RGB, excessive gradients, heavy glassmorphism, and one-note purple/blue palettes.

### 9.6 Typography Hierarchy

Use typography for task hierarchy:

- Screen title: product area and current object.
- Section title: workflow group.
- Control label: plain and compact.
- Metadata: quiet but readable.
- Scores/reasons: clear and scannable.

Avoid huge hero typography inside operational screens.

### 9.7 Desktop-First Behavior

Primary target:

- Desktop workstation.
- Large preview and multi-panel layout.
- Independent scroll regions.
- Long-running job visibility.

Secondary:

- Browser fallback.
- Smaller desktop widths should collapse panels predictably.

Mobile-first behavior is out of scope.

## 10. Figma MCP Structure

The Figma file must be structured for implementation-safe handoff.

### 10.1 Figma Pages

Create these pages:

1. `00 Cover + Principles`
2. `01 IA + Flow Maps`
3. `02 Design Tokens`
4. `03 Components`
5. `04 Source`
6. `05 Studio`
7. `06 Monitor`
8. `07 Results`
9. `08 Library`
10. `09 Downloads`
11. `10 Publish Advanced`
12. `11 System`
13. `12 States + Errors`
14. `13 Engineering Handoff`
15. `99 Out of Scope`

### 10.2 Sections

Each screen page should include sections:

- `Default`
- `Loading`
- `Empty`
- `Success`
- `Failure`
- `Partial / Warning`
- `Advanced Expanded`
- `Annotations`

Only include sections backed by real state for that screen.

### 10.3 Frames

Frame naming:

```text
Screen / State / Viewport / Version
```

Examples:

- `Source / Default / Desktop / V1`
- `Studio / AI Advanced Expanded / Desktop / V1`
- `Results / Partial Success / Desktop / V1`
- `Monitor / Running With Failed Part / Desktop / V1`

Desktop frame targets:

- Primary desktop: wide workstation.
- Secondary desktop: narrower desktop.

Do not create mobile-first frames unless specifically requested later.

### 10.4 Component Library

Required component groups:

- `Navigation`
- `Workspace Shell`
- `Source`
- `Studio Controls`
- `Monitor`
- `Results`
- `Library`
- `Downloads`
- `Publish Advanced`
- `System`
- `AI Status`
- `Status + Progress`
- `Media Preview`
- `Forms`
- `Feedback + Errors`
- `Diagnostics`

### 10.5 Component Variants

Required variants:

- Button: default, hover, active, disabled, loading.
- Icon button: default, hover, active, disabled.
- Input: default, focused, error, disabled, loading.
- Select/menu: default, open, disabled.
- Toggle: off, on, disabled.
- Slider/stepper numeric control.
- Status chip: queued, running, completed, partial, failed, interrupted, unsupported.
- AI chip: disabled, advisory, applied, skipped, blocked, unavailable.
- Progress row: waiting, active, done, failed, stuck.
- Output clip item: normal, selected, best, failed/missing media.
- Result summary: clean, partial, failed.
- Empty state: source, library, results, downloads.
- Error state: recoverable, blocking, missing dependency.

### 10.6 Naming Convention

Use product/domain names, not current DOM IDs.

Good:

- `Results/RankedClipItem`
- `Studio/SubtitleControls`
- `Monitor/PartProgressRow`
- `AI/InfluenceReport`
- `System/ReadinessGroup`

Avoid:

- `render_output_panel`
- `evStartBtn`
- `leftPanel2`
- `newCard`
- `magicAIBox`

### 10.7 Design Tokens

Token groups:

- `color/background`
- `color/surface`
- `color/text`
- `color/border`
- `color/accent`
- `color/status`
- `color/ai`
- `space`
- `radius`
- `type`
- `shadow`
- `motion`
- `size/control`
- `size/panel`

Status color tokens must cover:

- queued
- running
- completed
- partial
- failed
- interrupted
- unsupported
- unavailable

### 10.8 Auto-Layout Rules

All components and frames should use auto layout where possible.

Rules:

- No absolute-positioned text except media overlays in preview examples.
- Panels should have explicit min/max behavior.
- Lists should have repeatable row/card components.
- Preview regions should have stable aspect behavior.
- Control rows should not resize unpredictably when labels change.
- Text must wrap safely.
- Independent scroll regions must be annotated.

### 10.9 Responsive Behavior

Desktop-first breakpoints:

- Wide desktop: multi-panel workstation.
- Standard desktop: collapsible secondary panel.
- Narrow desktop/browser: stacked sections, no feature loss.

Do not design:

- Mobile app navigation.
- Touch-first editing.
- Phone layout as primary.

### 10.10 Annotation Strategy

Every major screen must include implementation annotations:

- Owning feature module.
- Primary entity.
- Backend endpoints.
- Required fields.
- Optional fields.
- Empty/loading/failure states.
- Unsupported assumptions.

Annotation examples:

- `SourceSession: session_id, duration, title, export_dir`
- `RenderDraft -> POST /api/render/process`
- `Results -> parse ResultPackage from jobs.result_json`
- `Media playback -> /api/jobs/{job_id}/parts/{part_no}/stream`
- `AI influence visible only when result_json.ai_render_influence exists`

### 10.11 Engineering Handoff Rules

Figma handoff must include:

- Screen responsibility.
- Component ownership.
- Entity mapping.
- Endpoint mapping.
- State mapping.
- Unsupported features list.
- Variant/state coverage.
- Notes for desktop/browser fallback.

Do not hand off:

- Raw visual-only screens without contract annotations.
- Components that require backend fields that do not exist.
- Fake content as if it were data-backed.

## 11. Explicit Out Of Scope

Do not include these as available product capabilities:

- Cloud sync.
- Cloud rendering.
- Multi-user collaboration.
- Teams, roles, permissions.
- Billing/subscriptions.
- Online asset library.
- Social analytics dashboard.
- Campaign management.
- Official TikTok/YouTube/Instagram API publishing.
- Guaranteed upload success.
- Fake one-click publish flow.
- Full nonlinear timeline editor.
- Drag-and-drop multi-track media timeline.
- Arbitrary clip sequencing.
- Keyframe animation editor.
- AI prompt box for arbitrary video editing.
- AI rewriting arbitrary FFmpeg commands.
- AI arbitrary subtitle timing rewrite.
- AI inventing clip timestamps.
- AI deleting outputs.
- AI social performance prediction.
- Live internet research during render.
- Professional audio mastering guarantee.
- Perfect translation guarantee.
- Perfect cinematic crop guarantee.
- Mobile-first app.
- Current UI visual reuse.
- Current CSS/DOM/JS architecture reuse.

Future-only ideas must be parked on `99 Out of Scope`, not blended into product screens.

## 12. Biggest Product Opportunities

These are opportunities already supported by implemented capability:

1. Make Results the hero of the product.

   Ranked outputs, best clip, reasons, warnings, and summaries are real. This is where the product becomes creator-first.

2. Turn AI from hidden metadata into trustable guidance.

   The product already has advisory, influence, promotion, quality gate, ranking, and explainability metadata. The design should surface it with clear boundaries.

3. Make partial success feel professional.

   Local rendering often has edge cases. Preserving successful clips while explaining failed parts is a major trust advantage.

4. Elevate subtitles, voice, and camera from settings to production tools.

   These are creator-facing quality controls, not miscellaneous toggles.

5. Keep advanced operation powerful but contained.

   Upload automation, diagnostics, and deep AI controls exist, but should not pollute the core render path.

## 13. Recommended Next Step

Before running MCP Figma generation:

1. Confirm v1 scope:
   - Core: Source, Studio, Monitor, Results, Library, Downloads, System.
   - Advanced optional: Publish.

2. Prepare Figma generation prompt from this spec:
   - Include IA.
   - Include screen blueprints.
   - Include state matrix.
   - Include component and token structure.
   - Include out-of-scope list.

3. Generate Figma structure first:
   - Pages, sections, components, tokens, annotations.
   - Then screens.

4. Review Figma for contract violations before any implementation starts.


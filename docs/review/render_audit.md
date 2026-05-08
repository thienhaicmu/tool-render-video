# Render System — Full Architecture Audit

> **Living document.** Original audit generated 2026-05-07. Patch notes appended below.
> All findings are grounded in actual file content with exact line references.

---

## Patch Status Log

### 2026-05-08 — AI Productization Phase 9: Packaging + Performance Stabilization

**Implemented:**
- `app/ai/diagnostics.py` (new) — `get_ai_runtime_diagnostics() -> dict`; returns `{dependencies, startup_safe, embedding_available, vector_store, memory, warnings}`; uses dependency detectors only — never loads models, never triggers embeddings, never raises; `embedding_available` checks library presence via `importlib.util.find_spec`, not model load; `memory.db_path` is sanitized to filename only (no full path exposed)
- `app/ai/rag/sqlite_store.py` — three new methods on `SQLiteMemoryStore`:
  - `health() -> dict` — checks DB file existence and row count without requiring `initialize()`; returns `{sqlite_available, count, warnings}`; never raises
  - `vacuum() -> bool` — opens connection with `isolation_level=None` (autocommit) to run `VACUUM` legally; returns `True` on success, `False` on any failure; requires `_ready=True`
  - `prune(max_rows=5000) -> int` — deletes oldest memories and their matching embeddings in a single transaction (embeddings deleted first for FK consistency); returns rows deleted; never raises; never blocks rendering
- `app/ai/rag/vector_store.py` — `health() -> dict` on `LocalVectorStore`; returns `{count, faiss_available, fallback_mode, warnings}`; uses `has_faiss()` detector, not FAISS import; never raises even on corrupted internal state
- `app/ai/rag/memory_store.py` — two new methods on `LocalMemoryStore`:
  - `get_memory_health() -> dict` — aggregates vector store + SQLite health; returns `{vector_count, sqlite_count, faiss_available, fallback_mode, sqlite_available, hydrated, warnings}`; never raises
  - `compact_memory(max_rows=5000) -> dict` — calls `prune()` then `vacuum()` if rows were deleted; returns `{pruned, vacuumed, message}`; never raises
- `app/routes/render.py` — `GET /api/render/ai-diagnostics` endpoint; read-only, no auth changes, matches existing `/queue-status` style; delegates to `get_ai_runtime_diagnostics()`; returns `{startup_safe, error}` fallback on any failure; no model loading, no embedding computation
- `tests/test_ai_phase9_packaging_performance.py` (new) — 39 tests covering: diagnostics import safety, `get_ai_runtime_diagnostics()` shape/behavior, dependency key presence, embedding lazy-load verification (reload-based sentinel check), `embed_text`/`embed_texts` None-safety, vector store `health()` in fallback mode, SQLite `health()`/`vacuum()`/`prune()` on temp DBs, embedding-memory FK consistency after prune, memory store health/compact, API key independence, GPU independence, model-load guard

**Verification:**
- 39/39 Phase 9 tests pass
- 486/486 full suite passes (zero regressions)
- `git diff --check` clean (LF→CRLF warnings are Windows `core.autocrlf` only)

**Constraints preserved:**
- No optional AI lib made mandatory
- No heavy import at module level (sentence-transformers/faiss/torch/mediapipe/faster-whisper never imported at startup)
- No render pipeline modified
- No render engine modified
- No DB schema changed
- No Electron packaging config changed
- No cloud dependencies added
- No background services added
- All diagnostics are read-only — zero side effects on render behavior

**Not yet implemented:**
- Full Electron packaging validation (installer size, bundle audit)
- Real startup profiling (time-to-first-render measurement)
- GPU/CPU model selection UI
- Render-time AI influence (Phase 10+)
- Memory compaction scheduled job (currently manual call only)

**Known limitations:**
- Diagnostics are lightweight snapshots — they do not benchmark model inference speed
- Optional AI libraries remain user-installed (`requirements-ai.txt`)
- Memory compaction is SQLite-only; in-memory vector store is not pruned (only rebuilds on app restart)
- `vacuum()` requires the store to be initialized (`_ready=True`); safe to call at any time otherwise (returns False)

---

### 2026-05-08 — AI Director Phase 8: Timeline Intelligence UI

**Implemented:**
- `index.html` — `#evAiOverlayLayer` div added inside `#evTimelineBarWrap` (after `#evTimelineLayers`); `#evAiTimelineLegend` div added after the `evTimeline` block, inside `view_editor`; both hidden by default; `aria-hidden="true"` set; no existing IDs or DOM structure changed
- `editor-view.js` — `aiPlan: null` added to `_ev` state object; reset to `null` in both `openEditorView()` and `openEditorView_withSession()` on session open; `_evSetDuration()` now calls `_evRenderAiTimeline()` after updating trim UI so overlay redraws whenever duration changes
- `editor-view.js` — `_evSetAiPlan(plan)` public setter: stores plan in `_ev.aiPlan` and triggers `_evRenderAiTimeline()`; `_evRenderAiTimeline()` builds absolute-positioned segment bars from `plan.selected_segments[].{start,end,score}`; segments with `score ≥ 0.7` get hook class (amber); populates legend with AI Clip / Hook chips and energy+emotion badge; clears overlay and hides legend when plan is absent, disabled, or duration is zero
- `render-ui.js` — `renderAiInsights()` calls `if (typeof _evSetAiPlan === 'function') _evSetAiPlan(aiDir)` immediately after the panel becomes visible, so the editor timeline overlay is populated whenever a completed render's AI plan is shown
- `app.css` — ~80 lines of Phase 8 styles appended at end; `.evAiOverlayLayer` (absolute, `bottom:12px`, `height:6px`, `pointer-events:none`, `z-index:2`); `.evAiSegBar` (blue clip bars, `rgba(99,179,237,.50)`); `.evAiSegBarHook` (amber hook bars with subtle glow, `rgba(251,191,36,.72)`); `.evAiTimelineLegend` (flex row, dark bg, `border-top`); `.evAiLegendItem`/`.evAiLegendHook` with `::before` color chips; `.evAiLegendEnergy` with `data-energy` color variants (high=green, mid=amber, low=blue)

**Visible behavior:**
- Editor timeline shows no overlay by default (clean, no regression)
- After a render completes with AI Director enabled, switching to editor view reveals colored segment bars overlaid on the timeline: blue for standard AI clips, amber/gold for high-score hook segments
- Legend row appears below the timeline showing clip/hook chip legend and a right-aligned energy+emotion summary badge (color-coded by energy tier)
- Hovering a segment bar shows a tooltip with start/end times and score
- Overlay is fully static — no per-frame updates; `pointer-events: none` throughout so seek and trim interactions are completely unaffected
- On editor re-open (`openEditorView*`), overlay and legend are cleared

**Constraints preserved:**
- No canvas, no SVG libraries, no chart dependencies
- No new API endpoints
- No WebSocket or render queue logic changed
- No existing CSS classes or editor DOM modified (additions only)
- `_evOnTimeUpdate()` untouched — no per-frame overlay work
- Overlay does not appear until a completed render provides AI metadata

**Not yet implemented:**
- Interactive AI controls (user-adjustable confidence thresholds)
- Beat-sync render execution triggered from UI
- Story intelligence UI
- Real-time pacing visualization during active render

---

### 2026-05-08 — AI Director Phase 7: Insights UI

**Implemented:**
- `index.html` — `#ai_insights_panel` div added inside `#render_active_panel`, after the dominant render card (`rdCard`); includes `#ai_conf_badge` (confidence badge) and `#ai_insights_body` (dynamic content); starts hidden (`hiddenView`); no existing IDs or layout changed
- `render-ui.js` — `renderAiInsights(job)` called at end of `updateRenderMainState()`; `resetAiInsightsPanel()` called from `resetRenderSessionUi()`; panel hides cleanly when `ai_director` is absent or `enabled=false`; all text content safely escaped via existing `esc()` helper
- `render-ui.js` — `renderAiInsights(job)` builds 6 sections: ① summary headline + bullets (max 5), ② confidence bars (Semantic/Pacing/Memory via CSS `--ai-bar-pct`), ③ pacing + camera cards in 2-col grid (behavior/BPM/emotion/energy/zoom), ④ subtitle card (tone/emphasis/density/beat-aware/emotion-aware), ⑤ memory card (only when `memory_context.results` is non-empty), ⑥ warning pills from `ai_summary.warnings`
- `render-ui.js` — `_aiBarLevel(pct)` maps 0-39→low, 40-69→mid, 70+→high; `_aiEnergyLabel(level)` maps float energy to High/Moderate/Low; `_aiBarRowHtml(label, pct)` generates CSS-only bar row HTML
- `app.css` — ~150 lines of new AI Insights styles appended at end; classes: `.aiInsightsPanel`, `.aiInHeader`, `.aiInLabel`, `.aiInConfBadge` (color-coded by level data attribute), `.aiInBody`, `.aiHeadline`, `.aiSummaryList/.aiSummaryItem`, `.aiConfGrid/.aiBarRow/.aiBar/.aiBarFill` (CSS custom property `--ai-bar-pct`), `.aiInsightGrid/.aiInsightCard/.aiInsightCardBadge` (color variants: default/green/amber), `.aiMemCard`, `.aiWarnPill`; no existing CSS classes modified

**Visible behavior:**
- AI Insights panel is hidden during active rendering (no `result_json.ai_director` yet)
- Panel appears after render completes if `ai_director_enabled=true` in request
- Confidence badge color-codes: green ≥70, amber 40–69, red <40
- Bar fills are pure CSS (no canvas, no SVG libraries, no chart deps)
- Pacing/camera/subtitle cards use compact badge layout with color semantics (green=positive, amber=caution, default=neutral)
- Memory card appears only when past render results were retrieved
- Warnings shown as amber pills below the main content
- Panel hides completely if no AI metadata — existing render card layout unchanged

**Constraints preserved:**
- No existing IDs, classes, or render flow modified (only additions)
- No React, Vue, or chart library added
- No WebSocket logic changed
- No backend API changes
- No render queue logic changed
- 447/447 backend tests still passing after changes
- `git diff --check` clean

**Not yet implemented:**
- Timeline AI overlays (per-clip reasoning markers)
- Interactive AI controls (user-adjustable confidence thresholds)
- Beat-sync render execution triggered from UI
- Story intelligence UI
- Real-time pacing visualization during active render

**Known limitations:**
- AI Insights only visible after render completion (result_json not set during active render)
- Compact visualization only — no detailed breakdown modals
- No timeline overlays yet

---

### 2026-05-08 — AI Director Phase 6: Explainability Foundation

**Implemented:**
- `app/ai/explainability/` package (new) — deterministic, rule-based, no external deps, never raises
- `reason_builder.py` (new) — four public functions: `build_clip_reasons`, `build_camera_reasons`, `build_subtitle_reasons`, `build_pacing_reasons`; each returns up to 5 deduplicated human-readable strings; explanations derived from existing plan data only — no hallucination; all functions wrapped in `try/except` returning `[]` on failure
- `confidence.py` (new) — `calculate_ai_confidence(edit_plan) -> dict`; returns `{overall, clip_selection, semantic, memory, pacing, camera, subtitle, warnings}` (all 0–100); weighted overall score (clip×0.30, semantic×0.20, memory×0.15, pacing×0.20, camera×0.075, subtitle×0.075); graceful degradation: semantic≤40 when embeddings unavailable, memory≤30 when RAG error, clip=20 when no segments; never raises
- `summary.py` (new) — `build_ai_summary(edit_plan, confidence) -> dict`; returns `{headline, summary_lines≤6, strengths≤6, warnings, confidence}`; headline reflects overall quality (Strong/Solid/Basic), energy level, emotion, and mode label; warnings derived from plan warnings + confidence warnings; never raises
- `AIEditPlan` expanded — two new fields: `explainability: dict = {}` and `confidence: dict = {}`; `to_dict()` updated with: `explainability` (full reasons + summary), `confidence` (full scores), `ai_summary` (compact headline/lines/strengths/warnings without nested confidence), `ai_confidence` (compact overall/semantic/memory/pacing subset for result_json)
- `ai_director.py` upgraded — `_attach_explainability(plan, job_id)` helper called at end of `_build_plan()`; guarded by local try/except so explainability crash can never block plan return; logs `ai_explainability_generated` and `ai_confidence_generated` at INFO level; explainability error appended to `plan.warnings` as `"explainability_error:*"` when it does fail

**Tests added:**
- `backend/tests/test_ai_explainability_phase6.py` — 64 tests covering reason builder imports/determinism/deduplication/content, confidence imports/structure/degradation rules (semantic≤40 on embeddings_unavailable, memory≤30 on rag_error, clip=20 on no segments), summary structure/compactness/headline quality signals, schema new fields and to_dict keys, AI Director integration (plan has explainability+confidence after creation, to_dict includes ai_summary/ai_confidence, crash isolation via monkeypatch, JSON serialization), constraint checks (no API key, no GPU, no cloud), Phase 1–5 regression

**Phase 6 design constraints preserved:**
- No cloud API calls, no API keys
- No ML models, no GPU
- No LLM reasoning — all explanations are deterministic from existing plan data
- No changes to render_pipeline.py, render_engine.py, subtitle_engine.py, motion_crop.py
- Explainability is observation-only metadata — render output unchanged
- All prior Phase 1–5 tests pass without modification (383 → 447 total)

**How it works:**
- `reason_builder` maps plan fields (behavior, emotion, BPM, scores, flags) to human-readable strings via rule lookups — same inputs always produce same outputs
- `confidence` scores each dimension from available evidence (segments, warnings, memory results, beat data) with explicit floor values when data is absent
- `summary` derives headline quality ("Strong/Solid/Basic") from overall confidence and combines emotion+energy+mode into a natural-language label
- All data flows into `to_dict()` → `result_json["ai_director"]["ai_summary"]` and `["ai_confidence"]` automatically, with no render_pipeline.py changes needed

**Not yet implemented:**
- Explainability UI — no frontend exposure yet
- Timeline AI overlays showing per-clip reasoning
- Interactive AI insights panel
- Story intelligence layer
- Render-time AI overrides based on confidence

**Known limitations:**
- Explanations are rule-based string mappings — intentionally compact, no natural language generation
- Confidence scores are heuristic (weighted rules), not calibrated probabilities
- `ai_summary` and `ai_confidence` appear inside `result_json["ai_director"]`, not at result_json top level

---

### 2026-05-08 — AI Director Phase 5: Camera + Subtitle Intelligence

**Implemented:**
- `camera_planner.py` (new) — deterministic, rule-based camera behavior planning; no external deps; never raises; priority rules: `clean_subtitle`→disabled, emotion(`surprise`/`urgency`)→`dramatic_push`, fast pacing/high energy(`>0.75`)→`fast_follow`, `storytelling`/`slow_build`→`slow_reveal`, default→mode config; all paths set `subtitle_safe=True`, `zoom_strength`, `follow_strength`, and `reason` string
- `subtitle_planner.py` (new) — deterministic, rule-based subtitle behavior planning; no external deps; never raises; mode-based base config: viral_tiktok=hype/punch/4words, podcast=clean/keyword/6words, storytelling=story/soft/6words, clean_subtitle=clean/none/7words; beat-aware override: if `beat_available AND pacing_style=="fast"` → `density="compact"`; emotion-aware override: if emotion in `{curiosity, surprise, urgency}` → `highlight_keywords=True`; all paths return `reason` string
- `AICameraPlan` expanded — new fields: `zoom_strength` (float, default 1.0), `follow_strength` (float, default 0.5), `motion_energy` (Optional[float]), `reason` (str); `to_dict()` updated
- `AISubtitlePlan` expanded — new fields: `emphasis_style` (str, default "none"), `density` (str, default "normal"), `beat_aware` (bool), `emotion_aware` (bool), `reason` (str); `to_dict()` updated
- `ai_modes.py` upgraded — each mode now has `subtitle_emphasis_style`, `subtitle_density`, `camera_zoom_strength` (viral_tiktok=punch/compact/1.12, podcast=keyword/normal/1.05, storytelling=soft/normal/1.05, clean_subtitle=none/comfortable/1.0)
- `ai_director.py` upgraded — imports `plan_camera_behavior`, `plan_subtitle_behavior`; builds `pacing_ctx` and `transcript_ctx` dicts from pacing plan output; injects `mode_name` into `mode_config_with_name`; calls `_safe_camera_plan()` and `_safe_subtitle_plan()` wrappers that catch all exceptions and return bare plan objects with warning entries (`camera_planner_error:*`, `subtitle_planner_error:*`)

**Tests added:**
- `backend/tests/test_ai_director_phase5_camera_subtitle.py` — 51 tests covering camera planner behaviors (fast_follow, dramatic_push, slow_reveal, none, subtitle_safe invariant, zoom/follow strengths, reason strings, crash safety), subtitle planner (per-mode defaults, beat_aware/emotion_aware overrides, reason strings, crash safety), schema expansion (new fields on both plan types, to_dict completeness), AI Director integration (expanded plans in output, planner crash fallbacks via monkeypatch on `ai_director` module namespace), ai_modes Phase 5 fields, and Phase 1–4 regression guards

**Phase 5 design constraints preserved:**
- No changes to `motion_crop.py` or `subtitle_engine.py` — plans are metadata only
- No camera/subtitle behavior forced into actual render output
- All camera/subtitle data is observation/planning metadata
- All prior Phase 1–4 tests pass without modification (332 → 383 total)

**Not yet implemented:**
- Applying `zoom_strength` to FFmpeg `motion_crop` parameters
- Applying `emphasis_style`/`density` to subtitle engine rendering
- UI controls exposing camera/subtitle intelligence settings
- Memory-context-informed camera/subtitle overrides (RAG feedback loop)

**Known limitations:**
- Camera and subtitle plans are planning hints only; render output is identical to pre-Phase-5
- `motion_energy` field is reserved but not yet populated

---

### 2026-05-08 — AI Director Phase 4: Beat + Emotion Pacing Foundation

**Implemented:**
- `beat_analyzer.py` upgraded — adds `energy` dict (`mean`, `peak`, `curve` ≤64 points) to all return paths; handles `None` audio_path with `"no_audio_path"` warning; full return shape guaranteed regardless of librosa availability
- `emotion_analyzer.py` (new) — rule-based keyword matching across 5 emotion categories (`urgency`, `surprise`, `curiosity`, `excitement`, `warning`); `analyze_text_emotion(text)` for single strings; `analyze_pacing_emotion(chunks)` for transcript-level aggregation; returns `{dominant, score, signals, warnings}`; no external deps; never raises
- `AIPacingPlan` dataclass (new, `edit_plan_schema.py`) — `beat_available`, `bpm`, `beat_count`, `energy_level`, `pacing_style`, `emotion`, `emotion_score`, `suggested_cut_style`, `warnings`; `to_dict()` is compact (no beat arrays, no energy curve)
- `AIEditPlan.pacing` field added — default `AIPacingPlan()` (safe for all existing code and tests)
- `ai_modes.py` upgraded — each mode now has `pacing_style`, `prefer_beat_sync`, `emotion_bias` (viral_tiktok=fast/True/curiosity, podcast_shorts=medium/False/clarity, storytelling=slow_build/False/curiosity, clean_subtitle=stable/False/neutral)
- `ai_director.py` upgraded — `_build_pacing_plan()` runs emotion analysis on transcript chunks; attempts beat analysis if `audio_path`/`source_path`/`video_path` in context; `_suggest_cut_style()` maps BPM→fast_cut/medium_cut/slow_cut or falls back to `pacing_style`; pacing warnings include `"beat_analysis_unavailable"` when no path provided
- `render_pipeline.py` — `source_path` added to `_ai_context` dict (one line, no behavior change)

**Tests added:**
- `backend/tests/test_ai_director_phase4_pacing.py` — 45 tests covering beat analyzer safety, emotion detection, pacing plan schema, mode config, AI Director integration, cut style logic, safety/regression guards

**Phase 4 design constraints preserved:**
- Beat analysis is observation-only; no FFmpeg command changes
- `analyze_beats()` never called at import time
- All pacing data is plan metadata only; existing render output unchanged
- All prior Phase 1–3 tests pass without modification (332 total)

**Not yet implemented:**
- Actual beat-synced cut timestamps in render commands
- Beat-synced zoom/pulse rendering effects
- Emotion-driven camera behavior
- Subtitle emphasis by beat
- UI controls for pacing/beat settings
- Librosa energy used to weight clip selection (Phase 5 candidate)

**Known limitations:**
- Beat quality depends on optional librosa — degrades to `beat_available=False` when absent
- Emotion detection is keyword-only; no ML models
- `pacing_style` influences cut style label only, not actual cuts yet

---

### 2026-05-08 — AI Director Phase 3: Persistent Learning Memory

**Implemented:**
- `SQLiteMemoryStore` (`rag/sqlite_store.py`) — stdlib `sqlite3` only, no ORM; auto-creates `ai_memory.db` under `APP_DATA_DIR` (packaging-safe, same dir as `app.db`); tables: `render_memories`, `embeddings`; methods: `initialize()`, `add_memory()`, `search_memories()`, `count()`, `load_vectors()`; all methods return safe defaults on any failure
- `write_render_memory()` (`rag/memory_writer.py`) — summarizes render result JSON into compact human-readable text; embeds if sentence-transformers available; persists to SQLite; falls back to text-only write if embeddings unavailable; never raises; never blocks rendering
- `LocalMemoryStore` upgraded (`rag/memory_store.py`) — integrates `SQLiteMemoryStore`; `initialize_with_sqlite()` attaches persistence + hydrates in-memory vector store from stored vectors; `add_render_memory()` writes to both SQLite and in-memory; `search_recent()` returns recent memories as text-only fallback (score=0.5)
- `initialize_memory_system(db_path=None)` factory — creates and hydrates a `LocalMemoryStore` in one call; always returns usable store
- `retrieve_ai_context()` upgraded (`rag/retriever.py`) — text-only fallback path: when embeddings unavailable but store has SQLite records, returns recent memories with `"text_only_fallback"` warning instead of empty; behavior unchanged when `memory_store=None` (preserves Phase 2 test compatibility)
- Render pipeline integration (`render_pipeline.py`) — after `upsert_job()`, calls `write_render_memory()` when `ai_director_enabled=True` or a plan was created; wrapped in bare `try/except`; zero impact on render result or job state

**Tests added:**
- `backend/tests/test_ai_director_phase3_memory.py` — 37 tests covering SQLite CRUD, persist/reload, vector round-trip, memory writer, text summary, retriever contract, AI Director end-to-end, safety guarantees, Phase 1/2 regression guard

**Persistence design:**
- DB path: `APP_DATA_DIR / "ai_memory.db"` (resolves to `%APPDATA%\RenderVideoTool\data\ai_memory.db` in packaged mode; `<project>/data/ai_memory.db` in dev)
- Memories stored without vectors still counted and returned via `search_recent()`
- Memories with vectors loaded on `initialize_with_sqlite()` for semantic search in next session
- No ORM, no migration system — only `CREATE TABLE IF NOT EXISTS`

**Not stored:**
- Raw filesystem paths, usernames, proxy credentials, API keys
- Full FFmpeg tracebacks (failure memories store compact summary only)

**Not yet implemented:**
- Beat-aware editing
- Emotion/story pacing
- Camera planner
- Subtitle planner
- UI AI memory controls
- Distributed/cloud vector DB

**Known limitations:**
- Retrieval quality depends on optional sentence-transformers
- Memory score influence intentionally capped at +5
- No cross-device sync
- Session hydration loads ≤500 most-recent vectors (prevents RAM growth)

---

### 2026-05-08 — AI Director Phase 2: Semantic Hook + Local RAG Memory

**Implemented:**
- `RenderMemory` / `MemorySearchResult` dataclasses (`rag/memory_schema.py`) — plain Python, no heavy deps
- `LocalMemoryStore` (`rag/memory_store.py`) — session-scoped in-memory store; `add_render_memory()` / `search_similar()` / `count()`; silently degrades when sentence-transformers absent
- `retrieve_ai_context()` (`rag/retriever.py`) — stable `{enabled, available, results, warnings}` contract; never raises; handles missing deps, missing store, empty store, and search errors independently
- `AIEditPlan.memory_context` field added (`edit_plan_schema.py`); `to_dict()` includes it
- `select_ai_segments()` extended with `memory_context` param (`clip_selector.py`); `_apply_memory_bonus()` adds up to +5 score to top segment when RAG hits score > 0.7; annotates reason with `rag_match`
- `create_ai_edit_plan()` RAG integration (`ai_director.py`): when `ai_use_rag_memory=True`, builds query from mode/market/duration/first-chunk text, calls retriever, attaches result to plan; errors append `rag:` warning prefix and do not crash the plan
- `_build_rag_query()` helper constructs a concise retrieval query for the memory store

**Tests added:**
- `backend/tests/test_ai_director_phase2_rag.py` — 25 tests covering schema, store, retriever contract, plan field, clip bonus, and end-to-end director RAG; all library-optional (pass without sentence-transformers / faiss)

**Constraints preserved:**
- `ai_use_rag_memory=False` default → `memory_context={}` on plan, zero regression risk
- All Phase 1 test_ai_director_phase1.py (24 tests) still pass without modification
- No SQLite persistence in Phase 2 — memory is session-scoped only

**Not yet implemented:**
- Persistent cross-session memory (SQLite / file-based)
- Market-specific retrieval weighting
- Auto-storage of completed renders into memory store
- Beat-aware editing, emotion/story pacing, render segment override

---

### 2026-05-08 — AI Director Phase 1

**Implemented:**
- `AIEditPlan` schema (`edit_plan_schema.py`) — dataclass, no heavy deps, `to_dict()` included
- Transcript normalization (`transcript_analyzer.py`) — accepts list[dict], list[obj], SRT string, plain text; returns [] on any failure
- Silence scoring (`silence_analyzer.py`) — gap-ratio penalty from transcript timing only; no FFmpeg
- Hook scoring (`hook_analyzer.py`) — rule-based always; optional 40% semantic upgrade via sentence-transformers (lazy-loaded)
- Clip selection (`clip_selector.py`) — window scoring with hook + density + duration fit + silence penalty; deduplicates overlapping windows; scene fallback
- AI mode configs (`ai_modes.py`) — `viral_tiktok`, `podcast_shorts`, `storytelling`, `clean_subtitle`
- AI Director orchestrator (`ai_director.py`) — `create_ai_edit_plan(request, context)`: returns `None` on disabled/failure, never raises
- `RenderRequest` AI fields — `ai_director_enabled=False` (all defaults preserve old behavior)
- Pipeline integration — optional call in `render_pipeline.py` after transcription; plan attached to `_result_payload["ai_director"]`; old pipeline runs unchanged when disabled

**Tests added:**
- `backend/tests/test_ai_director_phase1.py` — 24 tests; no GPU, no API keys, no video rendering

**Not yet implemented in Phase 1:**
- RAG memory retrieval (infrastructure exists in `rag/`)
- Beat-aware editing (librosa available but not connected)
- Emotion/story pacing analysis
- Aggressive render segment override (plan is observation-only)
- Semantic similarity across render history
- Market-specific clip preference learning

### 2026-05-08 — P0 Render Foundation Fixes

**Fixed:**
- 16:9 render dimension branch: `resolve_target_dimensions("16:9")` now returns `(1920, 1080)`. The original `else` fallback producing 1080×1440 has been replaced by an explicit `elif "16:9"` branch, extracted into the public helper `resolve_target_dimensions()` in `render_engine.py`.
- `motion_crop._codec_flags()` CPU paths: libx264 and libx265 now include `-maxrate 20M -bufsize 40M` via delegation to the unified `encoder_helpers.codec_extra_flags()`. NVENC path intentionally keeps unconstrained VBR (pipe-latency constraint).
- Body subject crop center formula: `_subject_to_crop_center()` body branch now uses `cy = y + h * 0.50` (mid-body). Face branch retains `cy = y + h * 0.34`.

**Also fixed in same patch (P0-P1 encoder unification):**
- 12 duplicated encoder helpers consolidated into `app/services/encoder_helpers.py`. Both `render_engine.py` and `motion_crop.py` now import from this single source of truth.
- `ffprobe_video_info()` in `motion_crop.py` now wraps `render_engine.probe_video_metadata()` — no uncached subprocess.
- `has_audio_stream()` in `motion_crop.py` now wraps `render_engine._has_audio_stream()`.

**Tests added:**
- `backend/tests/test_render_audit_p0_fixes.py` — 18 focused regression tests (no FFmpeg, no GPU)
- `backend/tests/test_render_guards.py` — dimension selector unit + integration tests
- `backend/tests/test_motion_crop_guards.py` — codec flags + body center guard tests
- `backend/tests/test_probe_unification.py` — probe consolidation guard

**Items intentionally deferred:**
- Smoke test (real render end-to-end): still P0 priority, not yet added.
- `_run_with_retry` stderr capture in `subtitle_engine.py`: P0, deferred.
- BGM filter duplication in `render_part()`: P3, deferred.
- Stall detection in progress timer: P2, deferred.

---

## A. Executive Summary

**Overall render system rating: 6.5 / 10**

The render system is architecturally sound and shows genuine production thinking: NVENC semaphore design, probe caching, retry logic, structured output validation with blackdetect, a progress subsystem with heartbeat threading, and market-aware viral scoring. However, three years of accretion have left a split-module duplication problem that has **already caused a real codec flag divergence** between `render_engine.py` and `motion_crop.py`, a silent 16:9 dimension bug, a body-crop formula that was never finished, and zero automated tests.

### Top 5 Risks

| # | Risk | Severity | Status |
|---|------|----------|--------|
| 1 | `motion_crop._codec_flags()` missing `-maxrate 20M -bufsize 40M` → unbounded bitrate when motion-aware crop is active | HIGH | **Fixed 2026-05-08** — CPU paths delegate to `encoder_helpers.codec_extra_flags()` |
| 2 | `render_part()` aspect_ratio `"16:9"` falls to `else` branch → 1080×1440 portrait output instead of 1920×1080 landscape | HIGH | **Fixed 2026-05-08** — explicit `elif "16:9"` branch in `resolve_target_dimensions()` |
| 3 | Face vs body crop center formula identical (`cy = y + h * 0.34`) for both branches in `_subject_to_crop_center()` — body subjects framed wrong | MEDIUM | **Fixed 2026-05-08** — body branch now `cy = y + h * 0.50` |
| 4 | Zero test suite — every regression is invisible, no smoke test for the entire pipeline | MEDIUM | **Partial** — focused regression tests added; smoke test (real render) still missing |
| 5 | `_run_with_retry()` in `subtitle_engine.py` does not capture stderr → FFmpeg errors during audio extraction are silently discarded | MEDIUM | Open |

### Top 5 Upgrade Priorities

1. ~~**P0 — Fix 16:9 dimension bug**~~ — **Done 2026-05-08.** `resolve_target_dimensions()` in `render_engine.py` now handles all four ratios explicitly.
2. ~~**P0 — Fix `motion_crop._codec_flags()` divergence**~~ — **Done 2026-05-08.** CPU paths unified through `encoder_helpers.codec_extra_flags()`.
3. ~~**P0 — Fix body crop center formula**~~ — **Done 2026-05-08.** Body branch uses `h * 0.50` in `_subject_to_crop_center()`.
4. ~~**P1 — Consolidate duplicate encoder helpers**~~ — **Done 2026-05-08.** `app/services/encoder_helpers.py` is the single source; both `render_engine.py` and `motion_crop.py` import from it.
5. **P0 — Add smoke test suite** — Still open. 10 s reference clip: cut → subtitle → render → validate dimensions + duration. Focused unit regression tests added, but end-to-end smoke test not yet written.

---

## B. Feature Health Matrix

| Feature | Status | Evidence | Main Issue | Upgrade | Priority |
|---------|--------|----------|------------|---------|----------|
| Pipeline Orchestration | Acceptable | `render_pipeline.py:872–1718` | `_process_one_part` closure is ~400 lines inside `run_render_pipeline` | Extract to top-level `_render_one_part(ctx)` | P2 |
| FFmpeg Encode (`render_part`) | Good | `render_engine.py` | **Fixed 2026-05-08** — `resolve_target_dimensions()` handles all aspect ratios correctly | — | Done |
| FFmpeg Encode (motion crop path) | Good | `motion_crop.py` | **Fixed 2026-05-08** — CPU codec flags unified via `encoder_helpers.codec_extra_flags()` | — | Done |
| Codec / GPU Detection | Good | `app/services/encoder_helpers.py` | **Fixed 2026-05-08** — 12 helpers extracted and unified; both files import from single source | — | Done |
| Output Validation | Good | `render_pipeline.py:591–823` | Duration tolerance 15% is generous for clips < 15s | Tighten for short clips | P2 |
| Frame Extraction / Preview | Acceptable | `render.py:184–296`, `render_engine.py:45–117`, `motion_crop.py:244–280` | 3 separate probe implementations; `motion_crop.ffprobe_video_info()` not cached | Unify to single cached `probe_video_metadata()` | P1 |
| Motion Crop / Subject Track | Acceptable | `motion_crop.py` | **Fixed 2026-05-08** — body `cy = h*0.50`; face retains `h*0.34` | — | Done |
| Subtitle Transcription | Good | `subtitle_engine.py:263–`, `render_pipeline.py:1515–1597` | One-time full transcription with heartbeat thread; correct design | — | — |
| SRT Slicing / ASS Conversion | Acceptable | `subtitle_engine.py:147–196` | `apply_playback_speed=False` is intentional; subtitles burned before `setpts` | Document explicitly | P3 |
| Voice / TTS Mix | Needs Inspection | `tts_service.py`, `audio_mix_service.py` | Files outside review scope; timeout and failure visibility unclear | Separate targeted review | P1 |
| Viral Scoring | Acceptable | `viral_scoring.py:1–743`, `render_pipeline.py:52–134` | Missing score defaults to 50 — masks real zero-score content | Differentiate absent vs neutral | P2 |
| Output Ranking | Acceptable | `render_pipeline.py:184–236` | `is_best_clip` init to `False`; `continuity_score` in `ranking_components` but weight=0 | Confirm best-clip pass runs | P1 |
| Render Queue / Progress | Acceptable | `render_pipeline.py:316–361` | No stall detection; parks at 85% when duration unknown | Add wall-clock stall threshold | P2 |
| Frontend Render Payload | Acceptable | `schemas.py`, `render-ui.js` | `retry_count` unbounded; `whisper_model` resolves silently | Add schema bounds; expose in UI | P2 |
| Test Coverage | **Partial** | `backend/tests/` (9 test files, 200+ tests) | Focused unit tests exist; end-to-end smoke test still missing | Add smoke test | P0 |

---

## C. Deep Findings

### 1. Render Pipeline Architecture

**What exists:**
`run_render_pipeline()` at `render_pipeline.py:872` is a single function orchestrating: download → scene detect → segment build → subtitle → per-part FFmpeg render → ranking → finalization. Parts run in `ThreadPoolExecutor` with `JOB_SEMAPHORE` (default 2, env `MAX_RENDER_JOBS`) at line 248.

**What is good:**
- `_set_stage()` at line 954 keeps DB progress consistent on every state transition
- `_render_progress_timer()` at line 316 uses `stop_event.wait()` — wakes immediately on job completion, never drifts
- `resume_from_last` logic at line 1630 skips already-done parts
- `_emit_render_event()` at line 418 writes to 3 targets simultaneously: job log, app.log, error.log
- `_render_error_code()` at line 401 classifies failure patterns into typed codes (RN001–RN006, VOICE001)

**What is weak/risky:**
- `_process_one_part` is an inner closure of ~400 lines (lines 1618–2100+). Closures this large capture too many outer-scope variables (`effective_channel`, `job_id`, `output_dir`, `source`, all payload fields), making unit testing impossible and refactors unsafe.
- `_probe_video_duration()` at line 515 spawns a fresh `ffprobe` subprocess. The cached `probe_video_metadata()` from `render_engine.py` is never used here — redundant subprocess call.
- If `ensure_channel()` at line 905 raises (filesystem permission), the job never reaches `upsert_job()` — DB shows `STARTING` forever.
- No stall detection: if FFmpeg hangs silently, the progress timer increments to 99% and never fails the job.

**Evidence:**
```python
# render_pipeline.py:515–527 — redundant probe, ignoring render_engine cache
def _probe_video_duration(video_path: Path) -> int:
    cmd = [get_ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", ...]
    try:
        r = subprocess.run(cmd, ...)
        return max(0, int(float((r.stdout or "0").strip() or 0)))
    except Exception:
        return 0
```

**Recommended upgrade:**
- Extract `_process_one_part` to a module-level `_render_one_part(ctx: PartRenderContext)` dataclass
- Replace `_probe_video_duration()` calls with `probe_video_metadata(path)["duration"]`
- Add wall-clock stall timeout to progress timer

**Files affected:** `render_pipeline.py`, `render_engine.py`
**Risk: MEDIUM**

---

### 2. FFmpeg Render Quality

**What exists:**
`render_part()` at `render_engine.py:798` builds a VF chain:
`scale+crop → zoom → canvas pad → [denoise] → effect → cinematic color → sharpen → format=yuv420p → fade → ass subtitle → title drawtext → text layers → setpts/speed → fps`

**Critical bug — 16:9 aspect ratio:**
```python
# render_engine.py:839-844 (original — BUG)
if aspect_ratio == "1:1":
    target_w, target_h = 1080, 1080
elif aspect_ratio == "9:16":
    target_w, target_h = 1080, 1920
else:  # "3:4", "4:5" AND "16:9" fall here — BUG
    target_w, target_h = 1080, 1440
```
`"16:9"` is a valid schema value but produces 1080×1440 (portrait 3:4). Correct would be 1920×1080.

> **Status Update — Fixed 2026-05-08:** The inline if/elif block was replaced by `resolve_target_dimensions(aspect_ratio)` — a standalone helper with explicit branches for all four ratios. `render_part()` now calls `target_w, target_h = resolve_target_dimensions(aspect_ratio)`. Regression guard: `tests/test_render_audit_p0_fixes.py::TestAspectRatioDimensions`.

**What is good:**
- NVENC semaphore scoped with `with` at line 983 — releases before CPU fallback
- CPU fallback at lines 992–1028 cleanly reconstructs the full command
- `hqdn3d` denoiser gated on `veryslow/slower` only
- `_cinematic_color_filter()` and `_cinematic_sharpen_filter()` skip sources below 480p at lines 314–327
- BT.709 color metadata applied: `-colorspace`, `-color_primaries`, `-color_trc`
- `force_accurate_cut` at `cut_video():461` handles keyframe-boundary inaccuracy

**What is weak/risky:**
- BGM filter_complex build (lines 945–967) is copy-pasted verbatim for the CPU fallback path at lines 1001–1027. Any mixing logic change must be made in both places.
- `title_text` escaping at line 901 handles `\\`, `:`, `'` but not `%` or `{` — could corrupt `drawtext` filter on edge inputs.
- No `-shortest` guard on the video/BGM amix `duration=first` path when source has no audio.

**Files affected:** `render_engine.py`
**Risk: HIGH (16:9 bug), LOW–MEDIUM (others)**

---

### 3. Frame Extraction / Preview / Thumbnail

**Are there 2 separate frame extraction features? Yes — 3 probe functions and 2 blackdetect passes.**

#### Feature 1: Editor Preview Transcode
- **File:** `render.py:184–296` — `_probe_preview_profile()`, `_is_browser_safe_preview()`, `_ensure_h264_preview()`
- **Purpose:** Convert any source to browser-safe H.264 for the Chromium editor preview
- **Method:** Fresh ffprobe per call → transcode at `crf=28 veryfast` if needed
- **Cache:** Single `preview_h264.mp4` per session dir (existence check at line 242)
- **Status:** Correct and purpose-specific; keep as-is

#### Feature 2: Cached General Probe (shared service)
- **File:** `render_engine.py:45–117` — `probe_video_metadata()`
- **Purpose:** `{duration, fps, has_audio, has_video, width, height}` for all pipeline stages
- **Method:** One ffprobe JSON call, cached by `(abspath, mtime_ns, size_bytes)` at line 32
- **Status:** The authoritative implementation; should be the single source of truth

#### Feature 3: Motion Crop Direct Probe (should be eliminated)
- **File:** `motion_crop.py:244–280` — `ffprobe_video_info()`
- **Purpose:** Get `(width, height, fps)` for crop coordinate calculation
- **Method:** Direct `subprocess.run(ffprobe ...)`, **NOT cached**
- **Problem:** Duplicates `probe_video_metadata()` work; issues a new subprocess every call

#### Blackdetect — 2 separate passes (both intentional):
- **Source blackdetect:** `render_engine.detect_bad_first_frame():576` — scans clip start in source, returns seconds to skip
- **Output blackdetect:** `render_pipeline._assess_output_quality():735` — scans first 0.5s of rendered output for validation
- These serve different purposes and should both be kept.

#### `has_audio_stream` — three implementations:
| Location | Method | Cached? |
|----------|--------|---------|
| `subtitle_engine.py:246` | raw subprocess | No |
| `motion_crop.py:283` | raw subprocess | No |
| `render_engine.py:407` (`_has_audio_stream`) | wraps `probe_video_metadata()` | Yes |

#### Which to keep / refactor:
- `_ensure_h264_preview()` — **KEEP AS-IS** (different purpose: transcode not metadata)
- `probe_video_metadata()` — **KEEP AND EXPAND** as the shared service
- `ffprobe_video_info()` in motion_crop — **REFACTOR** to wrap `probe_video_metadata()`
- `has_audio_stream()` in subtitle_engine and motion_crop — **REPLACE** with `render_engine._has_audio_stream()`

#### Shared service proposal:
```python
# motion_crop.py — replace ffprobe_video_info() body:
from app.services.render_engine import probe_video_metadata

def ffprobe_video_info(video_path: str):
    meta = probe_video_metadata(video_path)
    fps = meta["fps"] if meta["fps"] > 0 else 30.0
    return meta["width"], meta["height"], fps
```
4-line change. Zero API contract change. Eliminates redundant subprocesses.

**UI/API impact:** None. `ffprobe_video_info()` is only called internally within `motion_crop.py`.

**Files affected:** `motion_crop.py`, `subtitle_engine.py`, `render_engine.py`
**Risk: MEDIUM**

---

### 4. Motion Crop / Auto Reframe

**What exists:**
`render_motion_aware_crop()` in `motion_crop.py` uses OpenCV Haar cascades for face/body detection at 16-frame intervals (`subject_detect_interval=16` at config line 40), with EMA smoothing and velocity-limited Gaussian temporal smoothing. Config in `MotionCropConfig` at line 27.

**Critical bug — body crop center formula:**
```python
# motion_crop.py:748-751 (original — BUG)
if subject_kind == "body":
    cy = y + h * 0.34     # BUG: same as face — should be 0.50 for mid-body
else:
    cy = y + h * 0.34     # face: upper bias (correct for forehead/nose focus)
```
Both branches were identical. A detected body was framed as if it were a face — crop centers on upper chest/shoulder instead of visual mid-body. Clearly an unfinished refactor.

> **Status Update — Fixed 2026-05-08:** Body branch now uses `cy = y + h * 0.50`. Face branch retains `cy = y + h * 0.34`. Regression guard: `tests/test_render_audit_p0_fixes.py::TestBodyCropCenterFormula`.

**Codec flag divergence:**
```python
# motion_crop.py:178-183 (original — MISSING maxrate/bufsize)
return ["-crf", str(video_crf), "-profile:v", "high", "-level:v", "5.1",
        "-tune", "film", "-x264-params", x264p]

# render_engine.py:251-257 — CORRECT
return ["-crf", ..., "-maxrate", "20M", "-bufsize", "40M",
        "-profile:v", "high", ...]
```
Same divergence existed for libx265 (motion_crop.py:162–169 vs render_engine.py:235–242).

> **Status Update — Fixed 2026-05-08:** Both the 12-function encoder helper duplication and the codec flag divergence were resolved by extracting all shared encoder logic into `app/services/encoder_helpers.py`. `motion_crop._codec_flags()` now delegates CPU paths to `encoder_helpers.codec_extra_flags()` which includes `-maxrate 20M -bufsize 40M` for libx264 and libx265. NVENC path in `motion_crop` intentionally keeps unconstrained VBR (raw-pipe latency constraint — see comment in `_codec_flags()`). Regression guard: `tests/test_render_audit_p0_fixes.py::TestMotionCropCodecFlags`.

**Duplicated encoder helpers (all 6 must be in sync):**
| Function | render_engine.py | motion_crop.py |
|----------|-----------------|----------------|
| `_ffmpeg_encoders_text()` | line 142 | line 91 |
| `_has_encoder()` | line 152 | line 101 |
| `_nvenc_runtime_ready()` | line 156 | line 105 |
| `_resolve_codec()` / `_resolve_encoder()` | line 200 | line 129 |
| `_map_preset_for_encoder()` | line 260 | line 142 |
| `_codec_extra_flags()` / `_codec_flags()` | line 218 | line 154 |
| `_reup_video_filters()` | line 295 | line 186 |
| `_reup_audio_filter()` | line 304 | line 194 |
| `_safe_filter_path()` | line 412 | line 203 |
| `_detect_windows_fontfile()` | line 416 | line 207 |
| `_detect_windows_fonts_dir()` | line 432 | line 219 |
| `_get_custom_fonts_dir()` | line 442 | line 227 |

**What is good:**
- Velocity limiter (`max_pan_speed_ratio=0.010`) prevents jitter at `_apply_velocity_limiter()`
- Gaussian temporal smoothing (`window=45` frames) gives cinematic panning
- Scene-cut detection resets tracking state at `scene_aware_tracking=True`
- `lost_subject_hold_frames=45` prevents snap-to-center on momentary face loss
- `motion_fallback=True` gracefully degrades to pixel-diff mode
- `render_part_smart()` at `render_engine.py:1114` catches all exceptions and falls back to standard `render_part()`
- NVENC semaphore pre-acquired at `render_engine.py:1077–1079` before passing to `render_motion_aware_crop` — no double-acquire risk

**What is weak/risky:**
- `ffprobe_video_info()` issues uncached subprocess
- Codec flags diverged (missing maxrate/bufsize)
- `subject_padding=0.55` not exposed in schema; users cannot control zoom level

**Files affected:** `motion_crop.py`, `render_engine.py`
**Risk: HIGH (codec flags, body formula)**

---

### 5. Subtitle Feature

**What exists:**
Full pipeline at `render_pipeline.py:1515–1597`:
Whisper transcription (full video once) → `slice_srt_by_time()` per part → optional translation → optional hook text injection → `srt_to_ass_bounce()` or `srt_to_ass_karaoke()` → burn via `ass` FFmpeg filter.

**What is good:**
- Transcription is done **once** on the full source, then sliced per part — correct and efficient
- Heartbeat thread at line 1539 emits progress every 12s during Whisper — prevents UI stall
- `_MODEL_TRANSCRIBE_LOCKS` at `subtitle_engine.py:16` serializes concurrent Whisper calls per model — GPU-safe
- `slice_srt_by_time()` at line 147 correctly handles overlap-clipping and zero-rebasing
- `apply_playback_speed=False` at `render_pipeline.py:1750` is **correct by design**: subtitles are burned into pixels before `setpts` runs, so they automatically ride the frame through the speed change

**What is weak/risky:**
- `_run_with_retry()` at `subtitle_engine.py:211` uses bare `subprocess.run(command, check=True)` with no `capture_output`. FFmpeg errors during audio extraction are silently discarded.
- If the full SRT write fails (disk full, permissions), `full_srt_available` becomes `False` and all parts silently render without subtitles — only a WARNING is emitted.
- `_apply_subtitle_edits_to_srt()` at pipeline line 254 matches blocks by index + 0.5s timestamp tolerance. After translation, block indices can shift and edits apply to wrong blocks.
- Karaoke fallback to bounce when segment-level SRT is detected is silent — no log, no UI warning.

**Evidence:**
```python
# subtitle_engine.py:211-220 — stderr silently discarded on failure
def _run_with_retry(command: list[str], retries: int = 2, wait_sec: float = 0.8):
    attempt = 0
    while True:
        attempt += 1
        try:
            return subprocess.run(command, check=True)  # no capture_output!
        except Exception:
            if attempt > retries:
                raise
            time.sleep(wait_sec * attempt)
```

**Files affected:** `subtitle_engine.py`, `render_pipeline.py`
**Risk: MEDIUM**

---

### 6. Voice / Audio Feature

**Evidence available from imports only:**
```python
# render_pipeline.py:35-36
from app.services.tts_service import generate_narration_mp3
from app.services.audio_mix_service import mix_narration_audio
```
`voice_enabled`, `voice_language`, `voice_gender`, `voice_source` are in the schema.
`voice_source: "subtitle" | "translated_subtitle" | "manual"` routes to different narration text.

**Needs Inspection:** Full behavior of timeout, per-part failure isolation, audio sync, and error visibility requires reading `tts_service.py` and `audio_mix_service.py`. These were not in the review scope.

**Risk: UNKNOWN — P1 for separate targeted review**

---

### 7. Output Ranking / Market Viral

**What exists:**
Two-layer scoring:
1. `viral_scoring.score_part_for_market()` — market-specific component scores
2. `_compute_output_ranking_entry()` at `render_pipeline.py:184` — 6-component weighted combine

```python
# render_pipeline.py:197-204
raw_score = (
    segment_viral_score * 0.35
    + hook_score * 0.20
    + retention_score * 0.20
    + speech_density_score * 0.10
    + market_score * 0.10
    + duration_fit_score * 0.05
)
```

**What is good:**
- Ranking weights are explicit and documented
- `_output_ranking_reason()` at line 154 generates human-readable explanation strings
- `_first_score()` at line 147 has multi-name alias fallback for legacy field names
- `resolve_combined_score_weights()` at line 52 always normalizes to sum=1.0

**What is weak/risky:**
- `_score_component()` at line 137 returns `default=50.0` when a score is `None`. A part with **no** hook score (genuinely 0) is treated identically to a part with a **neutral** score (50). Failed scoring is indistinguishable from absent scoring.
- `is_best_clip: False` and `is_best_output: False` initialized at line 219 — never set to `True` inside this function. The auto_best_export pass must run after ranking. If the job fails before that pass, all clips report `is_best_clip=False`.
- `continuity_score` appears in `ranking_components` at line 213 but has **weight 0** in the raw_score formula. It influences reason strings but not the score — misleading.
- Duration scoring Gaussian curves (US 70±18s, EU 95±25s, JP 50±15s) are hardcoded; no UI to adjust per campaign.

**Files affected:** `render_pipeline.py`, `viral_scoring.py`
**Risk: MEDIUM**

---

### 8. Render Queue / Progress / Logs

**What exists:**
Per-job DB progress via `upsert_job_part()`, background `_render_progress_timer` at `render_pipeline.py:316`, and `_emit_render_event()` writing structured JSON to 3 log destinations.

**Progress timer design:**
```python
# render_pipeline.py:338-343
while not stop_event.wait(timeout=_PROGRESS_TICK_SEC):   # 3.0s
    elapsed = time.monotonic() - encode_start
    if expected_duration > 0:
        progress = min(99, 70 + int(30 * elapsed / expected_duration))
    else:
        progress = 85  # parks here forever when duration unknown
```

**What is good:**
- `stop_event.wait()` pattern wakes immediately on completion — no polling lag
- Progress clamped at 99%; caller always writes authoritative 100% after success
- Log entries include `error_code`, `traceback`, `duration_ms`, `step` — machine-parseable
- `_render_active_count` at line 251 tracks active render count

**What is weak/risky:**
- No stall detection. If FFmpeg hangs, progress parks at 85% (unknown duration) or interpolates to 99% and stays there. Job never auto-fails.
- `_render_active_count` is maintained but never exposed via the API — UI cannot see queue depth.
- Error codes RN001–RN006 and VOICE001 have no user-facing documentation.
- Heartbeat during transcription ticks every 12s; during render the timer ticks every 3s — inconsistent granularity.

**Files affected:** `render_pipeline.py`
**Risk: MEDIUM**

---

### 9. Frontend Render Payload

**Confirmed consumed fields from `schemas.py` and `render_pipeline.py`:**

| Field | Consumed at | Notes |
|-------|------------|-------|
| `render_profile` | pipeline:487 | `fast/balanced/quality/best` |
| `video_preset` / `video_crf` | pipeline:500–509 | override profile defaults |
| `motion_aware_crop` / `reframe_mode` | render_part_smart | |
| `add_subtitle` / `subtitle_style` | pipeline:1501, 1744 | |
| `subtitle_viral_min_score` | pipeline:1492 | gates subtitle per part |
| `hook_apply_enabled` / `hook_applied_text` | pipeline:898–903 | market viral hook |
| `text_layers` | pipeline:1000 | validated at entry |
| `resume_from_last` | pipeline:1602 | skip done parts |
| `playback_speed` | render_engine:911 | clamped 0.5–1.5 |
| `reup_mode` / `reup_bgm_*` | render_engine:931 | |

**What is weak/risky:**
- `retry_count` at pipeline line 950 is clamped `max(0, min(5, int(payload.retry_count)))` but the schema has no declared bounds — client can send arbitrary values.
- `whisper_model` defaults to `"auto"` resolving silently per profile. Users never see which model is running.
- `part_order="viral"` + `subtitle_only_viral_high=True` can silently render low-ranked parts without subtitles — no UI warning.
- `render_output_subdir` required in channel mode is enforced at runtime (`RuntimeError` at pipeline line 906), not at request validation.
- `edit_session_id` bypass at `render.py:132–134` skips all source validation; stale session returns confusing error instead of clean 404.

**Files affected:** `schemas.py`, `render.py`, `render_pipeline.py`
**Risk: LOW–MEDIUM**

---

### 10. Tests / QA Coverage

**Existing tests:** Zero. The `tests/` directory does not exist.

**Critical missing regression cases:**

| Test | Guards |
|------|--------|
| `cut_video` duration tolerance | stream-copy vs re-encode fallback path |
| 16:9 aspect ratio output dimensions | silent wrong-dimension render |
| Motion crop fallback when no face/body | `motion_fallback=True` path |
| Subtitle slicing at `playback_speed=1.5` | burn-in timing correctness |
| NVENC semaphore release on encode failure | no GPU deadlock |
| Output validation rejects empty file | `RN001` code fires |
| Karaoke with segment-level SRT | silent fallback to bounce |
| BGM mix with silent source | `amix`/`shortest` edge case |
| 16:9 render post-fix regression | confirms fix |
| Resume from last skips done parts | `resume_from_last=True` |

---

## D. Frame Extraction Special Review

See Section C.3 above for full analysis.

**Summary:**

| | Feature 1 | Feature 2 | Feature 3 |
|---|-----------|-----------|-----------|
| **Name** | Editor Preview Transcode | Cached General Probe | Motion Crop Probe |
| **File** | `render.py:184` | `render_engine.py:45` | `motion_crop.py:244` |
| **Function** | `_ensure_h264_preview()` | `probe_video_metadata()` | `ffprobe_video_info()` |
| **Cached?** | Yes (file on disk) | Yes (in-process dict) | **No** |
| **Purpose** | Browser-safe preview | All metadata | Width/height/fps |
| **Action** | Keep as-is | Keep and expand | Refactor to wrap Feature 2 |

**Shared service:** `render_engine.probe_video_metadata()` — already exists, just needs to be imported by `motion_crop.py` and `subtitle_engine.py`.

---

## E. Recommended Upgrade Roadmap

### P0 — Bug / Risk Fixes

| Item | File | Location | Change |
|------|------|----------|--------|
| Fix 16:9 render dimensions | `render_engine.py` | 839–844 | Add `elif aspect_ratio == "16:9": target_w, target_h = 1920, 1080` |
| Add maxrate/bufsize to motion_crop codec flags | `motion_crop.py` | 154–183 | Mirror `render_engine._codec_extra_flags()` maxrate/bufsize for both libx264 and libx265 |
| Fix body crop center formula | `motion_crop.py` | 748–751 | Change body branch to `cy = y + h * 0.50` |
| Fix `_run_with_retry` stderr capture | `subtitle_engine.py` | 211–220 | Add `capture_output=True`, propagate stderr on raise |
| Add smoke test: cut → render → validate | new `tests/test_smoke.py` | — | 10s reference clip, assert correct dims, >10KB, non-zero duration |

### P1 — Output Quality

| Item | File | Action |
|------|------|--------|
| Replace `motion_crop.ffprobe_video_info()` | `motion_crop.py:244` | Wrap `probe_video_metadata()` |
| Replace `has_audio_stream()` duplicates | `motion_crop.py:283`, `subtitle_engine.py:246` | Import `_has_audio_stream` from `render_engine.py` |
| Consolidate 12 duplicate encoder helpers | `motion_crop.py:91–238` | Extract to `app/services/encoder_helpers.py` |
| Review Voice / TTS service | `tts_service.py`, `audio_mix_service.py` | Confirm timeout, per-part isolation, failure visibility |
| Confirm `is_best_clip` pass runs before final write | `render_pipeline.py` | Find auto_best_export pass; add assertion or log |
| Replace `_probe_video_duration()` in pipeline | `render_pipeline.py:515` | Use `probe_video_metadata()["duration"]` |

### P2 — Product UX

| Item | Action |
|------|--------|
| Expose active Whisper model in progress UI | Surface `tuned["whisper_model"]` in progress event |
| Add stall detection to progress timer | Wall-clock check: if elapsed > max(120, expected_duration × 10), fail the part |
| Warn when `part_order=viral` + `subtitle_only_viral_high` silences parts | Emit `subtitle_skipped_viral_gate` WARNING event |
| Show score breakdown in part card | `ranking_components` already in part record; just render in UI |
| Make `render_output_subdir` schema-validated in channel mode | Add Pydantic validator in `RenderRequest` |
| Add stall-suspected event at `progress=85` for unknown-duration jobs | Emit WARNING after 5 min at 85% |

### P3 — Performance / Scale

| Item | Action |
|------|--------|
| Reduce BGM filter duplication | Extract `_build_bgm_filter_complex()` helper; used in both GPU and CPU paths in `render_part()` |
| Cache subtitle slice by (start, end, speed) | Skip re-slicing when SRT slice already exists at same params |
| Profile Whisper on large sources | Evaluate `faster-whisper` or `whisper.cpp` for 2–4× speedup |
| Expose `subject_padding` via schema | Add `motion_crop_subject_padding: float = 0.55` to `RenderRequest` |

---

## F. Do Not Touch List

These systems are correctly designed and must not be changed unless a specific defect is confirmed:

1. **`probe_video_metadata()` + `_PROBE_CACHE`** — `render_engine.py:45–117` — Caching strategy is correct; do not rewrite
2. **`_run_ffmpeg_with_retry()`** — `render_engine.py:120–139` — Retry + stderr capture is clean; do not change signature
3. **`_render_progress_timer()`** — `render_pipeline.py:316–361` — `stop_event.wait()` pattern is correct; do not convert to `time.sleep()`
4. **`slice_srt_by_time()` with `apply_playback_speed=False`** — `render_pipeline.py:1750` — The burn-in-before-setpts design is intentional and correct; changing it will break subtitle sync
5. **`NVENC_SEMAPHORE` scoping** — `render_engine.py:24`, `render_part_smart:1077–1112` — Pre-acquire before `render_motion_aware_crop` is correct; do not add a second acquire inside motion_crop
6. **`_validate_render_output()` + `_assess_output_quality()`** — `render_pipeline.py:591–823` — Solid two-phase validation; do not collapse
7. **`_apply_subtitle_edits_to_srt()`** — `render_pipeline.py:254–313` — The 0.5s tolerance guard and silent-skip design is intentional defensive behavior

---

## G. Patch Prompts

### Patch Prompt 1 — Fix Frame Extraction Duplication

```
You are patching motion_crop.py and subtitle_engine.py to eliminate private ffprobe
subprocesses in favour of the shared cached probe in render_engine.py.

Context:
- motion_crop.py:244–280 defines ffprobe_video_info() — fresh subprocess, not cached
- motion_crop.py:283–292 defines has_audio_stream() — fresh subprocess, not cached
- subtitle_engine.py:246–260 defines has_audio_stream() — fresh subprocess, not cached
- render_engine.py:45–117 defines probe_video_metadata() — one subprocess, cached by
  (abspath, mtime_ns, size_bytes); render_engine._has_audio_stream() wraps it

Tasks:
1. In motion_crop.py, add at the top:
     from app.services.render_engine import probe_video_metadata, _has_audio_stream
2. Replace ffprobe_video_info() body (lines 244–280) with:
     def ffprobe_video_info(video_path: str):
         meta = probe_video_metadata(video_path)
         fps = meta["fps"] if meta["fps"] > 0 else 30.0
         return meta["width"], meta["height"], fps
3. Replace motion_crop.has_audio_stream() (lines 283–292) with:
     has_audio_stream = _has_audio_stream
4. In subtitle_engine.py, replace has_audio_stream() (lines 246–260) similarly:
     from app.services.render_engine import _has_audio_stream as has_audio_stream
5. Render a test clip with motion_aware_crop=True and confirm no double ffprobe
   subprocess appears in the debug log.

Do not modify render_engine.probe_video_metadata().
Do not change any function signatures visible outside these files.
```

---

### Patch Prompt 2 — Fix Render Output Validation

```
You are strengthening render output validation in render_pipeline.py and adding
stall detection to the progress timer.

Current problems:
- _validate_render_output() uses 15% duration tolerance for all clips — too loose for
  short clips (e.g., 10s clip allows ±1.5s error).
- _render_progress_timer() parks at 85% forever when expected_duration is unknown and
  never fails a stalled job.
- _assess_output_quality() computes score_penalty but never acts on it.

Tasks:
1. In _validate_render_output() at line 680:
   Replace: tolerance = max(1.0, expected_duration * 0.15)
   With:    tolerance = max(0.5, min(expected_duration * 0.15, 3.0))
   (tightens for short clips, caps at 3.0s for long clips)

2. In _render_progress_timer() at line 316, add a stall guard:
   After the loop starts, compute:
     stall_deadline = encode_start + max(120.0, (expected_duration or 60.0) * 10)
   Inside the while loop, check:
     if time.monotonic() > stall_deadline:
         try:
             upsert_job_part(..., status=JobPartStage.FAILED, ...,
                             message="Render stall detected: wall-clock timeout exceeded")
             _emit_render_event(..., event="render.stall_detected", level="WARNING", ...)
         except Exception:
             pass
         stop_event.set()
         break

3. In the _process_one_part caller of _assess_output_quality(), after receiving the
   quality_result dict, if quality_result["score_penalty"] > 20:
     log a WARNING via _emit_render_event with the warnings list

Do not change _validate_render_output() signature.
Do not remove any existing checks.
```

---

### Patch Prompt 3 — Fix Motion Crop Quality

```
You are fixing two bugs in motion_crop.py and adding the missing codec bitrate flags.

Bug 1 — Body crop center formula (line 748–751):
  Both face and body branches compute cy = y + h * 0.34.
  For a detected body subject, the crop should center at mid-body, not near the top.
  Fix:
    if subject_kind == "body":
        cy = y + h * 0.50    # mid-body center
    else:
        cy = y + h * 0.34    # face: slight upward bias for forehead

Bug 2 — Missing bitrate cap for libx265 (motion_crop.py:162–169):
  Current:
    return ["-crf", str(video_crf), "-tag:v", "hvc1", "-x265-params", x265p]
  Fix: add "-maxrate", "20M", "-bufsize", "40M" before "-tag:v":
    return ["-crf", str(video_crf), "-maxrate", "20M", "-bufsize", "40M",
            "-tag:v", "hvc1", "-x265-params", x265p]

Bug 3 — Missing bitrate cap for libx264 (motion_crop.py:178–183):
  Current:
    return ["-crf", str(video_crf), "-profile:v", "high", ...]
  Fix: add "-maxrate", "20M", "-bufsize", "40M":
    return ["-crf", str(video_crf), "-maxrate", "20M", "-bufsize", "40M",
            "-profile:v", "high", "-level:v", "5.1", "-tune", "film",
            "-x264-params", x264p]

After fixing, verify by rendering a high-motion clip with motion_aware_crop=True
and checking the output file size is consistent with standard render_part() output.
Do not change MotionCropConfig or any function visible outside motion_crop.py.
```

---

### Patch Prompt 4 — Fix Subtitle Robustness

```
You are fixing subtitle reliability issues in subtitle_engine.py and render_pipeline.py.

Fix 1 — Capture stderr in _run_with_retry (subtitle_engine.py:211–220):
  Current:
    return subprocess.run(command, check=True)
  Replace with:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
  On CalledProcessError, re-raise with context:
    except subprocess.CalledProcessError as exc:
        if attempt > retries:
            stderr_tail = (exc.stderr or "")[-1000:].strip()
            raise RuntimeError(
                f"FFmpeg failed (exit={exc.returncode})"
                + (f": {stderr_tail}" if stderr_tail else "")
            ) from exc

Fix 2 — Log karaoke→bounce fallback:
  In srt_to_ass_karaoke(), when it falls back to bounce because word-level timing
  is missing, add before the fallback return:
    logger.warning("srt_to_ass_karaoke: segment-level SRT detected; falling back to bounce style")

Fix 3 — Warn on subtitle_edits misalignment after translation (render_pipeline.py):
  After translate_srt_file() succeeds (around line 1812) and _sub_edits is non-empty:
    if _sub_edits:
        _emit_render_event(..., event="subtitle_edits_may_misalign", level="WARNING",
            message="subtitle_edits applied after translation; index alignment is best-effort")

Do not change the public signatures of srt_to_ass_bounce() or srt_to_ass_karaoke().
Do not alter the apply_playback_speed=False design — it is intentional.
```

---

### Patch Prompt 5 — Improve Render Queue / Progress UI

```
You are adding stall visibility and queue depth to the render progress system.

Backend changes (render_pipeline.py):

1. Add a new GET endpoint to render.py at /api/render/queue-status:
   @router.get("/queue-status")
   def queue_status():
       from app.orchestration.render_pipeline import _render_active_count, _JOB_SEM_VALUE
       with _render_active_lock:
           active = _render_active_count[0]
       return {"active_renders": active, "max_renders": _JOB_SEM_VALUE}

2. In _render_progress_timer (render_pipeline.py:316), when expected_duration <= 0
   and time.monotonic() - encode_start > 300:
     emit a WARNING event with event="render.stall_suspected":
       _emit_render_event(..., event="render.stall_suspected", level="WARNING",
           message=f"Render has been running {elapsed:.0f}s with unknown duration")
   Emit at most once per job (use a local flag inside the timer).

3. After _assess_output_quality() returns, if quality_warnings is non-empty, include
   them in the final upsert_job_part() call so the UI can display them per-part.

Frontend changes (render-ui.js or render-engine.js):

4. Poll /api/render/queue-status every 10s when an active render is detected.
   Display "X of Y render slots active" in the status bar.
   Stop polling when no renders are active.

5. When a part record includes quality_warnings, show a yellow badge "⚠ Quality" on
   the part card with a tooltip listing the warning strings.

Do not add polling when no render job is active.
Do not change the _render_progress_timer stop_event pattern.
```

---

# H. AI Architecture Direction

## Current AI Capabilities

The current render system already contains multiple AI-assisted or AI-like systems:

### Existing AI Features
- Whisper subtitle transcription
- Subtitle translation pipeline
- Motion-aware crop
- Subject tracking
- EMA camera smoothing
- Scene-aware tracking reset
- Viral scoring
- Market-aware subtitle tone
- Hook scoring (heuristic-based)
- Ranking system
- Multi-market presets
- Smart fallback handling

### Current Strengths
- Strong render backbone
- Strong subtitle rendering pipeline
- Structured render events/logging
- Render validation system
- Motion smoothing stability
- Multi-market architecture
- Queue and progress infrastructure
- Electron-compatible architecture
- Offline-first rendering flow

---

## AI Phase Status

### AI Director Phase 1 — 2026-05-08

**Implemented:**
- AI Edit Plan schema (`AIClipPlan`, `AISubtitlePlan`, `AICameraPlan`, `AIEditPlan`)
- Transcript normalization — multi-format, fallback-safe
- Silence scoring from transcript gap analysis
- Rule-based hook scoring + optional semantic scoring (sentence-transformers, lazy-loaded)
- Clip selection foundation — hook + density + duration fit + silence penalty
- AI mode configs: `viral_tiktok`, `podcast_shorts`, `storytelling`, `clean_subtitle`
- Render pipeline integration — safe attachment to `result_json`, observation-only
- 24 unit tests — no GPU, no API keys

**Not yet implemented:**
- RAG memory retrieval and cross-render learning
- Beat-aware editing (librosa pipe)
- Emotion pacing and story structure analysis
- Aggressive render override (plan influences but does not yet replace segment selection)
- Market-specific learning

**Known limitations in Phase 1:**
- Clip selector samples transcript at `len(chunks) // 12` intervals — may miss short high-value windows in very long transcripts
- Silence penalty uses transcript gap data only — does not detect actual audio silence not reflected in transcript timing
- Semantic hook scoring requires sentence-transformers; unavailable in default packaging
- AI plan is attached to `result_json` for logging but does not yet drive render segment ordering

---

## Missing AI Capabilities

The system currently lacks higher-level semantic and planning intelligence.

### Missing Semantic AI
- Semantic hook understanding
- Context-aware clip understanding
- Emotion understanding
- Semantic pacing analysis

### Missing Editing Intelligence
- AI edit planning
- Story structure analysis
- Narrative pacing
- Dynamic camera behavior planning
- Dynamic subtitle emphasis

### Missing Learning Systems
- RAG memory
- Similar successful output retrieval
- Render memory persistence
- Cross-render learning
- Market-specific learning

### Missing Audio Intelligence
- Beat-aware editing
- BPM-aware pacing
- Music-aware transitions
- Emotion-aware rhythm planning

---

## AI Upgrade Principles

The AI system must follow these architectural rules:

### Principle 1 — AI Creates Plans
AI modules generate:
- edit plans
- recommendations
- scores
- behaviors

AI modules do NOT directly render video.

### Principle 2 — Existing Pipeline Remains Executor
The existing render pipeline remains:
- authoritative
- stable
- fallback-safe

AI layers must remain optional.

### Principle 3 — Local AI First
Prefer:
- local inference
- offline AI
- free/open-source AI

Avoid:
- mandatory cloud APIs
- mandatory subscriptions
- cloud-dependent rendering

### Principle 4 — Incremental Upgrades
AI features must:
- integrate gradually
- preserve compatibility
- avoid rewrite-style refactors

### Principle 5 — Fallback Safety
If any AI system fails:
- render pipeline must continue
- existing render behavior must remain functional

---

# I. AI Dependency Strategy

## Approved Optional AI Libraries

| Library | Purpose |
|---|---|
| faster-whisper | Subtitle transcription |
| sentence-transformers | Semantic understanding |
| faiss-cpu | RAG memory retrieval |
| librosa | Beat/BPM analysis |
| mediapipe | Face/body tracking |

---

## Dependency Rules

### All AI Dependencies Must Be Optional

Rules:
- no hard imports at startup
- no mandatory GPU
- no mandatory CUDA
- no mandatory API keys
- no cloud lock-in

### Required Import Pattern

Correct:

```python
try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

*End of audit. No code was modified. All file:line references are based on direct reads performed during this session.*

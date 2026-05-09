# Render Audit Ledger — AI Productization Phases

This document is the authoritative architecture ledger and safety contract for the
AI-assisted render pipeline. It records what each phase introduced and what
remains intentionally blocked.

---

## AI Productization Phase 35 — AI Clip Candidate Discovery Foundation

### Implemented

- AI clip candidate discovery schema (`AIClipCandidate`, `AIClipCandidatePack`)
- Deterministic clip discovery engine (`clip_candidate_engine.py`)
- Candidate safety validation (`clip_candidate_safety.py`)
- Retention/story-aware candidate ranking
- Creator-style-aware clip discovery
- Discovery-only orchestration integration (AI Director, Render Influence)
- Compact metadata pass-through in `AIEditPlan.clip_candidate_discovery`
- Optional request fields with bounded validation (`ai_clip_discovery_enabled`,
  `ai_clip_min_duration_sec`, `ai_clip_max_duration_sec`, `ai_clip_candidate_limit`)

### Discovery heuristics

| Heuristic | Source metadata |
|---|---|
| Hook detection | Story segment type `hook`, position < 20% |
| Climax/payoff detection | Story segment types `climax`, `payoff` |
| Pacing stability | BPM, energy level from Phase 4 pacing plan |
| Subtitle overload avoidance | Subtitle execution density metadata (Phase 17) |
| Silence-gap avoidance | Retention risk regions with category `silence_gap` (Phase 16) |
| Creator-style fit | Creator style adaptation confidence (Phase 23) |
| Retention probability | Overall retention score, risk region overlap penalty (Phase 16) |
| Safe duration enforcement | Per-request min/max duration bounds, clamped 5–180 / 10–300 sec |

### Discovery sources integrated

- Story intelligence — Phase 12
- Retention intelligence — Phase 16
- Timing optimization metadata — Phase 19
- Story optimization metadata — Phase 20
- Creator style adaptation — Phase 23
- Execution simulations — Phase 26
- Timing apply metadata — Phase 32
- Subtitle optimization metadata — Phase 33
- Camera motion guidance — Phase 34

### Safety boundaries (still intentionally blocked)

- **Actual clip cutting** — never executed
- **Segment mutation** — selected_segments order and content never changed
- **playback_speed mutation** — never touched
- **Subtitle timing rewrite** — never touched
- **FFmpeg mutation** — never touched
- **Segment reorder** — never performed
- **Executor override** — never performed
- **Autonomous rendering** — never triggered
- **Validation bypass** — never attempted
- **Cloud AI / external API** — not required
- **GPU** — not required
- **Internet** — not required

### Allowed behaviors

- Identify strong candidate windows from AI metadata
- Rank candidates by weighted composite score (retention 30%, hook 25%,
  story 20%, pacing 15%, creator style 10%)
- Recommend best safe candidate via `recommended_candidate_id`
- Expose reasons and warnings per candidate
- Provide compact advisory metadata only

### Structured log events

| Event | Description |
|---|---|
| `ai_clip_candidate_discovery_enabled` | Discovery ran and found candidates |
| `ai_clip_candidate_created` | Candidates built successfully |
| `ai_clip_candidate_recommended` | Best candidate selected |
| `ai_clip_candidate_discovery_skipped` | Discovery disabled or no windows found |

### Phase compatibility

- All Phase 1–34 behavior preserved
- `ai_clip_discovery_enabled` defaults to `False` — old requests unaffected
- `AIEditPlan.clip_candidate_discovery` defaults to `{}` — backward compatible

---

## AI Productization Phase 36 — AI Clip Duration & Segment Selection Foundation

### Implemented

- AI clip segment selection schema (`AIClipSegmentPlan`, `AIClipSegmentSelection`)
- Deterministic clip segment selector (`clip_segment_selector.py`)
- Segment plan safety validation (`clip_segment_safety.py`)
- Duration-bound segment validation (min/max enforced per-request)
- Selected segment metadata with rank, score, source_scores, reasons
- Rejected candidate reporting with reason codes
- Planning-only orchestration integration (AI Director, Render Influence)
- Compact metadata pass-through in `AIEditPlan.clip_segment_selection`
- New request fields: `ai_clip_segment_selection_enabled`, `ai_clip_target_count`
  (shares `ai_clip_min_duration_sec`/`ai_clip_max_duration_sec` from Phase 35)

### Selection behavior

| Behavior | Detail |
|---|---|
| Primary source | Phase 35 `clip_candidate_discovery.candidates` |
| Fallback | `edit_plan.selected_segments` when no Phase 35 candidates |
| Score weighting | retention 30%, hook 25%, story 20%, pacing 15%, creator style 10% |
| Warning penalties | `subtitle_overload` −8 pts, `silence_gap` / `overlaps_retention_risk` −5 pts |
| Overlap detection | Rejects candidates overlapping > 50% of shorter window's duration |
| Target limit | `ai_clip_target_count` (1–20, default 3) |
| Duration bounds | Shared with Phase 35: `ai_clip_min_duration_sec` / `ai_clip_max_duration_sec` |
| Ordering | Deterministic: score desc, candidate_id asc as tiebreaker |

### Structured log events

| Event | Description |
|---|---|
| `ai_clip_segment_selection_enabled` | Selection ran and found candidates |
| `ai_clip_segment_selected` | A segment plan was selected |
| `ai_clip_segment_rejected` | A candidate was rejected (reason logged) |
| `ai_clip_segment_selection_skipped` | Selection disabled or no candidates |

### Safety boundaries (still intentionally blocked)

- **Actual clip cutting** — never executed
- **Render execution** — never triggered
- **playback_speed mutation** — never touched
- **Subtitle timing rewrite** — never touched
- **FFmpeg mutation** — never touched
- **Source segment reorder** — never performed
- **Executor override** — never performed
- **Validation bypass** — never attempted
- **Cloud AI / external API** — not required
- **GPU** — not required
- **Internet** — not required

### Phase compatibility

- All Phase 1–35 behavior preserved
- `ai_clip_segment_selection_enabled` defaults to `False` — old requests unaffected
- `AIEditPlan.clip_segment_selection` defaults to `{}` — backward compatible

---

## AI Productization Phase 37 — AI Multi-Clip Batch Planning Foundation

### Implemented

- AI clip batch plan schema (`AIClipBatchPlan`, `AIClipBatchPlanSet`)
- Deterministic multi-clip batch planner (`clip_batch_planner.py`)
- Batch plan safety validation (`clip_batch_safety.py`)
- Selected segments → batch render plans conversion
- Strategy assignment per selected segment (render/variant/subtitle/camera/timing)
- Safe planned payload override filtering (forbidden keys stripped automatically)
- Planning-only batch orchestration metadata
- Compact metadata pass-through in `AIEditPlan.clip_batch_planning`
- New request fields: `ai_clip_batch_planning_enabled`, `ai_clip_batch_limit`

### Planning behavior

| Behavior | Detail |
|---|---|
| Primary source | Phase 36 `clip_segment_selection.selected_segments` |
| Fallback | `edit_plan.selected_segments` when no Phase 36 segments |
| Batch limit | `ai_clip_batch_limit` (1–20, default 5) |
| Plan IDs | `batch_01`, `batch_02`, … deterministic |
| Rank | Sequential 1, 2, … per output order |
| Recommended plan IDs | Safe plans only, at most 3 |
| Mode | Always `planning_only` |

### Strategy assignment heuristics

| Strategy type | Assignment rule |
|---|---|
| `render_strategy` | `subtitle_clarity` if subtitle_overload warning; `creator_style_focused` if confidence > 0.75; `camera_dynamic_safe` if camera motion dynamic; `retention_focused` if retention/hook/story > 70; else `safe_default` |
| `variant_strategy` | `single_safe` for conservative policy; `selected_variant` if balanced + variant available; `multivariant_limited` if aggressive/experimental + multivariant available |
| `subtitle_strategy` | `reduced_density` if subtitle_overload warning; `optimized` if subtitle apply enabled; else `default` |
| `camera_strategy` | `motion_guided` if camera apply enabled; else `default` |
| `timing_strategy` | `retention_optimized` if timing apply enabled; else `default` |

### Allowed planned_payload_override keys

`subtitle_density`, `subtitle_emphasis`, `camera_behavior`, `pacing_style`,
`creator_style`, `visual_rhythm_mode`, `ai_mode`

### Forbidden planned_payload_override keys (auto-stripped)

`playback_speed`, `segment_start`, `segment_end`, `subtitle_timing`,
`ffmpeg_args`, `codec`, `bitrate`, `crf`, `validation_rules`,
`output_path`, `render_command`, `render_segments`, `segment_order`,
`queue_priority`, `job_id`

### Safety boundaries (still intentionally blocked)

- **Actual batch render execution** — never executed
- **Render job creation** — never performed
- **Queue mutation** — never performed
- **FFmpeg mutation** — never touched
- **playback_speed mutation** — never touched
- **Subtitle timing rewrite** — never touched
- **Source segment reorder** — never performed
- **Executor override** — never performed
- **Validation bypass** — never attempted
- **Cloud AI / external API** — not required
- **GPU** — not required
- **Internet** — not required

### Allowed behaviors

- Convert selected clip segments into batch render plans
- Assign render/subtitle/camera/timing/variant strategies
- Attach safe planned payload overrides
- Rank and recommend batch plans
- Expose compact planning-only metadata

### Structured log events

| Event | Description |
|---|---|
| `ai_clip_batch_planning_enabled` | Batch planning ran and produced plans |
| `ai_clip_batch_plan_created` | A plan was created |
| `ai_clip_batch_plan_recommended` | Recommended plan IDs selected |
| `ai_clip_batch_planning_skipped` | Planning disabled or no segments found |

### Phase compatibility

- All Phase 1–36 behavior preserved
- `ai_clip_batch_planning_enabled` defaults to `False` — old requests unaffected
- `AIEditPlan.clip_batch_planning` defaults to `{}` — backward compatible

---

## AI Productization Phase 38 — AI-Assisted Existing Feature Enhancement Integration

### Implemented

- Unified AI feature enhancement integration (`feature_enhancement_engine.py`)
- Feature enhancement schema (`AIFeatureEnhancement`, `AIFeatureEnhancementPack`)
- Enhancement safety validation (`feature_enhancement_safety.py`)
- Assistive-only AI orchestration across all existing render features
- Subtitle enhancement integration (subtitle_text_apply + subtitle_execution)
- Camera enhancement integration (camera_motion_apply + visual rhythm)
- Timing enhancement integration (timing_apply + silence/dead-air guidance)
- Clip selection enhancement integration (Phase 35/36 + story/retention intelligence)
- Creator style enhancement integration (style adaptation + market + exec recommendations)
- Variant enhancement integration (variant selection + simulation + batch plans)
- Output ranking enhancement integration (output ranking + retention/story scoring)
- Compact metadata pass-through in `AIEditPlan.feature_enhancement`

### Architecture direction

| Principle | Detail |
|---|---|
| AI role | Enhance existing features — never replace them |
| Render authority | Deterministic render engine always has final authority |
| Creator control | User intent preserved; AI improves quality, not autonomy |
| Mode | Always `assistive_only` |

### Enhancement integration sources

| Category | Primary sources |
|---|---|
| Subtitle | `subtitle_text_apply`, `subtitle_execution`, creator style tone |
| Camera | `camera_motion_apply`, `beat_visual_execution`, motion energy |
| Timing | `timing_apply`, retention risk regions (silence/dead-air) |
| Clip selection | `clip_segment_selection`, `clip_candidate_discovery`, story, retention |
| Creator style | `creator_style_adaptation`, `creator_style`, `execution_recommendations` |
| Variant | `variant_selection`, `execution_simulation`, `clip_batch_planning` |
| Output ranking | `output_ranking`, retention score, story score |

### Safety boundaries (still intentionally blocked)

- **Autonomous render takeover** — never executed
- **FFmpeg mutation** — never touched
- **playback_speed mutation** — never touched
- **Subtitle timing rewrite** — never touched
- **Unrestricted editing** — never performed
- **Queue mutation** — never performed
- **Executor override** — never performed
- **Autonomous publishing** — never triggered
- **Cloud AI / external API** — not required
- **GPU** — not required
- **Internet** — not required

### Allowed behaviors

- Enhance existing subtitle quality via AI metadata
- Improve camera framing guidance from AI motion analysis
- Reduce dead-air and silence gaps via timing intelligence
- Improve clip selection via story and retention signals
- Apply creator style adaptation to existing features
- Provide variant ranking and batch planning enhancement
- Expose assistive-only improvement metadata

### Structured log events

| Event | Description |
|---|---|
| `ai_feature_enhancement_created` | Enhancement pack built successfully |
| `ai_feature_enhancement_applied` | Enhancement categories active |
| `ai_feature_enhancement_skipped` | No AI metadata available |
| `ai_feature_enhancement_assistive_only` | Confirms assistive-only mode |

### Phase compatibility

- All Phase 1–37 behavior preserved
- `AIEditPlan.feature_enhancement` defaults to `{}` — backward compatible
- No new request fields — enhancement always runs when AI Director is enabled

---

## AI Productization Phase 39 — External Creator Knowledge Ingestion Foundation

### Implemented

- Local-first creator knowledge ingestion (`knowledge_ingestion.py`)
- Creator knowledge schema (`AICreatorKnowledge`, `AIKnowledgeRegistry`) — appended to Phase 15 schema
- Safe knowledge registry (`knowledge_registry.py`)
- Knowledge safety validation (`knowledge_safety.py`) — 13 forbidden keys auto-stripped
- Creator/market/subtitle/pacing/hook knowledge categories
- Deterministic retrieval-ready creator intelligence foundation
- Example knowledge files: `knowledge/creators/`, `markets/`, `subtitles/`, `pacing/`, `hooks/`
- Compact metadata pass-through in `AIEditPlan.creator_knowledge`

### Architecture direction

| Principle | Detail |
|---|---|
| Knowledge source | Local JSON files only — no internet, no scraping |
| Ingestion mode | Deterministic, file-based, fallback-safe |
| Registry | Indexed by category + creator_style; cached per base_path |
| Safety | Forbidden keys stripped; source_type validated against allowlist |
| Phase 15 compat | `ExternalKnowledgeItem`, `KnowledgeSearchResult` preserved unchanged |

### Knowledge folder structure

```
knowledge/
  creators/   viral_tiktok.json, podcast.json
  markets/    us_shortform.json
  subtitles/  compact_hooks.json
  pacing/     fast_hook.json
  hooks/      question_hooks.json
```

### Forbidden knowledge keys (auto-stripped)

`script`, `executable`, `command`, `subprocess`, `ffmpeg_args`, `render_command`,
`shell`, `powershell`, `batch_script`, `python_code`, `live_scrape_url`,
`auth_token`, `api_key`

### Safety boundaries (still intentionally blocked)

- **Live internet scraping** — never performed
- **Autonomous crawling** — never triggered
- **Cloud AI dependency** — not required
- **Model fine-tuning** — never executed
- **FFmpeg mutation** — never touched
- **playback_speed mutation** — never touched
- **Subtitle timing rewrite** — never touched
- **Executor override** — never performed
- **GPU** — not required
- **Internet** — not required

### Structured log events

| Event | Description |
|---|---|
| `ai_creator_knowledge_loaded` | Knowledge files loaded from registry |
| `ai_creator_knowledge_ingested` | Single knowledge file parsed |
| `ai_creator_knowledge_skipped` | No knowledge files found |
| `ai_creator_knowledge_registry_ready` | Registry indexed and ready |

### Phase compatibility

- All Phase 1–38 behavior preserved
- `AIEditPlan.creator_knowledge` defaults to `{}` — backward compatible
- No new request fields — knowledge loading runs automatically when AI Director is enabled
- Phase 15 `ExternalKnowledgeItem`/`KnowledgeSearchResult` unchanged

---

## Phase 40 — Creator Pattern Extraction Engine

### What was added

- `app/ai/knowledge/pattern_schema.py` — `AICreatorPattern` and `AIPatternRegistry` dataclasses
- `app/ai/knowledge/pattern_safety.py` — pattern safety validation (12 forbidden keys, allowed pattern types)
- `app/ai/knowledge/pattern_extractor.py` — deterministic archetype-based pattern extraction for 5 categories
- `app/ai/knowledge/pattern_registry.py` — file-based + built-in archetype registry with module-level caching
- `knowledge/patterns/hooks/question_hook.json` — hook archetype seed file
- `knowledge/patterns/subtitles/compact_viral.json` — subtitle archetype seed file
- `knowledge/patterns/pacing/fast_hook.json` — pacing archetype seed file
- `knowledge/patterns/camera/dynamic_safe.json` — camera archetype seed file
- `knowledge/patterns/retention/loop_payoff.json` — retention archetype seed file
- `AIEditPlan.creator_patterns` — Phase 40 field (defaults to `{}`)

### Render Influence Report

Phase 40 reports to `skipped` only. Example entry:

```
creator_patterns:extraction_only_phase40(loaded=N,types=T)
```

### Pattern types

| Type | Built-in archetypes | Description |
|---|---|---|
| `hook` | 4 (question, curiosity, rapid, delayed_payoff) | Hook opening strategies |
| `subtitle` | 3 (compact_viral, podcast_readable, educational_clean) | Subtitle display patterns |
| `pacing` | 3 (fast_hook, calm_storytelling, high_energy_shortform) | Edit pacing styles |
| `camera` | 3 (dynamic_safe, cinematic_smooth, static_podcast) | Camera behavior patterns |
| `retention` | 3 (loop_payoff, rapid_reengagement, payoff_reinforcement) | Viewer retention tactics |

### Forbidden keys (pattern_safety)

`ffmpeg_args`, `render_command`, `shell`, `powershell`, `subprocess`, `executable`,
`python_code`, `api_key`, `auth_token`, `remote_script`, `playback_speed`, `subtitle_timing`

### Safety boundaries (still intentionally blocked)

- **Live internet access** — never performed
- **Subprocess execution** — never triggered
- **FFmpeg mutation** — never touched
- **Playback speed mutation** — never touched
- **Subtitle timing rewrite** — never touched
- **Model training** — never executed
- **GPU** — not required
- **Internet** — not required
- **API key** — not required

### Structured log events

| Event | Description |
|---|---|
| `ai_creator_patterns_loaded` | Patterns extracted from registry |
| `ai_creator_patterns_skipped` | No registry/knowledge available |
| `ai_creator_patterns_file_loaded` | Single pattern JSON file parsed |

### Phase compatibility

- All Phase 1–39 behavior preserved
- `AIEditPlan.creator_patterns` defaults to `{}` — backward compatible
- Pattern extraction runs automatically when AI Director is enabled and Phase 39 knowledge is available
- Phase 39 `AICreatorKnowledge`/`AIKnowledgeRegistry` types unchanged
- Phase 15 `ExternalKnowledgeItem`/`KnowledgeSearchResult` unchanged

---

## AI Productization Phase 41 — Retrieval-Based Creator Intelligence

See Phase 41 implementation. `AIEditPlan.creator_retrieval` defaults to `{}`.

---

## AI Productization Phase 42 — Adaptive Creator Intelligence Foundation

### Implemented

- Adaptive creator preference learning (`app/ai/adaptive/adaptive_learning.py`)
- Creator preference profiles (`app/ai/adaptive/adaptive_schema.py`)
  - `AICreatorPreferenceProfile` — learned style/subtitle/pacing/camera preferences with confidence scores
  - `AIAdaptiveLearningPack` — learning pack with creator profile, learned preferences, adaptive influences
- Adaptive creator safety validation (`app/ai/adaptive/adaptive_safety.py`)
  - 12 forbidden keys auto-stripped (password, token, api_key, auth, subprocess, executable,
    ffmpeg_args, render_command, playback_speed, subtitle_timing, queue_priority, output_path)
- Local adaptive creator memory (`app/ai/adaptive/adaptive_memory.py`)
  - JSON persistence in `data/adaptive/creator_profiles/`
  - Fallback-safe load/save/update — never raises
- Retrieval weighting adaptation via `adaptive_influences`
- Adaptive subtitle/pacing/camera enhancement weighting
- Assistive-only adaptive creator intelligence integration in AI Director and Render Influence
- `AIEditPlan.adaptive_creator_intelligence` field (defaults to `{}`)
- Phase 42 structured log events

### Architecture direction

| Principle | Detail |
|---|---|
| Learning source | Edit plan signals + explicit session context — no internet, no scraping |
| Persistence | Local JSON only (`data/adaptive/creator_profiles/`) |
| Influence mode | Always `assistive_only` — bounded influence weights [0.0, 0.30] |
| Confidence | Increments on repeated preference selection, clamped to [0.0, 1.0] |
| Render authority | Deterministic render engine always has final authority |

### Learning signals

| Signal | Source |
|---|---|
| `selected_creator_style` | Session context or `creator_style_adaptation.adapted_style` |
| `selected_subtitle_style` | Session context or `subtitle_text_apply.subtitle_style` |
| `selected_pacing_style` | Session context or `pacing.pacing_style` |
| `selected_camera_style` | Session context or `camera_motion_apply.camera_behavior` |
| `selected_duration_range` | Session context or derived from `selected_segments` duration |
| `selected_variant_strategy` | Session context or `variant_selection.selected_variant_id` |
| `export_completed` | Session context bool |

### Adaptive influence behavior (bounded, assistive-only)

| Influence | Condition | Max weight |
|---|---|---|
| `retrieval_ranking_weight` | style_confidence ≥ 0.20 | 0.15 |
| `subtitle_enhancement_weight` | subtitle_confidence ≥ 0.20 | 0.20 |
| `pacing_enhancement_weight` | pacing_confidence ≥ 0.20 | 0.20 |
| `camera_enhancement_weight` | camera_confidence ≥ 0.20 | 0.20 |
| `variant_ranking_weight` | export_history_count > 0 | 0.15 |

### Forbidden adaptive profile keys (auto-stripped)

`password`, `token`, `api_key`, `auth`, `subprocess`, `executable`,
`ffmpeg_args`, `render_command`, `playback_speed`, `subtitle_timing`,
`queue_priority`, `output_path`

### Still intentionally blocked

- **Unrestricted autonomous editing** — never executed
- **FFmpeg mutation** — never touched
- **playback_speed mutation** — never touched
- **Subtitle timing rewrite** — never touched
- **Executor override** — never performed
- **Queue mutation** — never performed
- **Internet scraping** — never performed
- **Model fine-tuning** — never executed
- **Cloud AI / external API** — not required
- **GPU** — not required
- **Internet** — not required

### Structured log events

| Event | Description |
|---|---|
| `ai_adaptive_profile_loaded` | Creator profile loaded from local JSON |
| `ai_adaptive_profile_updated` | Creator profile saved after learning |
| `ai_adaptive_learning_applied` | Learning signals applied to profile |
| `ai_adaptive_learning_skipped` | No feedback signals found this session |

### Phase compatibility

- All Phase 1–41 behavior preserved
- `AIEditPlan.adaptive_creator_intelligence` defaults to `{}` — backward compatible
- Adaptive learning runs automatically when AI Director is enabled
- No new required request fields — `ai_adaptive_profile_id` is optional

---

## AI Productization Phase 43 — Creator Feedback Loop Intelligence

### Implemented

- Creator feedback learning engine (`app/ai/feedback/feedback_learning.py`)
- Creator feedback schema (`app/ai/feedback/feedback_schema.py`)
  - `AICreatorFeedbackSignal` — single creator behavior event (export, select, ignore)
  - `AIFeedbackLearningPack` — pack with signals, learned patterns, ranking biases
- Creator feedback safety validation (`app/ai/feedback/feedback_safety.py`)
  - 12 forbidden keys auto-stripped
- Local feedback memory (`app/ai/feedback/feedback_memory.py`)
  - JSON persistence in `data/feedback/render_feedback/`
  - Pattern frequency counters per category
  - Capped at 200 signals to prevent unbounded growth
  - Fallback-safe load/save/record — never raises
- Output ranking feedback adaptation via `ranking_biases`
- Subtitle/pacing/camera feedback weighting from pattern frequency
- Retrieval weighting adaptation from creator style dominance
- Adaptive intelligence amplification when Phase 42 profile aligns
- Assistive-only feedback intelligence in AI Director and Render Influence
- `AIEditPlan.creator_feedback_intelligence` field (defaults to `{}`)

### Architecture direction

| Principle | Detail |
|---|---|
| Learning source | Creator export/select/ignore behavior + edit plan signals |
| Persistence | Local JSON only (`data/feedback/render_feedback/`) |
| Influence mode | Always `assistive_only` — bounded bias weights [0.0, 0.30] |
| Reliability gate | Minimum 3 signals before biases become active |
| Render authority | Deterministic render engine always has final authority |

### Feedback signal sources

| Signal | Source |
|---|---|
| `exported` | Session context — creator exported output |
| `selected` | Session context — creator selected output |
| `ignored` | Session context — creator ignored output |
| `selected_output_rank` | Session context or `output_ranking.best_output_id` |
| `creator_style` | Session context or `creator_style_adaptation.adapted_style` |
| `subtitle_style` | Session context or `subtitle_text_apply.subtitle_style` |
| `pacing_style` | Session context or `pacing.pacing_style` |
| `camera_style` | Session context or `camera_motion_apply.camera_behavior` |
| `duration_bucket` | Session context or derived from `selected_segments` |
| `selected_variant` | Session context or `variant_selection.selected_variant_id` |

### Ranking biases (bounded, assistive-only)

| Bias | Condition | Max |
|---|---|---|
| `output_ranking_bias` | ≥3 exports, top-rank ratio | 0.20 |
| `variant_ranking_bias` | ≥3 exports, low-rank ratio | 0.15 |
| `retrieval_weighting_bias` | creator_style dominance ≥3 | 0.20 |
| `subtitle_weighting_bias` | subtitle_style dominance ≥3 | 0.25 |
| `pacing_weighting_bias` | pacing_style dominance ≥3 (+ adaptive) | 0.25 |
| `camera_weighting_bias` | camera_style dominance ≥3 | 0.25 |

### Still intentionally blocked

- **Unrestricted autonomous editing** — never executed
- **FFmpeg mutation** — never touched
- **playback_speed mutation** — never touched
- **Subtitle timing rewrite** — never touched
- **Executor override** — never performed
- **Queue mutation** — never performed
- **Internet scraping** — never performed
- **Model fine-tuning** — never executed
- **Cloud AI / external API** — not required
- **GPU** — not required
- **Internet** — not required

### Structured log events

| Event | Description |
|---|---|
| `ai_feedback_loaded` | Feedback memory loaded from local JSON |
| `ai_feedback_signal_recorded` | A new feedback signal recorded |
| `ai_feedback_learning_applied` | Feedback patterns and biases applied |
| `ai_feedback_learning_skipped` | No signals yet to apply |

### Phase compatibility

- All Phase 1–42 behavior preserved
- `AIEditPlan.creator_feedback_intelligence` defaults to `{}` — backward compatible
- Feedback learning runs automatically when AI Director is enabled
- No new required request fields — all `ai_feedback_*` fields are optional

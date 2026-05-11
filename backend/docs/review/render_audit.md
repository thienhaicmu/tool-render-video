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

---

## AI Productization Phase 44 — Market-Aware Optimization Intelligence

### Implemented

- Market-aware optimization engine (`app/ai/market/market_optimizer.py`)
- Market optimization schema (`app/ai/market/market_schema.py`)
  - `AIMarketOptimizationProfile` — per-platform style/bias profile
  - `AIMarketOptimizationPack` — pack with market_profile + subtitle/pacing/camera/hook biases
- Market safety validation (`app/ai/market/market_safety.py`) — 9 forbidden keys auto-stripped
- Built-in market profiles (`app/ai/market/market_profiles.py`)
  - TikTok Viral — compact subtitle, fast hook, dynamic camera, aggressive hook
  - YouTube Shorts — readable subtitle, curiosity hook, medium-fast pacing
  - Facebook Reels — social framing, emotional hook, engagement pacing
  - Podcast — calm pacing, readable subtitle, stable framing
  - Educational — clean subtitle, measured pacing, readability-first
- Alias resolution (`tiktok` → `viral_tiktok`, `shorts` → `youtube_shorts`, etc.)
- Phase 42 adaptive amplification of market biases
- Phase 43 feedback amplification of market biases
- Assistive-only market intelligence in AI Director and Render Influence
- `AIEditPlan.market_optimization_intelligence` field (defaults to `{}`)

### Architecture direction

| Principle | Detail |
|---|---|
| Profile source | Local built-in profiles only — no internet, no scraping |
| Market resolution | Context > payload `ai_target_market` > payload `ai_mode` > plan mode |
| Bias amplification | Phase 42 adaptive (×0.08) + Phase 43 feedback (×0.06) |
| Influence mode | Always `assistive_only` — bounded bias weights [0.0, 0.30] |
| Render authority | Deterministic render engine always has final authority |

### Market profiles

| Market | Platform | Subtitle | Pacing | Camera | Hook bias |
|---|---|---|---|---|---|
| `viral_tiktok` | TikTok | compact | fast_hook | dynamic_safe | 0.90 |
| `youtube_shorts` | YouTube Shorts | readable | medium_fast | creator_framing | 0.75 |
| `facebook_reels` | Facebook Reels | medium_density | smooth_engagement | social_framing | 0.65 |
| `podcast` | Podcast | readable | calm_storytelling | static_podcast | 0.40 |
| `educational` | Educational | clean_readable | measured | static_framing | 0.50 |

### Bias weights (bounded, assistive-only)

All bias weights are clamped `[0.0, 0.30]`.

| Bias | Derivation |
|---|---|
| `subtitle_market_bias.weight` | `profile.subtitle_density_bias × 0.40` + adaptive amplifier |
| `pacing_market_bias.weight` | `profile.pacing_energy_bias × 0.40` + adaptive + feedback amplifier |
| `camera_market_bias.weight` | `profile.camera_motion_bias × 0.35` + adaptive + feedback amplifier |
| `hook_market_bias.weight` | `profile.hook_strength_bias × 0.35` |

### Forbidden market profile keys (auto-stripped)

`ffmpeg_args`, `render_command`, `playback_speed`, `subtitle_timing`,
`subprocess`, `executable`, `python_code`, `queue_priority`, `output_path`

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
| `ai_market_profile_loaded` | Market profile resolved and loaded |
| `ai_market_optimization_applied` | Market biases computed and attached |
| `ai_market_optimization_skipped` | Market confidence too low |

### Phase compatibility

- All Phase 1–43 behavior preserved
- `AIEditPlan.market_optimization_intelligence` defaults to `{}` — backward compatible
- Market optimization runs automatically when AI Director is enabled
- No new required request fields — `ai_target_market` is optional (falls back to `ai_mode`)

---

## AI Productization Phase 45 — AI Render Quality Evaluation

### Implemented

- Quality scoring engine (`app/ai/quality/quality_scoring.py`)
  - `score_render_quality(output_metadata, edit_plan, context)` → `AIRenderQualityScore`
  - 7-dimension weighted quality scoring: pacing(20%), subtitle(20%), camera(15%), hook(15%), retention(15%), creator_consistency(10%), market_fit(5%)
  - Failed-output penalty: 30% reduction on all dimensions when output is marked failed
  - Baseline score: 50.0 when no signals are available
- Quality evaluation orchestrator (`app/ai/quality/quality_evaluator.py`)
  - `evaluate_render_quality(outputs, edit_plan, context)` → `AIRenderQualityEvaluation`
  - Caps at 20 outputs per call
  - Selects `best_quality_output_id` by highest `overall_score`
- Quality evaluation schema (`app/ai/quality/quality_schema.py`)
  - `AIRenderQualityScore` — per-output score with 7 dimensions + confidence + flags + explanation
  - `AIRenderQualityEvaluation` — evaluation across all outputs + best output selection
- Quality safety validation (`app/ai/quality/quality_safety.py`) — 12 forbidden keys auto-stripped
- Post-render integration in `render_pipeline.py` (after `_ai_output_ranking`, before `_result_payload`)
- `AIEditPlan.render_quality_evaluation` field (defaults to `{}`)
- Render influence reporting: `_report_render_quality_evaluation()`

### Architecture direction

| Principle | Detail |
|---|---|
| Evaluation scope | Post-render, evaluation-only — never triggers rerender |
| Output cap | Maximum 20 outputs evaluated per render job |
| Best selection | Highest `overall_score` (first on tie) |
| Influence mode | Always `evaluation_only` — no mutation of outputs |
| Render authority | Deterministic render engine always has final authority |

### Quality dimensions

| Dimension | Weight | Signal sources |
|---|---|---|
| `pacing_quality` | 20% | `timing_apply`, `story_optimization`, `retention.risk_regions`, `market.pacing_bias` |
| `subtitle_readability` | 20% | `subtitle_text_apply`, `subtitle_execution`, `adaptive.subtitle_confidence`, `market.subtitle_bias` |
| `camera_smoothness` | 15% | `camera_motion_apply`, `beat_visual_execution`, `market.camera_bias` |
| `hook_strength` | 15% | `story.hook_score`, `retention.hook_score`, `clip_candidate_discovery`, `market.hook_bias` |
| `retention_quality` | 15% | `retention.overall_score`, `creator_feedback.total_exports`, `output_ranking` |
| `creator_consistency` | 10% | `creator_retrieval.matches`, `adaptive.style_confidence`, `creator_style_adaptation` |
| `market_fit` | 5% | `market_optimization_intelligence.market_profile.confidence`, active bias count |

### Forbidden quality evaluation keys (auto-stripped)

`ffmpeg_args`, `render_command`, `playback_speed`, `subtitle_timing`,
`delete_output`, `overwrite_output`, `rerender`, `queue_priority`,
`output_path_mutation`, `subprocess`, `executable`, `python_code`

### Still intentionally blocked

- **Rerender trigger** — never executed
- **Output deletion** — never performed
- **Output overwrite** — never performed
- **FFmpeg mutation** — never touched
- **playback_speed mutation** — never touched
- **Subtitle timing rewrite** — never touched
- **Executor override** — never performed
- **Internet** — not required
- **Cloud AI / external API** — not required
- **GPU** — not required

### Structured log events

| Event | Description |
|---|---|
| `ai_render_quality_score_created` | Single output scored |
| `ai_render_quality_evaluation_done` | All outputs evaluated, best selected |
| `ai_render_quality_evaluated` | Pipeline-level evaluation complete |

### Phase compatibility

- All Phase 1–44 behavior preserved
- `AIEditPlan.render_quality_evaluation` defaults to `{}` — backward compatible
- Quality evaluation runs post-render automatically when outputs are available
- Director pre-populates placeholder so field is always present in `plan.to_dict()`
- No new required request fields

---

## AI Productization Phase 46 — Creator Preset Evolution Intelligence

### Implemented

- Creator preset evolution engine (`app/ai/preset_evolution/preset_evolution_engine.py`)
  - `build_preset_evolution_pack(edit_plan, payload, context)` → `AIPresetEvolutionPack`
  - Combines creator behavior + market + feedback + quality signals to evolve presets
  - Built-in evolution templates for TikTok, Shorts, Reels, Podcast, Educational
- Creator preset schema (`app/ai/preset_evolution/preset_schema.py`)
  - `AICreatorPreset` — single preset with style/scoring/evolution metadata
  - `AIPresetEvolutionPack` — pack with recommended + evolved presets + best selection
- Creator preset safety validation (`app/ai/preset_evolution/preset_safety.py`) — 11 forbidden keys auto-stripped
- Creator preset memory (`app/ai/preset_evolution/preset_memory.py`)
  - Local JSON persistence at `data/preset_evolution/presets/`
  - Safe fallback to built-in presets on missing/corrupt file
  - 3 built-in starter presets: TikTok Viral, Podcast Clean, Educational
  - Cap at 50 evolved presets
- Creator preset scoring (`app/ai/preset_evolution/preset_scoring.py`)
  - Weighted: quality(35%) + creator_fit(25%) + market_fit(20%) + feedback(10%) + retrieval(10%)
  - Style match bonus for feedback alignment
  - Retrieval alignment scoring from Phase 41
- `AIEditPlan.creator_preset_evolution` field (defaults to `{}`)
- AI Director Phase 46 block: `_attach_creator_preset_evolution()`, `_append_preset_evolution_explainability()`
- Render influence reporting: `_report_creator_preset_evolution()`

### Architecture direction

| Principle | Detail |
|---|---|
| Evolution source | Local presets + AI signals (42–45) — no internet, no cloud AI |
| Market resolution | Context > payload `ai_target_market` > payload `ai_mode` > plan mode |
| Score amplification | Phase 44 market confidence (×10%) + Phase 42 style confidence (×8%) |
| Minimum confidence | 0.30 required to generate evolved preset |
| Influence mode | Always `assistive_only` — recommendation-only, never overrides user choice |

### Evolution templates

| Market | Evolved name | Style overrides |
|---|---|---|
| `viral_tiktok` / `tiktok` | TikTok Viral v2 | compact subtitle, fast_hook pacing, strong_open hook |
| `youtube_shorts` | YouTube Shorts v2 | readable subtitle, medium_fast pacing, curiosity_hook |
| `facebook_reels` | Facebook Reels v2 | medium_density subtitle, smooth_engagement, emotional_hook |
| `podcast` | Podcast Clean v2 | readable subtitle, calm_storytelling, stable framing |
| `educational` | Educational Pro | clean_readable subtitle, clarity_first pacing |

### Preset scoring weights

| Signal | Weight | Source |
|---|---|---|
| `quality_score` | 35% | Preset base quality |
| `creator_fit_score` | 25% | Preset creator alignment |
| `market_fit_score` | 20% | Preset market alignment |
| `feedback_score` | 10% | Phase 43 exports + style match |
| `retrieval_score` | 10% | Phase 41 retrieval matches |

### Forbidden preset keys (auto-stripped)

`ffmpeg_args`, `render_command`, `playback_speed`, `subtitle_timing`,
`rerender`, `delete_output`, `subprocess`, `executable`, `python_code`,
`queue_priority`, `output_path`

### Still intentionally blocked

- **Autonomous preset replacement** — never performed
- **FFmpeg mutation** — never touched
- **playback_speed mutation** — never touched
- **Subtitle timing rewrite** — never touched
- **Output deletion** — never performed
- **Autonomous rerender** — never triggered
- **Executor override** — never performed
- **Internet scraping** — never performed
- **Model fine-tuning** — never executed
- **Cloud AI / external API** — not required
- **GPU** — not required
- **Internet** — not required

### Structured log events

| Event | Description |
|---|---|
| `ai_preset_evolution_started` | Evolution engine started |
| `ai_preset_evolved` | Evolved preset generated |
| `ai_preset_recommended` | Preset scored above threshold and recommended |
| `ai_preset_evolution_skipped` | Confidence too low or no target market |
| `ai_preset_evolution_applied` | Pack attached to plan in director |

### Phase compatibility

- All Phase 1–45 behavior preserved
- `AIEditPlan.creator_preset_evolution` defaults to `{}` — backward compatible
- Preset evolution runs automatically when AI Director is enabled
- No new required request fields — `ai_target_market` is optional (falls back to `ai_mode`)

---

## AI Productization Phase 47 — Multi-Signal AI Render Orchestrator

### Implemented

- Unified signal aggregation layer (`app/ai/orchestrator/signal_aggregation.py`)
  - Aggregates creator, market, quality, preset, feedback, and retrieval signals
  - Gracefully tolerates missing signals — falls back to `{"available": False}`
  - Computes `active_signal_count` and aggregate `confidence` (active/6)
- Per-signal confidence engine (`app/ai/orchestrator/confidence_engine.py`)
  - Conservative scale factors per signal type
  - Aggregate confidence = mean of active (non-zero) signal scores
- Deterministic conflict resolver (`app/ai/orchestrator/conflict_resolver.py`)
  - Resolves subtitle_style, pacing_style, camera_style, hook_emphasis conflicts
  - Priority order: creator > feedback > preset > market > retrieval > quality
  - Lower-priority signal overrides only when confidence delta ≥ 0.25
  - Every resolution includes an explainable reason string
- Recommendation-only strategy planner (`app/ai/orchestrator/strategy_planner.py`)
  - Derives subtitle_style, subtitle_density, camera_motion, hook_emphasis,
    clip_selection_bias, ranking_priority from resolved conflicts
  - Conservative guard: aggregate confidence < 0.30 → safe defaults only
- Render orchestrator entry point (`app/ai/orchestrator/render_orchestrator.py`)
  - Public API: `orchestrate_render_signals(edit_plan, payload=None, context=None) → dict`
  - Runs all 4 steps: aggregate → confidence → conflict → strategy
  - Generates future UI-safe `explainability.why_this_strategy` list
- `AIEditPlan.multi_signal_orchestration` field (defaults to `{}`)
- AI Director Phase 47 block: `_attach_multi_signal_orchestration()` — runs last
- Render influence reporting: `_report_multi_signal_orchestration()`

### Architecture direction

| Principle | Detail |
|---|---|
| Phase role | Reasoning-only — aggregates all prior signals, never executes |
| Execution mode | Always `reasoning_only` — `strategy_mode` always `recommendation_only` |
| Signal sources | Phases 41–46 + Phase 23 creator style adaptation |
| Confidence guard | aggregate_confidence < 0.30 → conservative default strategy |
| Conflict resolution | Deterministic priority order with confidence-based override threshold |
| Explainability | `why_this_strategy` list powers future AI Strategy Panel |
| Render authority | Deterministic render engine always has final authority |

### Signal sources integrated

| Signal | Source phase |
|---|---|
| `creator_signal` | Phase 42 adaptive + Phase 23 style adaptation |
| `market_signal` | Phase 44 market optimization |
| `quality_signal` | Phase 45 render quality evaluation |
| `preset_signal` | Phase 46 creator preset evolution |
| `feedback_signal` | Phase 43 creator feedback loop |
| `retrieval_signal` | Phase 41 creator retrieval |

### Example orchestration output

```json
{
  "available": true,
  "enabled": true,
  "orchestration_mode": "reasoning_only",
  "confidence_scores": {
    "creator_confidence": 0.75,
    "market_confidence": 0.82,
    "quality_confidence": 0.61,
    "preset_confidence": 0.51,
    "feedback_confidence": 0.72,
    "retrieval_confidence": 0.60,
    "aggregate_confidence": 0.67
  },
  "resolved_conflicts": {
    "subtitle_style": {"winner": "feedback_preference", "value": "compact", "reason": "priority_preferred conf=0.72"},
    "hook_emphasis": {"winner": "market_preference", "value": "strong", "reason": "market_hook_bias_weight=0.24"},
    "conflict_count": 2,
    "resolution_mode": "deterministic"
  },
  "recommended_strategy": {
    "subtitle_style": "compact",
    "subtitle_density": "high",
    "camera_motion": "dynamic_subject",
    "hook_emphasis": "strong",
    "clip_selection_bias": "retention",
    "ranking_priority": "creator_fit"
  },
  "strategy_confidence": 0.67,
  "strategy_mode": "recommendation_only",
  "explainability": {
    "why_this_strategy": [
      "Creator intelligence adapted to 'viral_tiktok' style (confidence=0.75)",
      "Creator has 8 prior export(s) — feedback patterns active",
      "VIRAL_TIKTOK market optimization active (confidence=0.82)",
      "Preset 'tiktok_viral_v2' strongly matched (score=72.5)",
      "2 signal conflict(s) resolved — subtitle_style: feedback_preference preferred; pacing_style: feedback_preference preferred"
    ],
    "signal_count": 6,
    "strategy_confidence": 0.67
  }
}
```

### Safety boundaries (still intentionally blocked)

- **FFmpeg mutation** — never touched
- **Render rewrite** — never performed
- **Subtitle timing rewrite** — never touched
- **playback_speed mutation** — never touched
- **Rerender** — never triggered
- **Executor override** — never performed
- **Autonomous execution** — never triggered
- **Destructive mutation** — never performed
- **Cloud AI / external API** — not required
- **GPU** — not required
- **Internet** — not required

### Structured log events

| Event | Description |
|---|---|
| `ai_render_orchestrator_started` | Orchestrator started for a job |
| `ai_render_orchestrator_done` | Orchestration complete — logs active signals + confidence |
| `ai_render_orchestrator_skipped` | No active signals or no edit plan available |

### Phase compatibility

- All Phase 1–46 behavior preserved
- `AIEditPlan.multi_signal_orchestration` defaults to `{}` — backward compatible
- Orchestrator runs automatically when AI Director is enabled
- No new required request fields — all orchestrator inputs come from prior phase fields
- All Phase 41–46 AI signal fields remain unchanged

---

## Phase 48 — Safe Controlled Influence Engine

**Date:** 2026-05-11
**Status:** Implemented
**Module:** `app/ai/influence/` (7 files)

### Summary

Phase 48 implements a Safe Controlled Influence Engine that consumes the Phase 47 Multi-Signal Orchestration output and produces conservative, confidence-gated influence recommendations across four domains: subtitle style/density, camera motion, clip ranking, and market weights.

**Influence is recommendation-only.** The render executor retains full authority. No render mutation occurs.

### Architecture

```
Phase 47 multi_signal_orchestration
         │
         ▼
  Safety Gate (evaluate_gate)
  ├─ < 0.70  → blocked (no influence)
  ├─ 0.70–0.85 → soft tier (density + smoothing only)
  └─ > 0.85  → strong tier (all bias domains)
         │
         ├─ subtitle_bias.py   → style preset + density adjustment
         ├─ camera_bias.py     → smoothing + stability + deadzone
         ├─ ranking_bias.py    → priority bias + secondary sort
         └─ market_weighting.py → per-platform weight biases
         │
         ▼
  Unified safe_influence surface:
  {
    "subtitle_style_bias":   "clean_pro" | "viral_bold" | "boxed_caption" | ""
    "subtitle_density_bias": "lighter" | "unchanged" | ""
    "camera_motion_bias":    str (Phase 47 passthrough hint)
    "ranking_priority_bias": "retention" | "creator_fit" | ... | ""
  }
```

### Files

| File | Role |
|---|---|
| `app/ai/influence/__init__.py` | Package marker |
| `app/ai/influence/safety_gate.py` | Confidence tier classification (blocked/soft/strong) |
| `app/ai/influence/subtitle_bias.py` | Subtitle style + density bias |
| `app/ai/influence/camera_bias.py` | Camera smoothing + stability + deadzone bias |
| `app/ai/influence/ranking_bias.py` | Clip output ranking priority bias |
| `app/ai/influence/market_weighting.py` | Per-platform market weight biases |
| `app/ai/influence/influence_engine.py` | Main entry point, assembles all domain biases |

### Safety gate thresholds

| Confidence | Tier | Allowed influence |
|---|---|---|
| < 0.70 | blocked | None — returns disabled immediately |
| 0.70–0.85 | soft | Density bias + smoothing preference only |
| > 0.85 | strong | All bias domains |

### Market weight profiles

| Market | hook_weight | retention_weight | energy_weight | readability | story | calm |
|---|---|---|---|---|---|---|
| viral_tiktok / tiktok | 1.0 | 0.9 | 0.8 | 0.2 | 0.3 | 0.0 |
| youtube_shorts | 0.7 | 0.8 | 0.6 | 0.5 | 0.4 | 0.1 |
| facebook_reels | 0.6 | 0.7 | 0.5 | 0.6 | 0.5 | 0.2 |
| podcast | 0.1 | 0.4 | 0.1 | 1.0 | 0.7 | 0.9 |
| educational | 0.2 | 0.5 | 0.2 | 1.0 | 0.8 | 0.7 |

All biases bounded [0.0, 0.20] (conservative ceiling). Soft tier uses 0.6× multiplier.

### Example output (strong tier, tiktok, confidence=0.92)

```json
{
  "available": true,
  "enabled": true,
  "influence_mode": "safe_controlled",
  "gate": {"passed": true, "tier": "strong", "confidence": 0.92, "reason": "strong_tier"},
  "safe_influence": {
    "subtitle_style_bias": "clean_pro",
    "subtitle_density_bias": "lighter",
    "camera_motion_bias": "smooth_subject",
    "ranking_priority_bias": "retention"
  },
  "subtitle_bias":  {"available": true, "subtitle_style_bias": "clean_pro", ...},
  "camera_bias":    {"available": true, "smoothing_preference": "prefer_smooth", ...},
  "ranking_bias":   {"available": true, "ranking_priority_bias": "retention", ...},
  "market_weights": {"available": true, "target_market": "tiktok", "hook_weight_bias": 0.2, ...},
  "confidence": 0.92,
  "explainability": [
    "Safety gate passed — tier=strong confidence=0.92",
    "Subtitle bias: style→clean_pro, density→lighter",
    "Camera bias: motion→smooth_subject, smooth→prefer_smooth",
    "Ranking bias: priority→retention",
    "Market weights active for 'tiktok' platform"
  ],
  "warnings": []
}
```

### Safety boundaries

❌ No FFmpeg mutation
❌ No render rewrite
❌ No playback_speed mutation
❌ No subtitle timing rewrite
❌ No rerender
❌ No executor override
❌ No crop engine rewrite
❌ No autonomous execution
❌ No destructive pipeline changes

All output fields are metadata/recommendation-only. Render executor retains full authority.

### AIEditPlan field

```python
# Phase 48 — Safe controlled influence pack (populated by influence_engine module)
safe_influence_pack: dict = field(default_factory=dict)
```

Defaults to `{}`. Backward compatible with all prior phases.

### Render influence reporting

Phase 48 safe influence pack is reported in `render_influence.py` via `_report_safe_influence_pack()`.
- **Always** reports to `report["skipped"]` — never to `report["applied"]`
- Metadata-only; no render execution logged

### Structured log events

| Event | Description |
|---|---|
| `ai_safe_influence_started` | Influence engine started for a job |
| `ai_safe_influence_done` | Influence computed — logs confidence + tier |
| `ai_safe_influence_skipped` | Gate blocked or no orchestration output |

### Phase compatibility

- All Phase 1–47 behavior preserved
- `AIEditPlan.safe_influence_pack` defaults to `{}` — backward compatible
- Influence engine runs after Phase 47 in `_build_plan`, consuming `multi_signal_orchestration`
- No new required request fields
- All Phase 41–47 AI signal fields remain unchanged

---

## Phase 49A — Backend Metadata Contract for Visible AI UX

**Date:** 2026-05-11
**Status:** Implemented
**Module:** `app/ai/ux/` (2 files) + `render_pipeline.py` patch

### Summary

Phase 49A creates a stable, UI-safe metadata contract (`ai_ux`) that future frontend code can consume without knowing internal AI subsystem shapes. It is metadata-contract only: no UI changes, no render mutation, no executor override.

### Problem solved

Prior to Phase 49A, the frontend had no stable surface to display AI intelligence. Phases 47 and 48 produced rich internal metadata, but:
- Keys changed across phases
- Internal debug strings were mixed with presentable data
- No single compact shape existed for the UI to render

### Solution: `ai_ux` result field

A new `ai_ux` key is added to every `result_json` payload (additive, backward-compatible). Built by `build_ai_ux_metadata()` in `app/ai/ux/ai_ux_metadata.py`.

### Canonical shape

```json
{
  "ai_ux": {
    "available": true,
    "strategy": {
      "title": "AI Strategy",
      "creator_style": "Podcast Clean",
      "target_market": "US",
      "confidence": 0.87,
      "recommendations": [
        "Clean readable subtitles",
        "Balanced pacing",
        "Smooth subject tracking",
        "Moderate hook emphasis",
        "Retention-focused clip ranking"
      ],
      "why": [
        "Creator intelligence adapted to 'podcast_clean' style (confidence=0.82)",
        "Creator has 5 prior export(s) — feedback patterns active",
        "US market optimization active (confidence=0.75)"
      ]
    },
    "safe_influence": {
      "applied": true,
      "items": [
        "Cleaner subtitle style applied",
        "Lighter subtitle density recommended",
        "Smoother subject tracking bias",
        "Retention-boosted clip ranking"
      ]
    },
    "best_export": {
      "enabled": true,
      "why": [
        "Retention-optimized clip selected as best export",
        "High AI confidence in selection"
      ]
    }
  }
}
```

### Fallback shape (when AI unavailable)

```json
{"ai_ux": {"available": false}}
```

### Files

| File | Role |
|---|---|
| `app/ai/ux/__init__.py` | Package marker |
| `app/ai/ux/ai_ux_metadata.py` | `build_ai_ux_metadata()` builder — Phase 49A public API |
| `app/orchestration/render_pipeline.py` | +6 lines: call builder, add `ai_ux` to `_result_payload` |

### Data sources

| ai_ux field | Source |
|---|---|
| `strategy.confidence` | Phase 47 `confidence_scores.aggregate_confidence` |
| `strategy.target_market` | Phase 47 `aggregated_signals.market_signal.target_market` |
| `strategy.creator_style` | Phase 14 `creator_style.style_label` → Phase 23 `creator_style_adaptation.adapted_style` |
| `strategy.recommendations` | Phase 47 `recommended_strategy` — mapped to human-readable labels |
| `strategy.why` | Phase 47 `explainability.why_this_strategy` — filtered |
| `safe_influence.applied` | Phase 48 `safe_influence_pack.enabled` |
| `safe_influence.items` | Phase 48 `safe_influence_pack.safe_influence` — mapped to labels |
| `best_export.enabled` | Phase 30 `output_ranking.available` + `best_output_id` |
| `best_export.why` | Derived from Phase 48 ranking bias + gate tier |

### UI-safety guarantees

- No raw debug JSON exposed
- No stack traces
- No internal Python class names
- No snake_case keys in label strings
- Debug/error prefixes filtered from all string lists
- Confidence clamped [0.0, 1.0], rounded to 2 decimals
- All list outputs bounded (_MAX_RECOMMENDATIONS=5, _MAX_WHY=5, _MAX_INFLUENCE_ITEMS=5)
- Deterministic: identical inputs produce identical outputs

### Safety boundaries

❌ No FFmpeg mutation
❌ No render rewrite
❌ No playback_speed mutation
❌ No subtitle timing rewrite
❌ No rerender
❌ No executor override
❌ No autonomous execution
❌ No frontend redesign in this phase

All existing `result_json` fields are preserved unchanged. `ai_ux` is additive only.

### Phase compatibility

- All Phase 1–48 behavior preserved
- `ai_ux` defaults to `{"available": False}` on any error — never blocks render
- No new required request fields
- Backward compatible: consumers that don't read `ai_ux` are unaffected

---

## Phase 49B — Safe AI Strategy Panel

**Date:** 2026-05-11
**Status:** Implemented
**Files:** `static/js/render-ui.js`, `static/css/app.css`

### Summary

Phase 49B adds a compact, premium AI Strategy Panel to the Render Result surface using safe DOM injection. The panel renders Phase 49A `ai_ux` metadata in a creator-friendly format — no technical terminology, no raw JSON, no debug output.

### Placement

```
render_output_panel
├── renderOutputHeader  (Clips title, sort, Open Folder)
├── render_output_path  (output dir / error info)
├── mvRenderSummary     (viral render summary)
├── cs_preview_area     (center-stage preview)
├── [aiux_strategy_panel]  ← INJECTED HERE (above cards)
└── render_output_list  (clip cards grid)
```

### What the panel shows

| Section | Content |
|---|---|
| Header | "AI Strategy" label + confidence badge (e.g. "87% confidence") |
| Chips | Creator style pill + target market pill |
| Recommended | Up to 5 human-readable strategy bullets (✓ prefix) |
| Why | Up to 4 AI reasoning lines (• prefix, muted) |
| AI Adjustments | Up to 4 Phase 48 influence items applied (✦ prefix) |

### CSS isolation

All new CSS uses `.aiux-*` prefix namespace — zero bleed into existing layout:
- `.aiux-panel`, `.aiux-header`, `.aiux-title`, `.aiux-conf-badge`
- `.aiux-body`, `.aiux-chips`, `.aiux-chip`, `.aiux-chip--style`, `.aiux-chip--market`
- `.aiux-section`, `.aiux-section-label`, `.aiux-list`, `.aiux-list-item`
- `.aiux-check`, `.aiux-check--applied`, `.aiux-bullet`, `.aiux-list--why`

No global overrides. No `!important` abuse. No broad selectors.

### DOM injection approach

- `document.createElement('div')` + `innerHTML` + `insertBefore()` (never innerHTML on existing container)
- Panel inserted immediately before `render_output_list` inside `render_output_panel`
- Fully idempotent: re-renders remove the old panel before injecting
- `clearRenderOutputPanel()` calls `resetAiStrategyPanel()` — cleans up on reset

### Fallback safety

- If `ai_ux` is missing or `available=false`: silent no-op, no panel rendered
- If `render_output_panel` or `render_output_list` not found: silent no-op
- Entire injection wrapped in try/catch: never throws, never crashes render result
- Individual sections (chips, recs, why, adjustments) only render when non-empty

### Preserved IDs (unchanged)

`render_output_panel`, `render_output_list`, `render_output_badge`, `render_output_path`, `mvRenderSummary`, `cs_preview_area`, all `clipCard` elements, all `rc_*` and `abp_*` IDs.

### Safety contract

❌ No render pipeline modification
❌ No websocket flow modification
❌ No upload/editor/download/history flow modification
❌ No DOM renaming or movement of existing elements
❌ No global CSS overrides
❌ No index.html modification required

### Phase compatibility

- All Phase 1–49A behavior preserved
- Panel only appears when `ai_ux.available === true` in result_json
- Backward compatible: jobs without `ai_ux` show no panel (silent)

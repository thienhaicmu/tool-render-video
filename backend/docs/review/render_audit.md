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

---

## Phase 49C — Best Export Explanation on Output Cards

**Date:** 2026-05-11
**Status:** Implemented
**Files:** `static/js/render-ui.js` (+18 lines), `static/css/app.css` (+50 lines)

### Summary

Phase 49C adds a compact "Why this output?" explanation block inside the best output card. It reads `ai_ux.best_export.why` reasons from the Phase 49A metadata contract and injects them inside the card body when the card is flagged `isBest` and reasons are available.

### Detection logic

```
rk.isBest === true          (existing ranking flag — not recomputed)
AND _bestExportWhy.length > 0  (reasons parsed from ai_ux.best_export.why)
```

- `rk.isBest` comes from existing `_rankMap(job)` — no new ranking logic
- `ai_ux.best_export.enabled` must be `true` to populate reasons
- Max 3 reasons shown, filtered for non-empty strings
- All other cards: no change

### Card structure (best card only)

```
clipCard.isBestClip
  ├─ clipCardThumbWrap
  │    ├─ [video thumbnail]
  │    ├─ clipCardBestFlag ("Best")   ← existing — unchanged
  │    └─ clipCardDurTag (duration)
  └─ clipCardBody
       ├─ clipCardTitle
       ├─ clipCardScoreRow
       ├─ clipCardReason (if any)
       ├─ [aiux-best-export]           ← NEW (injected only on best card)
       │    ├─ aiux-best-title "Why this output?"
       │    └─ aiux-best-reasons
       │         ├─ ✓ Strong hook
       │         ├─ ✓ High subtitle readability
       │         └─ ✓ Best creator fit
       └─ clipCardActions (Preview · Download · Folder)
```

### CSS isolation

All new CSS uses `.aiux-best-*` prefix:
`.aiux-best-export`, `.aiux-best-title`, `.aiux-best-reasons`, `.aiux-best-reason`, `.aiux-best-check`

No global selectors. No overrides to `.clipCard`, `.clipCardBody`, `.clipCardActions`, or any existing class.

### Fallback behavior

| Condition | Result |
|---|---|
| `ai_ux` missing or `available: false` | `_bestExportWhy = []` → no section |
| `best_export.enabled` is false | `_bestExportWhy = []` → no section |
| `best_export.why` is empty | no section |
| `rk.isBest` is false | no section |
| JSON parse error | caught silently, `_bestExportWhy = []` |

### Safety contract

❌ No render pipeline modification
❌ No card action changes (Preview/Download/Folder unchanged)
❌ No existing badge duplication (`clipCardBestFlag` preserved as-is)
❌ No DOM renaming or movement
❌ No global CSS overrides
❌ No index.html modification

### Phase compatibility

- All Phase 49B AI Strategy Panel behavior preserved
- All Phase 1–49A behavior preserved
- Jobs without `ai_ux` show no explanation (silent fallback)
- Non-best cards entirely unchanged

---

## Phase 49D — AI UX Hardening & Regression Guard

**Date:** 2026-05-11
**Status:** Implemented
**Files:** `static/js/render-ui.js` (+70 lines), `static/css/app.css` (+10 lines)

### Summary

Phase 49D hardens the AI UX added in 49B/49C with shared helper functions, eliminating duplicated parsing, guarding all null/NaN/undefined paths, and adding CSS overflow guards.

### New helpers (all deterministic, never-raise)

| Helper | Purpose |
|---|---|
| `_aiSafeText(s, maxLen)` | Trims, rejects `"null"`/`"undefined"`, truncates to maxLen |
| `_aiSafeList(arr, maxLen, maxItems)` | Filters, deduplicates, bounds to safe string array |
| `_aiClampConf(v)` | Clamps confidence [0,1], rejects NaN/Infinity, rounds to 2dp |
| `_parseAiUx(job)` | Single parse point for `job.result_json.ai_ux`, returns null on any failure |
| `_shouldRenderAiStrategy(aiUx)` | Gate: true only when ≥1 displayable section exists |
| `_shouldRenderBestExport(aiUx, isBest)` | Gate: true only when card is best AND reasons are available |

### What was fixed

| Risk | Fix |
|---|---|
| Double `JSON.parse` of result_json | Single `_parseAiUx(job)` call, result shared |
| `null`/`undefined` string items shown | `_aiSafeList` filters via `_aiSafeText` |
| `"null"` / `"undefined"` literal strings | `_aiSafeText` rejects both |
| NaN confidence producing `NaN%` | `_aiClampConf` returns null → badge hidden |
| Long text overflowing cards/panel | `overflow-wrap`, `word-break` on list items |
| Long creator style chip overflow | `max-width:180px`, `text-overflow:ellipsis` on chips |
| Panel shown with zero content | `_shouldRenderAiStrategy` guards body emptiness |
| Best reasons shown on wrong card | `_shouldRenderBestExport(aiUx, isBest)` double-gates |
| Duplicate reasons in list | `_aiSafeList` deduplicates via Set |
| Hardcoded unicode in template strings | HTML entities (`&#x2713;`, `&#x2736;`, `&bull;`) |

### CSS changes

- `.aiux-list-item`: added `min-width:0`, `overflow-wrap:break-word`, `word-break:break-word`
- `.aiux-best-reason`: added `min-width:0`, `overflow-wrap:break-word`, `word-break:break-word`
- `.aiux-chip`: added `max-width:180px`, `overflow:hidden`, `text-overflow:ellipsis`, `white-space:nowrap`

### Manual validation checklist

- [ ] Render completes and result panel appears
- [ ] AI Strategy Panel visible when `ai_ux.available === true`
- [ ] AI Strategy Panel hidden when `ai_ux` missing or `available: false`
- [ ] Panel shows no content sections when all are empty
- [ ] Best card shows "Why this output?" only when `best_export.enabled && why.length`
- [ ] Non-best cards show no explanation
- [ ] Preview button works on best card
- [ ] Download button works on best card
- [ ] Open Folder button works on best card
- [ ] Active selection works (click to select)
- [ ] History tab still shows previous jobs
- [ ] No duplicate "Best" badges
- [ ] No `undefined` / `null` text visible anywhere
- [ ] No console errors in devtools
- [ ] No overlap at 640px viewport width
- [ ] Sort select still works (Best first / In order)
- [ ] Center-stage preview still opens on card click

### Remaining UI risks

- Panel fade-in animation replays on every sort reorder (cosmetic, not a bug)
- No explicit max-height on `.aiux-panel` — relies on bounded list sizes (max 5 items)
- If backend returns > 3 `best_export.why` reasons, extra are silently truncated by `_aiSafeList`

### Safety contract

❌ No render pipeline modification
❌ No websocket changes
❌ No DOM renaming or movement
❌ No global CSS overrides
❌ No index.html modification

---

## Phase 50A — Deep Subtitle Preference Intelligence

**Date:** 2026-05-11
**Status:** Implemented
**Module:** `app/ai/creator_subtitle/` (4 files)

### Summary

Phase 50A makes Creator Intelligence understand subtitle preferences more deeply.
Prior subtitle preference was coarse (style label + density). Phase 50A infers nine
distinct preference dimensions from available AI metadata signals — all metadata-only,
no render mutation, no subtitle engine rewrite.

### Nine preference dimensions

| Dimension | Allowed values |
|---|---|
| `style` | `viral_bold`, `clean_pro`, `boxed_caption`, `unknown` |
| `density` | `light`, `medium`, `dense`, `unknown` |
| `line_count` | `1`, `2`, `3` |
| `uppercase` | `uppercase`, `mixed`, `lowercase`, `unknown` |
| `keyword_emphasis` | `none`, `subtle`, `moderate`, `strong`, `unknown` |
| `motion_style` | `clean`, `bounce`, `karaoke`, `unknown` |
| `caption_box` | `none`, `minimal`, `boxed`, `unknown` |
| `readability_priority` | `low`, `medium`, `high`, `unknown` |
| `mobile_safe` | `true`, `false` |

### Signal priority order (style inference example)

1. Creator feedback dominant pattern — highest priority (actual creator choices)
2. Phase 48 safe influence style bias
3. Phase 47 orchestration `recommended_strategy.subtitle_style`
4. Phase 33 subtitle apply metadata (`subtitle_text_apply.subtitle_style`)
5. Phase 46 preset evolution `recommended_preset.subtitle_style`
6. Phase 44 market profile `market_profile.subtitle_style`
7. Fallback: `"unknown"`

### Confidence scoring

| Condition | Amplification |
|---|---|
| `active_signal_domains / 8` | Base score (0.0–1.0) |
| Phase 42 `subtitle_enhancement_weight > 0.20` | `weight × 0.10` |
| Phase 43 feedback exports ≥ 3 | `min(count × 0.02, 0.10)` |

Confidence clamped to `[0.0, 1.0]`, rounded to 2 decimal places.
Low confidence never suppressed — `unknown` is always a valid safe output.

### Example output

```json
{
  "available": true,
  "inference_mode": "metadata_only",
  "subtitle_preference": {
    "style": "clean_pro",
    "density": "medium",
    "line_count": 2,
    "uppercase": "mixed",
    "keyword_emphasis": "moderate",
    "motion_style": "clean",
    "caption_box": "minimal",
    "readability_priority": "high",
    "mobile_safe": true,
    "confidence": 0.72,
    "signals": [
      "Creator historically preferred clean_pro subtitle style",
      "AI influence recommended lighter subtitle density",
      "Subtitle readability score consistently high (avg=0.78)",
      "Medium max-words-per-line suggests two-line subtitle preference",
      "TikTok market balances readability with visual impact"
    ]
  },
  "warnings": []
}
```

### Files

| File | Role |
|---|---|
| `app/ai/creator_subtitle/__init__.py` | Package marker |
| `app/ai/creator_subtitle/subtitle_preference_schema.py` | `AISubtitlePreference`, `AISubtitlePreferencePack` dataclasses + allowed value sets |
| `app/ai/creator_subtitle/subtitle_preference_safety.py` | Forbidden key stripping (14 forbidden keys) |
| `app/ai/creator_subtitle/subtitle_preference_inference.py` | Main inference engine — `infer_subtitle_preference()` public API |

### Integration points

| File | Change |
|---|---|
| `app/ai/director/edit_plan_schema.py` | Added `creator_subtitle_preference: dict = field(default_factory=dict)` + `to_dict()` entry |
| `app/ai/director/ai_director.py` | Phase 50A block after Phase 48: `_attach_creator_subtitle_preference()` |
| `app/ai/director/render_influence.py` | `_report_creator_subtitle_preference()` — always to `skipped`, never `applied` |

### Safety boundaries

❌ No FFmpeg mutation
❌ No render pipeline changes
❌ No subtitle timing rewrite
❌ No ASS generation rewrite
❌ No transcription mutation
❌ No playback_speed mutation
❌ No rerender trigger
❌ No executor override
❌ No autonomous execution
❌ No cloud AI / external API required
❌ No GPU required
❌ No internet required

All nine preference dimensions are metadata advisory only.
Render executor retains full authority over all subtitle execution.

### Render influence reporting

Phase 50A always reports to `report["skipped"]`, never to `report["applied"]`.
Entry format:
```
creator_subtitle_preference:inference_only_phase50a(style=...,density=...,emphasis=...,confidence=...,signals=N)
```

### Forbidden safety keys (auto-stripped by subtitle_preference_safety.py)

`ffmpeg_args`, `render_command`, `playback_speed`, `subtitle_timing`,
`subprocess`, `executable`, `python_code`, `shell`, `powershell`,
`api_key`, `auth_token`, `queue_priority`, `output_path`, `rerender`, `delete_output`

### Structured log events

| Event | Description |
|---|---|
| `ai_subtitle_preference_started` | Inference engine started for a job |
| `ai_subtitle_preference_done` | Inference complete — logs style + confidence |
| `creator_subtitle_preference_error` | Inference failed, fallback attached |

### Phase compatibility

- All Phase 1–49D behavior preserved
- `AIEditPlan.creator_subtitle_preference` defaults to `{}` — backward compatible
- Inference runs automatically when AI Director is enabled
- No new required request fields
- All Phase 17, 33, 42–48 AI signal fields remain unchanged

---

## Phase 50C — Subtitle Preference Safe Influence

**Date:** 2026-05-11
**Status:** Implemented
**Branch:** feature/product-polish

### Mission

Use Phase 50A creator subtitle preference intelligence to safely improve subtitle output quality
through bounded tuning of six subtitle configuration dimensions.  No subtitle engine rewrite,
no ASS generation rewrite, no timing rewrite, no segmentation rewrite, no FFmpeg mutation.

### Six influence dimensions

| Dimension | Allowed values | Conservative rule |
|---|---|---|
| `preset_bias` | `viral_bold`, `clean_pro`, `boxed_caption`, `none`, `unknown` | Bias toward preferred preset; never force-switch |
| `density_nudge` | `reduce`, `none` | Reduction only — never forced increase |
| `emphasis_delta` | float [-0.30, +0.30] | Signed intensity offset; bounded absolutely |
| `line_count_bias` | -1, 0, +1 | Directional preference; no segmentation rewrite |
| `motion_style_bias` | `clean`, `bounce`, `karaoke`, `none`, `unknown` | Pass-through of inferred preference |
| `mobile_readability_nudge` | float [0.0, 0.20] | Font-scale / margin boost fraction |

### Confidence gate

| Confidence | Tier | Multiplier | Effect |
|---|---|---|---|
| < 0.75 | `low` | — | No influence; default subtitle behaviour |
| 0.75–0.88 | `medium` | 0.5 | Soft influence — all deltas at half strength |
| > 0.88 | `high` | 1.0 | Full bounded influence |

### Bounded tuning constants (subtitle_influence_schema.py)

| Constant | Value |
|---|---|
| `EMPHASIS_DELTA_MIN` | -0.30 |
| `EMPHASIS_DELTA_MAX` | +0.30 |
| `PRESET_BIAS_MAX` | 1.0 |
| `MOBILE_NUDGE_MAX` | 0.20 |
| `LINE_COUNT_BIAS_MIN/MAX` | -1 / +1 |
| `SOFT_TIER_MULTIPLIER` | 0.5 |

### Input / output example

**Input** (from `plan.creator_subtitle_preference`, Phase 50A output):
```json
{
  "available": true,
  "subtitle_preference": {
    "style": "clean_pro",
    "density": "dense",
    "keyword_emphasis": "moderate",
    "line_count": 1,
    "motion_style": "clean",
    "readability_priority": "high",
    "mobile_safe": true,
    "confidence": 0.90
  }
}
```

**Output** (stored in `plan.creator_subtitle_influence`):
```json
{
  "available": true,
  "confidence_tier": "high",
  "preset_bias": "clean_pro",
  "preset_bias_strength": 0.6,
  "density_nudge": "reduce",
  "emphasis_delta": 0.1,
  "line_count_bias": -1,
  "motion_style_bias": "clean",
  "mobile_readability_nudge": 0.1,
  "reasoning": [
    "Confidence tier=high (conf=0.90)",
    "preset_bias='clean_pro' strength=0.60 from style='clean_pro'",
    "density_nudge=reduce (dense->medium for readability)",
    "emphasis_delta=+0.10 from emphasis='moderate'",
    "mobile_readability_nudge=0.10 (readability='high', mobile_safe=True)"
  ],
  "warnings": []
}
```

### Files

| File | Role |
|---|---|
| `app/ai/creator_subtitle/subtitle_influence_schema.py` | Bounded constants + AISubtitleInfluencePack dataclass |
| `app/ai/creator_subtitle/subtitle_influence_engine.py` | `compute_subtitle_influence()` public API |
| `app/ai/director/edit_plan_schema.py` | `creator_subtitle_influence: dict` field added |
| `app/ai/director/ai_director.py` | Phase 50C block + `_attach_creator_subtitle_influence()` |
| `app/ai/director/render_influence.py` | `_report_creator_subtitle_influence()` reporting |
| `tests/test_ai_phase50c_subtitle_influence.py` | 80 focused tests |

### Integration points

- **Reads from:** `plan.creator_subtitle_preference` (Phase 50A output)
- **Writes to:** `plan.creator_subtitle_influence` (Phase 50C output)
- **Runs after:** Phase 50B (camera preference) in AI Director orchestration
- **Consumed by:** Subtitle configuration layer (optional — additive only)

### Render influence reporting

Phase 50C reports to `report["skipped"]` as `influence_ready_phase50c` — bounded influence
metadata only, no render execution path activated.
Entry format:
```
creator_subtitle_influence:influence_ready_phase50c(tier=...,preset_bias=...,bias_strength=...,density_nudge=...,emphasis_delta=...,motion_bias=...,mobile_nudge=...)
```

### Structured log events

| Event | Description |
|---|---|
| `ai_subtitle_influence_started` | Influence engine started for a job |
| `ai_subtitle_influence_done` | Influence complete — logs tier + preset_bias + available |
| `creator_subtitle_influence_error` | Influence failed, safe fallback attached |

### Safety guarantees

- No subtitle engine rewrite
- No ASS generation rewrite
- No subtitle timing rewrite
- No segmentation rewrite
- No FFmpeg mutation
- No executor override
- No autonomous execution
- All deltas bounded absolutely (constants in schema.py)
- Density can only be reduced, never forced higher
- Never raises — always returns safe fallback pack
- Deterministic — same input always produces same output
- Backward compatible — `creator_subtitle_influence` defaults to `{}`

### Phase compatibility

- All Phase 1–50B behaviour preserved
- `AIEditPlan.creator_subtitle_influence` defaults to `{}` — backward compatible
- Influence runs automatically when AI Director is enabled
- No new required request fields
- All Phase 50A subtitle preference inference unchanged

---

## Phase 50D — Creator Preference Fusion

**Date:** 2026-05-11
**Status:** Implemented
**Branch:** feature/product-polish

### Mission

Unify all creator intelligence signals from Phase 50A/B/C into one deterministic, creator-first
preference profile.  Improves creator consistency across subtitle and camera dimensions.
Prepares unified profile for Phase 51 Multi-Variant AI Evaluation Engine.

### Unified creator preference profile shape

```json
{
  "available": true,
  "subtitle": {
    "style": "clean_pro",
    "density": "medium",
    "keyword_emphasis": "moderate",
    "readability_priority": "high"
  },
  "camera": {
    "motion_style": "smooth_subject",
    "crop_aggressiveness": "low",
    "stability_priority": "high",
    "smoothness_priority": "high"
  },
  "clip": {
    "content_style": "educational",
    "ranking_preference": "retention"
  },
  "market_alignment": {
    "target_market": "educational",
    "market_fit": "high"
  },
  "quality_alignment": {
    "readability_priority": "high",
    "smoothness_priority": "high"
  },
  "confidence": 0.86,
  "reasoning": [
    "Subtitle: style='clean_pro' emphasis='moderate' (creator:'clean_pro', market:'clean_pro')",
    "Camera: motion='smooth_subject' stability='high' (creator:'smooth_subject', market:'smooth_subject')",
    "Content style: 'educational' (ranking_preference='retention')",
    "Quality: readability='high' smoothness='high'",
    "Fused confidence=0.86 from 3 signal(s) (sub=0.85, cam=0.82, exports=6)"
  ],
  "conflicts_resolved": [],
  "warnings": []
}
```

### Fusion signal sources and weights

| Source | Field | Weight |
|---|---|---|
| Phase 50A subtitle preference | `creator_subtitle_preference.subtitle_preference.confidence` | ~35% |
| Phase 50B camera preference | `creator_camera_preference.camera_preference.confidence` | ~35% |
| Phase 43 creator feedback exports | `creator_feedback_intelligence.learned_feedback_patterns.total_exports` | ~30% |

Confidence = weighted average of available signals + amplifier (exports ≥ 5 → +0.005/export, capped at +0.05).

### Conflict resolution philosophy

Creator history always beats market signal when creator preference is known.  When creator signal
is absent, market signal is used as fallback.  Conservative compromise applies only for emphasis:
if creator prefers less emphasis than market, the profile nudges one step toward market.

| Scenario | Resolution |
|---|---|
| Creator `clean_pro` + viral market | `clean_pro` (creator wins) |
| Creator `subtle` emphasis + `strong` market | `moderate` (one-step compromise) |
| Creator `strong` emphasis + `subtle` market | `strong` (creator wins) |
| Creator `static_center` + dynamic market | `smooth_subject` (safe middle) |
| Creator `smooth_subject` + dynamic market | `smooth_subject` (creator wins) |
| Creator unknown + any market | market signal used as fallback |

### Files

| File | Role |
|---|---|
| `app/ai/creator_fusion/__init__.py` | Package marker |
| `app/ai/creator_fusion/fusion_schema.py` | CreatorPreferenceProfile + 5 sub-dataclasses |
| `app/ai/creator_fusion/fusion_engine.py` | `fuse_creator_preferences()` public API |
| `app/ai/creator_fusion/conflict_resolver.py` | 3 conflict resolution functions |
| `app/ai/director/edit_plan_schema.py` | `creator_preference_profile: dict` field added |
| `app/ai/director/ai_director.py` | Phase 50D block + `_attach_creator_preference_profile()` |
| `app/ai/director/render_influence.py` | `_report_creator_preference_profile()` reporting |
| `tests/test_ai_phase50d_creator_fusion.py` | 85+ tests across 14 classes |

### Integration points

- **Reads from:** `creator_subtitle_preference` (50A), `creator_camera_preference` (50B),
  `creator_feedback_intelligence` (43), `market_optimization_intelligence` (44),
  `render_quality_evaluation` (45)
- **Writes to:** `plan.creator_preference_profile` (Phase 50D output)
- **Runs after:** Phase 50C in AI Director orchestration
- **Future consumers:** Phase 51 Multi-Variant AI Evaluation Engine

### Render influence reporting

Phase 50D always reports to `report["skipped"]` — advisory metadata only.
```
creator_preference_profile:fused_phase50d(subtitle_style=...,camera_motion=...,content_style=...,market_fit=...,confidence=...,conflicts_resolved=N)
```

### Structured log events

| Event | Description |
|---|---|
| `ai_creator_preference_fusion_started` | Fusion engine started |
| `ai_creator_preference_fusion_done` | Fusion complete — logs style, motion, confidence, conflicts |
| `creator_preference_profile_error` | Fusion failed, safe fallback attached |

### Safety guarantees

- No render pipeline rewrite
- No subtitle timing rewrite
- No motion_crop rewrite
- No FFmpeg mutation
- No executor override
- No autonomous execution
- Deterministic — same inputs always produce same output
- Never raises — always returns safe default profile
- `creator_preference_profile` defaults to `{}` — backward compatible

### Phase compatibility

- All Phase 1–50C behaviour preserved
- `AIEditPlan.creator_preference_profile` defaults to `{}` — backward compatible
- Fusion runs automatically when AI Director is enabled
- No new required request fields
- All Phase 50A/B/C outputs unchanged

---

## Phase 51A — Safe Strategy Variant Generator

**Date:** 2026-05-11
**Status:** Implemented
**Branch:** feature/product-polish
**Module:** `app/ai/strategy_variants/` (3 files)

### Mission

Generate up to 3 deterministic, metadata-only candidate render strategy variants from the
unified creator preference profile (Phase 50D), market intelligence (Phase 44), and render
quality evaluation (Phase 45).  Variants are candidate-only — they are never evaluated,
never ranked, never selected, and never applied to execution.  Phase 51B Variant Evaluation
Engine will evaluate and rank them.

### Variant types (deterministic order)

| # | Variant ID | Label | Source | Purpose |
|---|---|---|---|---|
| 1 | `creator_safe` | Creator Safe | Phase 50D `creator_preference_profile` | Preserve creator preferences exactly |
| 2 | `market_balanced` | Market Balanced | Phase 44 `market_optimization_intelligence` | Balance creator with target market |
| 3 | `quality_focused` | Quality Focused | Phase 45 `render_quality_evaluation` | Optimize for readability and smoothness |

Creator Safe is always generated first.  If creator profile unavailable, a conservative fallback
with all "unknown" fields is produced.  Market Balanced only generated when market profile
has a known target market.  Quality Focused only generated when output_scores is non-empty.

### Variant schema shape

```json
{
  "available": true,
  "strategy_variants": [
    {
      "id": "creator_safe",
      "label": "Creator Safe",
      "intent": "preserve creator preference",
      "subtitle": {
        "style": "clean_pro",
        "density": "medium",
        "keyword_emphasis": "moderate"
      },
      "camera": {
        "motion_style": "smooth_subject",
        "stability_priority": "high",
        "crop_aggressiveness": "low"
      },
      "ranking": {"priority": "retention"},
      "confidence": 0.84,
      "reasoning": [
        "Matches unified creator preference profile from Phase 50D fusion",
        "Preserves subtitle style='clean_pro' and camera motion='smooth_subject'"
      ]
    }
  ],
  "variant_count": 3,
  "generation_mode": "candidate_only",
  "warnings": []
}
```

### Allowed field values (enforced by frozenset validation)

| Field | Allowed values |
|---|---|
| `subtitle.style` | `viral_bold`, `clean_pro`, `boxed_caption`, `unknown` |
| `subtitle.density` | `light`, `medium`, `dense`, `unknown` |
| `subtitle.keyword_emphasis` | `none`, `subtle`, `moderate`, `strong`, `unknown` |
| `camera.motion_style` | `static_center`, `smooth_subject`, `dynamic_subject`, `unknown` |
| `camera.stability_priority` | `low`, `medium`, `high`, `unknown` |
| `camera.crop_aggressiveness` | `low`, `medium`, `high`, `unknown` |
| `ranking.priority` | `creator_fit`, `retention`, `hook_strength`, `readability`, `balanced`, `unknown` |
| `id` | `creator_safe`, `market_balanced`, `quality_focused` |

No arbitrary values. `_safe_val()` normalizes any out-of-set value to `"unknown"`.

### Market signal helpers (deterministic, local-only)

| Target market | subtitle.style | density | emphasis | camera.motion |
|---|---|---|---|---|
| `tiktok` / `reels` / `instagram` | `viral_bold` | `dense` | `strong` | `dynamic_subject` |
| `podcast` / `educational` | `clean_pro` | `light` | `subtle` | `static_center` |
| `youtube` / `shorts` | `clean_pro` | `medium` | `moderate` | `smooth_subject` |
| other | `unknown` | `medium` | `unknown` | `unknown` |

### Quality-focused derivation

| Signal | Threshold | Result |
|---|---|---|
| `avg_subtitle_readability ≥ 0.70` | high quality | style=`clean_pro`, density=`light`, emphasis=`subtle` |
| `avg_subtitle_readability < 0.70` | lower quality | style=`unknown`, density=`medium`, emphasis=`moderate` |
| `avg_camera_smoothness ≥ 0.40` | smooth | motion=`smooth_subject` |
| `avg_camera_smoothness < 0.40` | less smooth | motion=`static_center` |

Confidence = `avg_sub × 0.5 + avg_cam × 0.5`, clamped to [0.0, 1.0].

### Fallback behavior

| Condition | Behavior |
|---|---|
| `creator_preference_profile.available = False` | Conservative fallback: all "unknown", confidence=0.0, warning added |
| `market_profile` missing or target = "unknown" | No `market_balanced` variant generated |
| `output_scores` empty | No `quality_focused` variant generated |
| `edit_plan is None` | Returns unavailable pack with warning |
| Any exception | Never raises — returns safe fallback pack |

### Files

| File | Role |
|---|---|
| `app/ai/strategy_variants/__init__.py` | Package marker |
| `app/ai/strategy_variants/variant_schema.py` | `StrategyVariant`, `StrategyVariantPack` dataclasses + 7 allowed-value frozensets |
| `app/ai/strategy_variants/variant_generator.py` | `generate_strategy_variants()` public API |
| `app/ai/director/edit_plan_schema.py` | `strategy_variants: dict` field added |
| `app/ai/director/ai_director.py` | Phase 51A block + `_attach_strategy_variants()` |
| `app/ai/director/render_influence.py` | `_report_strategy_variants()` reporting |
| `tests/test_ai_phase51a_strategy_variants.py` | 70 tests across 11 classes |

### Integration points

- **Reads from:** `creator_preference_profile` (50D), `market_optimization_intelligence` (44),
  `render_quality_evaluation` (45)
- **Writes to:** `plan.strategy_variants` (Phase 51A output)
- **Runs after:** Phase 50D in AI Director orchestration
- **Future consumers:** Phase 51B Variant Evaluation Engine

### Render influence reporting

Phase 51A always reports to `report["skipped"]` — candidate generation only, no execution.

```
strategy_variants:generated_phase51a(count=3,ids=[creator_safe,market_balanced,quality_focused])
strategy_variants:not_generated_phase51a   ← when pack unavailable
```

### Structured log events

| Event | Description |
|---|---|
| `ai_strategy_variants_started` | Generation engine started for a job |
| `ai_strategy_variants_done` | Generation complete — logs count + variant IDs |
| `ai_director_strategy_variants_failed` | Generation failed, safe fallback attached |

### Safety boundaries

❌ No render pipeline rewrite
❌ No FFmpeg mutation
❌ No subtitle timing rewrite
❌ No motion_crop rewrite
❌ No playback_speed mutation
❌ No executor override
❌ No autonomous execution
❌ No variant evaluation (Phase 51B)
❌ No variant selection (Phase 51B)
❌ No variant application to execution
❌ No cloud AI / external API required
❌ No GPU required
❌ No internet required

Executor authority is fully preserved. All variant output is metadata-only.

### Phase compatibility

- All Phase 1–50D behaviour preserved
- `AIEditPlan.strategy_variants` defaults to `{}` — backward compatible
- Variant generation runs automatically when AI Director is enabled
- No new required request fields
- All Phase 50A/B/C/D outputs unchanged

---

## Phase 51B — Variant Evaluation Engine

**Date:** 2026-05-11
**Status:** Implemented
**Branch:** feature/product-polish
**Module:** `app/ai/strategy_variants/` (2 new files)

### Mission

Deterministically score and rank the safe strategy variants produced by Phase 51A using four
signal dimensions: creator_fit, market_fit, quality_fit, and safety_fit.  Produces a ranked
evaluation with `best_variant_id`.  Evaluation-only — no variant is selected for execution,
no render pipeline is altered, no executor authority is affected.  Phase 51C will consume
this evaluation for reasoning and recommendation.

### Scoring dimensions and weights

| Dimension | Weight | Signal sources |
|---|---|---|
| `creator_fit` | 35% | Phase 50D `creator_preference_profile.confidence` + style/motion alignment |
| `quality_fit` | 30% | Phase 45 `render_quality_evaluation.output_scores` averages |
| `market_fit`  | 20% | Phase 44 `market_optimization_intelligence.market_profile.confidence` + style match |
| `safety_fit`  | 15% | Variant confidence + stability/crop indicators |

All dimension scores are integers in `[0, 100]`. Composite = weighted sum, rounded to int.

### Per-variant scoring behavior

| Variant | creator_fit primary source | market_fit primary source | quality_fit primary source |
|---|---|---|---|
| `creator_safe` | Profile confidence × 80 + style/motion bonuses (max ~95) | Style/camera alignment with market target | Density/stability alignment + avg quality scores |
| `market_balanced` | Style/camera overlap with creator profile (base 45) | Market profile confidence × 70 + 15 | Moderate quality alignment |
| `quality_focused` | Readability/smoothness overlap with creator (base 40) | Market readability fit (educational/podcast bonus) | Directly from `avg_sub × 0.55 + avg_cam × 0.45` × 65 + 25 |

Safety fit:
- Base 75 (all Phase 51A variants are structurally safe)
- +15 if variant confidence ≥ 0.75, +8 if ≥ 0.50, +3 if > 0
- +5 if stability_priority = "high", +3 if crop_aggressiveness = "low"

### Ranking sort order (deterministic)

1. `score` descending (composite weighted score)
2. `safety_fit` descending (tie-break 1)
3. `creator_fit` descending (tie-break 2)
4. Variant order ascending (`creator_safe`=0, `market_balanced`=1, `quality_focused`=2)

No random ordering. No timestamp tiebreaking.

### Example output

```json
{
  "available": true,
  "best_variant_id": "quality_focused",
  "ranking": [
    {
      "id": "quality_focused",
      "score": 82,
      "creator_fit": 70,
      "market_fit": 65,
      "quality_fit": 90,
      "safety_fit": 93,
      "confidence": 0.77,
      "reasoning": [
        "Optimizes subtitle readability and camera smoothness signals",
        "Highest dimension: quality_fit=90"
      ]
    }
  ],
  "confidence": 0.78,
  "reasoning": [
    "'quality_focused' ranked first with composite score=82",
    "Score gap to runner-up 'creator_safe': 4 point(s)",
    "Creator preference profile available — creator_fit dimension active"
  ],
  "evaluation_mode": "evaluation_only",
  "warnings": []
}
```

### Fallback behavior

| Condition | Behavior |
|---|---|
| `strategy_variants` missing or empty | Returns unavailable pack with warning |
| `creator_preference_profile` missing | creator_fit uses conservative defaults (35–40) |
| `market_optimization_intelligence` missing | market_fit returns conservative 45 for all variants |
| `render_quality_evaluation` missing | quality_fit uses structural indicators only |
| `edit_plan is None` | Returns unavailable pack with warning `no_edit_plan` |
| Any exception | Never raises — returns safe fallback pack |

### Files

| File | Role |
|---|---|
| `app/ai/strategy_variants/evaluation_schema.py` | `VariantScore`, `VariantEvaluationPack` dataclasses |
| `app/ai/strategy_variants/variant_evaluator.py` | `evaluate_strategy_variants()` public API |
| `app/ai/director/edit_plan_schema.py` | `variant_evaluation: dict` field added |
| `app/ai/director/ai_director.py` | Phase 51B block + `_attach_variant_evaluation()` |
| `app/ai/director/render_influence.py` | `_report_variant_evaluation()` reporting |
| `tests/test_ai_phase51b_variant_evaluation.py` | 80+ tests across 13 classes |

### Integration points

- **Reads from:** `strategy_variants` (51A), `creator_preference_profile` (50D),
  `market_optimization_intelligence` (44), `render_quality_evaluation` (45)
- **Writes to:** `plan.variant_evaluation` (Phase 51B output)
- **Runs after:** Phase 51A in AI Director orchestration
- **Future consumers:** Phase 51C reasoning and recommendation layer

### Render influence reporting

Phase 51B always reports to `report["skipped"]` — evaluation advisory metadata only.

```
variant_evaluation:evaluated_phase51b(best='creator_safe',ranked=3,top_score=82,confidence=0.78)
variant_evaluation:not_evaluated_phase51b   ← when pack unavailable
```

### Structured log events

| Event | Description |
|---|---|
| `ai_variant_evaluation_started` | Evaluation engine started for a job |
| `ai_variant_evaluation_done` | Evaluation complete — logs best, ranked count, confidence |
| `ai_director_variant_evaluation_failed` | Evaluation failed, safe fallback attached |

### Safety boundaries

❌ No render pipeline rewrite
❌ No FFmpeg mutation
❌ No subtitle timing rewrite
❌ No motion_crop rewrite
❌ No playback_speed mutation
❌ No executor override
❌ No autonomous execution
❌ No best variant application to render
❌ No variant execution triggered
❌ No cloud AI / external API required
❌ No GPU required
❌ No internet required

Executor authority is fully preserved. `best_variant_id` is advisory metadata only.

### Phase compatibility

- All Phase 1–51A behaviour preserved
- `AIEditPlan.variant_evaluation` defaults to `{}` — backward compatible
- Evaluation runs automatically when AI Director is enabled
- No new required request fields
- All Phase 51A `strategy_variants` output unchanged

---

## Phase 51C — Best Strategy Reasoning

**Date:** 2026-05-11
**Status:** Implemented

### Mission

Turn Phase 51B variant evaluation results into clear, creator-facing reasoning that explains
why the best strategy variant was selected and what tradeoffs it represents.  Reasoning is
explanation-only — no variant is executed, no render pipeline is altered, no executor
authority is affected.

### Recommendation strength thresholds

| Strength | Condition |
|---|---|
| `none` | Confidence = 0.0 |
| `weak` | Confidence < 0.65 |
| `moderate` | Confidence ≤ 0.82, or confidence > 0.82 with score gap < 5 |
| `strong` | Confidence > 0.82 AND best-to-runner score gap ≥ 5 |

### Output fields (`best_strategy_reasoning`)

| Field | Type | Description |
|---|---|---|
| `selected_variant_id` | str or None | ID of the best variant (e.g. `"creator_safe"`) |
| `selected_label` | str | Human-readable label (e.g. `"Creator Safe"`) |
| `confidence` | float | Clamped 0–1 from Phase 51B evaluation confidence |
| `summary` | str | One-sentence creator-facing recommendation summary |
| `why_selected` | list[str] | Up to 4 creator-facing reasons for selection |
| `tradeoffs` | list[str] | Up to 2 notes about close runner-up alternatives |
| `recommendation_strength` | str | `none` / `weak` / `moderate` / `strong` |
| `warnings` | list[str] | Internal diagnostic notes; empty on success |

### Files introduced / modified

| File | Purpose |
|---|---|
| `app/ai/strategy_variants/reasoning_schema.py` | `BestStrategyReasoning` dataclass + strength constants |
| `app/ai/strategy_variants/strategy_reasoner.py` | `build_best_strategy_reasoning()` public API |
| `app/ai/director/edit_plan_schema.py` | `best_strategy_reasoning: dict` field added |
| `app/ai/director/ai_director.py` | Phase 51C block + `_attach_best_strategy_reasoning()` |
| `app/ai/director/render_influence.py` | `_report_best_strategy_reasoning()` reporting |
| `tests/test_ai_phase51c_best_strategy_reasoning.py` | 80 tests across 10 classes |

### Data flow

- **Reads from:** `variant_evaluation` (51B), `creator_preference_profile` (50D)
- **Writes to:** `plan.best_strategy_reasoning` (Phase 51C output)
- **Runs after:** Phase 51B in AI Director orchestration
- **Future consumers:** UI recommendation display, creator dashboard

### Render influence reporting

Phase 51C always reports to `report["skipped"]` — reasoning advisory metadata only.

```
best_strategy_reasoning:explained_phase51c(selected=creator_safe,strength=strong,confidence=0.85)
best_strategy_reasoning:no_recommendation_phase51c
```

### Safety boundaries (still intentionally blocked)

❌ No render pipeline rewrite
❌ No FFmpeg mutation
❌ No subtitle timing rewrite
❌ No executor override
❌ No autonomous execution
❌ No variant application to render
❌ No cloud AI / external API required
❌ No GPU required

### Backward compatibility

- All Phase 1–51B behaviour preserved
- `AIEditPlan.best_strategy_reasoning` defaults to `{}` — backward compatible
- Reasoning runs automatically when AI Director is enabled
- No new required request fields
- All Phase 51A/51B outputs unchanged

---

## Phase 52A — Subtitle Quality Intelligence v2

**Date:** 2026-05-11
**Status:** Implemented

### Mission

Make subtitle quality scoring significantly smarter by evaluating 5 quality dimensions
and 2 risk scores using only existing plan metadata.  Evaluation-only — no subtitle
mutation, no timing rewrite, no ASS rewrite, no render pipeline rewrite, no executor
override.

### Quality dimensions

| Dimension | Weight | Description |
|---|---|---|
| `mobile_readability` | 25% | Density, line count, mobile viewing comfort |
| `subtitle_balance` | 20% | Line balance, pacing consistency, density consistency |
| `keyword_emphasis_quality` | 15% | Emphasis targeting, highlight usage, overuse/underuse risk |
| `safe_zone_fit` | 20% | Margin fit, TikTok/mobile UI overlap risk, placement safety |
| `creator_fit` | 20% | Creator preference alignment (Phase 50A/C/D) |

### Risk scores

| Score | Description |
|---|---|
| `overload_risk` | Subtitle overload probability — lower is better |
| `fatigue_risk` | Viewer reading fatigue probability — lower is better |

Risk scores reduce overall score conservatively: each 10-pt average risk reduces
overall by ~1.2 pts.

### Output shape

```json
{
  "subtitle_quality_v2": {
    "mobile_readability": 87,
    "subtitle_balance": 81,
    "keyword_emphasis_quality": 84,
    "safe_zone_fit": 92,
    "creator_fit": 88,
    "overload_risk": 10,
    "fatigue_risk": 15,
    "overall": 86,
    "confidence": 0.84,
    "reasoning": [
      "Subtitle density is comfortable for mobile viewing",
      "Subtitle pacing and emphasis are well balanced",
      "Subtitle style aligns with your creator preferences"
    ]
  }
}
```

### Fallback (all inputs missing)

```json
{
  "subtitle_quality_v2": {
    "mobile_readability": 0,
    "subtitle_balance": 0,
    "keyword_emphasis_quality": 0,
    "safe_zone_fit": 0,
    "creator_fit": 0,
    "overload_risk": 0,
    "fatigue_risk": 0,
    "overall": 0,
    "confidence": 0.0,
    "reasoning": []
  }
}
```

### Metadata sources consumed

- Phase 17: `subtitle_execution` — density, emphasis, regions, beat sync
- Phase 32: `subtitle_text_apply` — text optimization signals
- Phase 44: `market_optimization_intelligence` — target market, subtitle market bias
- Phase 46: `creator_preset_evolution` — preset maturity signal
- Phase 50A: `creator_subtitle_preference` — style, density, emphasis preference + confidence
- Phase 50C: `creator_subtitle_influence` — tier, bias, emphasis delta, mobile nudge
- Phase 50D: `creator_preference_profile` — unified profile subtitle field
- Phase 4: `pacing` — BPM, energy level for fatigue scoring

### Files introduced / modified

| File | Purpose |
|---|---|
| `app/ai/subtitle_quality/__init__.py` | Package marker |
| `app/ai/subtitle_quality/subtitle_quality_schema.py` | `SubtitleQualityV2` dataclass + weights + fallback |
| `app/ai/subtitle_quality/subtitle_quality_scorer.py` | 7 deterministic dimension scorers + confidence |
| `app/ai/subtitle_quality/subtitle_quality_evaluator.py` | `evaluate_subtitle_quality_v2()` public API + reasoning |
| `app/ai/director/edit_plan_schema.py` | `subtitle_quality_v2: dict` field added |
| `app/ai/director/ai_director.py` | Phase 52A block + `_attach_subtitle_quality_v2()` |
| `app/ai/director/render_influence.py` | `_report_subtitle_quality_v2()` reporting |
| `tests/test_ai_phase52a_subtitle_quality_v2.py` | Tests across 10 classes |

### Data flow

- **Reads from:** `subtitle_execution` (17), `subtitle_text_apply` (32), `market_optimization_intelligence` (44), `creator_preset_evolution` (46), `creator_subtitle_preference` (50A), `creator_subtitle_influence` (50C), `creator_preference_profile` (50D), `pacing` (4)
- **Writes to:** `plan.subtitle_quality_v2`
- **Runs after:** Phase 51C in AI Director orchestration
- **Future consumers:** UI quality dashboard, variant scoring enrichment

### Render influence reporting

Phase 52A always reports to `report["skipped"]` — evaluation advisory metadata only.

```
subtitle_quality_v2:evaluated_phase52a(overall=86,confidence=0.84,mobile=87,...)
subtitle_quality_v2:no_result_phase52a
subtitle_quality_v2:no_signal_phase52a
```

### Safety boundaries (still intentionally blocked)

❌ No subtitle timing rewrite
❌ No subtitle segmentation rewrite
❌ No ASS generation rewrite
❌ No transcription mutation
❌ No FFmpeg mutation
❌ No render pipeline rewrite
❌ No playback_speed mutation
❌ No executor override
❌ No autonomous execution
❌ No cloud AI / external API required
❌ No GPU required

### Backward compatibility

- All Phase 1–51C behaviour preserved
- `AIEditPlan.subtitle_quality_v2` defaults to `{}` — backward compatible
- Evaluation runs automatically when AI Director is enabled
- No new required request fields
- All existing quality fields (Phase 45 `render_quality_evaluation`) unchanged

---

## Phase 52B — Camera Quality Intelligence v2

**Date:** 2026-05-11
**Status:** Implemented

### Mission

Make camera quality scoring significantly smarter by evaluating 4 quality dimensions
and 2 risk scores using only existing plan metadata.  Evaluation-only — no motion_crop
rewrite, no tracking rewrite, no scene detection mutation, no FFmpeg mutation, no
executor override.

### Quality dimensions

| Dimension | Weight | Description |
|---|---|---|
| `crop_smoothness` | 25% | Crop motion smoothness (blends Phase 45 signal at 30%) |
| `subject_stability` | 25% | Subject framing stability throughout the clip |
| `scene_continuity` | 20% | Scene-aware camera transition consistency |
| `creator_fit` | 20% | Creator camera preference alignment (Phase 50B/D) |

Weights sum to 0.90; the remaining 0.10 is reserved for risk penalty.

### Risk scores

| Score | Description |
|---|---|
| `micro_jitter_risk` | Micro-jitter probability — lower is better |
| `whip_pan_risk` | Rapid framing change probability — lower is better |

Risk deduction: `avg(jitter, whip_pan) × RISK_WEIGHT (0.10)` subtracted from overall,
making the effective weight budget sum to 1.0.

### Output shape

```json
{
  "camera_quality_v2": {
    "micro_jitter_risk": 12,
    "whip_pan_risk": 8,
    "crop_smoothness": 82,
    "subject_stability": 79,
    "scene_continuity": 75,
    "creator_fit": 84,
    "overall": 80,
    "confidence": 0.78,
    "reasoning": [
      "Subject framing remained stable throughout",
      "Crop motion is smooth and well controlled",
      "Crop motion matched your creator camera preference",
      "Low jitter risk improves camera quality"
    ]
  }
}
```

### Fallback (all inputs missing)

```json
{
  "camera_quality_v2": {
    "micro_jitter_risk": 0,
    "whip_pan_risk": 0,
    "crop_smoothness": 0,
    "subject_stability": 0,
    "scene_continuity": 0,
    "creator_fit": 0,
    "overall": 0,
    "confidence": 0.0,
    "reasoning": []
  }
}
```

### Metadata sources consumed

- Phase 4: `pacing` — BPM, energy level for motion energy baseline
- Phase 12: `story` — scene types for continuity evaluation
- Phase 18: `beat_visual_execution` — beat-sync camera hints
- Phase 34: `camera_motion_apply` — applied smoothing, stability, framing metadata
- Phase 42: `adaptive_creator_intelligence` — adaptive camera style signals
- Phase 44: `market_optimization_intelligence` — market stability target
- Phase 45: `render_quality_evaluation` — camera_smoothness score (blended 30%)
- Phase 46: `creator_preset_evolution` — preset maturity signal
- Phase 50B: `creator_camera_preference` — camera style + follow/zoom strength + confidence
- Phase 50D: `creator_preference_profile` — unified profile camera field

### Files introduced / modified

| File | Purpose |
|---|---|
| `app/ai/camera_quality/__init__.py` | Package marker |
| `app/ai/camera_quality/camera_quality_schema.py` | `CameraQualityV2` dataclass + weights + fallback |
| `app/ai/camera_quality/camera_quality_scorer.py` | 6 deterministic dimension scorers + confidence |
| `app/ai/camera_quality/camera_quality_evaluator.py` | `evaluate_camera_quality_v2()` public API + reasoning |
| `app/ai/director/edit_plan_schema.py` | `camera_quality_v2: dict` field added |
| `app/ai/director/ai_director.py` | Phase 52B block + `_attach_camera_quality_v2()` |
| `app/ai/director/render_influence.py` | `_report_camera_quality_v2()` reporting |
| `tests/test_ai_phase52b_camera_quality_v2.py` | 84 tests across 14 classes |

### Data flow

- **Reads from:** `creator_camera_preference` (50B), `camera_motion_apply` (34), `creator_preference_profile` (50D), `market_optimization_intelligence` (44), `beat_visual_execution` (18), `pacing` (4), `render_quality_evaluation` (45), `creator_preset_evolution` (46), `adaptive_creator_intelligence` (42), `story` (12)
- **Writes to:** `plan.camera_quality_v2`
- **Runs after:** Phase 52A in AI Director orchestration
- **Future consumers:** UI quality dashboard, variant scoring enrichment

### Render influence reporting

Phase 52B always reports to `report["skipped"]` — evaluation advisory metadata only.

```
camera_quality_v2:evaluated_phase52b(overall=80,confidence=0.78,smoothness=82,...)
camera_quality_v2:no_result_phase52b
camera_quality_v2:no_signal_phase52b
```

### Safety boundaries (still intentionally blocked)

❌ No motion_crop rewrite
❌ No tracking rewrite
❌ No scene detection mutation
❌ No FFmpeg mutation
❌ No render pipeline rewrite
❌ No playback_speed mutation
❌ No executor override
❌ No autonomous execution
❌ No cloud AI / external API required
❌ No GPU required

### Backward compatibility

- All Phase 1–52A behaviour preserved
- `AIEditPlan.camera_quality_v2` defaults to `{}` — backward compatible
- Evaluation runs automatically when AI Director is enabled
- No new required request fields
- All existing quality fields (Phase 45 `render_quality_evaluation`) unchanged

---

## Phase 52C — Hook Quality Intelligence v2

**Date:** 2026-05-11
**Status:** Implemented

### Mission

Make hook quality scoring significantly smarter by evaluating 6 quality dimensions
and 1 risk score using only existing plan metadata.  Evaluation-only — no hook
rewriting, no clip rewrite, no render mutation, no FFmpeg mutation, no render
pipeline rewrite, no executor override.

### Quality dimensions

| Dimension | Weight | Description |
|---|---|---|
| `first_3s_strength` | 25% | Opening hook signal strength — story hook, emotion, energy, pacing |
| `first_5s_retention` | 20% | First-five-second retention potential from retention score, BPM, pacing |
| `curiosity_strength` | 15% | Curiosity/tension signal from story segments, emotion, market hook bias |
| `open_loop_quality` | 10% | Unresolved curiosity / payoff expectation from story narrative structure |
| `market_fit` | 15% | Hook style alignment with target market preferences (US/JP/EU/KR) |
| `creator_fit` | 15% | Creator preference alignment (Phase 50D, 46, 42) |

Weights sum to 1.00.

### Risk score

| Score | Description |
|---|---|
| `hook_fatigue_risk` | Over-aggressive hook / repetitive hook pattern risk — lower is better |

Risk deduction: `(hook_fatigue_risk / 10) × 1.5` subtracted from overall score.
At maximum risk (100), penalty = 15 pts. Conservative by design.

### Output shape

```json
{
  "hook_quality_v2": {
    "first_3s_strength": 88,
    "first_5s_retention": 84,
    "curiosity_strength": 81,
    "open_loop_quality": 79,
    "hook_fatigue_risk": 24,
    "market_fit": 87,
    "creator_fit": 83,
    "overall": 85,
    "confidence": 0.84,
    "reasoning": [
      "Opening sequence creates strong early attention",
      "Hook pacing aligns with target market preferences",
      "Hook style matches your creator preferences"
    ]
  }
}
```

### Fallback (all inputs missing)

```json
{
  "hook_quality_v2": {
    "first_3s_strength": 0,
    "first_5s_retention": 0,
    "curiosity_strength": 0,
    "open_loop_quality": 0,
    "hook_fatigue_risk": 0,
    "market_fit": 0,
    "creator_fit": 0,
    "overall": 0,
    "confidence": 0.0,
    "reasoning": []
  }
}
```

### Metadata sources consumed

- Phase 4: `pacing` — BPM, energy level, emotion, pacing_style, suggested_cut_style
- Phase 12: `story` — segments (hook, tension, climax, payoff types), narrative structure
- Phase 16: `retention` — overall_score, risk_regions (start times for first-5s analysis)
- Phase 17: `subtitle_execution` — density, speech signals (confidence signal)
- Phase 42: `adaptive_creator_intelligence` — style confidence, total exports
- Phase 44: `market_optimization_intelligence` — target market, hook_market_bias, confidence
- Phase 46: `creator_preset_evolution` — preset maturity (evolved_presets signal)
- Phase 50D: `creator_preference_profile` — hook style/strength, pacing preference, confidence

### Files introduced / modified

| File | Purpose |
|---|---|
| `app/ai/hook_quality/__init__.py` | Package marker |
| `app/ai/hook_quality/hook_quality_schema.py` | `HookQualityV2` dataclass + weights + fallback |
| `app/ai/hook_quality/hook_quality_scorer.py` | 7 deterministic dimension scorers + confidence |
| `app/ai/hook_quality/hook_quality_evaluator.py` | `evaluate_hook_quality_v2()` public API + reasoning |
| `app/ai/director/edit_plan_schema.py` | `hook_quality_v2: dict` field added |
| `app/ai/director/ai_director.py` | Phase 52C block + `_attach_hook_quality_v2()` |
| `app/ai/director/render_influence.py` | `_report_hook_quality_v2()` reporting |
| `tests/test_ai_phase52c_hook_quality_v2.py` | 85 tests across 13 classes |

### Data flow

- **Reads from:** `pacing` (4), `story` (12), `retention` (16), `subtitle_execution` (17), `adaptive_creator_intelligence` (42), `market_optimization_intelligence` (44), `creator_preset_evolution` (46), `creator_preference_profile` (50D)
- **Writes to:** `plan.hook_quality_v2`
- **Runs after:** Phase 52B in AI Director orchestration
- **Future consumers:** UI quality dashboard, variant scoring enrichment, retention intelligence cross-reference

### Render influence reporting

Phase 52C always reports to `report["skipped"]` — evaluation advisory metadata only.

```
hook_quality_v2:evaluated_phase52c(overall=85,confidence=0.84,first_3s=88,...)
hook_quality_v2:no_result_phase52c
hook_quality_v2:no_signal_phase52c
```

### Safety boundaries (still intentionally blocked)

❌ No hook rewriting
❌ No clip rewrite
❌ No render mutation
❌ No FFmpeg mutation
❌ No render pipeline rewrite
❌ No playback_speed mutation
❌ No subtitle mutation
❌ No executor override
❌ No autonomous execution
❌ No cloud AI / external API required
❌ No GPU required

### Backward compatibility

- All Phase 1–52B behaviour preserved
- `AIEditPlan.hook_quality_v2` defaults to `{}` — backward compatible
- Evaluation runs automatically when AI Director is enabled
- No new required request fields
- All existing quality fields (Phase 45 `render_quality_evaluation`) unchanged

---

## Phase 52D — Unified Quality Score v2

**Date:** 2026-05-11
**Status:** Implemented

### Mission

Fuse subtitle_quality_v2 (52A), camera_quality_v2 (52B), and hook_quality_v2 (52C)
into one deterministic `render_quality_v2` unified score.  Adds creator fit, market fit,
and strategy fit dimensions derived from existing metadata.  Quality scoring only —
no render mutation, no executor override, no autonomous execution.

### Scoring dimensions and weights

| Dimension | Weight | Source |
|---|---|---|
| `subtitle_score` | 25% | `subtitle_quality_v2.overall` (Phase 52A) |
| `camera_score` | 25% | `camera_quality_v2.overall` (Phase 52B) |
| `hook_score` | 20% | `hook_quality_v2.overall` (Phase 52C) |
| `creator_fit` | 15% | Average of subscore creator_fits + Phase 50D profile confidence |
| `market_fit` | 10% | `hook_quality_v2.market_fit` (primary) + subtitle safe_zone_fit (proxy) |
| `strategy_fit` | 5% | Phase 51B variant_evaluation confidence + Phase 51C reasoning strength |

Weights sum to 1.00. No risk penalty in unified score (risk is handled within each subsystem).

### Confidence calculation

Confidence counts how many of 6 signal sources are populated:
1. `subtitle_quality_v2` (overall > 0 or confidence > 0)
2. `camera_quality_v2` (overall > 0 or confidence > 0)
3. `hook_quality_v2` (overall > 0 or confidence > 0)
4. `creator_preference_profile` (confidence > 0)
5. `market_optimization_intelligence` (available = true)
6. `variant_evaluation` (available = true)

`confidence = available_signals / 6`. Missing subsystems lower confidence proportionally.

### Output shape

```json
{
  "render_quality_v2": {
    "subtitle_score": 86,
    "camera_score": 88,
    "hook_score": 85,
    "creator_fit": 89,
    "market_fit": 83,
    "strategy_fit": 70,
    "overall": 87,
    "confidence": 0.86,
    "reasoning": [
      "Subtitle readability, camera stability, and hook strength are well balanced",
      "Creator preference alignment is strong",
      "Hook strength supports retention for the selected market"
    ]
  }
}
```

### Fallback (all inputs missing)

```json
{
  "render_quality_v2": {
    "subtitle_score": 0,
    "camera_score": 0,
    "hook_score": 0,
    "creator_fit": 0,
    "market_fit": 0,
    "strategy_fit": 0,
    "overall": 0,
    "confidence": 0.0,
    "reasoning": []
  }
}
```

### Metadata sources consumed

- Phase 51B: `variant_evaluation` — confidence, best_variant_id (for strategy_fit)
- Phase 51C: `best_strategy_reasoning` — recommendation_strength, confidence (for strategy_fit)
- Phase 52A: `subtitle_quality_v2` — overall, creator_fit, safe_zone_fit
- Phase 52B: `camera_quality_v2` — overall, creator_fit
- Phase 52C: `hook_quality_v2` — overall, creator_fit, market_fit
- Phase 44: `market_optimization_intelligence` — available, confidence (market_fit supplement)
- Phase 46: `creator_preset_evolution` — available, evolved_presets (creator_fit supplement)
- Phase 50D: `creator_preference_profile` — confidence (creator_fit supplement)

### Files introduced / modified

| File | Purpose |
|---|---|
| `app/ai/unified_quality/__init__.py` | Package marker |
| `app/ai/unified_quality/unified_quality_schema.py` | `UnifiedQualityV2` dataclass + `SCORE_WEIGHTS` + fallback |
| `app/ai/unified_quality/unified_quality_scorer.py` | 6 deterministic dimension scorers + confidence |
| `app/ai/unified_quality/unified_quality_evaluator.py` | `evaluate_unified_quality_v2()` public API + reasoning |
| `app/ai/director/edit_plan_schema.py` | `render_quality_v2: dict` field added |
| `app/ai/director/ai_director.py` | Phase 52D block + `_attach_unified_quality_v2()` |
| `app/ai/director/render_influence.py` | `_report_render_quality_v2()` reporting |
| `tests/test_ai_phase52d_unified_quality_v2.py` | 82 tests across 11 classes |

### Data flow

- **Reads from:** `subtitle_quality_v2` (52A), `camera_quality_v2` (52B), `hook_quality_v2` (52C), `variant_evaluation` (51B), `best_strategy_reasoning` (51C), `market_optimization_intelligence` (44), `creator_preset_evolution` (46), `creator_preference_profile` (50D)
- **Writes to:** `plan.render_quality_v2`
- **Runs after:** Phase 52C (last in Phase 52 quality series)
- **Future consumers:** UI unified quality dashboard, creator analytics, render decision support

### Render influence reporting

Phase 52D always reports to `report["skipped"]` — evaluation advisory metadata only.

```
render_quality_v2:evaluated_phase52d(overall=87,confidence=0.86,subtitle=86,camera=88,hook=85,...)
render_quality_v2:no_result_phase52d
render_quality_v2:no_signal_phase52d
```

### Safety boundaries (still intentionally blocked)

❌ No render mutation
❌ No hook rewriting
❌ No subtitle mutation
❌ No motion_crop rewrite
❌ No FFmpeg mutation
❌ No render pipeline rewrite
❌ No playback_speed mutation
❌ No executor override
❌ No autonomous execution
❌ No cloud AI / external API required
❌ No GPU required

### Backward compatibility

- All Phase 1–52C behaviour preserved
- `AIEditPlan.render_quality_v2` defaults to `{}` — backward compatible
- Evaluation runs automatically when AI Director is enabled
- No new required request fields
- All existing quality fields (Phase 45 `render_quality_evaluation`) unchanged
- Phase 52A/B/C subsystem fields unchanged — this phase reads them, never rewrites them

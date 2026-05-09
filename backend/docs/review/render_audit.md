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

# Render System — Full Architecture Audit

> **Living document.** Original audit generated 2026-05-07. Patch notes appended below.
> All findings are grounded in actual file content with exact line references.

---

## Patch Status Log
---

### 2026-05-12 — AI Intelligence v2 Phase 55E: Platform-Aware Render Strategy

**Implemented:**

- `app/ai/knowledge/platform_render_strategy_schema.py` (new) — `AIPlatformRenderStrategy` dataclass; explicit allowed-value frozensets for all four strategy domains (subtitle, camera, hook, ranking); `_normalize()` helper that maps any invalid value to `"unknown"`; `_sanitize_strategy()` strips forbidden execution keys from nested dicts; `_fallback_strategy()` returns valid available=False dict; `to_dict()` clamps confidence [0, 1], caps reasoning at 8 lines
- `app/ai/knowledge/platform_render_strategy_engine.py` (new) — `build_platform_render_strategy(plan)` public API; accepts AIEditPlan or dict via duck-typed `_get()`; reads `platform_context` (55A), `platform_subtitle_context` (55B), `platform_camera_context` (55C), `platform_hook_context` (55D), `creator_preference_profile` (50D), `render_quality_v2` (52D); fuses all four domain strategies with deterministic conflict resolution; never raises — fallback-safe
- `app/ai/director/edit_plan_schema.py` (updated) — `platform_render_strategy: dict = field(default_factory=dict)` added after Phase 55D field; included in `to_dict()`; backward-compatible
- `app/ai/director/ai_director.py` (updated) — Phase 55E block inserted after Phase 55D hook context; `_attach_platform_render_strategy(plan, job_id)` imports `build_platform_render_strategy` and attaches result to `plan.platform_render_strategy`; wrapped in try/except; never blocks render
- `tests/test_ai_phase55e_platform_render_strategy.py` (new) — 104 tests covering schema allowed-value sets, normalization, fallback shape, full fusion structure, TikTok+podcast conflict, YouTube Shorts+educational strategy, TikTok+viral_short_form (no conflict), missing platform fallback, missing creator profile, deterministic output, confidence computation, garbage-input normalization, safety key scanning, edit plan backward compatibility, duck-typed object acceptance

**What Phase 55E adds:**

- Unified platform-aware render strategy that fuses Phases 55A–55D platform contexts
- Deterministic conflict resolution between platform guidance and creator style preference
- Explicit allowed-value enforcement across all four strategy domains
- Creator-safe conservative conflict resolution (trust/clarity creators always get stable framing and clean subtitles regardless of platform energy pressure)
- Strategy output informing orchestrator reasoning, variant evaluation, and AI UX explanation

**Platform render strategy shape:**

```json
{
  "platform_render_strategy": {
    "available": true,
    "platform": "tiktok",
    "creator_type": "podcast",
    "strategy": {
      "subtitle": {
        "style_bias": "clean_pro",
        "density_bias": "compact",
        "keyword_emphasis": "selective",
        "readability_priority": "high"
      },
      "camera": {
        "motion_energy": "low_medium",
        "stability_priority": "high",
        "crop_aggressiveness": "low",
        "jitter_sensitivity": "high"
      },
      "hook": {
        "first_3s_priority": "high",
        "retention_priority": "high",
        "hook_energy": "moderate",
        "curiosity_style": "soft_direct"
      },
      "ranking": {
        "priority": "retention_creator_fit"
      }
    },
    "confidence": 0.8333,
    "reasoning": [
      "TikTok platform guidance supports strong early retention while podcast creator style keeps framing stable and subtitles clean.",
      "Platform subtitle guidance supports compact density with clean_pro style.",
      "Platform camera guidance supports low_medium motion energy and high stability priority.",
      "Platform hook guidance sets moderate hook energy with high first-3-second priority.",
      "Strategy balances TikTok retention pressure with podcast trust-focused style.",
      "Strategy prioritizes retention creator fit in variant ranking."
    ]
  }
}
```

**Fallback shape:**

```json
{
  "platform_render_strategy": {
    "available": false,
    "platform": "",
    "creator_type": "",
    "strategy": {},
    "confidence": 0.0,
    "reasoning": []
  }
}
```

**Conflict resolution behavior:**

| Scenario | Platform signal | Creator signal | Resolution |
|---|---|---|---|
| TikTok + podcast | high motion energy, viral style | stable, trust, clean | `motion_energy=low_medium`, `style_bias=clean_pro`, `hook_energy=moderate`, `curiosity_style=soft_direct`, `ranking=retention_creator_fit` |
| TikTok + podcast (camera) | high crop aggressiveness | trust creator safety | `crop_aggressiveness=low`, `stability_priority=high` |
| YouTube Shorts + educational | medium motion, balanced density | clarity, readability | `motion_energy=low_medium`, `style_bias=clean_pro`, `ranking=retention_creator_fit` |
| TikTok + viral_short_form | high energy, direct hook | viral creator, no conflict | `hook_energy=high`, `curiosity_style=direct`, `motion_energy=medium_high`, `ranking=retention` |
| Instagram Reels + any | boxed caption default | creator may override style | subtitle style respect creator-safe rules |

**Allowed values enforced per domain:**

| Domain | Field | Allowed set |
|---|---|---|
| subtitle | `style_bias` | `viral_bold`, `clean_pro`, `boxed_caption`, `unknown` |
| subtitle | `density_bias` | `compact`, `balanced`, `dense`, `unknown` |
| subtitle | `keyword_emphasis` | `none`, `selective`, `moderate`, `strong`, `unknown` |
| subtitle | `readability_priority` | `high`, `medium`, `low`, `unknown` |
| camera | `motion_energy` | `low`, `low_medium`, `medium`, `medium_high`, `high`, `unknown` |
| camera | `stability_priority` | `low`, `medium`, `medium_high`, `high`, `unknown` |
| camera | `crop_aggressiveness` | `low`, `medium`, `high`, `unknown` |
| camera | `jitter_sensitivity` | `high`, `medium`, `low`, `unknown` |
| hook | `first_3s_priority` | `low`, `medium`, `high`, `unknown` |
| hook | `retention_priority` | `low`, `medium`, `high`, `unknown` |
| hook | `hook_energy` | `low`, `moderate`, `high`, `unknown` |
| hook | `curiosity_style` | `subtle`, `soft_direct`, `direct`, `open_loop`, `unknown` |
| ranking | `priority` | `creator_fit`, `retention`, `hook_strength`, `readability`, `retention_creator_fit`, `balanced`, `unknown` |

**Confidence fusion:**

- Average of all available domain context confidences (55A–55D)
- Falls back to 0.5 if platform or creator_type is known but no context confidence available
- Falls back to 0.0 if no context and no platform/creator_type known
- Always clamped [0, 1]

**Advisory-only strategy contract:**

- Strategy informs orchestrator reasoning, variant evaluation, and AI UX explanation
- Strategy must NOT execute rendering
- Strategy must NOT override executor authority
- Strategy must NOT mutate the render pipeline
- `direct_execution`, `executor_override`, `ffmpeg_args`, `render_command`, `subtitle_timing`, `motion_crop`, `tracking_config`, `clip_boundaries`, `playback_speed`, `subprocess`, `executable`, `python_code`, `shell`, `transcript`, `hook_rewrite`, `crop_coordinates`, `output_path`, `queue_priority` — all stripped/blocked from output

**Fallback behavior:**

| Missing input | Result |
|---|---|
| No platform, no creator_type, no domain contexts | `available=False`, empty strategy |
| Platform known but no domain contexts | `available=True`, strategy from platform rules, confidence=0.5 |
| Creator_type known but no domain contexts | `available=True`, strategy from creator rules, confidence=0.5 |
| Malformed guidance values | Normalized to `"unknown"`, then rule-based default applied |
| None input to engine | Fallback dict returned, no crash |
| Empty dict input | Fallback dict returned, no crash |

**Integration points:**

- Runs after Phase 55D (platform_hook_context) so all platform domain contexts are populated
- Reads from `plan.platform_context`, `plan.platform_subtitle_context`, `plan.platform_camera_context`, `plan.platform_hook_context`, `plan.creator_preference_profile`, `plan.render_quality_v2`
- Does not call retrievers again — works entirely from plan metadata
- Preserved for future orchestrator consumption, strategy variant evaluation, and AI UX reasoning

**Safety boundaries enforced:**

- Strategy is metadata-only
- No payload mutation
- No render execution
- No FFmpeg mutation
- No subtitle timing rewrite
- No motion_crop rewrite
- No executor override
- No queue mutation
- No subprocess execution
- No internet access
- No API key required
- No autonomous execution

**Forbidden fields stripped/rejected:**

`ffmpeg_args`, `render_command`, `subtitle_timing`, `motion_crop`, `tracking_config`, `clip_boundaries`, `playback_speed`, `subprocess`, `executable`, `python_code`, `shell`, `transcript`, `hook_rewrite`, `crop_coordinates`, `direct_execution`, `executor_override`, `output_path`, `queue_priority`

**Architecture notes:**

- Phase 55E is the synthesis layer of the platform intelligence stack (55A–55E)
- Fused strategy resolves conflicts between platform pressure and creator safety before reaching orchestrator
- Conservative-first resolution ensures creator trust and clarity creators are never pushed into aggressive high-energy modes by platform signals
- Strategy uses duck-typed plan access so it works with both AIEditPlan objects and plain dicts in test/integration contexts
- Stable render executor remains final authority — strategy is purely advisory

**Intentionally still blocked:**

- Live internet scraping
- Autonomous crawling
- Model fine-tuning
- FFmpeg command mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Direct crop-coordinate rewrite
- Segment reorder
- Executor override
- Queue mutation
- Autonomous publishing

**Verification:**

- Phase 55E tests: 104 passed
- Full suite: 4744 passed, 1 skipped
- `py_compile` passed on all changed modules

---

### 2026-05-14 — Phase 59A: Subtitle Influence Promotion (first safe execution layer)

**Implemented:**

- `app/ai/subtitle_promotion/subtitle_promotion_engine.py` (new) — `promote_subtitle_influence(payload, edit_plan, context)` public API; promotes advisory subtitle signals to actual render config fields; never raises
- `app/ai/subtitle_promotion/__init__.py` (new) — package marker
- `app/ai/director/edit_plan_schema.py` (updated) — `subtitle_execution_promotion: dict` field added for promotion result storage; included in `to_dict()`
- `app/ai/director/render_influence.py` (updated) — `_apply_subtitle_promotion()` wired into `apply_ai_render_influence()` between subtitle influence and pacing; imports promotion engine, stores report on `edit_plan.subtitle_execution_promotion`, appends to `report["applied"]` / `report["skipped"]`
- `tests/test_ai_phase59a_subtitle_promotion.py` (new) — 32 tests

**What Phase 59A is:**

Phase 59A is the first *safe execution promotion* layer in the AI pipeline. All prior phases (10–57) produce advisory metadata that never touches the render pipeline. Phase 59A promotes two fields only:

| Field | Promotion action | When |
|---|---|---|
| `payload.subtitle_style` | Set to allowed preset | `add_subtitle=True`, user hasn't locked style, confidence ≥ 0.80 |
| `payload.highlight_per_word` | Enable (set to `True`) | Not already enabled, confidence ≥ 0.78, emphasis signal present |

**Allowed subtitle presets (promotion targets):**

Only these three canonical preset IDs may be promoted to `payload.subtitle_style`:
- `viral_bold` — full-screen bold, designed for word-level bounce
- `clean_pro` — minimal professional caption
- `boxed_caption` — opaque background box, block subtitles

Any other value (including Phase 50C outputs not in this set) is silently ignored.

**Signal priority for preset resolution:**

1. Phase 50C `creator_subtitle_influence.preset_bias` (most creator-specific)
2. Phase 55E `platform_render_strategy.strategy.subtitle.style_bias`
3. Phase 56 `platform_strategy_influence.subtitle.bias.style`
4. Phase 50A `creator_subtitle_preference.subtitle_preference.style` (broadest signal)

**Confidence gating:**

- `effective_conf = max(pref_conf, prs_conf)` where `prs_conf` is only read when `platform_render_strategy.available = True`
- Preset promotion requires `effective_conf >= 0.80`
- Emphasis promotion requires `effective_conf >= 0.78`

**User override rules:**

| Condition | Behavior |
|---|---|
| `subtitle_ai_style_lock = True` | No promotion — user has locked style |
| `subtitle_style` not in `{"pro_karaoke", None, ""}` | No promotion — user explicitly chose a style |
| `subtitle_style` in neutral set | Promotion eligible |
| `highlight_per_word` already `True` | No change (AI only enables, never disables) |

The neutral set `{"pro_karaoke", None, ""}` treats the schema default `"pro_karaoke"` as "no explicit user preference," because the schema field defaults to `"pro_karaoke"` and there is no reliable way to distinguish that from an explicit user choice without the `subtitle_ai_style_lock` flag.

**Density — advisory only:**

No direct density field exists on `RenderRequest`. Density bias from Phase 50C / Phase 50A is stored in the promotion report's `density_applied` field as an advisory recommendation but does NOT mutate any payload field.

**Promotion report shape:**

```json
{
  "subtitle_execution_promotion": {
    "applied": true,
    "preset_applied": "viral_bold",
    "density_applied": "medium",
    "keyword_emphasis_applied": true,
    "confidence": 0.8500,
    "reason": "promotion_applied",
    "reasoning": [
      "Creator subtitle influence recommended 'viral_bold' style",
      "Promoted preset 'viral_bold' is designed for word-level highlighting"
    ]
  }
}
```

**Safety contract enforced:**

| Boundary | Status |
|---|---|
| No subtitle timing rewrite | ✅ |
| No ASS generation rewrite | ✅ |
| No segmentation rewrite | ✅ |
| No transcript mutation | ✅ |
| No new subtitle preset generation | ✅ |
| No FFmpeg mutation | ✅ |
| No render pipeline rewrite | ✅ |
| No playback_speed mutation | ✅ |
| No executor override | ✅ |
| Only promotes from AI-neutral default style | ✅ |
| Preset validated against ALLOWED_PROMOTION_PRESETS | ✅ |
| Confidence gates enforced before any mutation | ✅ |
| Deterministic: same inputs → same output | ✅ |
| User override respected | ✅ |
| Never raises — fallback-safe on any error | ✅ |

**Fallback behavior:**

| Condition | Result |
|---|---|
| `add_subtitle = False` | No promotion, reason `subtitles_disabled` |
| `edit_plan = None` | No promotion, reason `no_edit_plan` |
| `subtitle_ai_style_lock = True` | No promotion, reason `user_override` |
| `subtitle_style` not neutral | No promotion, reason `user_override` |
| Confidence below threshold | No promotion, reason `no_eligible_promotion` |
| Any exception inside engine | Caught, fallback report returned, reason `promotion_error` |

**Verification:**

- Phase 59A tests: 32 passed
- `py_compile` passed on all changed modules
- `git diff --check` clean

---

### 2026-05-14 — Phase 59B: Camera Influence Promotion (second safe execution layer)

**Implemented:**

- `app/ai/camera_promotion/camera_promotion_engine.py` (new) — `promote_camera_influence(payload, edit_plan, context)` public API; promotes advisory camera signals to actual render config fields; quality-gated; never raises
- `app/ai/camera_promotion/__init__.py` (new) — package marker
- `app/ai/director/edit_plan_schema.py` (updated) — `camera_execution_promotion: dict` field added after Phase 59A field; included in `to_dict()`; backward-compatible
- `app/ai/director/render_influence.py` (updated) — `_apply_camera_promotion()` wired immediately after `_apply_camera_influence()`; imports promotion engine, stores report on `edit_plan.camera_execution_promotion`, appends to `report["applied"]` / `report["skipped"]`
- `tests/test_ai_phase59b_camera_promotion.py` (new) — 41 focused tests

**What Phase 59B is:**

Phase 59B is the second *safe execution promotion* layer. It promotes camera intelligence from Phases 50B, 55E, and 56 into two `RenderRequest` fields:

| Field | Promotion action | When |
|---|---|---|
| `payload.reframe_mode` | `"center"` → `"motion"` / `"subject"` / `"face"` | AI flags enabled, user hasn't overridden, confidence ≥ 0.82 |
| `payload.motion_aware_crop` | Enable (set to `True`) | Not already enabled, reframe eligible, confidence ≥ 0.85, quality gates pass |

**Allowed reframe mode promotion targets:**

- `motion` — dynamic subject following (high motion energy)
- `subject` — stable subject tracking (smooth subject, moderate energy)
- `face` — face-lock cropping

`"center"` is the neutral default — AI promotes FROM it, never TO it.

**Signal priority for reframe_mode resolution:**

1. Phase 50B `creator_camera_preference.camera_preference.motion_style` (most creator-specific)
   - `smooth_subject` → `subject`
   - `dynamic_subject` → `motion`
   - `static_center` → no change
2. Phase 55E `platform_render_strategy.strategy.camera.motion_energy` (requires `available=True`)
   - `high` / `medium_high` → `motion`
   - `medium` / `low_medium` → `subject`
   - `low` → no change
3. Phase 56 `platform_strategy_influence.camera.bias.motion_energy`

**Confidence gating:**

- `effective_conf = max(pref_conf, prs_conf)` where `prs_conf` is only read when `platform_render_strategy.available = True`
- Reframe promotion requires `effective_conf >= 0.82`
- motion_aware_crop requires `effective_conf >= 0.85`
- Advisory tuning requires `effective_conf >= 0.80`

**User override rules:**

| Condition | Behavior |
|---|---|
| `camera_ai_reframe_lock = True` | No promotion — user locked reframe |
| `reframe_mode` not in `{"center", None, ""}` | No promotion — user explicitly chose a mode |
| `reframe_mode` in neutral set | Promotion eligible |
| `motion_aware_crop` already `True` | Kept; AI only enables, never disables |

**Quality gates:**

| Risk signal | Source | Trigger | Effect |
|---|---|---|---|
| `micro_jitter_risk >= 60` | `camera_quality_v2` (Phase 52B) | High jitter detected | Downgrade `motion` → `subject`; block `motion_aware_crop`; scale tuning × 0.5 |
| `whip_pan_risk >= 60` | `camera_quality_v2` (Phase 52B) | High whip-pan detected | Block `motion_aware_crop`; block all advisory tuning |
| `camera_fit <= 30` (available=True) | `platform_quality_feedback` (Phase 57) | Low platform camera fit | Downgrade `motion` → `subject` (same as jitter flag) |

Quality gates NEVER force risky changes — they only restrict or downgrade.

**Tuning — advisory only (no payload mutation):**

MotionCropConfig parameters (deadzone, EMA alpha, hold_frames) do not exist on `RenderRequest`. Phase 59B reads `creator_camera_preference.tuning_pack` and stores bounded deltas in the promotion report's `tuning_applied` dict — no payload field is mutated.

| Parameter | Hard bound | Source |
|---|---|---|
| `deadzone_delta` | ±0.05 | Phase 50B tuning_pack |
| `smoothing_delta` | ±0.08 | Phase 50B ema_alpha_delta |
| `subject_hold_delta` | ±12 frames | Phase 50B hold_frames_delta |
| `crop_aggressiveness` | advisory label only | Phase 50B camera_preference |

**Promotion report shape:**

```json
{
  "camera_execution_promotion": {
    "applied": true,
    "reframe_mode_applied": "subject",
    "motion_aware_crop_applied": true,
    "tuning_applied": {
      "deadzone_delta": 0.03,
      "smoothing_delta": 0.05,
      "subject_hold_delta": 6,
      "crop_aggressiveness": "medium"
    },
    "confidence": 0.8800,
    "reason": "promotion_applied",
    "reasoning": [
      "Creator camera preference motion_style='smooth_subject' → reframe='subject'",
      "Reframe mode 'subject' justifies motion-aware crop with conf=0.880",
      "Advisory tuning: deadzone_delta=0.03, smoothing_delta=0.05, subject_hold_delta=6, crop_aggressiveness=medium"
    ]
  }
}
```

**Safety contract enforced:**

| Boundary | Status |
|---|---|
| No motion_crop algorithm rewrite | ✅ |
| No tracking logic rewrite | ✅ |
| No scene detection rewrite | ✅ |
| No FFmpeg mutation | ✅ |
| No render pipeline rewrite | ✅ |
| No playback_speed mutation | ✅ |
| No executor override | ✅ |
| No new reframe mode generation | ✅ |
| Only promotes from AI-neutral default ("center") | ✅ |
| Reframe validated against ALLOWED_PROMOTION_MODES | ✅ |
| Confidence gates enforced before any mutation | ✅ |
| Quality gates block risky promotions | ✅ |
| User override respected | ✅ |
| motion_aware_crop enable-only (never disabled) | ✅ |
| Tuning deltas bounded by hard limits | ✅ |
| Deterministic: same inputs → same output | ✅ |
| Never raises — fallback-safe on any error | ✅ |

**Fallback behavior:**

| Condition | Result |
|---|---|
| `ai_director_enabled = False` | No promotion, reason `ai_director_disabled` |
| `ai_render_influence_enabled = False` | No promotion, reason `ai_render_influence_disabled` |
| `edit_plan = None` | No promotion, reason `no_edit_plan` |
| `camera_ai_reframe_lock = True` | No promotion, reason `user_override` |
| `reframe_mode` not neutral | No promotion, reason `user_override` |
| Confidence below threshold | No promotion, reason `no_eligible_promotion` |
| Any exception inside engine | Caught, fallback report returned, reason `promotion_error` |

**Real render config impact:**

Before Phase 59B: `payload.reframe_mode` always stayed as the frontend-set value (default `"center"`). Motion-aware crop required explicit user toggle. Camera intelligence from 50B/55E was metadata only.

After Phase 59B: For creators with `smooth_subject` / `dynamic_subject` preference and ≥0.82 confidence, the render automatically uses subject or motion tracking reframe. For ≥0.85 confidence with no quality risks, motion_aware_crop (OpenCV optical-flow pre-pass) is also enabled for frame-accurate crop execution.

**Verification:**

- Phase 59B tests: 41 passed
- Full suite: 5028 passed, 1 skipped
- `py_compile` passed on all changed modules

---

### 2026-05-14 — Phase 59C: Segment Selection Promotion (first safe AI clip selection)

**Implemented:**

- `app/ai/segment_promotion/segment_promotion_engine.py` (new) — `promote_segment_selection(scored, edit_plan, payload, context)` public API; reorders the render pipeline's `scored` list to put AI-endorsed segments first; overlap-based matching; never raises
- `app/ai/segment_promotion/__init__.py` (new) — package marker
- `app/ai/director/edit_plan_schema.py` (updated) — `segment_selection_promotion: dict` field added after Phase 59B field; included in `to_dict()`; backward-compatible
- `app/orchestration/render_pipeline.py` (updated) — Phase 59C block inserted between beat execution and the `for idx, seg in enumerate(scored)` loop (injection window lines ~1914–1916); calls `promote_segment_selection`, stores report on `_ai_edit_plan.segment_selection_promotion`, emits render event
- `tests/test_ai_phase59c_segment_promotion.py` (new) — 36 focused tests

**What Phase 59C is:**

Phase 59C is the first AI execution promotion that affects **which clips are rendered and in what order**. Prior phases (59A/59B) modified payload config fields (subtitle_style, reframe_mode). Phase 59C modifies the **segment render list** itself.

**Promotion mechanism:**

The render pipeline builds `scored` (a list of scene-based segment dicts) from scene detection before the AI Director runs. Phase 59C compares AI `selected_segments` (transcript-based time windows) against the `scored` list using **overlap matching**, then **reorders** `scored` to put AI-endorsed segments first.

No new segments are created. No timestamps are modified. The existing dicts are just rearranged.

**Injection point:**

`render_pipeline.py` — after beat execution block, before `for idx, seg in enumerate(scored, start=1)`. This is the last possible moment to modify `scored` before it is committed to the DB as job parts.

**Overlap matching algorithm:**

A `scored` segment is "AI endorsed" if any valid AI segment overlaps it by:
- ≥ 1.0 second absolute overlap (`_MIN_OVERLAP_SECONDS`)
- ≥ 5% of the scored segment's duration (`_MIN_OVERLAP_RATIO`)

The scored segment receives the endorsement score = max AI score of all overlapping AI segments (normalized to 0–1). Endorsed segments are sorted by endorsement score descending, then non-endorsed segments follow in their original order.

**Confidence gate:**

- `effective_conf = mean(normalize(ai_seg.score) for ai_seg in valid_ai_segs)`
- Score normalization: values > 1.0 treated as 0–100 scale (÷ 100); values ≤ 1.0 treated as 0–1 scale
- Promotion requires `effective_conf >= 0.80`

**Segment validation (every AI segment checked):**

| Check | Rule |
|---|---|
| Start bound | `start >= 0.0` |
| End bound | `end > start` |
| Not NaN | `not math.isnan(start or end)` |
| Not Inf | `not math.isinf(start or end)` |
| Not None | start and end must be numeric |

Invalid AI segments are silently skipped. If ALL AI segments are invalid → fallback.

**Safety gates:**

| Condition | Behavior |
|---|---|
| `ai_director_enabled = False` | No promotion, reason `ai_director_disabled` |
| `ai_render_influence_enabled = False` | No promotion, reason `ai_render_influence_disabled` |
| `segment_ai_lock = True` | No promotion, reason `user_override:segment_ai_lock=true` |
| `edit_plan = None` | No promotion, reason `no_edit_plan` |
| `selected_segments` empty | No promotion, reason `no_selected_segments` |
| All AI segments invalid | No promotion, reason `no_valid_ai_segments` |
| `effective_conf < 0.80` | No promotion, reason `low_confidence` |
| No overlap found | No promotion, reason `no_overlap_found` |
| Any exception | Caught, original `scored` returned, pipeline continues |

**Promotion report shape:**

```json
{
  "segment_selection_promotion": {
    "applied": true,
    "selected_count": 2,
    "total_count": 4,
    "source": "ai_selected_segments",
    "confidence": 0.8600,
    "reason": "promotion_applied",
    "reasoning": [
      "AI endorsed 2/4 segments (mean_conf=0.860)",
      "2 non-endorsed segment(s) preserved at end",
      "Reorder only — no segments dropped"
    ],
    "fallback_used": false
  }
}
```

**Safety contract enforced:**

| Boundary | Status |
|---|---|
| No new timestamp generation | ✅ |
| No segment dict mutation | ✅ |
| No ffmpeg mutation | ✅ |
| No subtitle timing rewrite | ✅ |
| No ASS generation rewrite | ✅ |
| No motion_crop rewrite | ✅ |
| No playback_speed mutation | ✅ |
| No executor override | ✅ |
| Reorder only — existing segments preserved intact | ✅ |
| Overlap-validated matching only | ✅ |
| Confidence gate enforced before any reorder | ✅ |
| Original scored list returned unchanged on gate failure | ✅ |
| Final list never shorter than _MIN_FINAL_SEGMENTS | ✅ |
| Deterministic: same inputs → same output | ✅ |
| Never raises | ✅ |

**Real render impact:**

Before Phase 59C: `selected_segments` was advisory metadata only. Render always used the score-sorted output of scene detection regardless of AI transcript intelligence.

After Phase 59C: When AI director confidence ≥ 0.80 and AI segments overlap with scored segments, the AI-endorsed segments move to the front of the render queue (part_001, part_002, ...). This means:
- Platform delivery order prioritizes AI-selected content
- First export (most commonly used single-clip export) is the AI-recommended clip
- All clips still rendered (no content is dropped)

**Verification:**

- Phase 59C tests: 36 passed
- Full suite: 5064 passed, 1 skipped
- `py_compile` passed on all changed modules

---

### 2026-05-14 — AI Intelligence v2 Phase 60A: AI Influence Metrics & Telemetry

**Implemented:**

- `app/ai/metrics/__init__.py` (new) — package marker
- `app/ai/metrics/ai_execution_metrics_engine.py` (new) — `build_ai_execution_metrics(edit_plan, payload, context)` reads stored promotion reports from Phases 59A–59D and produces compact, deterministic telemetry; no side-effects, no mutations, never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `ai_execution_metrics: dict` and `ai_execution_summary: dict` fields added; included in `to_dict()`
- `app/orchestration/render_pipeline.py` (updated) — Phase 60A metrics block injected after Phase 59D segment gate, before the DB commit loop; stores results on `edit_plan.ai_execution_metrics` and `edit_plan.ai_execution_summary`; logs structured summary at INFO level
- `tests/test_ai_phase60a_execution_metrics.py` (new) — 27 tests including 5 required execution tests

**What Phase 60A adds:**

Phase 60A is observability-only. Zero render behavior change. It reads the promotion reports already written by Phases 59A–59D and computes answerable metrics about what actually happened.

**Questions now answerable:**
- Did AI subtitle promotion apply? Was it blocked by the quality gate?
- Did camera reframe promotion apply? Did whip-pan protection trigger?
- Did segment reordering apply? Did hook-fatigue fallback trigger?
- Did the user override any AI domain?
- What was the overall AI assistance level for this render?

**Telemetry shape — `ai_execution_metrics`:**

```json
{
  "ai_execution_metrics": {
    "subtitle": {
      "eligible":     true,
      "applied":      true,
      "blocked":      false,
      "fallback_used": false,
      "reason":       "promotion_applied",
      "confidence":   0.87
    },
    "camera": {
      "eligible":        true,
      "applied":         false,
      "blocked":         true,
      "reframe_applied": null,
      "crop_applied":    false,
      "tuning_applied":  false,
      "fallback_used":   true,
      "reason":          "promotion_applied",
      "confidence":      0.83
    },
    "segment": {
      "eligible":       true,
      "applied":        true,
      "blocked":        false,
      "selected_count": 3,
      "total_count":    5,
      "fallback_used":  false,
      "reason":         "promotion_applied",
      "confidence":     0.86
    },
    "quality_gate": {
      "subtitle_blocked":     false,
      "camera_blocked":       true,
      "segment_blocked":      false,
      "subtitle_gate_action": "no_change",
      "camera_gate_action":   "block_aggressive_motion",
      "segment_gate_action":  "allow_ai_selected_segments"
    },
    "user_override": {
      "subtitle": false,
      "camera":   false,
      "segment":  false
    },
    "confidence": 0.853
  }
}
```

**Telemetry shape — `ai_execution_summary`:**

```json
{
  "ai_execution_summary": {
    "subtitle_apply":        true,
    "camera_apply":          false,
    "segment_apply":         true,
    "quality_gate_blocks":   1,
    "user_override_count":   0,
    "overall_ai_assistance": "medium"
  }
}
```

**`overall_ai_assistance` values:**
| Applied domains | Level |
|-----------------|-------|
| 0 | `"none"` |
| 1 | `"low"` |
| 2 | `"medium"` |
| 3 | `"high"` |

**`eligible` vs `applied` distinction:**
- `eligible=true`: the AI system was active and attempted to evaluate this domain (no system-level disables)
- `applied=true`: the promotion ran AND was not reverted by the quality gate (net applied)
- `blocked=true`: the quality gate reverted a promotion that had been applied
- `user_override=true`: the user explicitly disabled AI for this domain via a lock flag

**Execution order in render_pipeline.py:**

```
apply_ai_render_influence()          ← 59A + 59B + 59D subtitle/camera gate
Phase 59C segment promotion
Phase 59D segment quality gate
Phase 60A metrics collection         ← reads all four above, no mutations
for idx, seg in enumerate(scored)    ← DB commit loop
```

**Safety contract:**
- No render mutation, no payload change, no influence change
- Never raises — returns fallback metrics on any error
- Reads only: `edit_plan.subtitle_execution_promotion`, `camera_execution_promotion`, `segment_selection_promotion`, `quality_gated_influence`
- Bounded output: compact metadata dicts only

**Verification:**

- Phase 60A focused tests: 27 passed (including 5 required execution tests)
- Full suite: 5114 passed, 1 skipped
- `py_compile` passed on all changed modules

---

### 2026-05-14 — AI Intelligence v2 Phase 60B: A/B Render Evaluation

**Implemented:**

- `app/ai/ab_evaluation/__init__.py` (new) — package marker
- `app/ai/ab_evaluation/ab_evaluation_engine.py` (new) — `build_ab_evaluation(edit_plan, baseline, context)` compares AI-ON candidate render quality against an optional AI-OFF baseline; supports two modes (full comparison with baseline / candidate-summary without baseline); never raises, no render mutation
- `app/ai/director/edit_plan_schema.py` (updated) — `ai_ab_evaluation: dict` field added after Phase 60A fields; included in `to_dict()`
- `app/orchestration/render_pipeline.py` (updated) — Phase 60B block injected after Phase 60A metrics; passes `baseline=None` since single renders have no stored baseline; stores result on `edit_plan.ai_ab_evaluation`
- `tests/test_ai_phase60b_ab_evaluation.py` (new) — 26 tests including 3 required execution tests

**What Phase 60B adds:**

Phase 60B is evaluation-only. No automatic rerender, no render behavior change. It reads quality metadata populated by Phases 52A–52D and 60A, computes per-dimension deltas, selects a winner, and generates honest creator-facing reasoning.

**Two evaluation modes:**

**Mode A — Full comparison** (baseline available):
- Computes `delta = candidate - baseline` for subtitle, camera, hook, overall
- Selects winner: `overall_delta >= +3 → ai_on`, `<= -3 → ai_off`, `-2..+2 → tie`
- Confidence = weighted blend: base(0.40) + dim coverage(0.20) + quality signal(0.20) + execution metrics(0.20)
- Returns `available=true` with full delta, winner, confidence, reasoning

**Mode B — Candidate summary only** (no baseline):
- Returns `available=false, reason="baseline_missing"`
- Returns `candidate_summary` with current quality scores
- `confidence=0.0`, `winner="unknown"`
- Never claims improvement without baseline

**Output shape — Mode A:**

```json
{
  "ai_ab_evaluation": {
    "available": true,
    "baseline":  {"label": "ai_off",  "quality": {"subtitle": 78, "camera": 80, "hook": 76, "overall": 78}},
    "candidate": {"label": "ai_on",   "quality": {"subtitle": 86, "camera": 84, "hook": 81, "overall": 84},
                  "ai_assistance_level": "high"},
    "delta":     {"subtitle": 8, "camera": 4, "hook": 5, "overall": 6},
    "winner":    "ai_on",
    "confidence": 0.82,
    "reasoning": ["AI ON improved subtitle quality (+8) vs baseline.",
                  "Overall quality improved by 6 points."]
  }
}
```

**Output shape — Mode B:**

```json
{
  "ai_ab_evaluation": {
    "available": false,
    "reason":    "baseline_missing",
    "candidate_summary": {
      "label":               "ai_on",
      "quality":             {"subtitle": 84, "camera": 82, "hook": 79, "overall": 82},
      "ai_assistance_level": "medium"
    },
    "baseline":   {},
    "candidate":  {},
    "delta":      {},
    "winner":     "unknown",
    "confidence": 0.0,
    "reasoning":  ["Baseline missing — A/B winner cannot be determined."]
  }
}
```

**Winner selection thresholds:**
| overall_delta | Winner |
|---------------|--------|
| >= +3 | `ai_on` |
| -2 to +2 | `tie` (dead-band) |
| <= -3 | `ai_off` |
| no comparable data | `unknown` |

**Baseline input shapes supported:**
- Shape A (flat): `{"quality": {"subtitle": int, "camera": int, "hook": int, "overall": int}, "label": "ai_off"}`
- Shape B (raw): `{"render_quality_v2": {...}, "subtitle_quality_v2": {...}, "camera_quality_v2": {...}, "hook_quality_v2": {...}}`

**Execution order in render_pipeline.py:**

```
Phase 60A metrics collection
Phase 60B A/B evaluation  ← reads candidate quality + optional baseline, no mutations
for idx, seg in enumerate(scored)  ← DB commit loop
```

**Safety contract:**
- No render mutation, no payload change, no automatic rerender
- Never raises — returns fallback on any error
- Never claims AI improvement without a valid baseline
- All scores clamped to [0, 100]; confidence clamped to [0.0, 1.0]
- Deterministic: same inputs → same output

**Verification:**

- Phase 60B focused tests: 26 passed (including 3 required execution tests)
- Full suite: 5140 passed, 1 skipped
- `py_compile` passed on all changed modules

---

### 2026-05-14 — AI Intelligence v2 Phase 59D: Quality-Gated Execution Influence

**Implemented:**

- `app/ai/quality_gate/__init__.py` (new) — package marker
- `app/ai/quality_gate/quality_gate_engine.py` (new) — Phase 59D core engine; `apply_quality_gate(payload, edit_plan, context)` handles subtitle and camera gates; `apply_segment_quality_gate(scored, scored_original, edit_plan, context)` handles segment gate; never raises; all advisory actions leave payload unchanged
- `app/ai/director/edit_plan_schema.py` (updated) — `quality_gated_influence: dict = field(default_factory=dict)` added after Phase 59C field; included in `to_dict()`
- `app/ai/director/render_influence.py` (updated) — `_apply_quality_gate()` injected after `_apply_subtitle_promotion()` (after 59A and 59B have run); stores gate result on `edit_plan.quality_gated_influence`; reverts go to `report["applied"]`, advisory/no-change go to `report["skipped"]`
- `app/orchestration/render_pipeline.py` (updated) — `_scored_original = list(scored)` saved before Phase 59C block; Phase 59D segment gate block injected after Phase 59C and before `for idx, seg in enumerate(scored)`; merges segment gate result into `edit_plan.quality_gated_influence["segment"]`
- `tests/test_ai_phase59d_quality_gate.py` (new) — 23 tests covering all gate actions for all three domains plus safety paths

**What Phase 59D adds:**

Phase 59D is a quality-signal-driven post-promotion gate. It runs AFTER Phases 59A, 59B, and 59C have applied their promotions and can revert those promotions when quality signals indicate the promotion would produce a worse result.

- **Subtitle gate**: reads `subtitle_quality_v2.keyword_emphasis_quality`, `overload_risk`, `safe_zone_fit`, `mobile_readability`
  - `block_keyword_strengthening`: `keyword_emphasis_quality < 40` → reverts `payload.highlight_per_word = False` if Phase 59A had applied it
  - `allow_density_reduction`: `overload_risk >= 60` → advisory, no revert
  - `allow_readability_bias`: `safe_zone_fit < 40` or `mobile_readability < 40` → advisory, no revert
  - `no_change`: all signals acceptable

- **Camera gate**: reads `camera_quality_v2.micro_jitter_risk`, `whip_pan_risk`
  - `block_aggressive_motion`: `whip_pan_risk >= 60` → reverts `payload.reframe_mode = "center"` when Phase 59B had set it to "motion"
  - `prefer_stability`: `micro_jitter_risk >= 60` → downgrades reframe_mode from "motion" to "subject"; advisory when already safe
  - `allow_subject_hold`: jitter risk high but reframe already safe → advisory, no revert
  - `no_change`: all signals acceptable

- **Segment gate**: reads `hook_quality_v2`, `render_quality_v2.hook_score`, `platform_quality_feedback.hook_fit`
  - `fallback_default_segments`: `hook_fatigue_risk >= 60` or `render_hook_score < 35` → reverts `scored` to `_scored_original`
  - `allow_reorder_only`: first_3s + overall both weak, or platform hook_fit low → advisory, no revert
  - `allow_ai_selected_segments`: hook quality acceptable → advisory confirmation
  - `no_change`: Phase 59C promotion was not applied, nothing to gate

**Gate execution order (render_pipeline.py):**

```
apply_ai_render_influence()          ← Phase 59A + 59B + 59D subtitle/camera gate
  └─ _apply_camera_promotion()       ← Phase 59B
  └─ _apply_subtitle_promotion()     ← Phase 59A
  └─ _apply_quality_gate()           ← Phase 59D (subtitle + camera gates)

_scored_original = list(scored)      ← snapshot before Phase 59C

Phase 59C block                      ← may reorder scored
Phase 59D segment gate block         ← may revert scored to _scored_original

for idx, seg in enumerate(scored)    ← DB commit loop
```

**Safety contract:**

- Gate actions `allow_density_reduction`, `allow_readability_bias`, `allow_subject_hold`, `allow_reorder_only`, `allow_ai_selected_segments` are advisory-only — they never mutate payload or scored
- Only `block_keyword_strengthening`, `block_aggressive_motion`, `prefer_stability`, and `fallback_default_segments` produce payload/scored mutations
- Confidence gate: quality signals with `confidence < 0.50` AND `overall == 0` are ignored (no gate applied)
- Segment gate only runs when Phase 59C `segment_selection_promotion.applied == True`
- Never raises — exception in either gate function returns original payload/scored + fallback report

**quality_gated_influence report shape:**

```json
{
  "quality_gated_influence": {
    "applied": true,
    "subtitle": {
      "gate_action": "block_keyword_strengthening",
      "reverted_fields": ["highlight_per_word"],
      "quality_signals": {"keyword_emphasis_quality": 25, "overload_risk": 20},
      "confidence": 0.85,
      "reasoning": ["keyword_emphasis_quality=25 < threshold 40"],
      "applied": true
    },
    "camera": {
      "gate_action": "no_change",
      "reverted_fields": [],
      "quality_signals": {"micro_jitter_risk": 30, "whip_pan_risk": 20},
      "confidence": 0.90,
      "reasoning": [],
      "applied": false
    },
    "segment": {
      "gate_action": "allow_ai_selected_segments",
      "reverted": false,
      "quality_signals": {"hook_fatigue_risk": 15, "hook_overall": 78},
      "confidence": 0.82,
      "reasoning": ["hook quality acceptable, AI segment selection allowed"],
      "applied": false
    }
  }
}
```

**Verification:**

- Phase 59D tests: 23 passed (including REQUIRED EXECUTION TEST: `test_execution_keyword_emphasis_blocked_by_low_quality`)
- Full suite: 5087 passed, 1 skipped
- `py_compile` passed on all changed modules

---

### 2026-05-08 — AI Productization Phase 41: Retrieval-Based Creator Intelligence

**Implemented:**
- `app/ai/retrieval/__init__.py` (new) — package marker for Phase 41 retrieval intelligence package
- `app/ai/retrieval/retrieval_schema.py` (new) — `AICreatorRetrievalMatch` dataclass and `AICreatorRetrievalPack` dataclass; compact metadata-only schema for creator pattern retrieval matches; includes subtitle/pacing/camera/retention/hook influence dictionaries; `retrieval_mode` remains `"assistive_only"`
- `app/ai/retrieval/retrieval_safety.py` (new) — retrieval sanitization and safety gates; strips forbidden execution fields; clamps confidence to `[0, 1]`; clamps retrieval_score to `[0, 100]`; rejects unsafe execution/mutation fields
- `app/ai/retrieval/retrieval_engine.py` (new) — `retrieve_creator_intelligence(edit_plan, payload=None, context=None)`; deterministic local retrieval engine using Phase 39 creator knowledge and Phase 40 creator patterns; retrieves subtitle, pacing, camera, retention, hook, and creator-style influence metadata
- `app/ai/director/edit_plan_schema.py` (updated) — `creator_retrieval: dict = field(default_factory=dict)` added to `AIEditPlan`; included in `to_dict()`; backward-compatible
- `app/ai/director/ai_director.py` (updated) — Phase 41 retrieval block added after creator knowledge/pattern metadata is available; attaches compact `creator_retrieval` metadata and explainability lines
- `app/ai/director/render_influence.py` (updated) — reports retrieval-based creator intelligence as assistive-only render influence metadata
- `tests/test_ai_phase41_retrieval_creator_intelligence.py` (new) — 72 tests covering schema, safety, retrieval engine, creator style retrieval, subtitle/pacing/camera/retention influence, no-mutation safety, edit plan integration, render influence, and environment requirements

**What Phase 41 adds:**

- Retrieval-based creator intelligence
- Creator archetype matching
- Context-aware creator pattern retrieval
- Subtitle influence retrieval
- Pacing influence retrieval
- Camera influence retrieval
- Retention influence retrieval
- Hook influence retrieval
- Assistive-only creator intelligence metadata

**Retrieval examples:**

| Clip context | Retrieved intelligence |
|-------------|------------------------|
| Viral shortform / TikTok-style | compact subtitles, fast pacing, dynamic camera, strong hook emphasis |
| Podcast / storytelling | readable subtitles, calm pacing, stable framing |
| Retention decay / dead air | reengagement patterns, silence/dead-air reduction guidance |
| Subtitle overload | compact subtitle patterns, readability-oriented subtitle influence |

**Safety boundaries enforced:**

- Retrieval is metadata-only
- `retrieval_mode` always `"assistive_only"`
- No payload mutation
- No render execution
- No FFmpeg mutation
- No playback_speed mutation
- No subtitle timing rewrite
- No executor override
- No queue mutation
- No subprocess execution
- No internet access
- No API key required
- No GPU required

**Forbidden fields stripped/rejected:**

`ffmpeg_args`, `render_command`, `playback_speed`, `subtitle_timing`, `queue_priority`, `output_path`, `subprocess`, `executable`, `python_code`, `shell`, `powershell`, `direct_crop_coordinates`

**Architecture notes:**

- Phase 41 connects Phase 39 external creator knowledge ingestion and Phase 40 creator pattern extraction to AI Director runtime orchestration
- AI Director can now retrieve creator intelligence dynamically based on clip context
- Retrieved metadata can influence existing subtitle, pacing, camera, hook, and retention systems safely
- This phase does not replace deterministic rendering logic
- Stable render executor remains final authority
- AI remains assistive, bounded, and metadata-first

**Intentionally still blocked:**

- Live internet scraping
- Autonomous crawling
- Model fine-tuning
- Unrestricted autonomous editing
- FFmpeg command mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Direct crop-coordinate rewrite
- Segment reorder
- Executor override
- Queue mutation
- Autonomous publishing

**Verification:**

- Phase 41 tests: 72 passed
- Full suite: 2771 passed
- `git diff --check` clean
- `py_compile` passed

**Status:**

Phase 41 complete. Retrieval-based creator intelligence is now available as an assistive metadata layer for AI Director and render influence reporting.

### 2026-05-08 — AI Productization Phase 34: Safe Camera Motion Apply Foundation

**Camera motion guidance metadata only. No crop coordinate rewrite. No FFmpeg mutation. Policy-gated (balanced/aggressive/experimental).**

**Implemented:**

- `app/ai/camera/__init__.py` (new) — package marker
- `app/ai/camera/camera_apply_schema.py` (new) — `AICameraMotionApply` dataclass (apply_id, camera_type, source_candidate_id, confidence, applied, safe, target_scope, changes, warnings, explanation; `to_dict()` clamps `beat_pulse_strength` [0, 0.35], clamps `max_camera_intensity` [0, 1], strips forbidden change keys, caps confidence [0, 1], caps warnings/explanation at 10, maps unknown camera types to "unknown"); `AICameraMotionApplyPack` dataclass (available, enabled, mode, applied, blocked, warnings; `to_dict()` caps applied/blocked at 20); `_ALLOWED_CAMERA_TYPES` (6 types); `_FORBIDDEN_CAMERA_TYPES` (5 types); `_ALLOWED_CHANGE_KEYS` (8 keys); `_FORBIDDEN_CHANGE_KEYS` (14 keys including all crop/ffmpeg/coordinate keys); `_MAX_BEAT_PULSE_STRENGTH = 0.35`, `_MAX_CAMERA_INTENSITY = 1.0`, `_MIN_CONFIDENCE = 0.65`
- `app/ai/camera/camera_apply_safety.py` (new) — `sanitize_camera_motion_changes(changes) -> dict`; strips forbidden keys, retains only allowed keys, clamps beat_pulse_strength [0, 0.35] and max_camera_intensity [0, 1]; `is_camera_motion_apply_safe(candidate, context) -> bool`; gates: not-dict → False, forbidden camera type hard-reject, unknown type reject, confidence ≥ 0.65, scope must be "metadata", any forbidden change key present → reject, sanitized changes must be non-empty; never raises
- `app/ai/camera/camera_apply_engine.py` (new) — `build_camera_motion_apply_pack(edit_plan, payload, context) -> AICameraMotionApplyPack`; policy gate: only `balanced`/`aggressive`/`experimental`; `_MAX_APPLIED = 6`; candidate sources: Phase 18 (`beat_visual_execution.pulse_regions`) → `beat_aware_pulse` with pulse_strength clamped to [0, 0.35] at collection time; Phase 23 (`creator_style_adaptation.adapted_style`) → `creator_style_camera`; Phase 5 camera plan (`subtitle_safe=True`) → `subtitle_safe_framing`; Phase 27 (`safe_render_mutations` visual_rhythm category) → `motion_smoothing_hint`; Phase 33 (`subtitle_text_apply` compact_overload/density_reduce applied) → `subtitle_safe_framing` (if not already present); logs `ai_camera_motion_apply_enabled`, `ai_camera_motion_guidance_applied`, `ai_camera_motion_guidance_blocked`, `ai_camera_motion_apply_skipped`; never raises; never mutates payload in-place; never rewrites crop coordinates
- `app/ai/director/edit_plan_schema.py` (updated) — `camera_motion_apply: dict = field(default_factory=dict)` added after Phase 33 field; `"camera_motion_apply": dict(self.camera_motion_apply)` in `to_dict()`; backward-compatible
- `app/ai/director/ai_director.py` (updated) — Phase 34 block inserted between Phase 33 (subtitle text apply) and Phase 6 (explainability); `_attach_camera_motion_apply(plan, request, job_id)` reads `ai_apply_policy` from request; `_append_camera_motion_apply_explainability()` appends: "Camera motion apply disabled by conservative policy" (disabled), "Direct crop coordinate rewrite remains blocked" (always), per-applied camera type labels, "Camera motion guidance blocked ({reason})" (first blocked); wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_camera_motion_apply(payload, edit_plan, report)` added; disabled → `report["skipped"]` as `"camera_motion_apply:disabled_phase34(applied=...,blocked=...)"` + `"direct_crop_coordinate_rewrite:always_blocked_phase34"`; active applied → `report["applied"]` as `"camera_motion_apply:applied({id},{type}:[changes])"`; blocked → `report["skipped"]` as `"camera_motion_apply:blocked({id},{type}:{reason})"`; always appends `"direct_crop_coordinate_rewrite:always_blocked_phase34"` to `report["skipped"]`; wired after `_report_subtitle_text_apply()`; payload never mutated
- `tests/test_ai_phase34_camera_motion_apply.py` (new) — 83 tests covering schema, safety, engine, edit plan compat, render influence, end-to-end

**Allowed camera types:**

| Type | Source |
|------|--------|
| `dynamic_safe` | General dynamic camera guidance |
| `subtitle_safe_framing` | Phase 5 camera plan / Phase 33 density |
| `beat_aware_pulse` | Phase 18 `beat_visual_execution` |
| `creator_style_camera` | Phase 23 `creator_style_adaptation` |
| `subject_lock_preference` | Subject tracking preference |
| `motion_smoothing_hint` | Phase 27 `safe_render_mutations` visual_rhythm |

**Allowed change keys (metadata only — no coordinates):**

`camera_behavior`, `subtitle_safe_framing`, `beat_pulse_strength` [0–0.35], `creator_style_camera`, `subject_lock_preference`, `motion_smoothing`, `max_camera_intensity` [0–1], `visual_rhythm_mode`

**Safety bounds:**

| Gate | Rule |
|------|------|
| Confidence | ≥ 0.65 |
| `target_scope` | must be "metadata" |
| `beat_pulse_strength` | clamped [0, 0.35] |
| `max_camera_intensity` | clamped [0, 1] |
| Forbidden change keys | hard-rejected before sanitization |
| Empty changes after sanitization | rejected |

**Policy gating:**

| Policy | Camera motion apply enabled |
|--------|----------------------------|
| `conservative` | ✗ |
| `balanced` | ✓ |
| `aggressive` | ✓ |
| `experimental` | ✓ |

**Intentionally still blocked:**

- Crop coordinate rewrite (always — `crop_x`, `crop_y`, `crop_w`, `crop_h`)
- FFmpeg filter rewrite (always)
- Arbitrary zoom curve (always)
- Unsafe subject jump (always)
- Scene reorder camera (always)
- Playback_speed mutation (always)
- Segment reorder (always)
- Executor override (always)

**Architecture notes:**

- Phase 34 sits between Phase 33 (subtitle text apply) and Phase 6 (explainability) — the third and final apply phase
- `report["skipped"]` always contains `"direct_crop_coordinate_rewrite:always_blocked_phase34"` regardless of enabled state — explicit audit trail of the safety invariant
- `target_scope="metadata"` is enforced by safety gate and reported in all applied entries
- Beat pulse strength is clamped at two levels: at collection time (in `_collect_candidates`) and again at `to_dict()` serialization
- Phase 34 is the third apply phase to add entries to `report["applied"]`

**Verification:**

- Phase 34 tests: 83 passed
- Full suite passes (2296 total, zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 33: Subtitle Text Optimization Apply Foundation

**Text/style metadata only. No subtitle timestamp rewrite. Policy-gated (balanced/aggressive/experimental).**

**Implemented:**

- `app/ai/subtitles/subtitle_apply_schema.py` (new) — `AISubtitleTextApply` dataclass (apply_id, optimization_type, source_candidate_id, confidence, applied, safe, target_scope, changes, warnings, explanation; `to_dict()` strips forbidden change keys, retains only `_ALLOWED_CHANGE_KEYS`, clamps `max_chars_per_line` to [18, 42], caps confidence [0, 1], caps warnings/explanation at 10, maps unknown optimization types to "unknown"); `AISubtitleTextApplyPack` dataclass (available, enabled, mode, applied, blocked, warnings; `to_dict()` caps applied/blocked at 20); `_ALLOWED_OPTIMIZATION_TYPES` (6 types); `_FORBIDDEN_OPTIMIZATION_TYPES` (5 types); `_ALLOWED_CHANGE_KEYS` (8 keys); `_FORBIDDEN_CHANGE_KEYS` (10 keys including all timestamp/timing keys)
- `app/ai/subtitles/subtitle_apply_safety.py` (new) — `sanitize_subtitle_text_changes(changes) -> dict`; strips forbidden keys, retains only allowed keys, clamps max_chars_per_line; `is_subtitle_text_apply_safe(candidate, context) -> bool`; gates: not-dict → False, forbidden opt type hard-reject, unknown opt type reject, confidence ≥ 0.65, scope must be "metadata", any forbidden change key present → reject, sanitized changes must be non-empty; never raises
- `app/ai/subtitles/subtitle_apply_engine.py` (new) — `build_subtitle_text_apply_pack(edit_plan, payload, context) -> AISubtitleTextApplyPack`; policy gate: only `balanced`/`aggressive`/`experimental`; candidate sources: Phase 17 (`subtitle_execution.global_hint`) → `compact_overload` and `keyword_emphasis`; Phase 23 (`creator_style_adaptation`) → `creator_style_tone`; Phase 16 (`retention.subtitle_overload_detected`) → `density_reduce`; Phase 19 (`timing_mutation` hold_hook) → `hook_emphasis`; capped at 6 applied; logs `ai_subtitle_text_apply_enabled`, `ai_subtitle_text_optimization_applied`, `ai_subtitle_text_optimization_blocked`, `ai_subtitle_text_apply_skipped`; never raises; never mutates payload in-place
- `app/ai/director/edit_plan_schema.py` (updated) — `subtitle_text_apply: dict = field(default_factory=dict)` added after Phase 32 field; `"subtitle_text_apply": dict(self.subtitle_text_apply)` in `to_dict()`; backward-compatible
- `app/ai/director/ai_director.py` (updated) — Phase 33 block inserted between Phase 32 (timing apply) and Phase 6 (explainability); `_attach_subtitle_text_apply(plan, request, job_id)` reads `ai_apply_policy` from request; `_append_subtitle_text_apply_explainability()` appends: "Subtitle text optimization disabled by conservative policy" (disabled), "Subtitle timestamp rewrite remains blocked" (always), per-applied optimization labels, "Subtitle optimization blocked ({reason})" (first blocked); wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_subtitle_text_apply(payload, edit_plan, report)` added; disabled → `report["skipped"]` as `"subtitle_text_apply:disabled_phase33(applied=...,blocked=...)"` + `"subtitle_timestamp_rewrite:always_blocked_phase33"`; active applied → `report["applied"]` as `"subtitle_text_apply:applied({id},{type}:[changes])"`; blocked → `report["skipped"]` as `"subtitle_text_apply:blocked({id},{type}:{reason})"`; always appends `"subtitle_timestamp_rewrite:always_blocked_phase33"` to `report["skipped"]`; wired after `_report_timing_apply()`; payload never mutated
- `tests/test_ai_phase33_subtitle_text_apply.py` (new) — 79 tests covering schema, safety, engine, edit plan compat, render influence, end-to-end

**Allowed subtitle optimization types:**

| Type | Source |
|------|--------|
| `compact_overload` | Phase 17 `density_mode=compact` |
| `keyword_emphasis` | Phase 17 `emphasis_strength > 0.3` |
| `safer_line_breaks` | General text safety |
| `density_reduce` | Phase 16 `subtitle_overload_detected` |
| `creator_style_tone` | Phase 23 `creator_style_adaptation` |
| `hook_emphasis` | Phase 19 `hold_hook` candidate |

**Allowed change keys (metadata/style only):**

`subtitle_density`, `subtitle_emphasis`, `keyword_emphasis`, `line_break_style`, `max_chars_per_line` [18–42], `creator_style_tone`, `hook_emphasis`, `readability_mode`

**Safety bounds:**

| Gate | Rule |
|------|------|
| Confidence | ≥ 0.65 |
| `target_scope` | must be "metadata" |
| `max_chars_per_line` | clamped [18, 42] |
| Forbidden change keys | hard-rejected before sanitization |
| Empty changes after sanitization | rejected |

**Policy gating:**

| Policy | Subtitle text apply enabled |
|--------|----------------------------|
| `conservative` | ✗ |
| `balanced` | ✓ |
| `aggressive` | ✓ |
| `experimental` | ✓ |

**Intentionally still blocked:**

- Subtitle timestamp rewrite (always)
- Subtitle timing shift (always)
- Full transcript rewrite (always)
- Generated script replacement (always)
- Playback_speed mutation (always)
- FFmpeg command mutation (always)
- Segment reorder (always)
- Executor override (always)

**Architecture notes:**

- Phase 33 sits between Phase 32 (timing apply) and Phase 6 (explainability) — after policy is resolved
- `report["skipped"]` always contains `"subtitle_timestamp_rewrite:always_blocked_phase33"` regardless of enabled state — this is an explicit audit trail of the safety invariant
- `target_scope="metadata"` is enforced by safety gate and reported in all applied entries
- Phase 33 is the second apply phase (after Phase 32 timing apply) to add entries to `report["applied"]`

**Verification:**

- Phase 33 tests: 79 passed
- Full suite passes (2213 total, zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 32: Safe Timing Mutation Apply Foundation

**First timing apply phase. Policy-gated. Bounded. Deterministic. No FFmpeg mutation.**

**Implemented:**

- `app/ai/timing/timing_apply_schema.py` (new) — `AITimingMutationApply` dataclass (mutation_id, mutation_type, source_candidate_id, confidence, applied, safe, start_sec, end_sec, delta_sec, reason, warnings, explanation; `to_dict()` caps delta at `_MAX_SINGLE_DELTA_SEC=1.5`, caps confidence [0,1], caps warnings/explanation at 10, maps unknown types to "unknown"); `AITimingApplyPack` dataclass (available, enabled, mode, applied_mutations, blocked_mutations, total_delta_sec, warnings; `to_dict()` caps total_delta at `_MAX_TOTAL_DELTA_SEC=4.0`, caps mutations at 20)
- `app/ai/timing/timing_apply_safety.py` (new) — `sanitize_timing_candidate(candidate) -> dict`; handles both Phase 19 (`start`/`end`/`max_trim_seconds`) and Phase 32 (`start_sec`/`end_sec`/`delta_sec`) key formats; `is_timing_mutation_safe(candidate, context) -> bool`; gates: forbidden type hard-reject, allowed type required, confidence ≥ 0.65, delta > 0 and ≤ 1.5 s, start ≥ 0, post-trim duration ≥ 2.0 s, protected window overlap, subtitle-dense region overlap; never raises
- `app/ai/timing/timing_apply_engine.py` (new) — `build_timing_apply_pack(edit_plan, payload, context) -> AITimingApplyPack`; policy resolution priority: `context["ai_apply_policy"]` > `payload.ai_apply_policy` > `edit_plan.ai_apply_policy["selected_policy"]` > "conservative"; only `aggressive`/`experimental` policies allow apply; collects candidates from Phase 19 (`timing_mutation`) and Phase 20 (`story_optimization.timing_hints`); Phase 19 action mapping: `trim_silence→trim_silence_gap`, `tighten_setup→tighten_setup`, `shorten_outro→shorten_outro`; unknown Phase 19 actions silently skipped; capped at 5 applied mutations; logs `ai_timing_apply_enabled`, `ai_timing_mutation_applied`, `ai_timing_mutation_blocked`, `ai_timing_apply_skipped`; never raises; never mutates payload in-place
- `app/ai/director/edit_plan_schema.py` (updated) — `timing_apply: dict = field(default_factory=dict)` added after Phase 31 field; `"timing_apply": dict(self.timing_apply)` in `to_dict()`; backward-compatible; Phase 31 `ai_apply_policy` unchanged
- `app/ai/director/ai_director.py` (updated) — Phase 32 block inserted between Phase 31 (policy) and Phase 6 (explainability); `_attach_timing_apply(plan, request, job_id)` reads `ai_apply_policy` from request; `_append_timing_apply_explainability()` appends: "Safe timing apply disabled by conservative policy" (disabled), "Safe {type} applied" (per applied mutation), "Unsafe timing mutation blocked ({reason})" (first blocked); wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_timing_apply(payload, edit_plan, report)` added; disabled → `report["skipped"]` as `"timing_apply:disabled_phase32(applied=...,blocked=...)"`; active applied mutations → `report["applied"]` as `"timing_apply:applied({id},{type}:delta=...s)"`; blocked mutations → `report["skipped"]` as `"timing_apply:blocked({id},{type}:{reason})"`; wired after `_report_ai_apply_policy()`; payload never mutated
- `tests/test_ai_phase32_timing_apply.py` (new) — 74 tests covering schema, safety, engine, edit plan compat, render influence, end-to-end

**Allowed timing mutation types:**

| Type | Source |
|------|--------|
| `trim_silence_gap` | Phase 19 `trim_silence` action |
| `tighten_setup` | Phase 19 `tighten_setup` action |
| `shorten_outro` | Phase 19 `shorten_outro` action |
| `reduce_dead_air` | Phase 20 story hint |

**Safety bounds:**

| Gate | Bound |
|------|-------|
| `_MAX_SINGLE_DELTA_SEC` | 1.5 s per mutation |
| `_MAX_TOTAL_DELTA_SEC` | 4.0 s total |
| `_MIN_CONFIDENCE` | 0.65 |
| Post-trim segment duration | ≥ 2.0 s |
| Protected hook/payoff window | no overlap |
| Subtitle-dense region | no overlap |

**Policy gating:**

| Policy | Timing apply enabled |
|--------|---------------------|
| `conservative` | ✗ |
| `balanced` | ✗ |
| `aggressive` | ✓ |
| `experimental` | ✓ |

**Intentionally still blocked:**

- FFmpeg command mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Executor authority override
- Validation bypass
- Autonomous unlimited rendering

**Architecture notes:**

- Phase 32 runs between Phase 31 (policy) and Phase 6 (explainability) — so effective policy is resolved before timing apply evaluates it
- Unknown Phase 19 `action` values are silently skipped at collection (not added to blocked) since they were never valid Phase 19 candidates; known forbidden Phase 20 `mutation_type` values are also skipped at collection
- `report["applied"]` receives timing apply entries for the first time in Phase 32 — prior phases only used `report["skipped"]` for advisory metadata
- Applied mutations are metadata only — no FFmpeg arg is modified, no subtitle file is rewritten, no segment order changes

**Verification:**

- Phase 32 tests: 74 passed
- Full suite passes (2134 total, zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 31: AI Apply Policy Layer Foundation

**Policy layer controls HOW MUCH AI influence is allowed. Hard safety blocks are NEVER bypassed.**

**Implemented:**

- `app/ai/policy/__init__.py` (new) — package marker; Phase 31 AI apply policy package
- `app/ai/policy/policy_schema.py` (new) — `AIApplyPolicy` dataclass (policy_name, allow_safe_mutations, allow_multivariant_execution, allow_execution_recommendations, allow_execution_simulation, allow_output_ranking, allow_timing_candidates, allow_creator_style_adaptation, allow_visual_rhythm_guidance, allow_aggressive_behavior, warnings, explanation; `to_dict()` caps warnings/explanation at 10, coerces all allow_* to bool); `AIPolicyDecision` dataclass (available, selected_policy, effective_policy, blocked_capabilities, warnings; `to_dict()` caps blocked_capabilities at 30)
- `app/ai/policy/policy_safety.py` (new) — `sanitize_policy(policy_name) -> str`; case-insensitive; invalid values → "conservative"; `build_policy(policy_name) -> AIApplyPolicy`; reads from `_POLICY_DEFINITIONS` dict, falls back to conservative on error; `get_blocked_capabilities(policy) -> list[str]`; always includes `_GLOBAL_HARD_BLOCKS` (7 keys: ffmpeg_mutation, playback_speed_mutation, subtitle_timing_rewrite, segment_reorder, executor_override, validation_bypass, autonomous_unlimited_rendering); adds capability-level blocks based on policy flags; never raises
- `app/ai/policy/policy_engine.py` (new) — `build_policy_decision(edit_plan, payload, context) -> AIPolicyDecision`; resolves policy name from context > payload attribute > edit_plan dict > default "conservative"; calls `build_policy()` + `get_blocked_capabilities()`; logs `ai_apply_policy_selected`/`ai_apply_policy_fallback`/`ai_apply_policy_blocked`; deterministic; never raises; never mutates payload
- `app/ai/director/edit_plan_schema.py` (updated) — `ai_apply_policy: dict = field(default_factory=dict)` added to `AIEditPlan`; `"ai_apply_policy": dict(self.ai_apply_policy)` in `to_dict()`; backward-compatible; Phase 30 `output_ranking` unchanged
- `app/ai/director/ai_director.py` (updated) — Phase 31 block inserted **early** (before Phase 6 explainability) so downstream phases can reference the effective policy; `_attach_ai_apply_policy(plan, request, job_id)` reads `ai_apply_policy` attribute from request; `_append_ai_apply_policy_explainability()` appends: "{Policy} AI apply policy enabled", "Aggressive orchestration remains safety-gated" (aggressive/experimental only), "Dangerous timing mutations remain blocked" (always); None guard; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_ai_apply_policy(payload, edit_plan, report)` added; policy summary → `report["skipped"]` as `"ai_apply_policy:phase31(policy=...,available=...,blocked_count=...)"`; wired into `apply_ai_render_influence()` after `_report_output_ranking()`; payload never mutated
- `tests/test_ai_phase31_apply_policy.py` (new) — comprehensive test suite covering schema invariants, safety gates, policy definitions, engine behavior, edit plan compat, render_influence reporter, and end-to-end integration

**Policy definitions:**

| Policy | allow_multivariant_execution | allow_timing_candidates | allow_aggressive_behavior | Hard blocks |
|--------|------------------------------|-------------------------|---------------------------|-------------|
| `conservative` | ✗ | ✗ | ✗ | Always |
| `balanced` | ✓ | ✗ | ✗ | Always |
| `aggressive` | ✓ | ✗ | ✓ | Always |
| `experimental` | ✓ | ✓ | ✓ | Always |

**Resolution priority:** `context["ai_apply_policy"]` > `request.ai_apply_policy` attribute > `edit_plan.ai_apply_policy["selected_policy"]` > `"conservative"`

**Global hard blocks (NEVER bypassed by any policy, 7 keys):**

`ffmpeg_mutation`, `playback_speed_mutation`, `subtitle_timing_rewrite`, `segment_reorder`, `executor_override`, `validation_bypass`, `autonomous_unlimited_rendering`

**Capability-level blocks per policy:**

- `conservative`: + `multivariant_execution`, `timing_candidate_apply`, `aggressive_behavior`
- `balanced`: + `timing_candidate_apply`, `aggressive_behavior`
- `aggressive`: + `timing_candidate_apply`
- `experimental`: no additional capability blocks (hard blocks always apply)

**Policy ordering invariant:** conservative blocks all capabilities blocked by any other policy (conservative ⊇ balanced ⊇ aggressive ⊇ experimental in terms of blocked set).

**Safety boundaries enforced:**

- Hard blocks are unconditional — `get_blocked_capabilities()` always prepends `_GLOBAL_HARD_BLOCKS`
- Invalid policy names → "conservative" via `sanitize_policy()` — no unknown policies can execute
- `_POLICY_DEFINITIONS` keys are frozen — no dynamic policy injection
- Policy never mutates payload, never calls FFmpeg, never touches render executor
- Phase 31 block is early (pre-Phase 6) so explainability lines reflect effective policy
- Never raises — all code wrapped in try/except with fallback to conservative
- Deterministic — same inputs → same policy decision every time
- No internet, no API keys, no GPU required

**Intentionally still blocked (by all policies):**

- FFmpeg command mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Executor authority override
- Validation bypass
- Autonomous unlimited rendering

**Architecture notes:**

- Phase 31 policy block runs before Phase 6 (explainability) — earliest possible position after plan construction
- Policy metadata in `ai_apply_policy` field is available to all downstream phases in the same `_build_plan()` call
- The policy does NOT yet gate downstream phase execution (e.g., if `allow_multivariant_execution=False`, the multivariant block still runs but produces an advisory-only result). Policy gating enforcement is a future hardening step.
- `report["applied"]` is NOT touched by Phase 31 — all policy reporting goes to `report["skipped"]`

**Verification:**

- Phase 31 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 30: AI Output Ranking & Best Export Recommendation

**Metadata-only output ranker. Recommendation-only. No upload, no publish, no file deletion.**

**Implemented:**

- `app/ai/output/__init__.py` (new) — package marker; Phase 30 AI output ranking package
- `app/ai/output/output_schema.py` (new) — `AIOutputScore` dataclass (output_id, path, variant_id, score, confidence, rank, recommended, quality_flags, warnings, explanation; `to_dict()` clamps score [0,100], confidence [0,1], caps quality_flags/warnings/explanation at 10); `AIOutputRanking` dataclass (available, mode, outputs, best_output_id, best_output_path, warnings; `to_dict()` hardcodes mode="recommendation_only", caps outputs at 20)
- `app/ai/output/output_safety.py` (new) — `sanitize_output_metadata(output) -> dict`; retains only `_SAFE_METADATA_KEYS` (21 safe metadata keys); `is_output_rankable(output) -> bool`; requires non-empty `output_id`; never raises; never opens/writes/deletes files
- `app/ai/output/output_ranker.py` (new) — `rank_variant_outputs(outputs, edit_plan, context) -> AIOutputRanking`; `_normalize_outputs()` handles list/dict/str input; `_extract_ai_context()` reads variant_selection, creator_style_adaptation, execution_simulation, multivariant_execution from edit plan; `_score_output()` scoring model: base=50 + rank_score_bonus(up to +30) + selected_variant(+10) + creator_style_confidence≥0.60(+5) + retention_gain>0(+5) − warning_penalty(10/warn, max 3) − failed(−50) − validation_failed(−10); deterministic; never raises; logs `ai_output_ranking_created`/`ai_output_ranking_fallback`
- `app/ai/director/edit_plan_schema.py` (updated) — `output_ranking: dict = field(default_factory=dict)` added to `AIEditPlan`; `"output_ranking": dict(self.output_ranking)` in `to_dict()`; backward-compatible; Phase 29 `multivariant_execution` unchanged
- `app/ai/director/ai_director.py` (updated) — Phase 30 block attaches placeholder `output_ranking` dict (available=False, warnings=["ranking_deferred_until_render_completion"]); actual ranking is post-render in pipeline; placeholder ensures field is always present in AI Director output
- `app/ai/director/render_influence.py` (updated) — `_report_output_ranking(payload, edit_plan, report)` added; both deferred and available rankings → `report["skipped"]` as `"output_ranking:deferred_phase30(best=...,outputs=...)"` or `"output_ranking:recommendation_only(best=...,outputs=...)"`; wired into `apply_ai_render_influence()` after `_report_multivariant_execution()`; no payload mutated; no files touched
- `app/orchestration/render_pipeline.py` (updated) — Phase 30 block added before `_result_payload` construction; builds `_ai_rank_inputs` from `_rank_entries_ordered` (successful) + `failed_parts` (with `failed=True`); calls `rank_variant_outputs(_ai_rank_inputs, edit_plan=_ai_edit_plan)`; attaches `_ai_output_ranking` to `_result_payload["ai_output_ranking"]` and updates `_ai_edit_plan.output_ranking` if plan exists; ranking error → warning-only fallback dict, render job NOT affected
- `tests/test_ai_phase30_output_ranking.py` (new) — comprehensive test suite covering schema invariants, safety gates, ranker behavior, scoring model, edit plan compat, render_influence reporter, and end-to-end integration

**Scoring model:**

| Signal | Effect |
|--------|--------|
| Base score | +50.0 |
| Existing rank score | +up to 30.0 (existing_score × 0.30) |
| Selected variant match | +10.0 |
| Creator style confidence ≥ 0.60 | +5.0 |
| Retention gain > 0 | +5.0 |
| Warning (per warning, max 3) | −10.0 each |
| Failed output | −50.0 |
| Validation failed | −10.0 |
| Final clamp | [0.0, 100.0] |

**`mode` always "recommendation_only"** — hardcoded in `AIOutputRanking.to_dict()`.

**Selected variant detection:** matches `variant_id` against `variant_selection.recommended_variant_id` OR `multivariant_execution.executed_plan_ids`.

**`_result_payload` keys added:**

- `ai_output_ranking` — `AIOutputRanking.to_dict()` result: `{available, mode, outputs[], best_output_id, best_output_path, warnings}`
- Existing `output_ranking` (native pipeline ranker) is unchanged

**Safety boundaries enforced:**

- `mode` always "recommendation_only" — hardcoded in `to_dict()`
- No files opened, read, written, or deleted in any ranking code path
- No upload, no publish, no autonomous export replacement
- Ranking failure → warning-only fallback dict, render job NOT affected
- `report["applied"]` not touched by Phase 30 — all output ranking goes to `report["skipped"]`
- Never raises — all code paths wrapped in try/except with logger.warning fallback
- No internet, no API keys, no GPU required
- Deterministic — same outputs + same edit_plan → same ranking

**Intentionally still blocked:**

- Auto-upload triggered by ranking
- Auto-publish triggered by ranking
- Output deletion (failed or low-ranked)
- File overwrite by export recommendation
- Autonomous export replacement
- FFmpeg mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Executor override
- Validation rule bypass

**Architecture notes:**

- `output_ranking` in `AIEditPlan` is a placeholder at AI Director time (no outputs exist yet)
- Actual ranking runs post-render in `render_pipeline.py` after `_rank_entries_ordered` is finalized
- AI output ranking is additive over the existing native pipeline ranking; both coexist in `_result_payload`
- The pipeline Phase 30 block is wrapped in try/except — ranking error never blocks the render job

**Verification:**

- Phase 30 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 29: Safe Multi-Variant Render Execution Foundation

**FIRST phase where AI-prepared variant plans may become actual render jobs.**

**Execution is opt-in only (`ai_multivariant_execution_enabled=True` required). Disabled by default.**

**Implemented:**

- `app/ai/multivariant/multivariant_execution_schema.py` (new) — `AIMultiVariantExecution` dataclass (execution_id, plan_id, variant_id, enabled, safe, advisory_origin, payload_overrides, blocked_fields, render_job_created, warnings, explanation; `to_dict()` hardcodes advisory_origin=True, caps blocked_fields/warnings/explanation at 20/10/10); `AIMultiVariantExecutionSet` dataclass (available, execution_enabled, executions, executed_plan_ids, blocked_plan_ids, warnings; `to_dict()` caps executions at 3)
- `app/ai/multivariant/multivariant_execution_safety.py` (new) — `sanitize_execution_overrides(overrides) -> dict`; `is_execution_override_safe(overrides) -> bool`; `collect_execution_blocked_fields(overrides) -> list`; `_ALLOWED_KEYS` = 7 safe metadata keys; `_FORBIDDEN_KEYS` = 15 keys (identical to Phase 28 planning); never raises; never mutates originals
- `app/ai/multivariant/multivariant_execution.py` (new) — `build_multivariant_execution_set(edit_plan, payload, context) -> AIMultiVariantExecutionSet`; reads plans from `edit_plan.multivariant_render_plans.plans`; execution gated by `ai_multivariant_execution_enabled` flag in context; limit clamped to [1, 3]; safe plans produce payload copies via `_make_payload_copy()` — original never mutated; unsafe/not-safe-to-enqueue plans → blocked; limit-exceeded plans → blocked; `_disabled_set()` returns all plans as blocked with execution_enabled=False; logs `ai_multivariant_execution_created`/`ai_multivariant_execution_blocked`/`ai_multivariant_execution_skipped`; deterministic; never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `multivariant_execution: dict = field(default_factory=dict)` added to `AIEditPlan`; `"multivariant_execution": dict(self.multivariant_execution)` in `to_dict()`; backward-compatible; Phase 28 `multivariant_render_plans` unchanged
- `app/ai/director/ai_director.py` (updated) — `_attach_multivariant_execution(plan, request, job_id)` added; runs after Phase 28 (multi-variant planning); reads `ai_multivariant_execution_enabled` and `ai_multivariant_execution_limit` from request; calls `build_multivariant_execution_set(plan, payload=None, context)`; logs `ai_multivariant_execution_built` at INFO; `_append_multivariant_execution_explainability()` appends: "Safe multi-variant execution enabled" + "Bounded render variants prepared" (when enabled + executed), "Multi-variant execution disabled (opt-in required)" (when disabled), "Dangerous execution overrides remain blocked" (always); None guard; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_multivariant_execution(payload, edit_plan, report)` added; when disabled: `report["skipped"]` as `"multivariant_execution:disabled_phase29(plans=...,blocked=...)"`; when enabled: executed plans → `report["applied"]` as `"multivariant_exec:executed({id},{plan_id}:[overrides])"`, blocked → `report["skipped"]` as `"multivariant_exec:blocked({id},{plan_id}:reason)"`; wired into `apply_ai_render_influence()` after `_report_multivariant_plans()`; payload never mutated
- `tests/test_ai_phase29_multivariant_execution.py` (new) — comprehensive test suite covering schema invariants, safety gates, execution engine behavior, edit plan schema compatibility, render_influence reporter, and end-to-end integration

**Execution request flags (opt-in):**

| Flag | Default | Description |
|------|---------|-------------|
| `ai_multivariant_execution_enabled` | `False` | Must be True to create any render jobs |
| `ai_multivariant_execution_limit` | `2` | Max execution jobs; clamped to [1, 3] |

**Execution limit clamping:** `max(1, min(3, ai_multivariant_execution_limit))`

**Allowed execution override keys (Phase 29 = Phase 28 allowed set):**

`subtitle_density`, `subtitle_emphasis`, `camera_behavior`, `pacing_style`, `creator_style`, `visual_rhythm_mode`, `ai_mode`

**Forbidden execution override keys (15 total — same as Phase 28):**

`playback_speed`, `segment_start`, `segment_end`, `subtitle_timing`, `ffmpeg_args`, `codec`, `bitrate`, `crf`, `validation_rules`, `output_path`, `render_command`, `render_segments`, `segment_order`, `queue_priority`, `job_id`

**Execution plan processing:**

1. Extract plans from `edit_plan.multivariant_render_plans.plans`
2. For each plan: check `safe_to_enqueue` + run `is_execution_override_safe()` on overrides
3. Unsafe/not-safe-to-enqueue → blocked (no render job)
4. If limit reached → blocked (no render job)
5. Safe plan within limit → `_make_payload_copy(payload, sanitized_overrides)` → `render_job_created=True`
6. `advisory_origin` is always True on every execution

**`_make_payload_copy` behavior:**

- `payload=None` → returns dict of safe overrides only
- `payload` is dict → shallow copy + apply safe overrides
- `payload` has `__dict__` → copy of vars + apply safe overrides
- Never mutates original payload
- Never propagates forbidden keys

**Safety boundaries enforced:**

- Execution disabled by default — `ai_multivariant_execution_enabled=False` produces no render jobs
- `advisory_origin` always True — hardcoded in `AIMultiVariantExecution.to_dict()`
- Original payload never mutated — `_make_payload_copy()` always creates a copy
- Max 3 execution jobs — enforced by `_MAX_EXECUTION_JOBS = 3` clamp
- Forbidden keys stripped by `sanitize_execution_overrides()` before any copy
- `is_execution_override_safe()` gate: False blocks plan even if `safe_to_enqueue=True`
- render_influence applied/skipped distinction: executed → applied, everything else → skipped
- Never blocks render — all Phase 29 code wrapped in try/except in AI Director and engine
- Deterministic — same edit_plan + same context → same execution set
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- Executor authority override
- FFmpeg command mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Autonomous unlimited rendering (hard limit: 3 jobs max, opt-in only)
- Validation bypass
- Output path mutation
- Render queue direct manipulation

**Architecture notes:**

- Phase 29 is the FIRST phase where render jobs are created from AI planning metadata
- Execution jobs are payload copies — the render executor receives a bounded job descriptor, not a mutated original
- `payload=None` at AI Director time means execution job descriptors are override-only dicts (no base payload); downstream render execution will merge these with the actual render payload
- `report["applied"]` now includes both Phase 27 safe mutations AND Phase 29 execution jobs
- `_report_multivariant_execution()` runs after `_report_multivariant_plans()` in the influence chain

**Verification:**

- Phase 29 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 28: Safe Multi-Variant Render Planning Foundation

**Planning-only phase: prepares renderable variant jobs WITHOUT enqueueing or executing them.**

**Implemented:**

- `app/ai/multivariant/__init__.py` (new) — package marker; Phase 28 safe multi-variant render planning package
- `app/ai/multivariant/multivariant_schema.py` (new) — `AIMultiVariantRenderPlan` dataclass (plan_id, variant_id, label, renderable, safe_to_enqueue, advisory_only, mutation_ids, planned_payload_overrides, blocked_fields, warnings, explanation; `to_dict()` hardcodes advisory_only=True, caps mutation_ids at 20, caps explanation at 300 chars, coerces bool fields); `AIMultiVariantRenderSet` dataclass (available, mode, plans, recommended_plan_id, warnings; `to_dict()` hardcodes mode="planning_only", caps plans at 5)
- `app/ai/multivariant/multivariant_safety.py` (new) — `sanitize_variant_payload_overrides(overrides) -> dict`; strips forbidden + unknown keys, drops None values; `is_multivariant_plan_safe(overrides) -> bool`; returns False if any forbidden key detected; `collect_blocked_fields(overrides) -> list`; returns list of forbidden keys present; `_ALLOWED_KEYS = {subtitle_density, subtitle_emphasis, camera_behavior, pacing_style, creator_style, visual_rhythm_mode, ai_mode}`; `_FORBIDDEN_KEYS` = Phase 27 set (13 keys) + `queue_priority` + `job_id` = 15 keys total; never raises
- `app/ai/multivariant/multivariant_planner.py` (new) — `build_multivariant_render_plans(edit_plan, payload=None, context=None) -> AIMultiVariantRenderSet`; builds up to 5 plans from AI planning metadata; `_build_baseline_plan()` (always present, ai_mode=advisory, pacing_style=standard); `_build_recommended_variant_plan()` (from variant_selection + variants + safe_render_mutations); `_build_compact_subtitle_plan()` (from subtitle_execution; skipped if no density/emphasis/mutation_ids); `_build_creator_style_plan()` (gate: confidence ≥ 0.40; camera via style map, pacing via style); `_build_retention_plan()` (gate: retention_score < 70; skipped when score ≥ 70 or not present); `_select_recommended()` prefers safe_to_enqueue non-baseline plans; `_fallback_set()` returns available=False with baseline only; deterministic; never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `multivariant_render_plans: dict = field(default_factory=dict)` added to `AIEditPlan`; `"multivariant_render_plans": dict(self.multivariant_render_plans)` in `to_dict()`; backward-compatible; Phase 27 `safe_render_mutations` field unchanged
- `app/ai/director/ai_director.py` (updated) — `_attach_multivariant_render_plans(plan, job_id)` added; runs after Phase 27 (safe mutations); calls `build_multivariant_render_plans(plan, payload=None, context)`; logs `ai_multivariant_plans_built` at INFO; `_append_multivariant_plans_explainability(plan, render_set_dict)` appends: "Multi-variant render plans prepared", "Recommended variant render plan is safe to enqueue later" (when non-baseline recommended), "Automatic variant rendering remains blocked" (always); None guard on plan; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_multivariant_plans(payload, edit_plan, report)` added; all plans → `report["skipped"]` as `"multivariant_render_plans:deferred_phase28(count=...,safe=...,recommended=...)"` — no plans enqueued, no payload mutated; wired into `apply_ai_render_influence()` after `_report_safe_mutations()`
- `tests/test_ai_phase28_multivariant_planning.py` (new) — comprehensive test suite covering schema invariants, safety gates, planner plan generation, selection logic, edit plan schema compatibility, render_influence reporter, and end-to-end integration

**Plan types and trigger conditions:**

| Plan ID | Label | Trigger condition |
|---------|-------|-------------------|
| `mvplan_baseline` | Baseline Safe Render Plan | Always present |
| `mvplan_recommended_variant` | Recommended Variant Render Plan | variant_selection has recommended_variant_id OR variants list non-empty |
| `mvplan_compact_subtitle` | Compact Subtitle Render Plan | subtitle_execution has density/emphasis OR subtitle mutations present |
| `mvplan_creator_style` | Creator Style Render Plan | creator_style_adaptation confidence ≥ 0.40 and style non-empty |
| `mvplan_retention_optimized` | Retention-Optimized Render Plan | retention_score present and < 70 |

**Allowed payload override keys (Phase 28 safety gate):**

| Key | Purpose |
|-----|---------|
| `subtitle_density` | Subtitle density override |
| `subtitle_emphasis` | Subtitle emphasis override |
| `camera_behavior` | Camera behavior override |
| `pacing_style` | Pacing style override |
| `creator_style` | Creator style label |
| `visual_rhythm_mode` | Visual rhythm mode |
| `ai_mode` | AI mode marker |

**Phase 28 forbidden keys (15 total = Phase 27 13 + 2 new):**

Phase 27 forbidden keys (inherited): `playback_speed`, `segment_start`, `segment_end`, `subtitle_timing`, `ffmpeg_args`, `codec`, `bitrate`, `crf`, `validation_rules`, `output_path`, `render_command`, `render_segments`, `segment_order`

Phase 28 additions: `queue_priority`, `job_id`

**`safe_to_enqueue` logic:**

- `safe_to_enqueue=True` only when `collect_blocked_fields(overrides)` returns empty list
- `safe_to_enqueue=False` when any forbidden key detected in planned_payload_overrides
- Baseline plan is always `safe_to_enqueue=True` because its overrides are hardcoded clean

**Recommended plan selection:**

1. Prefer `safe_to_enqueue=True` non-baseline plans (first match)
2. Fall back to any `safe_to_enqueue=True` plan (including baseline)
3. Fall back to first plan in list

**Safety boundaries enforced:**

- `mode` is always "planning_only" — hardcoded in `AIMultiVariantRenderSet.to_dict()`
- `advisory_only` is always True — hardcoded in `AIMultiVariantRenderPlan.to_dict()`
- Max 5 plans in any render set — enforced by `[:_MAX_PLANS]` slice
- All plans → `report["skipped"]` in render_influence — no plan ever reaches `report["applied"]`
- No render jobs created, no queue touched, no payload mutated
- `_FORBIDDEN_KEYS` (15 keys) always stripped by `sanitize_variant_payload_overrides()`
- Never blocks render — all Phase 28 code wrapped in try/except in AI Director and planner
- Deterministic — same edit_plan always produces same render set
- No internet, no API keys, no GPU required
- Payload object passed to `build_multivariant_render_plans()` is always None (same pattern as Phase 27)

**Intentionally still blocked:**

- Render queue enqueueing
- Job creation and job_id assignment
- FFmpeg command mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Render structure mutation
- Autonomous rendering
- Executor override
- Output validation mutation

**Architecture notes:**

- Phase 28 is the FIRST phase to prepare renderable multi-variant job descriptors — all as planning metadata only
- `safe_to_enqueue=True` on a plan means the plan's overrides are clean of forbidden keys — not that the job will or should be enqueued in this phase
- `report["applied"]` is still populated only by Phase 27 safe mutations — Phase 28 adds nothing to applied list
- `_report_multivariant_plans()` runs last in the render influence chain (after `_report_safe_mutations()`, before `_update_explainability()`)

**Verification:**

- Phase 28 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 27: Safe AI-Assisted Render Mutations

**First phase where bounded AI mutations are applied to AI guidance metadata fields.**

**Implemented:**

- `app/ai/mutations/__init__.py` (new) — package marker; Phase 27 safe mutation package
- `app/ai/mutations/mutation_schema.py` (new) — `VALID_MUTATION_CATEGORIES` frozenset ({subtitle, pacing, camera, creator_style, visual_rhythm}); `AISafeMutation` dataclass (mutation_id, category, confidence, applied, safe, source_recommendation_id, changes, warnings, explanation; `to_dict()` clamps confidence [0,1], caps explanation at 5, coerces invalid category to ""); `AISafeMutationPack` dataclass (available, advisory_mode, mutations, applied_mutation_ids, blocked_mutations, warnings; `to_dict()` caps mutations at 10, caps applied/blocked lists at 20)
- `app/ai/mutations/mutation_safety.py` (new) — `sanitize_mutation_changes(changes) -> dict`; strips forbidden keys and unknown keys, retains only `_ALLOWED_KEYS`, drops None values; `is_mutation_safe(changes) -> bool`; returns False if any forbidden key detected; `apply_safe_mutation(payload, changes) -> dict`; creates a shallow copy of payload (dict or object with `__dict__`), applies only allowed keys, never mutates original; `_ALLOWED_KEYS = {subtitle_density, subtitle_emphasis, camera_behavior, pacing_style, creator_style, visual_rhythm_mode, ai_mode}`; `_FORBIDDEN_KEYS = {playback_speed, segment_start, segment_end, subtitle_timing, ffmpeg_args, codec, bitrate, crf, validation_rules, output_path, render_command, render_segments, segment_order}`; never raises; original payload never mutated in-place
- `app/ai/mutations/mutation_engine.py` (new) — `build_safe_mutations(edit_plan, payload=None, context=None) -> AISafeMutationPack`; reads `execution_recommendations.recommendations` (Phase 25 output); per-category builders: `_build_baseline_mutation()` (always applied), `_build_retention_mutation()` (gate: safe_to_apply + confidence ≥ 0.50), `_build_creator_style_mutation()` (gate: confidence ≥ 0.50; maps to safe camera values via `_STYLE_TO_CAMERA_SAFE`), `_build_subtitle_mutation()` (gate: confidence ≥ 0.40), `_build_visual_rhythm_mutation()` (gate: confidence ≥ 0.35; energetic/moderate → beat_light, calm → beat_none), `_build_pacing_mutation()` (gate: confidence ≥ 0.50); unsafe/low-confidence mutations → `changes={}`, `applied=False`, added to `blocked_mutations`; `advisory_mode=True` when zero mutations applied; emits `ai_safe_mutation_applied`/`ai_safe_mutation_blocked` at INFO, `ai_safe_mutation_skipped` on fallback; deterministic; never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `safe_render_mutations: dict = field(default_factory=dict)` added to `AIEditPlan`; `"safe_render_mutations": dict(self.safe_render_mutations)` in `to_dict()`; backward-compatible; Phase 26 `execution_simulation` field unchanged
- `app/ai/director/ai_director.py` (updated) — `_attach_safe_render_mutations(plan, job_id)` added; runs after Phase 26 (execution simulation); calls `build_safe_mutations(plan, payload=None, context)`; `_append_safe_render_mutations_explainability(plan, pack_dict)` appends: "Safe subtitle density mutation applied" (subtitle), "Visual rhythm guidance safely adjusted" (visual_rhythm), "Creator style mutation applied safely" (creator_style), "Safe pacing mutation applied" (pacing), "Dangerous timing mutations remain blocked" (always); None guard on plan; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_safe_mutations(payload, edit_plan, report)` added; applied mutations → `report["applied"]` as `"safe_mutation:applied({id},{cat}:[changes])"` — FIRST AI-managed mutations to reach the applied list; blocked mutations → `report["skipped"]` as `"safe_mutation:blocked({id},{cat})"` ; emits `ai_safe_mutation_applied`/`ai_safe_mutation_blocked` at INFO; no payload mutation; wired into `apply_ai_render_influence()` after `_report_execution_simulation()`
- `tests/test_ai_phase27_safe_render_mutations.py` (new) — comprehensive test suite covering mutation schema, safety gates, apply_safe_mutation payload invariants, mutation engine, AIEditPlan field, render_influence reporter, safety invariants, and AI Director integration

**Allowed mutation keys and gates:**

| Category | Allowed keys | Confidence gate |
|----------|-------------|-----------------|
| `safe_baseline` | `ai_mode`, `pacing_style` | always applied (conf=1.0) |
| `pacing` | `pacing_style` | ≥ 0.50 + safe_to_apply |
| `creator_style` | `creator_style`, `camera_behavior` | ≥ 0.50 + safe_to_apply |
| `subtitle` | `subtitle_density`, `subtitle_emphasis` | ≥ 0.40 + safe_to_apply |
| `visual_rhythm` | `visual_rhythm_mode` | ≥ 0.35 + safe_to_apply |

**Pacing style canonicalisation:** fast_cuts→fast_hook, fast→fast_hook, retention_optimized→retention_focus, story_driven→story_driven, standard→standard, slow_build→slow_build, medium→standard, slow→slow_build

**Camera behaviour safety mapping:** viral_tiktok/cinematic/storytelling/commentary→dynamic_safe; educational/podcast/product_demo/interview/safe_generic→static

**Visual rhythm safety mapping:** energetic→beat_light, moderate→beat_light, calm→beat_none

**Safety boundaries enforced:**

- Original payload NEVER mutated — `apply_safe_mutation()` always creates a copy
- `_FORBIDDEN_KEYS` (13 keys incl. playback_speed, ffmpeg_args, segment_order, render_segments) always stripped by `sanitize_mutation_changes()`
- Unsafe mutations have `changes={}` and `applied=False` — empty changes reach the report as blocked
- `is_mutation_safe()` returns False if any forbidden key detected in changes
- `advisory_mode=True` set on pack when zero mutations are applied
- Applied mutations only affect AI guidance metadata fields — never FFmpeg commands, timings, or render payload execution fields
- Applied mutations appear in `report["applied"]` — but only as AI metadata, no payload object mutation occurs in `_report_safe_mutations`
- No FFmpeg commands altered. No subtitle timing rewrite. No segment reorder. No playback_speed mutation.
- Never blocks render — all Phase 27 code wrapped in try/except in AI Director and engine
- Deterministic — same edit_plan always produces same mutation pack
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- FFmpeg command mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Render structure mutation
- Render queue mutation
- Autonomous rendering
- Executor override
- Output validation mutation

**Architecture notes:**

- Phase 27 is the FIRST phase where mutations appear in `report["applied"]` (all prior phases added to `report["skipped"]`)
- Mutations are proposed and validated at AI Director time (when edit_plan is built); no payload is needed because changes target AI guidance metadata fields only
- `apply_safe_mutation(payload, changes) -> dict` is available for downstream use when a payload dict copy is needed; it is not called in the main reporting path to preserve the "no payload mutation" invariant in render_influence

**Verification:**

- Phase 27 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 26: Execution Simulation Layer Foundation

**Implemented:**

- `app/ai/simulation/__init__.py` (new) — package marker; Phase 26 simulation package
- `app/ai/simulation/simulation_schema.py` (new) — `VALID_SAFETY_LEVELS` frozenset ({safe, caution, blocked}); `AIExecutionSimulation` dataclass (simulation_id, recommendation_id, label, estimated_retention_gain, estimated_story_gain, estimated_subtitle_clarity_gain, estimated_pacing_gain, confidence, safety_level, advisory_only always True, warnings, explanation; `to_dict()` hardcodes advisory_only=True, clamps confidence [0,1], clamps all gains [-100,100], caps explanation at 5, coerces invalid safety_level to "safe"); `AISimulationPack` dataclass (available, mode always "simulation_only", simulations, recommended_simulation_id, warnings; `to_dict()` hardcodes mode="simulation_only", caps simulations at 10)
- `app/ai/simulation/simulation_scoring.py` (new) — `score_simulation(simulation, edit_plan=None) -> dict`; weighted gain blend (retention×0.35 + story×0.25 + subtitle×0.20 + pacing×0.20) centered at 50; safety penalties: caution −15, blocked −50; low-confidence (<0.40) dampening toward 50; returns {"overall_score":0-100, "confidence":0-1, "reasons":[], "warnings":[]}; deterministic; never raises
- `app/ai/simulation/execution_simulator.py` (new) — `simulate_execution_recommendations(edit_plan, context) -> AISimulationPack`; primary path reads `execution_recommendations.recommendations` (Phase 25 output) and simulates each by category (retention, creator_style, subtitle, visual_rhythm, pacing, safe_baseline); supplemental direct-metadata path fills gaps: `_simulate_retention()` (gain: 18/10/4 for score <40/<70/≥70), `_simulate_subtitle()` (gain: 12/6/3 for compact/normal/other + 3 bonus for emphasis), `_simulate_visual_rhythm()` (pacing: 10/7/5 for >120/>80/≤80 bpm), `_simulate_story_pacing()` (story_driven/fast_cuts/standard), `_simulate_creator_style()` (retention=confidence×8, pacing=confidence×10); `_select_recommended()`: scores via `score_simulation()`, picks best non-baseline only if it beats baseline by >2 pts; `sim_safe_baseline` always present; emits `ai_execution_simulation_created` at INFO, `ai_execution_simulation_fallback` on error; deterministic; never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `execution_simulation: dict = field(default_factory=dict)` added to `AIEditPlan`; `"execution_simulation": dict(self.execution_simulation)` in `to_dict()`; backward-compatible; Phase 25 `execution_recommendations` field unchanged
- `app/ai/director/ai_director.py` (updated) — `_attach_execution_simulation(plan, job_id)` added; runs after Phase 25 (execution recommendations) so simulation reads full recommendation context; calls `simulate_execution_recommendations(plan, context)`; `_append_execution_simulation_explainability(plan, pack_dict)` appends: "Execution simulation estimated retention improvement (+X.Y)" or "Execution simulation prepared (advisory metadata only)", "Subtitle clarity simulation available" (when present), "Simulation remains advisory-only"; None guard on plan; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_execution_simulation(payload, edit_plan, report)` added; checks `edit_plan.execution_simulation`, adds `"execution_simulation:deferred_phase26(count=...,recommended=...)"` to report["skipped"]; no payload mutation; wired into `apply_ai_render_influence()` after `_report_execution_recommendations()`
- `tests/test_ai_phase26_execution_simulation.py` (new) — comprehensive test suite covering simulation schema, scoring, simulator builder, AIEditPlan field, render_influence reporter, safety invariants, and AI Director integration

**Simulation gain model:**

| Simulation | Retention | Story | Subtitle | Pacing | Source |
|------------|-----------|-------|----------|--------|--------|
| retention_pacing (fast_cuts) | +18 (low) / +10 (mid) | — | — | +8 | retention.score |
| creator_style | confidence×8 | — | — | confidence×10 | creator_style_adaptation |
| compact_subtitle | — | — | +12/+6/+3 | — | subtitle_execution.density |
| visual_rhythm (energetic) | +6 | — | — | +10 | beat_visual_execution.bpm |
| story_pacing (story_driven) | — | (100-score)×0.15 | — | +8 | story_optimization |
| safe_baseline | 0 | 0 | 0 | 0 | always present |

**Scoring formula:** `overall = clamp(50 + Σ(gain×weight) − safety_penalty − low_conf_dampening, 0, 100)`

**Safety penalties:** safe: −0, caution: −15, blocked: −50

**Recommendation selection:** best non-baseline simulation selected only when `score > baseline_score + 2.0`; otherwise `sim_safe_baseline` is recommended

**Safety boundaries enforced:**

- `advisory_only` always True — hardcoded in `AIExecutionSimulation.to_dict()`
- `mode` always "simulation_only" — hardcoded in `AISimulationPack.to_dict()`
- Simulations contain no `recommended_settings` — no forbidden key exposure
- Blocked simulations penalized −50 pts in scoring (prefer safe/caution)
- safe_baseline always available as stable neutral reference
- No FFmpeg commands altered
- No payload mutation — simulator reads edit_plan, never writes render payload
- No subtitle timing rewrite, no segment reorder, no playback_speed mutation
- No autonomous execution of any simulation result
- Never blocks render — all Phase 26 code wrapped in try/except in AI Director and simulator
- Deterministic — same edit_plan always produces same simulation pack
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- Actual execution apply
- Autonomous rendering
- FFmpeg mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Payload mutation
- Executor override
- Output duplication

**Architecture notes:**

- Phase 26 runs after Phase 25 (execution recommendations) so simulations can reference recommendation-backed metadata for higher fidelity estimates
- Supplemental direct-metadata simulators fire for any gain category not already covered by a recommendation-backed simulation (no duplicates)
- `score_simulation()` is pure — same simulation object always returns same score regardless of edit_plan context

**Verification:**

- Phase 26 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 25: Safe Execution Recommendation Layer

**Implemented:**

- `app/ai/execution/__init__.py` (new) — package marker; Phase 25 execution package
- `app/ai/execution/execution_schema.py` (new) — `VALID_CATEGORIES` frozenset ({subtitle, pacing, camera, creator_style, retention, visual_rhythm, safe_baseline}); `AIExecutionRecommendation` dataclass (recommendation_id, label, category, confidence, safe_to_apply, advisory_only always True, recommended_settings, blocked_settings, warnings, explanation; `to_dict()` hardcodes advisory_only=True, clamps confidence [0,1], caps explanation at 5, coerces invalid category to "safe_baseline"); `AIExecutionPack` dataclass (available, mode always "advisory", recommendations, recommended_pack_id, warnings; `to_dict()` hardcodes mode="advisory", caps recommendations at 10)
- `app/ai/execution/execution_safety.py` (new) — `sanitize_execution_settings(settings) -> dict`; strips all forbidden keys, retains only `_ALLOWED_KEYS`; `is_execution_recommendation_safe(recommendation, context) -> bool`; checks recommended_settings for forbidden keys; `_ALLOWED_KEYS = {subtitle_density, subtitle_emphasis, camera_behavior, pacing_style, creator_style, visual_rhythm_mode, hook_density, target_duration_hint, ai_mode}`; `_FORBIDDEN_KEYS = {playback_speed, segment_start, segment_end, subtitle_timing, ffmpeg_args, codec, bitrate, crf, validation_rules, output_path, render_command}`; never raises; no payload mutation
- `app/ai/execution/execution_recommendation.py` (new) — `build_execution_recommendations(edit_plan, context) -> AIExecutionPack`; reads: creator_style_adaptation, retention, subtitle_execution, beat_visual_execution, story_optimization; safe_baseline always built first; `_build_creator_style_recommendation()`: maps Phase 23 style_id to camera_behavior + pacing_style; safe_to_apply=True only when confidence ≥ 0.50; `_build_retention_recommendation()`: fast_cuts/high-hook for score<40, retention_optimized/medium for score<70, standard/low otherwise; `_build_visual_rhythm_recommendation()`: energetic(>120bpm)/moderate(>80bpm)/calm; `_build_story_pacing_recommendation()`: story_driven for three_act/hero_journey, fast_cuts for montage/highlight; `_select_recommended()`: max by confidence×100 + category bonus (retention+15, creator_style+10, pacing+8, subtitle+6, visual_rhythm+4) minus 20 if not safe_to_apply; all settings sanitized via `sanitize_execution_settings()` before attachment; emits `ai_execution_recommendations_created` at INFO, `ai_execution_recommendation_fallback` on error; deterministic; never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `execution_recommendations: dict = field(default_factory=dict)` added to `AIEditPlan`; `"execution_recommendations": dict(self.execution_recommendations)` in `to_dict()`; backward-compatible; Phase 24 `render_decision_preview` field unchanged
- `app/ai/director/ai_director.py` (updated) — `_attach_execution_recommendations(plan, job_id)` added; runs after Phase 24 (render decision preview); calls `build_execution_recommendations(plan, context)`; `_append_execution_recommendations_explainability(plan, pack_dict)` appends: "AI execution recommendation pack prepared", "Retention-oriented pacing recommendation available" / "Creator-style execution recommendation available" / "Story-driven pacing recommendation available", "Autonomous execution remains blocked"; None guard on plan; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_execution_recommendations(payload, edit_plan, report)` added; checks `edit_plan.execution_recommendations`, adds `"execution_recommendations:deferred_phase25(count=...,recommended=...)"` to report["skipped"]; no payload mutation; wired into `apply_ai_render_influence()` after `_report_render_decision_preview()`
- `tests/test_ai_phase25_execution_recommendation.py` (new) — comprehensive test suite covering execution schema, safety gates, recommendation builder, AIEditPlan field, render_influence reporter, safety invariants, and AI Director integration

**Recommendation categories and scoring:**

| Category | Bonus | Source |
|----------|-------|--------|
| `retention` | +15 | retention.overall_retention_score |
| `creator_style` | +10 | creator_style_adaptation.primary_style |
| `pacing` | +8 | story_optimization.flow_type |
| `subtitle` | +6 | subtitle_execution.density |
| `visual_rhythm` | +4 | beat_visual_execution.bpm |
| `safe_baseline` | 0 | always present |

**Retention pacing thresholds:**

| Score range | Pacing style | Hook density |
|-------------|-------------|--------------|
| < 40 | fast_cuts | high |
| 40–69 | retention_optimized | medium |
| ≥ 70 | standard | low |

**Safety boundaries enforced:**

- `advisory_only` always True — hardcoded in `AIExecutionRecommendation.to_dict()`
- `mode` always "advisory" — hardcoded in `AIExecutionPack.to_dict()`
- `_FORBIDDEN_KEYS` (playback_speed, segment_start, segment_end, subtitle_timing, ffmpeg_args, codec, bitrate, crf, validation_rules, output_path, render_command) always stripped by `sanitize_execution_settings()`
- `is_execution_recommendation_safe()` returns False if any forbidden key detected
- safe_baseline always available as stable fallback
- No FFmpeg commands altered
- No payload mutation — builder reads edit_plan, never writes render payload
- No subtitle timing rewrite
- No segment reorder
- No playback_speed mutation
- No autonomous execution of any recommendation
- Never blocks render — all Phase 25 code wrapped in try/except in AI Director and builder
- Deterministic — same edit_plan always produces same recommendations
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- Autonomous execution of recommendations
- Direct render mutation
- FFmpeg filter chain mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Payload mutation
- Automatic execution apply
- Render executor override

**Architecture notes:**

- Phase 25 runs after Phase 24 (render decision preview) so all prior AI phase outputs are available
- safe_baseline recommendation always scored at confidence=1.0 but with 0 category bonus, so a high-confidence retention/style recommendation will be selected as recommended_pack_id instead
- `_ALLOWED_KEYS` whitelist is the authoritative list of settings the recommendation layer can suggest
- Creator style → camera behavior mapping mirrors Phase 23 adaptation hints for consistency

**Verification:**

- Phase 25 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 24: AI Render Decision Preview Foundation

**Implemented:**

- `app/ai/preview/__init__.py` (new) — package marker; Phase 24 preview package
- `app/ai/preview/preview_schema.py` (new) — `VALID_SAFETY_STATUSES` frozenset ({safe, caution, blocked, unavailable}); `AIRenderDecisionPreview` dataclass (available, mode, selected_variant_id, creator_style, decision_summary, recommended_actions, blocked_actions, safety_status, confidence, warnings, explanation; `to_dict()` hardcodes mode="advisory", clamps confidence [0,1], caps recommended_actions at 10, explanation at 8, coerces invalid safety_status to "safe"); `AIPreviewSafetyReport` dataclass (safe_to_preview, safe_to_execute always False, blocked_reasons, advisory_only always True, warnings; `to_dict()` hardcodes safe_to_execute=False and advisory_only=True)
- `app/ai/preview/decision_preview.py` (new) — `build_render_decision_preview(edit_plan, context) -> dict`; aggregates variant_selection, creator_style_adaptation, retention, story_optimization, subtitle_execution, timing_mutation metadata into a single advisory summary; `_BLOCKED_ACTIONS = [autonomous_rendering_of_selected_variant, ffmpeg_filter_chain_mutation, timing_mutation_application, subtitle_timing_rewrite, playback_speed_mutation, segment_reorder]` always included; `_determine_safety_status()`: unavailable when no variant metadata, caution when ret_score<40 or variant_confidence<0.30, safe otherwise; `_compute_overall_confidence()`: weighted blend of variant_confidence, style_confidence, ret_score/100, narrative_score/100; result always includes `safety_report` sub-dict; emits `ai_render_decision_preview_created` at INFO, `ai_render_decision_preview_fallback` on error; deterministic; never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `render_decision_preview: dict = field(default_factory=dict)` added to `AIEditPlan`; `"render_decision_preview": dict(self.render_decision_preview)` in `to_dict()`; backward-compatible
- `app/ai/director/ai_director.py` (updated) — `_attach_render_decision_preview(plan, job_id)` added; runs after Phase 22 (variant selection) to aggregate all prior phase outputs; calls `build_render_decision_preview(plan, context)`; `_append_render_decision_preview_explainability(plan, preview_dict)` appends: "AI render decision preview prepared", "Selected advisory variant summarized", "Autonomous render actions remain blocked"; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_render_decision_preview(payload, edit_plan, report)` added; checks `edit_plan.render_decision_preview`, adds `"render_decision_preview:deferred_phase24(status=...,confidence=...,selected_variant=...)"` to report["skipped"]; no payload mutation; wired into `apply_ai_render_influence()` after `_report_variant_selection()`
- `tests/test_ai_phase24_render_decision_preview.py` (new) — comprehensive test suite covering preview schema, decision_preview builder, blocked actions constant, AIEditPlan field, render_influence reporter, safety invariants, and AI Director integration

**Safety boundaries enforced:**

- `safe_to_execute` always False — hardcoded in both `AIPreviewSafetyReport.to_dict()` and the constant
- `advisory_only` always True — hardcoded in `AIPreviewSafetyReport.to_dict()`
- `mode` always "advisory" — hardcoded in `AIRenderDecisionPreview.to_dict()`
- `_BLOCKED_ACTIONS` always present in every preview result regardless of metadata
- `phase24_advisory_only_mode` always in `safety_report.blocked_reasons`
- No FFmpeg commands altered
- No payload mutation — preview reads all prior phase metadata, never writes render payload
- No subtitle timing rewrite
- No segment reorder
- No playback_speed mutation
- No autonomous rendering of any variant
- Never blocks render — all Phase 24 code wrapped in try/except in AI Director and decision_preview
- Deterministic — same edit_plan always produces same preview
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- Autonomous rendering based on selected variant
- FFmpeg filter chain mutation
- Timing mutation application
- Subtitle timing rewrite
- Playback_speed mutation
- Segment reorder
- Any payload mutation

**Architecture notes:**

- Phase 24 runs after Phase 22 (variant selection) so it can aggregate all prior AI phase outputs into a unified advisory summary
- Reads from: variants, variant_selection, creator_style_adaptation, retention, story_optimization, subtitle_execution, timing_mutation, explainability
- Advisory mode is a permanent constraint in Phase 24 — not a configurable parameter
- `_BLOCKED_ACTIONS` is a module-level constant to prevent accidental omission

**Verification:**

- Phase 24 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 23: Creator Style Adaptation Foundation

**Implemented:**

- `app/ai/styles/style_schema.py` (updated, Phase 23 additions) — `DetectedStyleProfile` dataclass added (style_id, label, confidence, pacing_style, subtitle_style, camera_style, energy_level, hook_density, explanation, warnings; `to_dict()` coerces invalid style_id to `safe_generic`); `CreatorStyleSet` dataclass added (detected, primary_style, styles, fallback_used, warnings; `to_dict()` caps styles at 5); `VALID_P23_STYLES` frozenset added ({viral_tiktok, cinematic, educational, podcast, product_demo, storytelling, commentary, interview, safe_generic}); Phase 14 classes unchanged (backward compatible)
- `app/ai/styles/style_classifier.py` (updated, Phase 23 additions) — `detect_creator_styles(edit_plan, context) -> CreatorStyleSet` added; reads Phase 14 `creator_style.dominant_style` and maps to Phase 23 ID via `_P14_TO_P23` dict; derives secondary style candidates from pacing/retention/story metadata; `safe_generic` fallback when p14 dominant=unknown or confidence<20; emits `ai_creator_style_detected` at INFO, `ai_creator_style_fallback` when fallback; deterministic; never raises; Phase 14 `classify_creator_style()` unchanged
- `app/ai/styles/style_adapter.py` (new) — `build_style_adaptation(style_profile, edit_plan, context) -> dict`; maps Phase 23 style_id to advisory hint dict ({subtitle_density, subtitle_style, pacing_hint, camera_hint, hook_density_hint, visual_rhythm_hint, preset_hint}); safety gate strips any key not in `_SAFE_HINT_KEYS` and any key in `_FORBIDDEN_HINT_KEYS`; context-aware adjustments: low retention score raises hook_density from low→medium; compact subtitle execution lowers subtitle_density from high→medium; emits `ai_creator_style_adaptation_applied` at INFO; deterministic; never raises; never mutates payload
- `app/ai/styles/style_scoring.py` (new) — `score_style_fit(style_profile, variant, edit_plan) -> dict`; returns {style_fit_score 0-100, confidence 0-1, reasons, warnings}; per-style × per-purpose fit score table (`_STYLE_PURPOSE_FIT`); low confidence (<0.30) dampens score toward neutral 60; safe_generic always returns stable 58-65 range; deterministic; never raises; no ML models; no external APIs
- `app/ai/variants/variant_selector.py` (updated, Phase 23 additions) — `_compute_style_bonuses(scored, edit_plan) -> dict` added; reads `edit_plan.creator_style_adaptation` (detected + confidence ≥ 0.20); calls `score_style_fit()` for each variant; applies bonus = (fit_score − 60) / 100 × 16 (range −8 to +8) to sort key only; original score dict unchanged (confidence math unaffected); `_sort_key` updated to include bonus; never raises; all prior Phase 22 logic preserved
- `app/ai/director/edit_plan_schema.py` (updated) — `creator_style_adaptation: dict = field(default_factory=dict)` added to `AIEditPlan`; `"creator_style_adaptation": dict(self.creator_style_adaptation)` in `to_dict()`; backward-compatible; Phase 14 `creator_style` field unchanged
- `app/ai/director/ai_director.py` (updated) — `_attach_creator_style_adaptation(plan, job_id)` added; runs between Phase 20 and Phase 21 so style adaptation is available when variant selector executes; calls `detect_creator_styles(plan)` + `build_style_adaptation(primary_profile, plan)`; stores compact {detected, primary_style, confidence, adaptation, fallback_used, warnings}; `_append_creator_style_adaptation_explainability(plan, style_set, adaptation_result)` appends: "Creator style classified as viral TikTok", "Fast pacing adaptation suggested", "Creator style: safe generic fallback used", etc.; wrapped in try/except; never blocks render; Phase 14 `_attach_creator_style()` call preserved
- `tests/test_ai_phase23_creator_style.py` (new) — comprehensive test suite covering style schema, detect_creator_styles, build_style_adaptation, score_style_fit, AIEditPlan field, AI Director integration, variant selector style-fit bonus, and all safety boundaries

**Supported Phase 23 style IDs:**

| ID | Label | Pacing | Subtitle | Camera | Hook Density |
|----|-------|--------|----------|--------|--------------|
| `viral_tiktok` | Viral TikTok | fast | punch | fast_follow | high |
| `cinematic` | Cinematic | slow_build | minimal | slow_reveal | low |
| `educational` | Educational | medium | bold | static | medium |
| `podcast` | Podcast | medium | clean | static | low |
| `product_demo` | Product Demo | medium | overlay | static | medium |
| `storytelling` | Storytelling | slow_build | minimal | pan | medium |
| `commentary` | Commentary | fast | bold | reaction | high |
| `interview` | Interview | slow | clean | static | low |
| `safe_generic` | Generic | default | default | auto | medium |

**Phase 14 → Phase 23 mapping:**

| Phase 14 | Phase 23 |
|----------|----------|
| podcast_viral | viral_tiktok |
| high_energy_reaction | commentary |
| storytelling_cinematic | cinematic |
| documentary_clean | podcast |
| educational_focus | educational |
| anime_edit | viral_tiktok |
| gameplay_highlight | commentary |
| motivation_short | viral_tiktok |
| interview_clip | interview |
| calm_minimal | safe_generic |

**Verification:**

- Phase 23 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- Adaptation output contains only advisory hint keys (subtitle_density, pacing_hint, camera_hint, etc.)
- `_FORBIDDEN_HINT_KEYS` (playback_speed, segment_start, segment_end, subtitle_timing, ffmpeg_args, codec, crf, bitrate, output_path, validation_rules) always stripped
- No FFmpeg commands altered
- No payload mutation — style detection and adaptation read edit_plan, never write render payload
- No subtitle timing rewrite
- No segment reorder
- No playback_speed mutation
- Style-fit bonus applied to sort key only — base scores unchanged, confidence gate unaffected
- Never blocks render — all Phase 23 code wrapped in try/except in AI Director
- Deterministic — same edit_plan always produces same style detection result
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- Autonomous rendering based on detected style
- Creator-style auto-editing (FFmpeg filter chains)
- playback_speed mutation
- subtitle timing rewrite
- segment reorder
- payload mutation
- automatic export selection

**Architecture notes:**

- Phase 23 runs after Phase 20 (story optimization) and before Phase 21 (variant planning) so the style adaptation is available when the variant selector executes in Phase 22
- Phase 14 `creator_style` dict (dominant_style, confidence, etc.) preserved untouched; Phase 23 adds `creator_style_adaptation` as a separate field
- Style-fit bonus in variant selector: max ±8 pts on sort key — cannot override safety gates or high-risk penalties
- `safe_generic` always available as stable fallback with neutral score range (58-65)

**Integrated systems:**

- Creator Style Classification (Phase 14) — dominant_style mapped to Phase 23 ID
- Retention Intelligence (Phase 16) — low retention score raises hook_density hint
- Story Optimization (Phase 20) — narrative flow feeds secondary style signal
- Variant Selector (Phase 22) — style-fit bonus applied per variant
- Explainability (Phase 6) — compact lines appended to summary_lines

### 2026-05-08 — AI Productization Phase 22: AI Best Variant Selector Foundation

**Implemented:**

- `app/ai/variants/variant_selector.py` (new) — `select_best_variant(variant_set, edit_plan, context) -> dict`; returns {selected_variant_id, selection_confidence, selection_reasons, rejected_variants, fallback_used}; accepts `AIVariantSet`, serialised dict, or any object with `variants` attribute; scores all candidates via `score_variant()`; sort key: (−score, purpose_priority, risk_priority); skips `risk="high"` variants when any safe option exists; confidence gate: if selection_confidence < 0.50 and non-baseline selected, falls back to `safe_baseline`; emits `ai_variant_selected` at INFO, `ai_variant_selector_fallback` on fallback, `ai_variant_selection_skipped` when no variants; deterministic; never raises; never renders; never mutates payload
- `app/ai/variants/variant_scoring.py` (updated, Phase 22 additions) — `_RISK_PENALTIES["high"]` raised 30→40 for stronger selection pressure; `_BASELINE_FLOOR = 58.0` guarantees `safe_baseline` always scores ≥ 58; `normalized_score` field added to return dict (score / 100.0); `expected_gain` baseline shifted to `_BASELINE_FLOOR`; backward-compatible (all Phase 21 callers still receive `score`, `expected_gain`, `reasons`, `warnings`)
- `app/ai/director/edit_plan_schema.py` — `variant_selection: dict = field(default_factory=dict)` added to `AIEditPlan`; `"variant_selection": dict(self.variant_selection)` in `to_dict()`; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_variant_selection(plan, job_id)` added; runs only when `ai_variant_planning_enabled=True` AND `plan.variants.get("available")`; stores compact {selected_variant_id, selection_confidence, selection_reasons, fallback_used, rejected_count}; `_append_variant_selection_explainability(plan, selection)` appends: "AI selected retention-focused variant", "Safe baseline retained due to low confidence", "Creator-style variant scored highest", etc.; all wrapped in try/except; never block render; Phase 22 runs after Phase 21 in `_build_plan`
- `app/ai/director/render_influence.py` — `_report_variant_selection(payload, edit_plan, report)` added; reports selection as deferred in Phase 22; compact `report["skipped"]` entry with selected/confidence/fallback/rejected; no variant rendered, no payload mutated, no FFmpeg altered; called inside `apply_ai_render_influence` try block
- `tests/test_ai_phase21_variant_rendering.py` — `test_returns_dict_with_expected_keys` updated from strict set equality to `issubset` to accommodate new `normalized_score` field (non-breaking backward compatibility fix)
- `tests/test_ai_phase22_best_variant_selector.py` (new) — 48 tests covering selector core behaviour, confidence fallback, priority heuristics, scoring normalization, AIEditPlan field, AI Director integration, render influence defer, and all safety boundaries

**Verification:**

- Phase 22 tests pass (48 tests)
- Full suite passes (1402 tests, zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- No variant is ever rendered by the selector — metadata only
- `risk="high"` variants skipped from selection whenever any safe option exists
- Confidence gate < 0.50 → always falls back to `safe_baseline`
- `safe_baseline` guaranteed floor score (≥ 58) — selector always has a stable fallback
- No payload mutation — selector reads variant metadata, never writes to render payload
- No segment start/end timing changes
- No playback_speed changes
- No FFmpeg command changes
- No subtitle timing changes
- No automatic rendering of selected variant
- Never blocks render — all Phase 22 code wrapped in try/except in AI Director
- Deterministic — same input always produces same selected_variant_id

**Selection heuristics (priority order):**
1. Highest `score_variant()` score (base + confidence boost + safety gate + context boost − risk penalty)
2. Tiebreak: purpose_priority (retention → hook → story → subtitle → creator_style → pacing → safe_baseline)
3. Tiebreak: risk_priority (low → medium → high)
4. Confidence gate fallback: score < 50 → safe_baseline returned instead

**Intentionally still blocked:**

- Autonomous rendering of selected variant
- Multi-variant execution queue
- Auto-export best variant
- UI auto-selection
- Timing mutation application
- FFmpeg mutation
- Payload mutation

**Architecture notes:**

- Selector operates on Phase 21 `AIVariantSet` or its serialised dict form — no extra analysis
- `_report_variant_selection` in render_influence records plan as "deferred_phase22" — safe pass-through for future execution phase
- Phase 22 runs after Phase 21 in `_build_plan`; if Phase 21 produced no variants, Phase 22 is skipped
- `normalized_score` in scoring is additive — existing callers are unaffected

**Integrated systems:**

- Variant Planning (Phase 21) — AIVariantSet is the selector's input
- Variant Scoring (Phase 21/22) — `score_variant()` drives ranking
- Retention Intelligence (Phase 16) — context boost for low retention score
- Story Optimization (Phase 20) — context boost for weak_hook / low narrative_score
- Explainability (Phase 6) — compact lines appended to summary_lines

### 2026-05-08 — AI Productization Phase 21: Safe Autonomous Variant Rendering Foundation

**Implemented:**

- `app/ai/variants/__init__.py` (new) — package marker
- `app/ai/variants/variant_schema.py` (new) — `AIVariantPlan` dataclass (variant_id, label, purpose, confidence, risk, suggested_changes, expected_gain, safe_to_render, warnings); `AIVariantSet` dataclass (available, mode, variants capped at 5, recommended_variant_id, warnings); `VALID_PURPOSES` = {safe_baseline, retention, hook, subtitle, pacing, story, creator_style}; `VALID_RISKS` = {low, medium, high}; `clamp_variant_count(value) -> int` clamps to [1, 5]; no Pydantic, no heavy deps
- `app/ai/variants/variant_safety.py` (new) — `sanitize_variant_changes(changes) -> dict` strips all forbidden keys; `is_variant_safe(variant, context) -> bool`; gates: risk != "high", no forbidden keys in suggested_changes, non-empty variant_id; `ALLOWED_CHANGE_KEYS` = {subtitle_density, subtitle_emphasis, camera_behavior, pacing_style, target_duration_hint, creator_style, ai_mode}; `FORBIDDEN_CHANGE_KEYS` = {playback_speed, segment_start, segment_end, subtitle_timing, ffmpeg_args, codec, crf, bitrate, validation_rules, output_path}; never raises
- `app/ai/variants/variant_scoring.py` (new) — `score_variant(variant, edit_plan, context) -> dict`; returns {score 0-100, expected_gain 0-100, reasons, warnings}; base scores per purpose; risk penalty (high=-30, medium=-8); confidence boost (up to +15); safety gate modifier (+5 safe, -20 unsafe); context boosts from edit_plan retention/story/subtitle metadata; deterministic; never raises
- `app/ai/variants/variant_generator.py` (new) — `generate_variant_plans(edit_plan, context, count=3) -> AIVariantSet`; always includes safe_baseline; factories: retention (low retention score), hook (weak_hook issue), subtitle (subtitle_execution available), pacing (non-fast current pacing), story (low narrative_score), creator_style (dominant_style classified); sanitizes + safety-gates + scores all candidates; recommends highest expected_gain safe variant; mode always "advisory"; max 5 variants; never raises; never enqueues render; never mutates payload or edit_plan; emits `ai_variant_plans_generated` at INFO
- `app/models/schemas.py` — `ai_variant_planning_enabled: bool = False` and `ai_variant_count: int = 3` added after ai_timing_mutation_enabled; backward-compatible defaults
- `app/ai/director/edit_plan_schema.py` — `variants: dict = field(default_factory=dict)` added to `AIEditPlan`; `"variants": dict(self.variants)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_variant_plans(plan, count, job_id)` added; runs only when `ai_variant_planning_enabled=True`; calls `generate_variant_plans(plan, ...)` with clamped count; `_append_variant_explainability(plan, variant_set)` appends: "AI variant planning prepared safe A/B options", "Retention-focused variant suggested", "Compact subtitle variant available", "Hook-strengthening variant prepared"; all helpers wrapped in try/except; never block render; Phase 21 runs after Phase 20 in `_build_plan`
- `app/ai/director/render_influence.py` — `_report_variant_plans(payload, edit_plan, report)` added; reports variant planning as deferred in Phase 21; adds compact entry to `report["skipped"]` with mode/variants/safe/recommended counts; no extra render jobs enqueued, no payload mutated, no FFmpeg commands altered; called inside `apply_ai_render_influence` try block
- `tests/test_ai_phase21_variant_rendering.py` (new) — 73 tests covering schema defaults, to_dict(), valid purposes/risks, count clamping, variant safety, forbidden key stripping, scoring, generator invariants, request flags, AIEditPlan field, AI Director integration, render influence defer, and all safety boundaries

**Verification:**

- Phase 21 tests pass (73 tests)
- Full suite passes (1354 tests, zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- `FORBIDDEN_CHANGE_KEYS` always stripped from `suggested_changes` before storage
- `high` risk variants never receive `safe_to_render=True` from safety gate
- `mode` always `"advisory"` — variants are metadata only
- No extra render jobs enqueued — generator is pure metadata computation
- No payload mutation — generator reads edit_plan, never writes to payload
- No segment start/end timing changes
- No playback_speed changes
- No FFmpeg command changes
- No subtitle timing changes
- No segment reordering
- No automatic rendering of any variant
- Never blocks render — all Phase 21 code wrapped in try/except in AI Director
- Deterministic heuristics only — no cloud AI, no API keys, no GPU
- `ai_variant_planning_enabled` defaults to `False` — zero behavior change for existing requests

**Intentionally still blocked:**

- Actual multi-variant rendering
- Variant queue execution
- AI best variant selector with autonomous rendering
- UI variant selection
- Auto-export best variant
- Timing mutation application
- FFmpeg mutation
- Payload mutation

**Architecture notes:**

- Variant generator builds on all prior Phase 11–20 metadata — no new analysis
- Factory priority: baseline → retention → hook → subtitle → pacing → story → creator_style
- All candidates sanitized via `sanitize_variant_changes()` before scoring
- `_report_variant_plans` in render_influence records the plan as "deferred_phase21" — safe pass-through for future phases
- `clamp_variant_count` enforces [1, 5] regardless of request value

**Integrated systems:**

- Retention Intelligence (Phase 16) — low retention_score triggers retention variant
- Story Optimization (Phase 20) — weak_hook issue triggers hook variant; low narrative_score triggers story variant
- Subtitle Execution (Phase 17) — available subtitle_execution triggers subtitle variant
- Creator Style (Phase 14) — dominant_style triggers creator_style variant
- Pacing Intelligence (Phase 4) — non-fast pacing_style triggers pacing variant
- Explainability (Phase 6) — compact lines appended to summary_lines

### 2026-05-08 — AI Productization Phase 20: Story-driven Edit Optimization Foundation

**Implemented:**

- `app/ai/story_optimization/__init__.py` (new) — package marker
- `app/ai/story_optimization/story_optimization_schema.py` (new) — `StoryOptimizationIssue` dataclass (start, end, issue_type, severity, reason, suggested_action, confidence, safe_to_auto_apply always False in to_dict(), metadata); `StoryOptimizationPlan` dataclass (available, narrative_score, flow_type, issues capped at 10, recommendations capped at 8, warnings); `VALID_ISSUE_TYPES` = {weak_hook, missing_setup, long_setup, weak_build_up, missing_climax, weak_payoff, abrupt_outro, unclear_arc, retention_risk, unknown}; `VALID_SEVERITIES` = {low, medium, high}; `VALID_FLOW_TYPES` = {hook_to_climax, linear, flat, unknown}; no Pydantic, no heavy deps
- `app/ai/story_optimization/hook_optimizer.py` (new) — `analyze_hook_quality(story_context, retention_context, transcript_chunks) -> list[StoryOptimizationIssue]`; gates: hook segment presence, weak_hook retention risk, retention_risk score > 0.5; severity: high (no hook), medium (retention risk), low (mildly elevated score); no text rewriting; never raises; safe_to_auto_apply always False
- `app/ai/story_optimization/payoff_analyzer.py` (new) — `analyze_payoff_quality(story_context, retention_context) -> list[StoryOptimizationIssue]`; detects missing payoff (high severity), unclear_payoff retention risk, abrupt_ending, pacing_decay in payoff region, elevated payoff retention_risk; never raises; advisory only
- `app/ai/story_optimization/arc_optimizer.py` (new) — `analyze_story_arc(story_context, pacing_context, retention_context) -> dict`; returns {flow_type, narrative_score, issues, warnings}; flow classification: hook_to_climax (hook + climax present), linear (≥3 segments + linear flow), flat (≤1 segment or flat arc), unknown; base score from segment presence weights (hook=20, setup=10, build_up=15, climax=25, payoff=15, outro=5); bonus for full arc (+10-20); energy modifier (±5); retention risk deduction (-2 per risk); 60/40 blend with story retention_score when available; issues: weak_hook (no hook), missing_climax, weak_build_up (hook→climax without build-up), unclear_arc (flat), long_setup (setup > 1.5× climax+build_up duration); no segment reorder; never raises; emits `ai_story_arc_analyzed` at INFO
- `app/ai/story_optimization/story_recommender.py` (new) — `build_story_optimization_plan(story_context, retention_context, pacing_context, transcript_chunks) -> StoryOptimizationPlan`; combines hook + payoff + arc analyses; deduplicates issues by issue_type; issue-driven recommendations from map + flow-type recommendation; max 10 issues, max 8 recommendations; all safe_to_auto_apply=False enforced; never raises; emits `ai_story_optimization_generated` + `ai_story_optimization_issues_detected` at INFO
- `app/ai/director/edit_plan_schema.py` — `story_optimization: dict = field(default_factory=dict)` added to `AIEditPlan`; `"story_optimization": dict(self.story_optimization)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_story_optimization(plan, chunks, pacing_ctx, job_id)` added; called after Phase 19 in `_build_plan`; pulls story/retention context from plan; `_append_story_optimization_explainability(plan, opt_plan)` appends: "Strong hook-to-climax flow detected" (hook_to_climax), "Story arc can be tightened" (long_setup/weak_build_up), "Payoff clarity may improve retention" (weak_payoff/abrupt_outro), "Opening hook may need strengthening" (weak_hook), "Narrative arc needs clearer structure" (unclear_arc/missing_climax); all helpers wrapped in try/except; never block render
- `app/ai/director/render_influence.py` — `_report_story_optimization(payload, edit_plan, report)` added; reports story optimization as deferred in Phase 20; adds compact entry to `report["skipped"]` with flow/score/issue/recommendation counts; no segment ordering changed, no timing changed, no subtitle rewritten, no FFmpeg commands altered; called inside `apply_ai_render_influence` try block
- `tests/test_ai_phase20_story_optimization.py` (new) — 69 tests covering schema defaults, to_dict(), valid types/severities, hook optimizer, payoff analyzer, arc optimizer, story recommender, render influence defer, AI Director integration, and all safety boundaries

**Verification:**

- Phase 20 tests pass (69 tests)
- Full suite passes (1281 tests, zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- `safe_to_auto_apply` structurally False in `StoryOptimizationIssue.to_dict()` — cannot be overridden regardless of stored value
- No segment start/end timing changes — story optimization is metadata-only in Phase 20
- No playback_speed changes
- No FFmpeg command changes
- No subtitle timing changes
- No automatic segment reordering
- No transcript text rewriting
- Never blocks render — all Phase 20 code wrapped in try/except in AI Director
- Deterministic heuristics only — no cloud AI, no API keys, no GPU

**Not yet implemented (intentionally blocked):**

- Automatic segment reordering
- Story-aware timing execution
- Autonomous narrative editing
- AI-generated hook rewriting
- Render-time story mutation

**Known limitations:**

- Advisory only — all issues have safe_to_auto_apply=False
- Deterministic heuristics only — no ML models
- No segment/timing mutation
- No subtitle rewrite
- No autonomous editing

**Architecture notes:**

- Story optimization builds on existing Phase 12 story structure, Phase 16 retention risks, and Phase 4 pacing — no new analysis
- Arc scoring blends structural segment presence (60%) with Phase 12 retention_score (40%) for stability
- `_report_story_optimization` in render_influence records the plan as "deferred_phase20" — safe pass-through for future phases
- Phase 20 runs after Phase 19 (timing mutation) in the AI Director `_build_plan` sequence
- Issues are deduplicated by issue_type before capping at 10

**Integrated systems:**

- Story Intelligence (Phase 12) — segments, dominant_arc, narrative_flow, retention_score drive arc classification
- Retention Intelligence (Phase 16) — risk_regions drive hook/payoff issue detection
- Pacing Intelligence (Phase 4) — energy_level biases narrative score up/down
- Explainability (Phase 6) — compact lines appended to summary_lines

### 2026-05-08 — AI Productization Phase 19: Retention-driven Timing Mutation Foundation

**Implemented:**

- `app/ai/timing/__init__.py` (new) — package marker
- `app/ai/timing/timing_schema.py` (new) — `TimingMutationCandidate` dataclass (start, end, action, confidence, reason, risk_category, max_trim_seconds clamped [0, 1.5], safe_to_apply, warnings); `TimingMutationPlan` dataclass (available, mode, candidates capped at 10, estimated_retention_gain, warnings); `VALID_ACTIONS` = {tighten_setup, trim_silence, shorten_outro, hold_hook, no_change, none}; `_MAX_TRIM_SECONDS = 1.5`, `_MIN_CONFIDENCE = 0.70`, `_MIN_REGION_DURATION = 3.0`, `_MAX_CANDIDATES = 10`; no Pydantic, no heavy deps
- `app/ai/timing/timing_safety.py` (new) — `clamp_trim_seconds(value, max_value=1.5) -> float`; `is_candidate_safe(candidate, context=None) -> bool`; gates: confidence ≥ 0.70, action not in {no_change, none, hold_hook}, region duration ≥ 3.0 s, start ≥ 0, max_trim_seconds ≤ 1.5; never raises
- `app/ai/timing/timing_analyzer.py` (new) — `analyze_timing_candidates(retention_context, story_context, pacing_context, transcript_chunks) -> list[TimingMutationCandidate]`; risk-to-action map: long_setup→tighten_setup, silence_gap→trim_silence, pacing_decay (last 25%)→shorten_outro, weak_hook→hold_hook (max_trim=0, advisory only), unclear_payoff→no_change (max_trim=0); confidence derived from severity + pacing energy boost; max_trim per category: long_setup=1.0, silence_gap=0.8, pacing_decay=1.5; never trim more than 25% of region; max 10 candidates; safe_to_apply always False from analyzer; never raises; emits `ai_timing_candidates_analyzed` at INFO
- `app/ai/timing/timing_recommender.py` (new) — `build_timing_mutation_plan(..., enabled=False) -> TimingMutationPlan`; enabled=False → mode='advisory', all safe_to_apply=False; enabled=True → runs is_candidate_safe gate; estimated_retention_gain computed from safe candidates (confidence × trim_ratio × 0.05 cap); never raises; emits `ai_timing_mutation_plan_generated` at INFO
- `app/models/schemas.py` — `ai_timing_mutation_enabled: bool = False` added after ai_beat_transition_enabled; backward-compatible default preserves existing behavior
- `app/ai/director/edit_plan_schema.py` — `timing_mutation: dict = field(default_factory=dict)` added to `AIEditPlan`; `"timing_mutation": dict(self.timing_mutation)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_timing_mutation(plan, chunks, pacing_ctx, enabled, job_id)` added; called after Phase 18 in `_build_plan`; pulls retention/story context from plan; `_append_timing_mutation_explainability(plan, timing_plan)` appends: "Retention risk: setup pacing candidate identified" (tighten_setup), "Retention risk: silence gap trim candidate identified" (trim_silence), "Retention risk: outro pacing decay candidate identified" (shorten_outro), "Timing mutation plan advisory-only (no segments changed)" (advisory mode), "Timing mutation plan ready (N safe candidates, est. gain=X%)" (enabled mode); all helpers wrapped in try/except; never block render
- `app/ai/director/render_influence.py` — `_report_timing_mutation(payload, edit_plan, report)` added; reports timing mutation as deferred in Phase 19; adds compact entry to `report["skipped"]` with mode/candidate/safe/gain counts; no segment start/end changed, no playback_speed changed, no FFmpeg commands altered; called inside `apply_ai_render_influence` try block
- `tests/test_ai_phase19_timing_mutation.py` (new) — 63 tests covering schema defaults, to_dict(), valid actions, safety gates, analyzer heuristics, recommender modes, render influence defer, AI Director integration, and all safety boundaries

**Verification:**

- Phase 19 tests pass (63 tests)
- Full suite passes (1212 tests, zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- `max_trim_seconds` hard cap: 1.5 s — no AI-proposed trim exceeds this
- `hold_hook` in `_ADVISORY_ONLY_ACTIONS` — can never receive safe_to_apply=True
- `no_change` and `none` in `_ADVISORY_ONLY_ACTIONS` — advisory-only actions always blocked
- `confidence` gate: ≥ 0.70 — low-confidence candidates always blocked
- `region duration` gate: ≥ 3.0 s — micro-regions always blocked
- `start ≥ 0` gate — hook region start never trimmed below zero
- `enabled=False` default — advisory-only mode; no segment timing changed until explicitly opted in
- No segment start/end timing changes — timing mutation is metadata-only in Phase 19
- No playback_speed changes
- No FFmpeg command changes
- No subtitle timing changes
- Never blocks render — all Phase 19 code wrapped in try/except in AI Director
- Deterministic heuristics only — no cloud AI, no API keys, no GPU

**Architecture notes:**

- Timing candidates are derived from retention risk regions (Phase 16) — no new audio analysis
- `pacing_decay` rule only applies to the last 25% of content to prevent erroneous mid-video trim proposals
- `hold_hook` produces advisory-only candidates with max_trim=0 — signals the hook needs strengthening, not cutting
- `_report_timing_mutation` in render_influence records the plan as "deferred_phase19" — safe pass-through for future phases
- Phase 19 runs after Phase 18 (beat visual execution) in the AI Director `_build_plan` sequence
- estimated_retention_gain is bounded (confidence × trim_ratio × 0.05 per candidate, sum capped at 1.0)

**Integrated systems:**

- Retention Intelligence (Phase 16) — risk_regions drive all candidate generation
- Story Intelligence (Phase 12) — story segments available for future region refinement
- Pacing Intelligence (Phase 4) — energy_level and total_duration used for confidence boosts and last-quarter check
- Explainability (Phase 6) — compact lines appended to summary_lines

### 2026-05-08 — AI Productization Phase 18: Beat-synced Visual Execution Foundation

**Implemented:**

- `app/ai/visuals/__init__.py` (new) — package marker
- `app/ai/visuals/beat_visual_schema.py` (new) — `BeatPulseRegion` dataclass (start, end, pulse_strength clamped [0, 0.15], pulse_style, beat_count, warnings); `TransitionHint` dataclass (start, end, transition_style, confidence, reason, safe_to_apply always False in to_dict()); `BeatVisualExecutionPlan` dataclass (available, execution_mode="metadata_only", bpm, pulse_regions capped at 12, transition_hints capped at 10, warnings); `VALID_PULSE_STYLES` = {none, soft_pulse, punch_pulse, cinematic_pulse}; `VALID_TRANSITION_STYLES` = {none, soft_cut, beat_pulse, energy_pop, cinematic_push}; `_MAX_PULSE_STRENGTH = 0.15`, `_BPM_MIN = 60.0`, `_BPM_MAX = 190.0`, `_MIN_BEAT_COUNT = 4`; no Pydantic, no heavy deps
- `app/ai/visuals/beat_pulse.py` (new) — `build_beat_pulse_regions(pacing_context, beat_execution_context, story_context, retention_context) -> list[BeatPulseRegion]`; gate checks: beat_available required, BPM must be [60, 190], beat_count ≥ 4; style selection: dominant_arc in {tension_release, emotional_peak, curiosity_build, setup_payoff} → cinematic_pulse; energy ≥ 0.7 + fast pacing or bpm ≥ 120 → punch_pulse; energy < 0.3 → soft_pulse; per-story-segment regions with boost for hook/climax/tension/build_up; retention risk overlap softens pulse × 0.5; fallback single region when no story segments; max 12 regions; never raises; emits `ai_beat_pulse_regions_generated` at INFO
- `app/ai/visuals/transition_planner.py` (new) — `build_transition_hints(pacing_context, story_context, retention_context, creator_style_context) -> list[TransitionHint]`; advisory-only; safe_to_apply structurally False; segment-pair transition map: hook→build_up=beat_pulse, build_up→climax=cinematic_push, climax→payoff=energy_pop, etc.; hype creator styles (anime_edit, high_energy_reaction, gameplay_highlight, podcast_viral) → energy_pop override; calm styles (documentary_clean, calm_minimal, interview_clip) → soft_cut override; fast pacing + beat + bpm in range → beat_pulse fallback; arc fallback mapping; max 10 hints; never raises; emits `ai_transition_hints_generated` at INFO
- `app/ai/visuals/visual_execution.py` (new) — `build_beat_visual_execution_plan(...) -> BeatVisualExecutionPlan`; orchestrates pulse regions + transition hints; execution_mode always "metadata_only"; availability requires beat_available + valid bpm + beat_count ≥ 4; never raises; emits `ai_beat_visual_execution_generated` at INFO
- `app/ai/director/edit_plan_schema.py` — `beat_visual_execution: dict = field(default_factory=dict)` added to `AIEditPlan`; `"beat_visual_execution": dict(self.beat_visual_execution)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_beat_visual_execution(plan, pacing_ctx, job_id)` added; called after Phase 17 in `_build_plan`; pulls beat_execution/story/retention/creator_style context from plan; `_append_beat_visual_explainability(plan, visual_plan)` appends: "Beat pulse visual rhythm planned" (punch_pulse regions), "Cinematic visual rhythm planned" (cinematic_pulse regions), "High-energy visual transition hints detected" (energy_pop/cinematic_push/beat_pulse hints), "Visual beat execution remains metadata-only"; all helpers wrapped in try/except; never block render
- `app/ai/director/render_influence.py` — `_report_beat_visual_execution(payload, edit_plan, report)` added; reports beat visual execution as deferred in Phase 18; adds compact entry to `report["skipped"]` with bpm/pulse_regions/transition_hints counts; no FFmpeg commands altered, no timing changed, no visual effects applied; called inside `apply_ai_render_influence` try block
- `tests/test_ai_phase18_beat_visual_execution.py` (new) — 80+ tests covering schema defaults, to_dict(), pulse planner gates, energy/arc style mapping, density softening, transition advisory, render influence defer, AI Director integration, and all safety boundaries

**Verification:**

- Phase 18 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- `pulse_strength` hard cap: 0.15 — matches Phase 11 beat_execution constraint
- `safe_to_apply` structurally False in `TransitionHint.to_dict()` — cannot be overridden
- `execution_mode` always "metadata_only" — planner never sets anything else
- BPM gate: [60.0, 190.0] — outside range → empty regions returned
- beat_count gate: ≥ 4 — below threshold → empty regions returned
- No FFmpeg command changes — beat visual plan is metadata only
- No clip start/end timing changes
- No subtitle timing changes
- No playback_speed changes
- No output validation/status rule changes
- No librosa at runtime — all metadata sourced from existing pacing/beat context
- Never blocks render — all Phase 18 code wrapped in try/except in AI Director
- Deterministic heuristics only — no cloud AI, no API keys, no GPU

**Architecture notes:**

- Beat visual execution builds on existing Phase 11 beat metadata (`plan.beat_execution`) and Phase 4 pacing context — no new audio analysis
- Pulse regions are derived from story segment boundaries (Phase 12) — no new timing introduced
- Transition hints are advisory boundaries between adjacent story segments — no cut mutation
- `_report_beat_visual_execution` in render_influence records the plan as "deferred_phase18" — safe pass-through for future phases
- Phase 18 runs after Phase 17 (subtitle execution) in the AI Director `_build_plan` sequence

**Integrated systems:**

- Beat/Pacing Intelligence (Phase 4/11) — beat_available, bpm, beat_count, energy_level, pacing_style drive all gates
- Story Intelligence (Phase 12) — story segments provide region boundaries; dominant_arc informs pulse/transition style
- Retention Intelligence (Phase 16) — risk_regions soften pulse in overlap zones
- Creator Style Intelligence (Phase 14) — dominant_style biases transition hint style
- Explainability (Phase 6) — compact lines appended to summary_lines

**What Beat Visual Execution can do now:**

- Generate compact beat pulse regions from BPM/energy/story segment metadata
- Classify pulse style per region: punch_pulse (high energy), cinematic_pulse (cinematic arc), soft_pulse (low energy)
- Soften pulse in retention risk overlap zones
- Generate advisory transition hints for adjacent story segment pairs
- Map creator style and story arc to specific transition styles
- Expose compact `"beat_visual_execution"` key in render result_json
- Report beat visual execution as safely deferred in render_influence
- Append advisory explainability lines to AI summary

**Not yet implemented:**

- Actual FFmpeg beat pulse visual effect
- Actual beat-synced transitions in rendered output
- Timeline-driven transition editor
- Autonomous timing mutation
- Playback speed mutation
- per-frame visual beat synchronization

**Known limitations:**

- Metadata-first execution only — no visual output change in Phase 18
- Advisory transition hints only — `safe_to_apply` always False
- No FFmpeg visual mutation
- No clip timing mutation
- No subtitle timing mutation
- Pulse regions derived from story segment boundaries — not from precise audio beat timestamps

> Phase 18 extends the AI system from subtitle execution intelligence toward beat-synced visual rhythm planning, enabling energy-aware pulse regions and advisory transition hints while preserving complete render stability and safety.

---

### 2026-05-08 — AI Productization Phase 17: Dynamic Subtitle Execution Foundation

**Implemented:**

- `app/ai/subtitles/__init__.py` (new) — package marker
- `app/ai/subtitles/subtitle_execution_schema.py` (new) — `SubtitleExecutionHint` dataclass (emphasis_strength, density_mode, emotion_style, beat_sync_strength, keyword_focus, warnings); `SubtitleExecutionRegion` dataclass (start, end, style, emphasis, emotion, beat_strength, metadata); `SubtitleExecutionPlan` dataclass (available, regions capped at 20, global_hint, warnings); `VALID_DENSITY_MODES` = {compact, normal, expressive}; `VALID_EMOTION_STYLES` = {neutral, hype, dramatic, calm, emotional, punch}; all have `to_dict()` methods; no Pydantic, no heavy deps
- `app/ai/subtitles/subtitle_emphasis.py` (new) — `build_subtitle_emphasis(transcript_chunks, pacing_context, emotion_context, retention_context) -> dict`; deterministic only; never raises; `_detect_hook_strength()` scores hook keyword density in early chunks (ratios → 0.85/0.6/0.3/0.1); `_extract_keyword_focus()` extracts keyword_focus list from early chunks; emotion contribution: urgency/excitement/surprise/hype → +0.3–0.5; energy_level > 0.7 → +0.25 emphasis +0.3 beat_sync; beat_available + bpm ≥ 120 → +0.2–0.4 beat_sync; weak_hook retention risk → +0.1 emphasis; all values clamped [0, 1]; emits `ai_subtitle_emphasis_generated` at INFO
- `app/ai/subtitles/subtitle_density.py` (new) — `analyze_subtitle_density(transcript_chunks, pacing_context, story_context) -> dict`; deterministic only; never raises; overload detection: avg_words > 6.0 or max_words > 12 → compact + overload_detected; pacing fast/dynamic → compact; slow_build/slow → expressive; avg_words < 3.0 → expressive; story arc curiosity_build/tension_release/front_loaded → compact; emits `ai_subtitle_density_detected` at INFO
- `app/ai/subtitles/subtitle_emotion.py` (new) — `detect_subtitle_emotion_style(emotion_context, story_context, creator_style_context) -> dict`; deterministic only; never raises; maps emotion → style via `_EMOTION_STYLE_MAP`; maps pacing_style → style via `_PACING_STYLE_MAP`; maps dominant_arc → style via `_ARC_STYLE_MAP`; maps creator_style → style via `_CREATOR_STYLE_MAP`; confidence = top_score × 0.8 + gap × 0.4, clamped [0, 1]; supported mappings: hype/fast pacing → punch/hype; cinematic/tension arc → dramatic; calm/slow → calm; emotional arc → emotional
- `app/ai/subtitles/subtitle_execution.py` (new) — `build_subtitle_execution_plan(...) -> SubtitleExecutionPlan`; orchestrates emphasis + density + emotion; builds temporal regions from transcript chunks (max 20); chunk score > 0.7 → hook style + +0.15 emphasis; story hook/climax segment bounds → style annotation; all region emphasis and beat_strength values clamped [0, 1]; never raises; emits `ai_subtitle_execution_generated` at INFO
- `app/ai/director/edit_plan_schema.py` — `subtitle_execution: dict = field(default_factory=dict)` added to `AIEditPlan`; `"subtitle_execution": dict(self.subtitle_execution)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_subtitle_execution(plan, chunks, pacing_ctx, job_id)` added; called after Phase 16 in `_build_plan`; builds execution plan from story/retention/creator_style context; stores `execution_plan.to_dict()` on `plan.subtitle_execution`; `_append_subtitle_execution_explainability(plan, execution_plan)` appends: "Dynamic subtitle emphasis enabled" (emphasis > 0.3), "Emotion-aware subtitle execution detected" (non-neutral emotion), "Compact subtitle density recommended" (density == compact), "Beat-aware subtitle emphasis enabled" (beat_sync > 0.3); both helpers never raise; wrapped in try/except
- `app/services/subtitle_engine.py` — `apply_subtitle_execution_hints(blocks, subtitle_execution) -> dict` added; safely reads global_hint fields (emphasis_strength, emotion_style, density_mode, keyword_focus); validates and clamps all values; returns `{applied: True, ...}` on success, `{applied: False, ...}` on missing/unavailable metadata; never mutates subtitle blocks timing or text; never raises; emits `subtitle_execution_hints_applied` at INFO
- `tests/test_ai_phase17_dynamic_subtitles.py` (new) — 78+ tests covering all schema, emphasis, density, emotion, execution planner, AIEditPlan field, subtitle engine hints, AI Director integration, and safety boundary requirements

**Verification:**

- Phase 17 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- No transcript text mutation in any code path
- No subtitle timing mutation — start/end never altered
- No SRT segmentation rewrite
- No playback_speed mutation
- No FFmpeg command changes
- No autonomous subtitle rewriting
- All emphasis/beat_sync values structurally clamped to [0.0, 1.0]
- Density mode validated against frozenset before use
- Emotion style validated against frozenset before use
- Max 20 execution regions — no unbounded output
- Never blocks render pipeline — all subtitle execution errors are caught and recorded as warnings
- Deterministic heuristics only — no cloud AI, no API keys, no external inference, no GPU
- `apply_subtitle_execution_hints` is read-only — returns hints dict, never mutates blocks

**Architecture notes:**

- Subtitle execution intelligence is metadata-first: the plan is built and stored in `result_json["subtitle_execution"]` but does not yet alter ASS generation architecture, karaoke timing, or FFmpeg commands
- `build_subtitle_execution_plan` combines emphasis + density + emotion sub-systems into a single plan object
- All three sub-systems (emphasis, density, emotion) are independently callable and fallback-safe
- Regions are built from transcript chunk boundaries — no new timing introduced
- `apply_subtitle_execution_hints` in subtitle_engine.py is a safe read interface for downstream render steps
- Phase 17 runs after Phase 16 (retention intelligence) in the AI Director `_build_plan` sequence

**Integrated systems:**

- Story Intelligence (Phase 12) — story segments used for region style annotation (hook/climax)
- Retention Intelligence (Phase 16) — risk_regions used for emphasis boost on hook risk
- Creator Style Intelligence (Phase 14) — dominant_style used for emotion style hint
- Beat/Pacing Intelligence (Phase 4) — energy_level, bpm, beat_available drive emphasis and beat_sync
- Explainability (Phase 6) — compact lines appended to summary_lines

**What Dynamic Subtitle Execution can do now:**

- Detect hook keyword density and translate to emphasis strength
- Map pacing/emotion/story signals to subtitle emotion styles (neutral/hype/dramatic/calm/emotional/punch)
- Detect overloaded subtitle density regions and recommend compact/expressive modes
- Build temporal execution regions (max 20) with per-region style, emphasis, and beat_strength hints
- Annotate hook and climax regions from story intelligence
- Boost emphasis when retention hook risk is detected
- Expose compact `"subtitle_execution"` key in render result_json with global_hint + regions
- Append advisory explainability lines to AI summary

**Not yet implemented:**

- Subtitle timing mutation
- Autonomous subtitle rewriting
- Adaptive subtitle segmentation
- Beat-synced karaoke timing mutation
- AI-generated subtitle text
- Adaptive ASS style switching from execution hints

**Known limitations:**

- Metadata-first execution — execution plan is advisory; does not yet alter ASS generation, karaoke logic, or FFmpeg subtitle burn
- Bounded subtitle influence only — no timing, no text, no segmentation changes
- No transcript rewriting — subtitle text is read-only throughout
- No autonomous subtitle generation — all subtitle content originates from Whisper transcription
- Emphasis hints are informational — not yet wired to per-block ASS style overrides

> Phase 17 extends the AI system from retention intelligence toward dynamic subtitle execution planning, enabling emotion-aware, beat-aware, and density-aware subtitle metadata while preserving complete subtitle timing stability and render safety.

---

### 2026-05-08 — AI Productization Phase 16: Retention Intelligence Foundation

**Implemented:**

* `app/ai/retention/__init__.py` (new) — package marker
* `app/ai/retention/retention_schema.py` (new) — retention risk dataclasses and compact retention analysis schema; deterministic only; no external deps
* `app/ai/retention/dropoff_detector.py` (new) — heuristic viewer drop-off risk analysis using transcript pacing, silence gaps, subtitle density, hook strength, and story transitions
* `app/ai/retention/retention_analyzer.py` (new) — retention scoring pipeline combining story structure, pacing energy, subtitle readability, and narrative progression into compact retention analysis
* `app/ai/retention/retention_recommender.py` (new) — advisory-only retention recommendations; never mutates render timing, segments, subtitles, playback speed, or FFmpeg commands
* `app/ai/director/edit_plan_schema.py` — `retention: dict = field(default_factory=dict)` added to `AIEditPlan`; included in `to_dict()` output
* `app/ai/director/ai_director.py` — Retention Intelligence block added after Story Intelligence and Creator Style Intelligence; compact retention analysis attached to `plan.retention`; explainability integration added with safe fallback guards
* `tests/test_ai_phase16_retention_intelligence.py` (new) — retention analysis, drop-off detection, explainability, advisory recommendation, schema, and AI Director integration coverage

**Detection categories:**

* `weak_hook`
* `long_setup`
* `low_energy`
* `silence_gap`
* `subtitle_overload`
* `story_drop`
* `unclear_payoff`
* `pacing_decay`

**Verification:**

* 91/91 Phase 16 tests pass
* 959/959 full suite passes (zero regressions)
* `git diff --check` clean

**Safety boundaries enforced:**

* Deterministic heuristics only — no cloud AI, no API keys, no external inference
* Metadata-first execution only
* Advisory-only recommendations
* No segment timing mutation
* No automatic cuts
* No subtitle timing mutation
* No playback_speed mutation
* No FFmpeg command mutation
* Never blocks render pipeline execution
* Never raises on malformed transcript or missing AI context

**Architecture notes:**

* Retention analysis operates entirely on existing AI metadata and transcript context
* No real viewer analytics required
* Retention intelligence is explainability-focused in Phase 16
* Retention recommendations remain advisory metadata only
* Compatible with all prior AI phases and safe fallback execution
* Integrated after Story Intelligence and Creator Style Intelligence inside AI Director

**Integrated systems:**

* Story Intelligence
* Beat/Pacing Intelligence
* Explainability
* Timeline Intelligence
* Smart Preset Evolution
* Creator Style Intelligence
* External Knowledge Learning

**What Retention Intelligence can do now:**

* Detect likely viewer drop-off regions
* Estimate retention pacing quality
* Detect weak hooks and long setup regions
* Identify subtitle overload risk
* Identify pacing decay and story-energy collapse
* Generate advisory retention recommendations
* Append retention insight lines to explainability summaries
* Expose compact `"retention"` metadata in render result_json

**Not yet implemented:**

* Retention-driven timing mutation
* Automatic silence removal
* Autonomous edit optimization
* Viewer analytics integration
* Retention-based subtitle rewriting
* Beat-synced retention execution

**Known limitations:**

* No real viewer analytics integration
* Heuristic scoring only
* No autonomous editing
* No automatic pacing mutation
* Recommendations remain advisory only
* Retention analysis does not yet alter rendered output

> Phase 16 extends the AI system from story understanding toward viewer-retention-aware editing analysis while preserving stable render execution.

### 2026-05-08 — AI Productization Phase 15: External Knowledge Learning Foundation

**Implemented:**
- `app/ai/knowledge/__init__.py` (new) — empty package marker
- `app/ai/knowledge/knowledge_schema.py` (new) — `ExternalKnowledgeItem` dataclass (id, source_type, text, market, platform, style, topic, tags, confidence 0-1, metadata); `KnowledgeSearchResult` dataclass (id, score, text, metadata) with `to_dict()` that caps text at 500 chars; `VALID_SOURCE_TYPES` frozenset = {manual_note, trend_summary, style_pattern, hook_pattern, subtitle_pattern, pacing_pattern, market_pattern}; no Pydantic, no heavy deps
- `app/ai/knowledge/knowledge_ingest.py` (new) — `parse_knowledge_json(data) -> list[ExternalKnowledgeItem]`; never raises; validates each item for required id/source_type/text fields and valid source_type membership; skips malformed items with debug logging; confidence clamped to [0, 1]; tags normalized to list[str]; emits `ai_external_knowledge_loaded count=N skipped=M` at INFO; `ingest_knowledge_file(path: str) -> dict` reads local JSON file only, returns `{loaded, skipped, items, warnings}`; returns file_not_found warning if path missing; never raises on corrupt JSON
- `app/ai/knowledge/knowledge_store.py` (new) — `LocalKnowledgeStore` with in-memory `_items: list[ExternalKnowledgeItem]` and parallel `_vectors: list[Optional[list[float]]]`; `add_item(item) -> bool` tries to embed text via existing `app.ai.rag.embeddings.embed_text`, stores vector or None if unavailable; `add_items(items) -> int` returns count of successful adds; `search(query, top_k=5, filters=None) -> list[KnowledgeSearchResult]` uses vector cosine search if query embeds successfully (items without vectors get 0.0), falls back to keyword token-overlap scoring otherwise; `_apply_filters` passes items with None field through (market-agnostic items included regardless of filter); `_keyword_score` = (matched_tokens / total_tokens) × (0.5 + confidence × 0.5); `_build_result` sets metadata with source_type, market, platform, style, topic, tags, confidence; never raises
- `app/ai/knowledge/knowledge_retriever.py` (new) — `retrieve_external_knowledge(query, context=None, top_k=5) -> dict`; never raises; expects `context["knowledge_store"]` as `LocalKnowledgeStore`; builds field filters from `context["market"]` and `context["style"]`; returns `{available: False, results: [], warnings: ["no_knowledge_store"]}` when store absent; returns `{available: False, ..., warnings: ["knowledge_store_empty"]}` when count=0; on matches: returns `{available: True, results: [KnowledgeSearchResult.to_dict(), ...], warnings: []}`; emits `ai_external_knowledge_matched count=N top_score=X.XXX` at INFO; emits debug on skip
- `app/ai/director/edit_plan_schema.py` — `external_knowledge: dict = field(default_factory=dict)` added to `AIEditPlan`; `"external_knowledge": dict(self.external_knowledge)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_external_knowledge(plan, chunks, pacing_ctx, context, mode, job_id)` added; checks `context.get("knowledge_store")`; if absent sets `available=False`; builds query from mode + market + transcript excerpt (first 5 chunks, max 200 chars); extracts style_hint from `plan.creator_style["dominant_style"]` if Phase 14 already ran; calls `retrieve_external_knowledge` with `{knowledge_store, market, style}` context; stores compact summary via `_build_knowledge_summary` on `plan.external_knowledge`; `_build_knowledge_summary(result)` → `{available, matched_items, top_matches: [{source_type, market, style, score, text[:300]}]}`; `_append_knowledge_explainability(plan, result)` appends "External curated knowledge matched this edit style" and "Market-specific hook guidance identified" (when hook_pattern result present) with dedup guard; Phase 15 block added after Phase 14 in `_build_plan`; all helpers never raise; emits `ai_external_knowledge_matched` / `ai_external_knowledge_skipped` logs
- `tests/test_ai_phase15_external_knowledge.py` (new) — 79 tests covering: schema defaults and to_dict() for both dataclasses, VALID_SOURCE_TYPES completeness, ingest (valid JSON, malformed items skipped, missing id/text/source_type skipped, invalid source_type skipped, empty list, non-dict input, confidence clamping, tags normalization, file_not_found warning, loaded count, items in result, corrupt JSON fallback), store (empty count, add_item returns True, count increases, add_items count, invalid type returns False, search empty returns empty, returns KnowledgeSearchResult list, keyword search finds matching item, top_k respected, score field present, never raises on garbage query, market filter excludes non-matching, None market passes through, metadata has source_type/market/style, empty/None add_items), retriever (never raises on None/empty args, available False without store, required keys present, available True with populated store, results is list, top_k respected, empty store returns False, market filter passed through, warnings is list), AIEditPlan field (has field, defaults {}, in to_dict, value propagated), AI Director integration (sets dict, available False without store, never raises on empty chunks/None context/garbage store, available True with populated store, top_matches present and capped at 5, build_knowledge_summary available False/True, text capped at 300, explainability append never raises, line added on results, hook pattern adds market line, no duplicate lines, style_hint from creator_style), no external dependencies (no API key, no GPU, no internet, no real rendering, safe imports, works without sentence_transformers, no copyrighted names, never raises on broken store)

**Verification:**
- 79/79 Phase 15 tests pass
- 868/868 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- Local curated JSON files only — no network access, no web scraping, no cloud APIs in any code path
- Advisory metadata only — `external_knowledge` dict in result_json never mutates render commands, subtitles, timing, or segments
- `available=False` returned whenever store is absent, empty, or broken — render pipeline continues unaffected
- No API keys required — knowledge store uses existing optional embedding layer (`sentence-transformers`) with keyword fallback
- `_apply_filters` never blocks items with None fields — market-agnostic knowledge items always pass through
- Never raises in any code path — all knowledge failures are caught and recorded as warnings
- No copyrighted creator names, trend dumps, or scraped content permitted in schema or logic

**Architecture notes:**
- External knowledge is context-injected — `LocalKnowledgeStore` is passed via `context["knowledge_store"]`, not a global singleton
- Vector search uses existing `app.ai.rag.embeddings.embed_text` — no new model dependency
- Keyword fallback is deterministic and works without any AI library installed
- In-memory only in Phase 15 — no SQLite persistence, no disk writes from the knowledge layer
- Phase 15 runs after Phase 14 (creator style); style_hint from `plan.creator_style` is used to filter results

**Integrated systems:**
- AI Director — Phase 15 block attached in `_build_plan` after Phase 14
- Creator Style Intelligence — style_hint extracted from `plan.creator_style["dominant_style"]` for query filtering
- Explainability — `_append_knowledge_explainability` adds up to 2 advisory lines to summary
- Existing embedding layer (`app.ai.rag.embeddings`) — reused for optional vector search

**What External Knowledge Learning can do now:**
- Ingest curated local JSON knowledge files (manual notes, trend summaries, style/hook/pacing/market patterns)
- Store items in memory with optional embedding vectors for semantic search
- Fall back to keyword token-overlap search when embeddings are unavailable
- Filter search results by market and style from the render context
- Attach compact `"external_knowledge"` key to render result_json with matched_items count and top 5 matches
- Append advisory lines to AI explainability summary when knowledge matches edit style
- Identify market-specific hook guidance from matched hook_pattern knowledge items

**Not yet implemented:**
- Online trend ingestion
- Automatic web crawling or social platform API integrations
- Knowledge persistence UI
- Auto-application of external knowledge to render settings
- Knowledge confidence calibration
- Per-market knowledge version management

**Known limitations:**
- Local curated JSON only — no internet access, no autonomous trend ingestion
- Advisory metadata only — no effect on rendered output
- In-memory only — knowledge is lost when process restarts unless store is re-populated
- No autonomous training — all knowledge must be manually curated
- Keyword search is token-overlap only; no TF-IDF, no BM25 weighting

> Phase 15 extends the AI system with a safe, local, auditable external knowledge layer, allowing curated editing/trend knowledge to inform AI recommendations without requiring internet access, cloud APIs, or autonomous training.

---

### 2026-05-08 — AI Productization Phase 14: Creator Style Intelligence

**Implemented:**
- `app/ai/styles/style_schema.py` (new) — `CreatorStyleProfile` dataclass (style_id, display_name, pacing_style, subtitle_style, camera_behavior, hook_style, story_arc_style, energy_level, notes); `StyleClassification` dataclass (available, dominant_style, confidence 0-100, secondary_styles list capped at 3, matched_traits list capped at 6, warnings); `StyleRecommendation` dataclass (recommended_style, confidence 0-100, suggested_adjustments dict, reasons list capped at 5, warnings); all have `to_dict()` methods; no Pydantic, no heavy deps
- `app/ai/styles/style_profiles.py` (new) — 10 creator archetypes in `_PROFILES` dict: `podcast_viral` (fast pacing, punch subtitle, fast_follow camera, urgency hook, high energy), `high_energy_reaction` (fast pacing, punch subtitle, dramatic_push camera, surprise hook, very_high energy), `storytelling_cinematic` (slow_build pacing, minimal subtitle, slow_reveal camera, curiosity hook, medium energy), `documentary_clean` (slow pacing, clean subtitle, static camera, informational hook, low energy), `educational_focus` (medium pacing, bold subtitle, static camera, question hook, medium energy), `anime_edit` (fast pacing, bold subtitle, dramatic_push camera, dramatic hook, very_high energy), `gameplay_highlight` (fast pacing, overlay subtitle, fast_follow camera, reaction hook, high energy), `motivation_short` (medium_fast pacing, bold subtitle, slow_reveal camera, urgency hook, high energy), `interview_clip` (slow pacing, clean subtitle, static camera, question hook, low energy), `calm_minimal` (slow pacing, minimal subtitle, static camera, story hook, very_low energy); `STYLE_IDS` frozenset; `STYLE_DURATION_HINTS` dict (motivation_short/anime_edit=30s, high_energy_reaction=45s, podcast_viral/gameplay_highlight/calm_minimal=60s, etc.); `get_profile(style_id)` and `get_all_profiles()` helpers; no copyrighted creator names anywhere
- `app/ai/styles/style_classifier.py` (new) — `classify_creator_style(transcript_context, pacing_context, emotion_context, story_context, memory_context) -> StyleClassification`; never raises; deterministic rule-based scoring only; `_build_signals()` aggregates all inputs into flat signal dict; `_score_style(style_id, signals) -> (float, list[str])` applies per-archetype rules (energy_level, pacing_style, emotion, bpm, narrative_flow, dominant_arc, chunk_count); confidence formula: base = min(75, best_score), clarity bonus = min(25, gap×0.8) where gap is spread between 1st and 2nd scores; emits `ai_creator_style_classified` at INFO
- `app/ai/styles/style_recommender.py` (new) — `recommend_style_adjustments(classification, current_context=None) -> StyleRecommendation`; never raises; advisory only; `_SAFE_ADJUSTMENT_FIELDS = frozenset({subtitle_style, pacing_style, camera_behavior, hook_style, target_duration_hint})`; `_UNSAFE_FIELDS = frozenset({playback_speed, segment_start, segment_end, timing, codec, bitrate, fps, resolution, ffmpeg, output_format})` — safety gate strips all unsafe keys before returning; loads profile via `get_profile(dominant)`, builds adjustments from profile fields; adds `target_duration_hint` from `STYLE_DURATION_HINTS`; reasons (max 5): archetype display name detected, pacing style identified, energy level match, matched signals, high-confidence match; emits `ai_creator_style_recommended` at INFO
- `app/ai/director/edit_plan_schema.py` — `creator_style: dict = field(default_factory=dict)` added to `AIEditPlan`; `"creator_style": dict(self.creator_style)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_creator_style(plan, chunks, pacing_ctx, job_id)` added; builds `transcript_ctx = {"text": joined first 15 chunks, "chunk_count": len(chunks)}`; passes `story_ctx = dict(plan.story)` for story context; calls `classify_creator_style` then `recommend_style_adjustments`; stores `{**classification.to_dict(), "recommendation": recommendation.to_dict()}` on `plan.creator_style`; `_append_style_explainability(plan, classification)` maps each style_id to a human-readable line via `_STYLE_LINES` dict, appends with dedup guard; Phase 14 block added after Phase 13 in `_build_plan`; both helpers never raise
- `app/orchestration/render_pipeline.py` — `"creator_style": _ai_edit_plan.creator_style if _ai_edit_plan is not None else {}` added to `_result_payload` dict
- `tests/test_ai_phase14_creator_styles.py` (new) — 74 tests covering: schema defaults and to_dict() for all three dataclasses, caps (traits at 6, secondary_styles at 3, reasons at 5), profiles (all 10 archetypes present, required fields, no copyrighted creator names in display_names or notes, duration hints positive, get_all_profiles returns copy), classifier safety (never raises on None/garbage/empty inputs, dominant_style always string, valid style_id or "unknown", confidence in 0-100, available=True with signals), high-urgency classification (high energy + fast pacing → podcast_viral or high_energy_reaction, urgency emotion favors podcast_viral, very_high energy + bpm → reaction or anime, matched_traits nonempty for strong signals), calm classification (calm pacing → documentary or calm_minimal, very_low energy → calm_minimal, neutral/low energy not podcast), cinematic classification (narrative arc → cinematic, setup_payoff arc favors cinematic, curiosity + structured flow not high-energy), recommender safety (never raises on None/unavailable/unknown, no playback_speed/timing/ffmpeg suggestions, reasons ≤5, confidence 0-100, only safe adjustment fields, no copyrighted creators in reasons, advisory only no mutation), recommender suggestions (returns StyleRecommendation, recommended_style matches dominant, adjustments nonempty for known style, reasons nonempty, target_duration_hint present), AIEditPlan field (has field, defaults to {}, in to_dict), AI Director integration (sets creator_style dict, never raises on empty chunks or None pacing, includes recommendation key, explainability append never raises, line added for known style, no duplicate lines, never raises on missing explainability), result JSON compactness (classification to_dict compact, recommendation to_dict compact, full dict has recommendation key), no external dependencies (no API key, no GPU, no external models, no real rendering, safe imports, no network calls)

**Verification:**
- 74/74 Phase 14 tests pass
- 789/789 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- `_UNSAFE_FIELDS` frozenset prevents playback_speed, timing, codec, bitrate, fps, resolution, ffmpeg, output_format from ever appearing in suggested_adjustments
- `_SAFE_ADJUSTMENT_FIELDS` whitelist ensures only subtitle_style, pacing_style, camera_behavior, hook_style, target_duration_hint can be returned
- Advisory only — `recommend_style_adjustments` returns recommendations only; nothing auto-applied
- No copyrighted creator names in any profile display_name, notes field, reason string, or log message
- Classification is archetype-based only — no imitation of any real creator
- Deterministic rule-based scoring only — no ML model, no external inference
- Never raises in any code path — all style intelligence failures caught and recorded as warnings
- No external API calls, no GPU, no optional AI libraries required

**Architecture notes:**
- Creator styles are archetype-based only — no copyrighted creator replication
- Deterministic classification only — heuristic rule scoring, no model inference
- Metadata-first execution — `creator_style` dict in result_json is advisory, no render command mutation
- Advisory-only recommendations — suggestions must be explicitly applied by downstream logic or user
- No timing mutation — style intelligence never alters clip boundaries, segment order, or playback speed
- No render command mutation — FFmpeg commands are never modified by style intelligence

**Integrated systems:**
- AI Director — Phase 14 block attached in `_build_plan` after Phase 13
- Story Intelligence — `story_ctx` passed to classifier for narrative_flow and dominant_arc signals
- Beat/Pacing Intelligence — `pacing_context` passed for energy_level, bpm, pacing_style signals
- Smart Preset Evolution — runs before style intelligence; style complements preset recommendations
- Explainability — `_append_style_explainability` appends human-readable archetype line to summary
- Timeline Intelligence — transcript chunks passed for text density and hook keyword scoring

**What Creator Style Intelligence can do now:**
- Classify editing content into one of 10 creator archetypes from combined signals
- Score each archetype using energy, pacing, emotion, BPM, narrative arc, and text signals
- Compute confidence from score spread (narrow competition → lower confidence)
- Recommend safe style-compatible subtitle_style, pacing_style, camera_behavior, hook_style
- Suggest advisory target_duration_hint from archetype-specific duration hints
- Expose compact `"creator_style"` key in render result_json with classification + recommendation
- Append human-readable archetype detection line to AI explainability summary

**Not yet implemented:**
- Creator-specific fine tuning
- Autonomous creator adaptation
- Online creator learning
- Creator A/B testing
- Creator-style render mutation

**Known limitations:**
- No copyrighted creator imitation — archetypes are generic editing style categories only
- No external creator scraping — all profiles are statically defined
- No automatic preset mutation — recommendations remain advisory
- Recommendations remain advisory — no effect on rendered output
- Confidence is heuristic (not calibrated to actual user satisfaction or creator intent)
- All 10 archetypes are fixed; no user-defined custom archetypes in Phase 14

> Phase 14 extends the AI system from generic editing intelligence toward creator-style-aware editing archetypes while preserving render stability and fallback-safe execution.

---

### 2026-05-08 — AI Productization Phase 13: Smart Preset Evolution

**Implemented:**
- `app/ai/presets/preset_schema.py` (new) — `PresetPerformanceSample` dataclass (preset, ai_mode, market, score, duration, subtitle_tone, camera_behavior, pacing_style, story_arc, status, metadata); `PresetRecommendation` dataclass (recommended_preset, confidence 0-100, reasons list capped at 5, suggested_adjustments dict, warnings); `PresetEvolutionReport` dataclass (available, market, ai_mode, best_samples list capped at 5, recommendation, warnings); all have `to_dict()` methods; no Pydantic, no heavy deps
- `app/ai/presets/preset_analyzer.py` (new) — `analyze_preset_performance(memories, context=None) -> PresetEvolutionReport`; never raises; accepts list of memory result dicts (from retriever) or MemorySearchResult-like objects; parses each into `PresetPerformanceSample` with `_parse_sample()` — handles dict with "metadata" key, direct attributes, or both; relevance scoring: status weight (completed=1.0, completed_with_errors=0.7, failed=0.2), market match +0.25, mode match +0.25, output score ÷ 100 × 0.30; sorts by relevance, separates usable from failed; confidence formula: base = min(60, usable×12), penalty for <3 samples, failure rate penalty up to −25, market+mode match bonus up to +20; returns `PresetEvolutionReport` with `recommendation=None` (filled by recommender); emits `ai_preset_evolution_generated` log at INFO
- `app/ai/presets/preset_recommender.py` (new) — `recommend_preset(report, current_context=None) -> PresetRecommendation`; never raises; advisory only — never mutates payload; dominant pattern extraction via `Counter.most_common(1)` across best_samples for subtitle_tone, camera_behavior, pacing_style; `target_duration_hint` from median duration of high-score (≥60) samples; `ai_mode_hint` from most common mode; `_UNSAFE_FIELDS` safety gate strips playback_speed, codec, bitrate, fps, resolution, output_format, validation, ffmpeg, timing before returning; reasons list (max 5): market match, mode match, subtitle tone learning, camera behavior pattern, pacing style correlation; confidence: base = min(50, n×15), high-score bonus up to +20, context match bonus up to +20
- `app/ai/director/edit_plan_schema.py` — `preset_evolution: dict = field(default_factory=dict)` added to `AIEditPlan`; `"preset_evolution": dict(self.preset_evolution)` added to `to_dict()` output; backward-compatible (all existing tests pass)
- `app/ai/director/ai_director.py` — `_attach_preset_evolution(plan, memory_ctx, mode, context, job_id)` added; called after `_attach_story_intelligence` inside `_build_plan`; extracts memories from `memory_ctx.get("results", [])`; builds `preset_context = {"market": market, "mode": mode}`; calls `analyze_preset_performance` then `recommend_preset`; attaches recommendation to report; stores `report.to_dict()` on `plan.preset_evolution`; when no memories available sets `{"available": False, "warnings": ["no_memory_available_for_preset_analysis"]}`; `_append_preset_explainability(plan, report)` appends ("Preset recommendation based on similar successful renders", "Subtitle tone suggestion learned from prior high-score outputs") when confidence ≥ 30.0; dedup guard prevents duplicate lines; both helpers never raise
- `app/orchestration/render_pipeline.py` — `"preset_evolution": _ai_edit_plan.preset_evolution if _ai_edit_plan is not None else {}` added to `_result_payload` dict
- `tests/test_ai_phase13_preset_evolution.py` (new) — 63 tests covering: schema defaults and to_dict() for all three dataclasses, reasons/best_samples caps, analyzer safety (empty/None/garbage inputs never raise, empty/None → available=False, malformed entries skipped, all-failed → available=False), high-score completed samples (produce available report, populate best_samples, cap at 5, completed_with_errors usable), failed samples (warn in report, mixed still works, all-failed gives no usable), market/mode relevance (same market rank higher, same mode rank higher, market/mode stored in report), recommender safety (never raises, unavailable report → confidence 0, None context safe, playback_speed/codec/ffmpeg/timing never suggested, reasons ≤5, confidence 0-100, only allowed adjustment fields), recommender suggestions (subtitle_tone from dominant samples, camera_behavior from dominant, reasons nonempty, all keys in to_dict), AIEditPlan preset_evolution field (has field, defaults to {}, in to_dict), AI Director with no memory (sets available=False, never raises on garbage, works with real memories), explainability integration (appends safely, never raises on missing/None explainability or report, no duplicate lines), result JSON compactness (best_samples ≤5, all keys present, recommendation in output, no raw memory text), no external dependencies (no API key, no GPU, no real rendering, no torch, no sentence_transformers, safe imports)

**Verification:**
- 63/63 Phase 13 tests pass
- 715/715 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- `_UNSAFE_FIELDS` frozenset prevents playback_speed, codec, bitrate, fps, resolution, output_format, validation, ffmpeg, timing from ever appearing in suggested_adjustments
- Advisory only — `recommend_preset` returns recommendations only; nothing auto-applied
- No preset is silently overwritten — `preset_evolution` is metadata only, not wired to payload mutation
- All-failed memories → `available=False`, no recommendation generated
- Empty/missing memory context → `available=False`, warning recorded, render continues
- Never raises in any code path — all preset evolution failures are caught and recorded as warnings
- No external API calls, no GPU, no optional AI libraries required

**What Preset Evolution can do now:**
- Parse historical render memories (from RAG retriever results) into structured performance samples
- Score each sample by market/mode relevance + output score + status weight
- Identify high-performing patterns: dominant subtitle_tone, camera_behavior, pacing_style
- Recommend preset name from most-common preset in best samples
- Suggest safe adjustments: subtitle_tone, camera_behavior, pacing_style, target_duration_hint, ai_mode_hint
- Include confidence score (0-100) and up to 5 human-readable reasons
- Expose compact `"preset_evolution"` key in render result_json
- Append advisory lines to AI explainability summary

**Not yet implemented:**
- Auto-applying evolved presets (explicitly deferred)
- UI preset recommendation controls
- A/B preset testing
- Online learning or feedback loops
- Autonomous preset mutation
- Per-market preset version branching

**Known limitations:**
- Advisory only — no effect on rendered output
- Deterministic heuristics only — no ML, no semantic understanding of preset quality
- Quality depends entirely on the richness of stored render memories; sparse memory → low confidence
- Confidence formula is heuristic (not calibrated to actual user satisfaction)
- Does not change user-selected preset automatically under any circumstance

---

### 2026-05-08 — AI Productization Phase 12: Story Intelligence Foundation

**Implemented:**
- `app/ai/story/story_schema.py` (new) — `StorySegment` dataclass (start, end, segment_type, confidence, emotion, retention_risk, notes); `StoryAnalysis` dataclass (available, narrative_flow, segments, dominant_arc, retention_score, warnings); both have `to_dict()` methods; `VALID_SEGMENT_TYPES` frozenset (`hook`, `setup`, `build_up`, `tension`, `climax`, `payoff`, `outro`, `unknown`); `to_dict()` caps segments at 12 to prevent giant result dumps
- `app/ai/story/story_analyzer.py` (new) — `analyze_story_structure(transcript_chunks, pacing_context=None, emotion_context=None, memory_context=None) -> StoryAnalysis`; never raises; deterministic heuristics only — no ML, no external APIs, no audio loading; divides video into 5 temporal phases (early 0-20%, middle 20-50%, peak 50-75%, late 75-90%, outro 90-100%); classifies each phase using: hook keyword density scoring from transcript text, per-phase energy modulation from `pacing_context.energy_level`, and pacing_style; `_classify_phase` maps (phase_name, text_score, energy_score) → segment_type; computes `dominant_arc` (curiosity_build, setup_payoff, tension_release, emotional_peak, linear_build, front_loaded, informational), `narrative_flow` (hook_to_climax, hook_to_payoff, linear_build, front_loaded, flat), and `retention_score` (0-100, duration-weighted by segment type and confidence); emits `ai_story_analysis_generated` log at INFO with flow/arc/retention/segment count
- `app/ai/story/retention.py` (new) — `estimate_retention(segment, context=None) -> dict` returning `{score:int 0-100, risk:float 0-1, reasons:list[str], warnings:list[str]}`; deterministic only, no ML; per-type score/risk adjustments (hook +20/-0.20, outro -20/+0.25, climax +22/-0.22, etc.); confidence modifier (< 0.30 → −10 score, +0.10 risk); emotion modifier (`curiosity/urgency/surprise/excitement` → +8 score; `sadness/boredom/calm` → −8 score); incorporates `segment.retention_risk` from analyzer via averaging; never raises on garbage input
- `app/ai/director/edit_plan_schema.py` — `story: dict = field(default_factory=dict)` added to `AIEditPlan`; `"story": dict(self.story)` added to `to_dict()` output; backward-compatible (all existing tests pass)
- `app/ai/director/ai_director.py` — `_attach_story_intelligence(plan, chunks, pacing_ctx, memory_ctx, job_id)` added; called after `_attach_explainability` inside `_build_plan`; calls `analyze_story_structure` with transcript chunks and pacing context dict; stores `story.to_dict()` on `plan.story`; `_append_story_explainability(plan, story)` appends compact lines to `plan.explainability.summary.summary_lines` ("Strong opening hook detected", "Narrative climax identified", "Narrative tension peak identified", "Narrative build-up identified", "Retention pacing weakened near ending"); both helpers wrapped in try/except — never block rendering
- `app/orchestration/render_pipeline.py` — `"story": _ai_edit_plan.story if _ai_edit_plan is not None else {}` added to `_result_payload` dict alongside `ai_director`/`ai_render_influence`/`ai_beat_execution`
- `tests/test_ai_phase12_story_intelligence.py` (new) — 61 tests covering: StorySegment/StoryAnalysis schema defaults and to_dict(), VALID_SEGMENT_TYPES, segment cap at 12, analyzer safety (empty/None/garbage inputs never raise, empty → available=False, valid → available=True, no invalid segment types), hook detection (hook keywords in early position → hook segment, neutral text → no hook), build-up detection (rising energy → build_up, low energy → no build_up), climax detection (high intensity → tension or climax), retention risk (all required keys, hook > outro score, outro > hook risk, low confidence increases risk, score/risk clamped 0-100/0-1, never raises on garbage, curiosity emotion reduces risk), AIEditPlan story field (has field, in to_dict(), defaults to {}), result JSON compactness (≤12 segments, all required keys, valid segment types, strings for arc/flow), explainability integration (appends safely, hook line added, never raises on missing/garbage explainability or summary), no external dependencies (no API key, no GPU, no real rendering, no librosa, no torch, safe imports), narrative flow and arc (hook_to_climax on hook+tension, retention_score 0-100, nonempty strings, segments produced, timing non-negative, retention_risk in range)

**Verification:**
- 61/61 Phase 12 tests pass
- 652/652 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- No transcript mutations — story analyzer reads chunks read-only
- No segment timing mutations — start/end never altered
- No subtitle timing mutations
- No playback_speed mutations
- No FFmpeg command changes
- No external API calls, no GPU, no ML models, no audio loading
- Deterministic only — same inputs always produce same story classification
- Story analysis failure never blocks render — wrapped in try/except
- Result JSON limited to 12 segments maximum (no transcript dumps)
- All segment types validated against `VALID_SEGMENT_TYPES` frozenset

**What Story Intelligence can do now:**
- Detect opening hook segments from keyword-dense early transcript text
- Classify narrative build-up phases from rising energy context
- Identify tension/climax regions from peak energy signals
- Estimate per-segment viewer dropout risk deterministically
- Compute overall retention score (0-100, duration-weighted)
- Determine dominant narrative arc (curiosity_build, tension_release, etc.)
- Determine narrative flow shape (hook_to_climax, linear_build, flat, etc.)
- Append compact narrative insight lines to existing AI explainability summary
- Expose compact `"story"` key in render result_json

**Not yet implemented:**
- Story-aware render retiming (Phase 13+)
- Autonomous narrative editing
- Retention-driven cut mutation
- Story-driven subtitle timing or emphasis
- Full emotional arc execution via FFmpeg
- Per-chunk audio-based energy analysis (currently uses whole-video energy_level from pacing context)

**Known limitations:**
- Story classification is positional + keyword-heuristic only — relies on transcript text keyword density and pacing energy_level from beat analysis
- No semantic understanding of narrative meaning — "build_up" is energy-based, not plot-based
- Energy is a single global value from pacing_context, not per-segment audio energy
- Metadata-first: story segments in result_json are advisory only, no effect on rendered output in Phase 12

---

### 2026-05-08 — AI Productization Phase 11: Beat-aware Render Execution

**Implemented:**
- `app/models/schemas.py` — Three new opt-in fields added to `RenderRequest` AI Director section: `ai_beat_execution_enabled: bool = False`, `ai_beat_pulse_enabled: bool = True`, `ai_beat_transition_enabled: bool = False`; all default-false/safe so existing requests are unaffected
- `app/ai/director/edit_plan_schema.py` — `AIBeatExecutionPlan` dataclass added (enabled, beat_available, bpm, beat_count, pulse_strength, suggested_transition_style, execution_mode="metadata_only", warnings); `beat_execution: dict` field added to `AIEditPlan`; `to_dict()` updated to include `"beat_execution"` key
- `app/ai/director/beat_execution.py` (new) — `build_beat_execution_plan(edit_plan, payload, context=None) -> dict`; never raises; never mutates payload, timing, or subtitles; BPM gate: [60.0, 190.0]; beat_count gate: ≥4; pulse_strength clamped to ≤0.15 (energy_level * 0.20); transition style: "metadata_only" if transition disabled, "beat_pulse" if fast/dynamic + BPM ≥ 120 + pulse enabled, else "soft_cut"; execution_mode always "metadata_only" in Phase 11; all metadata sourced from `edit_plan.pacing` — no librosa, no audio models
- `app/ai/director/render_influence.py` — `_apply_pacing_influence` upgraded from report-only to Phase 11 integration: when `ai_beat_execution_enabled=True` AND `pacing.beat_available=True`, calls `build_beat_execution_plan`, stores result on `edit_plan.beat_execution`, records applied or skipped entry; when disabled, records `beat_execution_disabled` in skipped; `_update_explainability` extended to append beat status line (`"Beat-aware execution planned safely"` or `"Beat execution skipped: <reason>"`) after the AI render influence line; deduplication guard prevents duplicates
- `app/orchestration/render_pipeline.py` — AI Beat Execution block inserted after the Phase 10 influence block: `_ai_beat_report` initialized to `{"enabled": False}`; if `ai_beat_execution_enabled=True` and plan exists, checks `edit_plan.beat_execution` cache (populated by influence module if both were enabled together), otherwise calls `build_beat_execution_plan` directly; logs `ai_beat_execution_planned` at INFO with bpm/count/enabled, or `ai_beat_execution_skipped` at DEBUG; `"ai_beat_execution": _ai_beat_report` added to `_result_payload` dict
- `tests/test_ai_phase11_beat_execution.py` (new) — 52 tests covering: schema defaults (AIBeatExecutionPlan, AIEditPlan.beat_execution, RenderRequest fields), disabled behavior (no pacing, beat unavailable, bpm None, None/garbage inputs), BPM validation (< 60 skip, = 60 accept, > 190 skip, = 190 accept, 0 skip, negative skip), beat count validation (< 4 skip, = 4 accept, 0 skip, stored in report), pulse strength bounds (high energy capped at 0.15, zero energy = 0.0, None energy defaults, never negative), transition style logic (disabled → metadata_only, fast+120bpm+pulse → beat_pulse, fast+120bpm+no pulse → soft_cut, dynamic+125bpm → beat_pulse, slow style → soft_cut, fast+low bpm → soft_cut), safety no-mutations (playback_speed unchanged, non-default speed unchanged, segment start/end unchanged, execution_mode always metadata_only), report shape (all 10 keys present, lists, applied entry on success, bpm stored), integration with render_influence (beat planned when enabled, stored on plan, disabled skips + notes, explainability beat line added), no external dependencies (no API key, no librosa, no torch, no GPU, no file I/O)

**Verification:**
- 52/52 Phase 11 tests pass
- 591/591 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- `execution_mode` structurally locked to "metadata_only" — no timing changes possible in Phase 11
- `pulse_strength` hard cap: 0.15
- BPM must be in [60.0, 190.0] or entire beat plan is skipped
- `beat_count` must be ≥ 4 or plan is skipped
- `playback_speed` — structurally never touched
- Segment `start`, `end`, `score` — structurally never touched
- Subtitle timing, text, emphasis — structurally never touched
- No librosa, no audio model loading — all beat metadata from `edit_plan.pacing` only
- Beat execution block is opt-in: `ai_beat_execution_enabled=False` by default

**Not yet implemented:**
- Beat-synced FFmpeg cut timing (Phase 12+)
- Real-time pulse visual effect in video output
- UI toggle for `ai_beat_execution_enabled`
- Subtitle emphasis driven by beat timing
- Full camera behavior execution (AI zoom/push rendered via FFmpeg)

**Known limitations:**
- Phase 11 beat execution is metadata-only: the plan is built and stored in result_json but does not yet alter any FFmpeg command or clip boundary
- `pulse_strength` and `suggested_transition_style` are advisory fields for downstream phases; no visual difference in rendered output in Phase 11

---

### 2026-05-08 — AI Productization Phase 10: Safe Render Influence

**Implemented:**
- `app/models/schemas.py` — `ai_render_influence_enabled: bool = False` added to `RenderRequest`; opt-in only; defaults to False so all existing requests behave identically to before; placed in the AI Director section with other AI flags
- `app/ai/director/render_influence.py` (new) — `apply_ai_render_influence(payload, edit_plan, context=None) -> tuple[object, dict]`; `clamp_ai_influence(value, min, max, default) -> float`; never raises; mutates payload in-place (required: pipeline reads payload fields directly throughout); returns same payload object plus influence_report
- `render_influence.py` — Camera influence: activates `motion_aware_crop=True` only when `camera.behavior` is in `{"fast_follow", "dramatic_push", "slow_reveal"}` AND payload already has `motion_aware_crop=True` OR `reframe_mode` is in `{"motion", "subject", "face"}` — the safety gate prevents force-enabling motion crop on static renders; `zoom_strength` clamped to ≤1.18, `follow_strength` clamped to ≤0.85
- `render_influence.py` — Subtitle influence: enables `highlight_per_word=True` only when `subtitle.highlight_keywords=True` AND `add_subtitle=True` on payload; never alters subtitle text, timing, ASS formatting, or market subtitle policy
- `render_influence.py` — Pacing influence: report-only in Phase 10; pacing_style and energy_level recorded in skipped list with `beat_sync_deferred=phase11` annotation; no clip duration or cut timing changes
- `render_influence.py` — Memory influence: report-only in Phase 10; memory context result count recorded in skipped list; no render settings altered based on memory
- `render_influence.py` — Explainability update: appends compact status line (`"AI render influence applied safely (N adjustments)"` or `"AI render influence enabled (no adjustments needed)"`) to `edit_plan.explainability.summary.summary_lines` if it exists; deduplication guard prevents duplicate lines; cosmetic-only, never raises on missing explainability
- `app/orchestration/render_pipeline.py` — AI Render Influence block inserted after AI Director plan creation (line ~1695) and before per-part loop; `_ai_influence_report` initialized to `{"enabled": False}`; only invoked when `_ai_edit_plan is not None` AND `ai_render_influence_enabled=True`; outer try/except ensures any module-level crash still leaves render running with the original payload; logs `ai_render_influence_applied` at INFO or `ai_render_influence_module_failed` at WARNING; `ai_render_influence` key added to `_result_payload` dict alongside `ai_director`
- `tests/test_ai_phase10_render_influence.py` (new) — 53 tests covering: schema defaults/backward-compat, module import safety, None plan/payload/corrupt plan never raises, `clamp_ai_influence` bounds, zoom/follow clamped values in applied report, `playback_speed` never touched, segment `start`/`end`/`score` never touched, subtitle timing/text fields never touched, influence report shape (`enabled/applied/skipped/warnings`), camera gate (only when motion_aware_crop or motion reframe), subtitle gate (only when add_subtitle=True), pacing/memory always skipped (report-only), explainability line append + dedup guard, fallback on corrupt plan fields, no API key, no GPU, no real video

**Verification:**
- 53/53 Phase 10 tests pass
- 539/539 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- `zoom_strength` hard cap: 1.18 (AI plan values above this are clamped)
- `follow_strength` hard cap: 0.85
- `motion_aware_crop` only enabled if payload already permits motion-aware render
- `highlight_per_word` only enabled if `add_subtitle=True`
- `playback_speed` — structurally never touched
- Segment `start`, `end`, `score` — structurally never touched
- Subtitle timing, text, ASS logic — structurally never touched
- Output validation fields — structurally never touched
- Pacing cuts — deferred (Phase 11)
- Memory-driven render changes — deferred (Phase 11)

**Not yet implemented:**
- Beat-synced cuts (Phase 11)
- Render-time subtitle emphasis override
- Full camera behavior execution (AI zoom/push rendered via FFmpeg)
- UI toggle for `ai_render_influence_enabled`
- Autonomous editing

**Known limitations:**
- AI influence is intentionally conservative in Phase 10
- Camera influence activates `motion_aware_crop` but does not pass AI zoom/follow values into the FFmpeg motion crop pass (those are payload-level fields not yet linked to AI values)
- Pacing style observation does not yet alter cut timing or segment ordering
- Memory context is observed but not applied to render settings until Phase 11

---

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

---

# Phase 53A — Knowledge Injection Foundation

**Date:** 2026-05-11
**Status:** Complete — evaluation/advisory only

## Summary

Phase 53A introduces a deterministic, local-only knowledge injection foundation. Knowledge packs are curated JSON files loaded at runtime; the retriever scores them by domain and tag overlap and attaches a `KnowledgeContext` to the edit plan. All outputs are advisory metadata — no render mutation, no executor override, no autonomous execution.

## New Files

| File | Purpose |
|---|---|
| `backend/knowledge/packs/subtitle_readability_basics.json` | Seed knowledge pack (domain: subtitle, 2 rules) |
| `backend/app/ai/knowledge/knowledge_pack_schema.py` | Pack schema dataclasses + validation helpers + fallback |
| `backend/app/ai/knowledge/knowledge_pack_loader.py` | Local JSON pack loader, deterministic sort |
| `backend/app/ai/knowledge/knowledge_pack_retriever.py` | Domain/tag retrieval engine + context builder |
| `backend/tests/test_ai_phase53a_knowledge_injection.py` | 76 tests across 13 classes |

## Modified Files

| File | Change |
|---|---|
| `backend/app/ai/director/edit_plan_schema.py` | Added `knowledge_injection: dict` field + `to_dict()` entry |
| `backend/app/ai/director/ai_director.py` | Added Phase 53A orchestration block + `_attach_knowledge_injection()` helper |
| `backend/app/ai/director/render_influence.py` | Added `_report_knowledge_injection()` to chain (always → `skipped`) |

## Safety Contract

- Local only — no internet, no cloud API, no vector DB, no embeddings
- Never raises — all public functions wrapped in try/except with fallback returns
- Deterministic — same inputs always produce the same output
- Bounded — `_MAX_MATCHES=20`, `_MAX_REASONING=5`, `max_results` param on retriever
- Advisory only — knowledge informs, never executes; all phase reports to `skipped`, never `applied`
- Pack content is data only — no executable code, no arbitrary Python imports triggered by packs

## Retrieval Scoring

```
score = domain_match (2 pts if domain matches) + tag_overlap (1 pt per shared tag)
sort  = (-score, pack_id, rule_id) for full determinism on ties
```

## Context Builder Signal Sources

| Signal | Domain activated | Tags added |
|---|---|---|
| `subtitle_quality_v2.overall > 0` or `confidence > 0` | subtitle | subtitle, readability |
| `camera_quality_v2.overall > 0` or `confidence > 0` | camera | camera |
| `hook_quality_v2.overall > 0` or `confidence > 0` | hook | hook |
| `pacing.pacing_style` in (upbeat, fast, dynamic) | — | short_form |
| `pacing.energy_level >= 0.60` | — | mobile |
| `market_optimization_intelligence.target_market` | — | market string |

## Test Results

- Focused: **76/76** passed
- Full regression: **4232/4232** passed (0 regressions)

---

# Phase 53B — Subtitle Knowledge Injection Pack

**Date:** 2026-05-11
**Status:** Complete — evaluation/advisory only

## Summary

Phase 53B extends the Phase 53A knowledge foundation with a curated subtitle knowledge pack layer. Four subtitle-domain JSON packs (mobile readability, TikTok short-form, podcast/talking-head, educational) are loaded by a dedicated `subtitle_knowledge_retriever` with its own `AISubtitleKnowledgeItem` / `AISubtitleKnowledgePack` schema. Two integration hooks add optional knowledge enrichment to Phase 52A (subtitle quality evaluator) and Phase 50A (subtitle preference inference). All influence is additive reasoning metadata — subtitle timing, text, FFmpeg, and the render pipeline are never mutated.

## New Files

| File | Purpose |
|---|---|
| `backend/knowledge/subtitles/mobile_readability.json` | Mobile readability subtitle knowledge pack |
| `backend/knowledge/subtitles/tiktok_shortform.json` | TikTok short-form subtitle knowledge pack |
| `backend/knowledge/subtitles/podcast_talking_head.json` | Podcast/talking-head subtitle knowledge pack |
| `backend/knowledge/subtitles/educational_subtitle.json` | Educational subtitle knowledge pack |
| `backend/app/ai/knowledge/subtitle_knowledge_schema.py` | `AISubtitleKnowledgeItem` + `AISubtitleKnowledgePack` dataclasses |
| `backend/app/ai/knowledge/subtitle_knowledge_retriever.py` | Tag-based retrieval + `build_subtitle_reasoning()` |
| `backend/tests/test_ai_phase53b_subtitle_knowledge.py` | 36 focused tests |

## Modified Files

| File | Change |
|---|---|
| `backend/app/ai/knowledge/knowledge_registry.py` | Added `"subtitles"` to `_KNOWLEDGE_SUBDIRS` |
| `backend/app/ai/subtitle_quality/subtitle_quality_evaluator.py` | Added `_mobile_knowledge_hint()` + call in `_build_reasoning()` |
| `backend/app/ai/creator_subtitle/subtitle_preference_inference.py` | Added `_get_knowledge_signal()` + call after confidence computation |

## Safety Contract

- Local only — no internet, no cloud API
- Never raises — all hooks wrapped in try/except, return `""` on any error
- Guard: knowledge hooks fire only when `style != "unknown" and active_domains > 0`
- Additive only — enriches `reasoning` list and `signals` list; never mutates subtitle timing, text, or render parameters

## Test Results

- Focused: **36/36** passed
- Full regression: **4268/4268** passed (0 regressions)

---

# Phase 53C — Camera Knowledge Injection Pack

**Date:** 2026-05-12
**Status:** Complete — evaluation/advisory only

## Summary

Phase 53C mirrors Phase 53B for the camera domain. Five camera-domain JSON packs (stable framing, interview/talking-head, vertical short-form, dynamic viral, anti-jitter) are loaded by a dedicated `camera_knowledge_retriever` with its own `AICameraKnowledgeItem` / `AICameraKnowledgePack` schema. Two integration hooks add optional knowledge enrichment to Phase 52B (camera quality evaluator — jitter hint) and Phase 50B (camera preference inference — motion style signal). All influence is additive reasoning metadata — motion_crop, tracking, scene detection, FFmpeg, and the render pipeline are never mutated.

## New Files

| File | Purpose |
|---|---|
| `backend/knowledge/camera/stable_framing.json` | Stable framing / low-jitter camera knowledge pack |
| `backend/knowledge/camera/interview_talking_head.json` | Interview / talking-head camera knowledge pack (`creator_style: podcast`) |
| `backend/knowledge/camera/vertical_shortform.json` | Vertical short-form / TikTok safe-zone camera knowledge pack |
| `backend/knowledge/camera/dynamic_viral.json` | Dynamic viral motion camera knowledge pack |
| `backend/knowledge/camera/anti_jitter.json` | Anti-jitter / anti-whip-pan camera knowledge pack |
| `backend/app/ai/knowledge/camera_knowledge_schema.py` | `AICameraKnowledgeItem` + `AICameraKnowledgePack` dataclasses |
| `backend/app/ai/knowledge/camera_knowledge_retriever.py` | Tag-based retrieval + `build_camera_reasoning()` |
| `backend/tests/test_ai_phase53c_camera_knowledge.py` | 39 focused tests |

## Modified Files

| File | Change |
|---|---|
| `backend/app/ai/knowledge/knowledge_registry.py` | Added `"camera"` to `_KNOWLEDGE_SUBDIRS` |
| `backend/app/ai/camera_quality/camera_quality_evaluator.py` | Added `_jitter_knowledge_hint()` + call in `_build_reasoning()` when `jitter >= 35` |
| `backend/app/ai/creator_camera/camera_preference_inference.py` | Added `_get_camera_knowledge_signal()` + call after confidence computation |

## Safety Contract

- Local only — no internet, no cloud API
- Never raises — all hooks wrapped in try/except, return `""` on any error
- Guard: knowledge hooks fire only when `motion_style != "unknown" and active_domains > 0`
- Additive only — enriches `reasoning` list and `signals` list; never mutates motion_crop, tracking, scene detection, or render parameters
- No motion_crop rewrite, no tracking rewrite, no FFmpeg mutation, no executor override

## Knowledge Hook Logic

| Hook | File | Trigger condition | Effect |
|---|---|---|---|
| `_jitter_knowledge_hint()` | `camera_quality_evaluator.py` | `len(reasoning) < 6 and jitter >= 35` | Appends anti-jitter guidance string to reasoning |
| `_get_camera_knowledge_signal()` | `camera_preference_inference.py` | `len(signals) < 5 and motion_style != "unknown" and active_domains > 0` | Appends motion-style aligned knowledge signal |

## Test Results

- Focused: **39/39** passed
- Full regression: **4307/4307** passed (0 regressions)

---

# Phase 53D — Hook / Retention Knowledge Injection Pack

**Date:** 2026-05-12
**Status:** Complete — evaluation/advisory only

## Summary

Phase 53D injects curated hook, retention, curiosity, opening-sequence, and market-specific hook expertise into the hook quality AI system (Phase 52C). Seven hook-domain JSON packs (opening 3-second hook, first-5-second retention, curiosity/open-loop, US market hook, EU market hook, JP market hook, hook fatigue/overuse) are loaded by a dedicated `hook_knowledge_retriever` with its own `AIHookKnowledgeItem` / `AIHookKnowledgePack` schema. Three integration hooks add optional knowledge enrichment to Phase 52C (hook quality evaluator — first-3s hint, curiosity hint, market hint). All influence is additive reasoning metadata — hook text, transcript, clip boundaries, subtitle timing, motion_crop, FFmpeg, and the render pipeline are never mutated.

## Hook Knowledge Domains

| Domain | Description |
|---|---|
| Opening 3-second hook | Immediate attention capture, first-frame strength, direct value proposition |
| First 5-second retention | Momentum after hook, early payoff signal, continuation pressure |
| Curiosity / open loop | Curiosity gap, unresolved question, story tension, payoff expectation |
| Market-specific — US | Direct hook, high energy, clear promise, strong result framing |
| Market-specific — EU | Trust-first hook, informative opening, credibility-oriented setup |
| Market-specific — JP | Subtle curiosity, story-first opening, softer emotional tension |
| Hook fatigue / overuse | Hype overuse risk, formulaic pattern fatigue, creator style mismatch |

## New Files

| File | Purpose |
|---|---|
| `backend/knowledge/hooks/opening_3s_hook.json` | Opening 3-second hook knowledge pack |
| `backend/knowledge/hooks/first_5s_retention.json` | First 5-second retention knowledge pack |
| `backend/knowledge/hooks/curiosity_open_loop.json` | Curiosity and open-loop knowledge pack |
| `backend/knowledge/hooks/market_hook_us.json` | US market hook knowledge pack |
| `backend/knowledge/hooks/market_hook_eu.json` | EU market hook knowledge pack |
| `backend/knowledge/hooks/market_hook_jp.json` | JP market hook knowledge pack |
| `backend/knowledge/hooks/hook_fatigue_overuse.json` | Hook fatigue / overuse knowledge pack |
| `backend/app/ai/knowledge/hook_knowledge_schema.py` | `AIHookKnowledgeItem` + `AIHookKnowledgePack` dataclasses |
| `backend/app/ai/knowledge/hook_knowledge_retriever.py` | Tag-based retrieval + `build_hook_reasoning()` |
| `backend/tests/test_ai_phase53d_hook_knowledge.py` | 44 focused tests |

## Modified Files

| File | Change |
|---|---|
| `backend/app/ai/hook_quality/hook_quality_evaluator.py` | Added `_first3s_knowledge_hint()`, `_curiosity_knowledge_hint()`, `_market_hook_hint()` + calls in `_build_reasoning()` |

## Safety Contract

- Local only — no internet, no cloud API
- Never raises — all hooks wrapped in try/except, return `""` on any error
- Guard: knowledge hints fire only when reasoning list has room (`len(lines) < 6`) AND score is below threshold
- Additive only — enriches `reasoning` list; never mutates hook text, transcript, clip boundaries, or render parameters
- No transcript rewrite, no hook text rewrite, no clip segmentation mutation
- No subtitle engine mutation, no motion_crop mutation, no FFmpeg mutation, no executor override

## Knowledge Hook Logic

| Hook | File | Trigger condition | Effect |
|---|---|---|---|
| `_first3s_knowledge_hint()` | `hook_quality_evaluator.py` | `len(reasoning) < 6 and first_3s < 55` | Appends opening-hook guidance string to reasoning |
| `_curiosity_knowledge_hint()` | `hook_quality_evaluator.py` | `len(reasoning) < 6 and curiosity < 50` | Appends curiosity/open-loop guidance string to reasoning |
| `_market_hook_hint()` | `hook_quality_evaluator.py` | `len(reasoning) < 6 and market < 55` | Appends market-specific hook guidance string to reasoning |

## Retrieval Behavior

```
retrieve_knowledge(domain="hook", tags=["first_3s", "opening"]) → opening 3s knowledge
retrieve_knowledge(domain="hook", tags=["curiosity", "open_loop"]) → curiosity knowledge
retrieve_knowledge(domain="hook", tags=["market_hook", "us"]) → US market hook knowledge
retrieve_knowledge(domain="hook", tags=["fatigue"]) → fatigue / overuse knowledge
```

## Test Results

- Focused: **44/44** passed
- Full regression: **4351/4351** passed (0 regressions)

---

# Phase 53E — Knowledge-Aware Render Reasoning

**Date:** 2026-05-12
**Status:** Complete — advisory/metadata only

## Summary

Phase 53E connects Phase 53B/C/D domain retrievers (subtitle, camera, hook) into a unified cross-domain `knowledge_reasoning_context`. A new `knowledge_reasoning_context.py` module reads active quality signals from the edit plan, derives relevant retrieval tags per domain, calls the appropriate domain retriever, and assembles a structured advisory reasoning context. The context is attached to `AIEditPlan.knowledge_reasoning_context` via a Phase 53E block in `ai_director.py` and optionally enriches unified quality v2 reasoning via `_knowledge_reasoning_hint()`. All influence is advisory metadata — no render mutation, no executor override, no autonomous execution.

## Knowledge Routing

| Domain | Signal Source | Tags Derived |
|---|---|---|
| Subtitle | `subtitle_quality_v2.mobile_readability < 70` | `["mobile", "readability"]` |
| Subtitle | `creator_subtitle_preference.style == "viral_bold"` | `["tiktok", "shortform"]` |
| Subtitle | `creator_subtitle_preference.style == "clean_pro"` | `["podcast", "clean"]` |
| Camera | `camera_quality_v2.micro_jitter_risk >= 35` | `["anti_jitter", "jitter"]` |
| Camera | `camera_quality_v2.whip_pan_risk >= 35` | `["stable_framing", "smooth"]` |
| Camera | `creator_camera_preference.motion_style == "static_center"` | `["interview", "talking_head"]` |
| Hook | `hook_quality_v2.first_3s_strength < 55` | `["first_3s", "opening"]` |
| Hook | `hook_quality_v2.curiosity_strength < 50` | `["curiosity", "open_loop"]` |
| Hook | `hook_quality_v2.hook_fatigue_risk >= 40` | `["fatigue", "overuse"]` |
| Hook | `market_optimization_intelligence.target_market` | `["market_hook", market_code]` |

## Context Schema

```json
{
  "knowledge_reasoning_context": {
    "available": true,
    "domains": ["camera", "hook", "subtitle"],
    "matches": [
      {"domain": "subtitle", "rule_id": "mobile_readability_subtitle", "title": "...", "confidence": 0.75},
      {"domain": "camera", "rule_id": "anti_jitter_camera", "title": "...", "confidence": 0.75},
      {"domain": "hook", "rule_id": "opening_3s_hook", "title": "...", "confidence": 0.75}
    ],
    "confidence": 0.75,
    "reasoning": [
      "Subtitle knowledge is relevant to the current subtitle quality signals",
      "Camera knowledge is relevant to the current camera quality signals",
      "Knowledge matched across subtitle, camera and hook domains supports quality reasoning"
    ]
  }
}
```

## New Files

| File | Purpose |
|---|---|
| `backend/app/ai/knowledge/knowledge_reasoning_context.py` | Cross-domain routing, retrieval, and context assembly |
| `backend/tests/test_ai_phase53e_knowledge_reasoning.py` | 44 focused tests |

## Modified Files

| File | Change |
|---|---|
| `backend/app/ai/director/edit_plan_schema.py` | Added `knowledge_reasoning_context: dict` Phase 53E field + `to_dict()` entry |
| `backend/app/ai/director/ai_director.py` | Added Phase 53E block + `_attach_knowledge_reasoning_context()` helper |
| `backend/app/ai/unified_quality/unified_quality_evaluator.py` | Added `_knowledge_reasoning_hint()` + call in `_build_reasoning()` |

## Safety Contract

- Local only — no internet, no cloud API
- Never raises — all code wrapped in try/except, fallback returns `available=False` context
- Deterministic — same edit plan inputs always produce the same context output
- Bounded — max 3 domain retrievals × 1 item each = max 3 matches per context
- Advisory only — enriches `reasoning` list and `knowledge_reasoning_context` metadata field; never mutates subtitle timing, motion_crop, clip boundaries, FFmpeg, or render parameters
- No executor override, no autonomous execution
- Safety filter: `_FORBIDDEN_KEYS` frozenset guards against execution-related content leaking into match output
- No raw JSON pack content exposed — only `rule_id`, `title`, and `confidence` surfaced

## AI UX Reasoning

`safe_knowledge_reasoning_summary(ctx)` produces a single creator-facing line:

```
"AI used subtitle, camera and hook knowledge to support this recommendation."
```

Rules:
- Never exposes raw knowledge JSON
- Never exposes internal rule IDs beyond the knowledge_id
- Never exposes file paths or stack traces
- Returns empty string when context is unavailable

## Executor Authority

The render executor retains full authority. Knowledge-aware reasoning is metadata only:
- `knowledge_reasoning_context` is attached to `AIEditPlan` but never read by the render executor
- No render path reads `knowledge_reasoning_context` to alter execution behavior
- Quality scores are unchanged — knowledge reasoning enriches *reasoning text* only

## Test Results

- Focused: **44/44** passed
- Full regression: **4395/4395** passed (0 regressions)

---

# Phase 54 — Knowledge-Aware Influence Upgrade

**Date:** 2026-05-12
**Status:** Complete — advisory metadata only

## Summary

Phase 54 builds on Phase 53E's `knowledge_reasoning_context` to produce per-domain influence support metadata. Each active knowledge domain (subtitle, camera, hook/ranking) receives a bounded `confidence_delta` and creator-facing reasoning strings. Three enrich helpers (subtitle, camera, ranking) allow downstream influence engines to optionally append knowledge reasoning to their output — additive only, no bias values changed. The Phase 48 safety gate is never bypassed or lowered by knowledge.

## New Files

| File | Purpose |
|---|---|
| `backend/app/ai/knowledge/knowledge_influence_context.py` | Phase 54 context builder + enrich helpers |
| `backend/tests/test_ai_phase54_knowledge_influence.py` | 41 focused tests |

## Modified Files

| File | Change |
|---|---|
| `backend/app/ai/director/edit_plan_schema.py` | Added `knowledge_influence_context: dict` Phase 54 field + `to_dict()` entry |
| `backend/app/ai/director/ai_director.py` | Added Phase 54 block + `_attach_knowledge_influence_context()` helper |
| `backend/app/ai/knowledge/knowledge_influence_context.py` | Fixed enrich helpers to return `{}` instead of `None` for falsy inputs |

## Confidence Delta Bounds (strictly enforced)

| Domain | Fixed Delta | Max Per Domain | Max Total |
|---|---|---|---|
| Subtitle | 0.04 | 0.05 | 0.10 |
| Camera | 0.03 | 0.05 | 0.10 |
| Ranking (hook) | 0.04 | 0.05 | 0.10 |
| **Total** | 0.07–0.11 clamped | — | **0.10** |

Delta is advisory metadata only — never fed into `evaluate_gate()`.

## Public API

```python
from app.ai.knowledge.knowledge_influence_context import (
    build_knowledge_influence_context,
    enrich_subtitle_influence_reasoning,
    enrich_camera_influence_reasoning,
    enrich_ranking_influence_reasoning,
)

# Build per-domain influence support from Phase 53E context
ctx = build_knowledge_influence_context(edit_plan)

# Enrich influence dicts (additive, preserves all other fields)
subtitle_inf = enrich_subtitle_influence_reasoning(subtitle_inf, ctx["influence_support"]["subtitle"])
camera_inf   = enrich_camera_influence_reasoning(camera_inf, ctx["influence_support"]["camera"])
ranking_inf  = enrich_ranking_influence_reasoning(ranking_inf, ctx["influence_support"]["ranking"])
```

## Enrich Helper Contract

- **Additive only** — appends to existing `reasoning` list, never replaces
- **Cap at 6** — merged reasoning capped at 6 items total
- **Preserves all other fields** — `{**influence_dict, "reasoning": merged}`
- **Never raises** — wrapped in try/except, fallback returns original dict (or `{}` for None input)
- **No bias mutation** — enrich helpers never alter bias values, deltas, or scores

## Safety Contract

- Local only — no internet, no cloud API
- Never raises — all code wrapped in try/except
- Deterministic — same inputs → same output
- Advisory only — `confidence_delta` is metadata, NEVER fed into safety gate
- Safety gate unchanged — Phase 48 `evaluate_gate()` is never called with boosted confidence
- Bounded — per-domain max 0.05, total max 0.10
- Safety filter — `_FORBIDDEN_INFLUENCE_KEYS` frozenset blocks execution-related keys from output
- No raw knowledge pack content exposed — only creator-facing reasoning strings

## Safety Gate Preservation

The Phase 48 safety gate retains full authority:

```python
# evaluate_gate() is called with raw plan confidence — knowledge delta is never passed to it
gate = evaluate_gate(plan_confidence)  # unchanged
# knowledge_influence_context is metadata on the plan, not an input to evaluate_gate
```

A plan with confidence 0.65 remains BLOCKED regardless of knowledge delta (+0.10 → 0.75 hypothetically, but delta is never fed to the gate).

## Test Results

- Focused: **41/41** passed
- Full regression: **4436/4436** passed (0 regressions)

---

# Phase 55A — Platform Knowledge Foundation

**Date:** 2026-05-12
**Status:** Complete — advisory metadata only

## Summary

Phase 55A creates a deterministic local platform knowledge framework. Curated JSON packs describe platform-specific and creator-archetype-specific guidance (subtitle density, camera stability, hook priority). A new loader reads from `knowledge/platforms/`, a retriever provides filtered deterministic access, and a context builder attaches advisory metadata to `AIEditPlan.platform_context`. This is a foundation-only phase — no influence mutation, no render execution change.

## New Files

| File | Purpose |
|---|---|
| `backend/app/ai/knowledge/platform_knowledge_schema.py` | `AIPlatformKnowledgeItem`, `AIPlatformKnowledgePack`, `AIPlatformContext` dataclasses |
| `backend/app/ai/knowledge/platform_knowledge_loader.py` | Local JSON loader with safety filter, file-size cap, module cache |
| `backend/app/ai/knowledge/platform_knowledge_retriever.py` | `retrieve_platform_knowledge()` + `build_platform_context()` public API |
| `backend/knowledge/platforms/tiktok_shortform_foundation.json` | TikTok short-form seed pack |
| `backend/knowledge/platforms/youtube_shorts_foundation.json` | YouTube Shorts seed pack |
| `backend/knowledge/platforms/instagram_reels_foundation.json` | Instagram Reels seed pack |
| `backend/knowledge/platforms/podcast_creator_foundation.json` | Podcast creator archetype seed pack |
| `backend/knowledge/platforms/educational_creator_foundation.json` | Educational creator archetype seed pack |
| `backend/tests/test_ai_phase55a_platform_knowledge.py` | 53 focused tests |

## Modified Files

| File | Change |
|---|---|
| `backend/app/ai/director/edit_plan_schema.py` | Added `platform_context: dict` Phase 55A field + `to_dict()` entry |
| `backend/app/ai/director/ai_director.py` | Added Phase 55A block + `_attach_platform_context()` helper |

## Platform Knowledge Architecture

### JSON pack schema

```json
{
  "knowledge_id": "tiktok_shortform_foundation",
  "platform": "tiktok",
  "creator_type": "viral_short_form",
  "version": 1,
  "title": "TikTok Short-Form Foundation",
  "description": "...",
  "tags": ["tiktok", "shortform", "viral", "mobile"],
  "domains": ["subtitle", "camera", "hook"],
  "guidance": {
    "subtitle": {"density_bias": "compact", "readability_priority": "high"},
    "camera": {"stability_priority": "medium", "aggressiveness": "moderate"},
    "hook": {"first_3s_priority": "high", "retention_priority": "high"}
  },
  "confidence": 0.82
}
```

### Loader contract

- Reads `knowledge/platforms/*.json` via a **separate loader** from Phase 39 `knowledge_registry.py` (different schema)
- Hard limits: 500 KB file-size cap, 100 item max
- Safety filter: rejects any file containing forbidden execution keys (`ffmpeg_args`, `render_command`, `motion_crop`, `subprocess`, …)
- Deterministic final sort: alphabetical by `knowledge_id`
- Module-level cache: same path → same list (test-clearable via `clear_cache()`)
- Never raises — malformed files silently skipped

### Retrieval rules

```
retrieve_platform_knowledge(platform, creator_type, base_path, max_results)
```

| Filter combination | Behaviour |
|---|---|
| both platform + creator_type | exact dual-match first, then platform-only, then creator_type-only, alpha tiebreak |
| platform only | any item with matching platform |
| creator_type only | any item with matching creator_type |
| neither | all items |

- `max_results` clamped `[1, 10]`
- Always returns `AIPlatformKnowledgePack` — never None, never raises

### Context builder

```python
build_platform_context(platform, creator_type, base_path)
# → {"platform_context": {available, platform, creator_type, matches, confidence, reasoning}}
```

Reads `platform` / `creator_type` from request in `_attach_platform_context()` and attaches the result to `AIEditPlan.platform_context`.

## Seed Packs

| knowledge_id | platform | creator_type | domains | confidence |
|---|---|---|---|---|
| `tiktok_shortform_foundation` | tiktok | viral_short_form | subtitle, camera, hook | 0.82 |
| `youtube_shorts_foundation` | youtube_shorts | viral_short_form | subtitle, camera, hook | 0.80 |
| `instagram_reels_foundation` | instagram_reels | viral_short_form | subtitle, camera, hook | 0.78 |
| `podcast_creator_foundation` | general | podcast | subtitle, camera | 0.81 |
| `educational_creator_foundation` | general | educational | subtitle, camera, hook | 0.79 |

## Supported identifiers

**Platforms:** `tiktok`, `youtube_shorts`, `instagram_reels`, `general`
**Creator archetypes:** `podcast`, `talking_head`, `educational`, `storytelling`, `viral_short_form`, `general`

Future phases (55B–55D) will add domain-specific intelligence using this foundation.

## Safety Contract

- Local only — no internet, no cloud API, no scraping, no autonomous learning
- Never raises — all paths wrapped in try/except with fallback returns
- Deterministic — same inputs → same output (no randomness)
- Advisory only — `platform_context` is metadata, never alters render parameters
- Foundation only — no influence mutation, no scoring change, no executor override
- Safety filter — `_FORBIDDEN_KEYS` frozenset rejects packs with execution-related keys
- No raw file paths in creator-facing reasoning strings
- Executor authority unchanged — render pipeline never reads `platform_context`
- Backward compatible — `platform_context` defaults to `{}` when platform/creator_type not provided

## Executor Authority

The render executor retains full authority. Platform knowledge is foundation metadata only:
- `platform_context` is attached to `AIEditPlan` but never read by the render executor
- No render path reads `platform_context` to alter execution behavior
- Quality scores, timing, subtitle segmentation, motion_crop, and FFmpeg are unchanged

## Future Phases

| Phase | Mission |
|---|---|
| 55B | Platform Subtitle Intelligence — subtitle guidance from platform context ✅ |
| 55C | Platform Camera Intelligence — camera guidance from platform context |
| 55D | Platform Hook Intelligence — hook/retention guidance from platform context |
| 55E | Platform-Aware Render Strategy — cross-domain platform strategy |

## Test Results

- Focused: **53/53** passed
- Full regression: **4489/4489** passed (0 regressions)

---

# Phase 55B — Platform Subtitle Intelligence

**Date:** 2026-05-12
**Status:** Complete — advisory metadata only

## Summary

Phase 55B extends Phase 55A with subtitle-specific platform intelligence. Five new subtitle-focused JSON packs (TikTok, YouTube Shorts, Instagram Reels, podcast, educational) are retrieved by `platform_subtitle_retriever.py`, which filters the Phase 55A platform loader to subtitle-domain items, merges guidance, and builds an advisory `platform_subtitle_context` dict. Light integration hooks add optional one-line hints to the Phase 52A subtitle quality evaluator and the Phase 50A subtitle preference inference engine — additive only, never mutating subtitle execution.

## New Files

| File | Purpose |
|---|---|
| `backend/app/ai/knowledge/platform_subtitle_retriever.py` | Phase 55B retriever + `build_platform_subtitle_context()` |
| `backend/knowledge/platforms/tiktok_subtitle_intelligence.json` | TikTok subtitle intelligence pack |
| `backend/knowledge/platforms/youtube_shorts_subtitle_intelligence.json` | YouTube Shorts subtitle pack |
| `backend/knowledge/platforms/instagram_reels_subtitle_intelligence.json` | Instagram Reels subtitle pack |
| `backend/knowledge/platforms/podcast_subtitle_intelligence.json` | Podcast/talking-head subtitle pack |
| `backend/knowledge/platforms/educational_subtitle_intelligence.json` | Educational creator subtitle pack |
| `backend/tests/test_ai_phase55b_platform_subtitle.py` | 48 focused tests |

## Modified Files

| File | Change |
|---|---|
| `backend/app/ai/director/edit_plan_schema.py` | Added `platform_subtitle_context: dict` Phase 55B field + `to_dict()` entry |
| `backend/app/ai/director/ai_director.py` | Added Phase 55B block + `_attach_platform_subtitle_context()` helper |
| `backend/app/ai/subtitle_quality/subtitle_quality_evaluator.py` | Added `_platform_subtitle_hint()` — optional Phase 55B reasoning hint |
| `backend/app/ai/creator_subtitle/subtitle_preference_inference.py` | Added `_get_platform_subtitle_signal()` — optional Phase 55B preference signal |

## platform_subtitle_context Shape

```json
{
  "platform_subtitle_context": {
    "available": true,
    "platform": "tiktok",
    "creator_type": "viral_short_form",
    "guidance": {
      "density_bias": "compact",
      "readability_priority": "high",
      "keyword_emphasis": "selective",
      "line_count_preference": 2,
      "overload_risk_sensitivity": "high",
      "mobile_safe_required": true,
      "animation_level": "medium",
      "style_preference": "viral_bold"
    },
    "confidence": 0.83,
    "reasoning": [
      "TikTok Subtitle Intelligence supports compact density with high readability priority"
    ]
  }
}
```

Fallback:
```json
{"platform_subtitle_context": {"available": false, "guidance": {}, "confidence": 0.0, "reasoning": []}}
```

## Subtitle Packs

| knowledge_id | platform | creator_type | Key guidance |
|---|---|---|---|
| `tiktok_subtitle_intelligence` | tiktok | viral_short_form | compact density, high readability, selective emphasis, mobile_safe |
| `youtube_shorts_subtitle_intelligence` | youtube_shorts | viral_short_form | normal density, high readability, moderate emphasis, low animation |
| `instagram_reels_subtitle_intelligence` | instagram_reels | viral_short_form | compact density, medium readability, moderate emphasis |
| `podcast_subtitle_intelligence` | general | podcast | normal density, high readability, subtle emphasis, low animation, clean_pro |
| `educational_subtitle_intelligence` | general | educational | normal density, high readability, moderate emphasis, concept_highlighting |

## Retrieval Architecture

`retrieve_platform_subtitle_knowledge(platform, creator_type, tags, base_path, max_results)`:
1. Loads all platform items via Phase 55A `load_platform_knowledge()`
2. Filters to items with `"subtitle"` in their `domains` list
3. Filters by platform and/or creator_type
4. Optional tag filter (any-match) — falls back to unfiltered when no match
5. Deterministic sort: exact dual-match → platform-only → creator_type-only → alpha
6. Merges subtitle guidance from top matches (first item wins on conflicts)
7. Strips forbidden execution keys from guidance via `_safe_guidance()`

## Integration Hooks

| Hook | Location | Guard | Effect |
|---|---|---|---|
| `_platform_subtitle_hint()` | Phase 52A subtitle quality evaluator | `len(lines) < 6` | Appends one platform reasoning hint |
| `_get_platform_subtitle_signal()` | Phase 50A subtitle preference inference | `len(signals) < 5 AND active_domains > 0` | Appends one platform preference signal |

Both hooks:
- Read `plan.platform_subtitle_context` via `getattr(edit_plan, ...)` — no AttributeError risk
- Return `""` (no-op) when context is unavailable — existing behavior unchanged
- Truncate output to 100 chars for UI display
- Never mutate subtitle values, scores, or confidence

## Safety Contract

- Local only — no internet, no cloud API, no scraping
- Never raises — all paths wrapped in try/except
- Deterministic — same inputs → same output
- Advisory only — `platform_subtitle_context` is metadata, never alters subtitle execution
- No subtitle timing rewrite, no ASS rewrite, no segmentation rewrite
- Safety filter — forbidden execution keys rejected by loader (`ffmpeg_args`, `render_command`, `motion_crop`, etc.) — entire file rejected, not just keys stripped
- No raw file paths in creator-facing reasoning strings
- Executor authority unchanged — render pipeline never reads `platform_subtitle_context`
- Backward compatible — defaults to `{}` when platform/creator_type not provided

## Test Results

- Focused: **48/48** passed
- Full regression: **4537/4537** passed (0 regressions)


---

### 2026-05-12 — AI Productization Phase 55C: Platform Camera Intelligence

**Implemented:**
- `backend/knowledge/platforms/tiktok_camera_intelligence.json` — TikTok camera intelligence pack
- `backend/knowledge/platforms/youtube_shorts_camera_intelligence.json` — YouTube Shorts camera pack
- `backend/knowledge/platforms/instagram_reels_camera_intelligence.json` — Instagram Reels camera pack
- `backend/knowledge/platforms/podcast_camera_intelligence.json` — Podcast/talking-head camera pack
- `backend/knowledge/platforms/educational_camera_intelligence.json` — Educational creator camera pack
- `backend/app/ai/knowledge/platform_camera_retriever.py` — Phase 55C retriever + `build_platform_camera_context()`

**Modified Files:**

| File | Change |
|---|---|
| `backend/app/ai/director/edit_plan_schema.py` | Added `platform_camera_context: dict` Phase 55C field + `to_dict()` entry |
| `backend/app/ai/director/ai_director.py` | Added Phase 55C block + `_attach_platform_camera_context()` helper |
| `backend/app/ai/camera_quality/camera_quality_evaluator.py` | Added `_platform_camera_hint()` — optional Phase 55C reasoning hint |
| `backend/app/ai/creator_camera/camera_preference_inference.py` | Added `_get_platform_camera_signal()` — optional Phase 55C preference signal |

## platform_camera_context Shape

```json
{
  "platform_camera_context": {
    "available": true,
    "platform": "tiktok",
    "creator_type": "viral_short_form",
    "guidance": {
      "motion_energy": "high",
      "stability_priority": "medium",
      "jitter_sensitivity": "low",
      "subject_continuity": "high",
      "deadzone_bias": "narrow",
      "crop_aggressiveness_guidance": "medium",
      "smoothness_priority": "medium"
    },
    "confidence": 0.82,
    "reasoning": [
      "TikTok Camera Intelligence recommends high motion energy with medium stability priority"
    ]
  }
}
```

Fallback:
```json
{"platform_camera_context": {"available": false, "guidance": {}, "confidence": 0.0, "reasoning": []}}
```

## Camera Packs

| knowledge_id | platform | creator_type | Key guidance |
|---|---|---|---|
| `tiktok_camera_intelligence` | tiktok | viral_short_form | high motion energy, medium stability, low jitter_sensitivity, narrow deadzone |
| `youtube_shorts_camera_intelligence` | youtube_shorts | viral_short_form | medium motion energy, high stability, high smoothness_priority |
| `instagram_reels_camera_intelligence` | instagram_reels | viral_short_form | high motion energy, medium stability, narrow deadzone |
| `podcast_camera_intelligence` | general | podcast | low motion energy, high stability, high jitter_sensitivity, wide deadzone |
| `educational_camera_intelligence` | general | educational | low motion energy, high stability, high jitter_sensitivity, wide deadzone |

## Retrieval Architecture

`retrieve_platform_camera_knowledge(platform, creator_type, tags, base_path, max_results)`:
1. Loads all platform items via Phase 55A `load_platform_knowledge()`
2. Filters to items with `"camera"` in their `domains` list
3. Filters by platform and/or creator_type
4. Optional tag filter (any-match) — falls back to unfiltered when no match
5. Deterministic sort: exact dual-match → platform-only → creator_type-only → alpha
6. Merges camera guidance from top matches (first item wins on conflicts)
7. Strips forbidden execution keys from guidance via `_safe_guidance()`

## Integration Hooks

| Hook | Location | Guard | Effect |
|---|---|---|---|
| `_platform_camera_hint()` | Phase 52B camera quality evaluator | `len(lines) < 6` | Appends one platform reasoning hint |
| `_get_platform_camera_signal()` | Phase 50B camera preference inference | `len(signals) < 5 AND active_domains > 0` | Appends one platform preference signal |

Both hooks:
- Read `plan.platform_camera_context` via `getattr(edit_plan, ...)` — no AttributeError risk
- Return `""` (no-op) when context is unavailable — existing behavior unchanged
- Truncate output to 100 chars for UI display
- Never mutate camera values, scores, or confidence

## Safety Contract

- Local only — no internet, no cloud API, no scraping
- Never raises — all paths wrapped in try/except
- Deterministic — same inputs → same output
- Advisory only — `platform_camera_context` is metadata, never alters camera execution
- No motion_crop rewrite, no tracking config change, no FFmpeg mutation
- Safety filter — forbidden execution keys rejected by loader (`ffmpeg_args`, `render_command`, `motion_crop`, etc.) — entire file rejected, not just keys stripped
- No raw file paths in creator-facing reasoning strings
- Executor authority unchanged — render pipeline never reads `platform_camera_context`
- Backward compatible — defaults to `{}` when platform/creator_type not provided

## Test Results

- Focused: **50/50** passed (1 skipped)
- Full regression: **4587/4587** passed (0 regressions)


---

### 2026-05-12 — AI Productization Phase 55D: Platform Hook & Retention Intelligence

**Implemented:**
- `backend/knowledge/platforms/tiktok_hook_intelligence.json` — TikTok hook/retention pack
- `backend/knowledge/platforms/youtube_shorts_hook_intelligence.json` — YouTube Shorts hook pack
- `backend/knowledge/platforms/instagram_reels_hook_intelligence.json` — Instagram Reels hook pack
- `backend/knowledge/platforms/podcast_hook_intelligence.json` — Podcast/talking-head hook pack
- `backend/knowledge/platforms/educational_hook_intelligence.json` — Educational creator hook pack
- `backend/knowledge/platforms/viral_storytelling_hook_intelligence.json` — Viral storytelling hook pack
- `backend/app/ai/knowledge/platform_hook_retriever.py` — Phase 55D retriever + `build_platform_hook_context()`

**Modified Files:**

| File | Change |
|---|---|
| `backend/app/ai/director/edit_plan_schema.py` | Added `platform_hook_context: dict` Phase 55D field + `to_dict()` entry |
| `backend/app/ai/director/ai_director.py` | Added Phase 55D block + `_attach_platform_hook_context()` helper |
| `backend/app/ai/hook_quality/hook_quality_evaluator.py` | Added `_platform_hook_hint()` — optional Phase 55D reasoning hint |

## platform_hook_context Shape

```json
{
  "platform_hook_context": {
    "available": true,
    "platform": "tiktok",
    "creator_type": "viral_short_form",
    "guidance": {
      "first_3s_priority": "high",
      "retention_priority": "high",
      "curiosity_strength": "medium_high",
      "hook_energy": "high",
      "slow_intro_risk": "high",
      "payoff_expectation": "strong",
      "hook_style": "direct_promise",
      "open_loop_quality": "strong",
      "first_5s_retention": "high",
      "hype_level": "medium",
      "trust_priority": "low",
      "clarity_priority": "high"
    },
    "confidence": 0.84,
    "reasoning": [
      "TikTok Hook Intelligence prioritizes high first-3-second attention with high retention priority"
    ]
  }
}
```

Fallback:
```json
{"platform_hook_context": {"available": false, "guidance": {}, "confidence": 0.0, "reasoning": []}}
```

## Hook Packs

| knowledge_id | platform | creator_type | Key guidance |
|---|---|---|---|
| `tiktok_hook_intelligence` | tiktok | viral_short_form | high first_3s_priority, direct_promise, high hook_energy, strong payoff |
| `youtube_shorts_hook_intelligence` | youtube_shorts | viral_short_form | high first_5s_retention, direct_promise, high clarity_priority |
| `instagram_reels_hook_intelligence` | instagram_reels | viral_short_form | high first_3s, emotional hook_style, high emotional_stakes |
| `podcast_hook_intelligence` | general | podcast | trust_first hook_style, high trust_priority, low hype_level |
| `educational_hook_intelligence` | general | educational | concept_first hook_style, strong payoff_expectation, high clarity |
| `viral_storytelling_hook_intelligence` | general | storytelling | story_invitation, high narrative_tension, high emotional_stakes |

## Domains

All hook packs carry `domains: ["hook", "retention"]` — both hook quality and retention signals.

## Retrieval Architecture

`retrieve_platform_hook_knowledge(platform, creator_type, tags, base_path, max_results)`:
1. Loads all platform items via Phase 55A `load_platform_knowledge()`
2. Filters to items with `"hook"` in their `domains` list
3. Filters by platform and/or creator_type
4. Optional tag filter (any-match) — falls back to unfiltered when no match
5. Deterministic sort: exact dual-match → platform-only → creator_type-only → alpha
6. Merges hook guidance from top matches (first item wins on conflicts)
7. Strips forbidden execution keys from guidance via `_safe_guidance()`

## Integration Hook

| Hook | Location | Guard | Effect |
|---|---|---|---|
| `_platform_hook_hint()` | Phase 52C hook quality evaluator | `len(lines) < 6` | Appends one platform hook reasoning hint |

The hook:
- Reads `plan.platform_hook_context` via `getattr(edit_plan, ...)` — no AttributeError risk
- Returns `""` (no-op) when context is unavailable — existing behavior unchanged
- Never mutates hook text, transcript, clip boundaries, or scores

## Safe Guidance Keys

`first_3s_priority`, `retention_priority`, `curiosity_strength`, `hook_energy`, `slow_intro_risk`,
`payoff_expectation`, `hook_style`, `open_loop_quality`, `first_5s_retention`, `hype_level`,
`trust_priority`, `clarity_priority`, `emotional_stakes`, `narrative_tension`

## Safety Contract

- Local only — no internet, no cloud API, no scraping
- Never raises — all paths wrapped in try/except
- Deterministic — same inputs → same output
- Advisory only — `platform_hook_context` is metadata, never alters hook execution
- No transcript rewrite, no hook text rewrite, no clip boundary mutation, no render mutation
- Safety filter — forbidden execution keys rejected by loader (`ffmpeg_args`, `render_command`, `hook_rewrite`, `transcript`, etc.) — entire file rejected
- Executor authority unchanged — render pipeline never reads `platform_hook_context`
- Backward compatible — defaults to `{}` when platform/creator_type not provided

## Test Results

- Focused: **53/53** passed

---

# Phase 55E — Platform-Aware Render Strategy

**Module:** `app/ai/knowledge/platform_render_strategy_engine.py`
**Schema:** `app/ai/knowledge/platform_render_strategy_schema.py`
**Plan field:** `platform_render_strategy` (added to `AIEditPlan` in `edit_plan_schema.py`)
**Director hook:** `_attach_platform_render_strategy(plan, job_id)` — after Phase 55D

## Purpose

Fuses platform subtitle (55B), camera (55C), and hook (55D) intelligence into one deterministic advisory `platform_render_strategy`. This is the first module that synthesises multiple platform contexts into a single coherent strategy.

## Output Model

```json
{
  "platform_render_strategy": {
    "available": true,
    "platform": "tiktok",
    "creator_type": "podcast",
    "confidence": 0.8475,
    "strategy": {
      "subtitle": {
        "style_bias": "viral_bold",
        "density_bias": "dense",
        "keyword_emphasis": "high",
        "readability_priority": "high"
      },
      "camera": {
        "motion_energy": "low_medium",
        "stability_priority": "high",
        "crop_aggressiveness": "low",
        "jitter_sensitivity": "high"
      },
      "hook": {
        "first_3s_priority": "high",
        "hook_energy": "moderate",
        "retention_priority": "high",
        "curiosity_style": "soft_direct"
      },
      "ranking": {
        "priority": "retention_creator_fit"
      }
    },
    "reasoning": ["TikTok platform guidance and podcast creator intelligence are informing strategy."]
  }
}
```

Fallback:

```json
{"platform_render_strategy": {"available": false, "platform": "", "creator_type": "", "strategy": {}, "confidence": 0.0, "reasoning": []}}
```

## Allowed Value Sets (frozensets)

All strategy field values are normalised against explicit allowed sets — any unknown value becomes `"unknown"`:

| Field | Allowed values |
|---|---|
| `subtitle.style_bias` | `viral_bold`, `clean_pro`, `boxed_caption`, `unknown` |
| `subtitle.density_bias` | `dense`, `normal`, `minimal`, `unknown` |
| `subtitle.keyword_emphasis` | `high`, `medium`, `low`, `none`, `unknown` |
| `subtitle.readability_priority` | `high`, `medium`, `low`, `unknown` |
| `camera.motion_energy` | `high`, `medium_high`, `medium`, `low_medium`, `low`, `unknown` |
| `camera.stability_priority` | `high`, `medium_high`, `medium`, `low`, `unknown` |
| `camera.crop_aggressiveness` | `high`, `medium`, `low`, `unknown` |
| `camera.jitter_sensitivity` | `high`, `medium`, `low`, `unknown` |
| `hook.first_3s_priority` | `high`, `medium`, `low`, `unknown` |
| `hook.retention_priority` | `high`, `medium`, `low`, `unknown` |
| `hook.hook_energy` | `high`, `moderate`, `low`, `unknown` |
| `hook.curiosity_style` | `direct`, `soft_direct`, `open_loop`, `subtle`, `unknown` |
| `ranking.priority` | `creator_fit`, `retention`, `hook_strength`, `readability`, `retention_creator_fit`, `balanced`, `unknown` |

## Conflict Resolution

Creator safety > platform energy pressure. Key rules:

| Condition | Conflict | Resolution |
|---|---|---|
| TikTok + podcast | High energy vs stable camera | `motion_energy → low_medium`, `stability_priority → high`, `crop_aggressiveness → low` |
| TikTok + podcast | `viral_bold` subtitle vs creator trust | `style_bias = viral_bold` (allowed — bold is compatible with trust) |
| TikTok + podcast | `direct` curiosity style | `curiosity_style → soft_direct` (conservative trust cap) |
| TikTok + podcast | `high` hook energy | `hook_energy → moderate` (trust creator cap) |
| YouTube Shorts + educational | `medium` camera motion | `motion_energy → low_medium` (clarity cap) |
| High retention platform + trust/clarity creator | Retention vs creator fit | `ranking.priority → retention_creator_fit` |
| Trust creator only | Any | `ranking.priority → creator_fit` |
| Educational creator | Any | `ranking.priority → readability` |

Hook energy remap: raw guidance value `"medium"` → normalised `"moderate"` before allowed-set check.

## Confidence Computation

`confidence = avg(subtitle_context.confidence, camera_context.confidence, hook_context.confidence)` from available contexts only. Clamped `[0, 1]`.

## Safety Contract

- Local only — no internet, no cloud API, no subprocess
- Never raises — all paths wrapped in try/except
- Deterministic — same inputs → same output
- Advisory only — `platform_render_strategy` is metadata, never alters render parameters
- No render mutation, no executor override, no pipeline change
- Executor authority unchanged — render pipeline never reads `platform_render_strategy`
- Backward compatible — fallback when no platform/creator_type context available

## Test Results

- Focused: **104/104** passed

---

# Phase 56 — Platform-Aware Strategy Influence

**Module:** `app/ai/knowledge/platform_strategy_influence_context.py`
**Plan field:** `platform_strategy_influence` (added to `AIEditPlan` in `edit_plan_schema.py`)
**Director hook:** `_attach_platform_strategy_influence(plan, job_id)` — after Phase 55E

## Purpose

Reads `platform_render_strategy` (Phase 55E) and builds per-domain influence support context for subtitle, camera, and ranking domains. Enriches existing influence reasoning additively (never changes bias values). Bounded confidence deltas ensure the safety gate is never affected.

## Output Model

```json
{
  "platform_strategy_influence": {
    "available": true,
    "platform": "tiktok",
    "creator_type": "podcast",
    "subtitle": {
      "supported": true,
      "bias": {"style": "viral_bold", "density": "dense", "keyword_emphasis": "high"},
      "confidence_delta": 0.04,
      "reasoning": ["Platform strategy supports dense viral_bold subtitles for tiktok podcast content"]
    },
    "camera": {
      "supported": true,
      "bias": {"motion_energy": "low_medium", "stability_priority": "high", "crop_aggressiveness": "low"},
      "confidence_delta": 0.03,
      "reasoning": ["Platform strategy supports stable podcast framing"]
    },
    "ranking": {
      "supported": true,
      "bias": {"priority": "retention_creator_fit"},
      "confidence_delta": 0.05,
      "reasoning": ["Platform strategy supports retention and creator-fit ranking for tiktok podcast content"]
    },
    "confidence": 0.8475,
    "platform_strategy_influence_reasoning": [
      "Tiktok platform guidance and podcast creator intelligence are informing safe influence.",
      "Platform strategy supports dense viral_bold subtitles for tiktok podcast content",
      "Platform strategy supports stable podcast framing"
    ]
  }
}
```

Fallback:

```json
{"platform_strategy_influence": {"available": false, "confidence": 0.0}}
```

## Confidence Delta Limits (Phase 54 contract)

| Limit | Value |
|---|---|
| Max delta per domain | 0.05 |
| Max total boost | 0.10 |
| subtitle delta | 0.04 |
| camera delta | 0.03 |
| ranking delta | 0.05 |

Confidence deltas are **advisory metadata only** — they are NEVER fed into the Phase 48 safety gate evaluation.

## Ranking Support Boundary

`ranking` domain is NOT supported when `ranking.priority` is `"balanced"` or `"unknown"` — these are neutral/default values that do not indicate a meaningful platform preference.

## Enrichment Pattern (Additive Only)

Three public enrichment helpers append platform-strategy reasons to existing influence dicts:

| Function | Target | Cap |
|---|---|---|
| `enrich_subtitle_influence_reasoning(influence_dict, platform_subtitle_support)` | `plan.creator_subtitle_influence.reasoning` | 6 total |
| `enrich_camera_influence_reasoning(influence_dict, platform_camera_support)` | `plan.creator_camera_preference.camera_preference.reasoning` | 6 total |
| `enrich_ranking_influence_reasoning(influence_dict, platform_ranking_support)` | `plan.safe_influence_pack.reasoning` or `.explainability` | 6 total |

All enrichment functions:
- Only append, never replace existing reasons
- Never modify bias values or tuning values
- Return the original dict unchanged if support is False or input is empty

## Safety Contract

- Local only — no internet, no cloud API, no subprocess
- Never raises — all paths wrapped in try/except
- Deterministic — same inputs → same output
- Advisory only — `confidence_delta` is metadata, NEVER fed to safety gate
- Safety gates (Phase 48: BLOCKED < 0.70, SOFT 0.70–0.85, STRONG > 0.85) are NEVER modified
- No render mutation, no executor override, no pipeline change
- No subtitle timing rewrite, no motion_crop rewrite, no clip boundary mutation
- Forbidden execution keys (`ffmpeg_args`, `render_command`, etc.) stripped from all output

## Test Results

- Focused: **85/85** passed

---

# Phase 57 — Platform-Aware Quality Feedback Loop

**Module:** `app/ai/knowledge/platform_quality_feedback_evaluator.py`
**Plan field:** `platform_quality_feedback` (added to `AIEditPlan` in `edit_plan_schema.py`)
**Director hook:** `_attach_platform_quality_feedback(plan, job_id)` — after Phase 56

## Purpose

Evaluates whether render outputs align with the target platform strategy and quality expectations. Produces per-domain platform fit scores (subtitle, camera, hook, strategy) and creator-facing feedback (strengths, improvement opportunities, reasoning). **Quality feedback only** — no render mutation, no rerender, no executor override.

## Output Model

```json
{
  "platform_quality_feedback": {
    "available": true,
    "platform": "tiktok",
    "creator_type": "podcast",
    "platform_fit": 85,
    "subtitle_fit": 88,
    "camera_fit": 84,
    "hook_fit": 80,
    "strategy_fit": 81,
    "overall": 85,
    "confidence": 0.8150,
    "strengths": [
      "Subtitles are compact and readable for tiktok podcast content",
      "Camera stability fits podcast-style content delivery"
    ],
    "improvement_opportunities": [
      "Opening hook could create stronger first-3-second attention for tiktok"
    ],
    "reasoning": [
      "Output aligns well with Tiktok podcast strategy while preserving creator style",
      "Subtitle quality is the strongest contributor to platform fit",
      "Platform strategy confidence is strong — guidance is highly reliable"
    ]
  }
}
```

Fallback:

```json
{
  "platform_quality_feedback": {
    "available": false,
    "platform_fit": 0, "subtitle_fit": 0, "camera_fit": 0,
    "hook_fit": 0, "strategy_fit": 0, "overall": 0,
    "confidence": 0.0, "strengths": [], "improvement_opportunities": [], "reasoning": []
  }
}
```

## Input Sources

| Field | Phase | Used for |
|---|---|---|
| `platform_render_strategy` | 55E | Platform + creator type, strategy per domain, PRS confidence |
| `platform_strategy_influence` | 56 | Per-domain support flags, PSI confidence |
| `subtitle_quality_v2` | 52A | Raw subtitle quality score (base for subtitle_fit) |
| `camera_quality_v2` | 52B | Raw camera quality score (base for camera_fit) |
| `hook_quality_v2` | 52C | Raw hook quality score (base for hook_fit) |
| `render_quality_v2` | 52D | `strategy_fit` score + evaluation confidence |
| `platform_subtitle_context` | 55B | Subtitle context confidence → platform alignment factor |
| `platform_camera_context` | 55C | Camera context confidence → platform alignment factor |
| `platform_hook_context` | 55D | Hook context confidence → platform alignment factor |

## Scoring Weights

| Dimension | Weight |
|---|---|
| `subtitle_fit` | 0.25 |
| `camera_fit` | 0.25 |
| `hook_fit` | 0.25 |
| `strategy_fit` | 0.15 |
| `platform_context_confidence` | 0.10 |

All scores clamped `[0, 100]`. Overall confidence clamped `[0.0, 1.0]`.

## Per-Domain Fit Scoring

### Subtitle Fit

1. Base = `subtitle_quality_v2.overall`
2. If `platform_subtitle_context.available`: blend `0.70 × raw + 0.30 × (context_confidence × 100)`
3. If `platform_strategy_influence.subtitle.supported`: add 3-point bonus (capped at 100)
4. Without context: fit = raw quality

### Camera Fit

1. Base = `camera_quality_v2.overall`
2. If `platform_camera_context.available`: blend `0.70 × raw + 0.30 × (context_confidence × 100)`
3. If `platform_strategy_influence.camera.supported`: add 3-point bonus (capped at 100)
4. Without context: fit = raw quality

### Hook Fit

1. Base = `hook_quality_v2.overall`
2. If `platform_hook_context.available`: blend `0.70 × raw + 0.30 × (context_confidence × 100)`
3. Without context: fit = raw quality

### Strategy Fit

1. If `render_quality_v2.strategy_fit > 0`: blend `0.60 × rqv2_strategy + 0.40 × (prs_confidence × 100)`
2. If `platform_strategy_influence.available`: add 5-point bonus (capped at 100)
3. If no rqv2 strategy score: `prs_confidence × 75`

### Platform Context Confidence Score (used in weighted overall)

`0.70 × (prs_confidence × 100) + 0.30 × (psi_confidence × 100)` when PSI is available; otherwise `prs_confidence × 100`.

### Confidence (output field)

`(platform_render_strategy.confidence + render_quality_v2.confidence) / 2`, clamped `[0.0, 1.0]`.

## Feedback Text Generation

| Output | Threshold | Cap |
|---|---|---|
| `strengths` | score ≥ 75 | max 3 items |
| `improvement_opportunities` | score < 65 | max 3 items |
| `reasoning` | always | max 3 items |

All feedback text:
- Creator-facing natural language only
- No raw JSON, no internal file paths, no stack traces
- No low-level implementation details
- Platform and creator type incorporated in language when available

**Strength categories**: subtitle quality (readability/clarity by creator type), camera quality (stability for trust creators, energy for high-energy platforms), hook quality (retention for short-form platforms, trust for podcast/talking head), strategy alignment.

**Improvement categories**: hook first-3-second attention (highest priority for retention platforms), subtitle platform alignment, camera stability/alignment, strategy alignment.

## Safety Contract

- Local only — no internet, no cloud API, no subprocess
- Never raises — try/except wraps entire evaluation
- Deterministic — same inputs → same output
- **Quality feedback only**: no render mutation, no rerender trigger, no executor override
- No subtitle timing rewrite, no motion_crop rewrite, no clip boundary mutation
- No transcript rewrite, no hook text rewrite, no FFmpeg mutation
- No autonomous execution, no render pipeline change
- Executor authority unchanged — render pipeline never reads `platform_quality_feedback`
- Forbidden execution keys (`ffmpeg_args`, `render_command`, `subtitle_timing`, `motion_crop`, etc.) never appear in output
- Backward compatible — Phase 56 and all prior phase fields unchanged

## Test Results

- Focused: **76/76** passed
- Full regression: **4640/4640** passed (0 regressions)

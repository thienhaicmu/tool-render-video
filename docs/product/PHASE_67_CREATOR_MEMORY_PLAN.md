# PHASE 67 — CREATOR MEMORY PLAN
## Light Personalization: Learn From Behavior, Never From Configuration

**Branch:** `feature/ai-output-upgrade`
**Prerequisite:** Phase 66 Explainability — COMPLETE, zero regressions
**Plan date:** 2026-05-19
**Planning only — no implementation in this session**

---

## 1. EXECUTIVE SUMMARY

The creator experience problem in Phase 67 is not that the tool lacks memory. **Nine distinct memory systems already exist.** The problem is that they operate invisibly and incompletely, producing the feeling that the tool is guessing randomly — even when it isn't.

**What already works (and creators don't know about):**
- Keep/Avoid clips → directly promoted/excluded in every rerender (strongest signal)
- Subtitle style learning → auto-sets the subtitle selector after session 3
- Platform learning → auto-sets the platform after session 3
- Creator DNA → applies a +3 hook-sort bonus after 10+ actions
- Series fingerprint → detects consistent preset/platform/style patterns

**What doesn't exist yet:**
1. A visible surface telling creators what has been learned
2. Clip duration preference derived from Keep/Avoid behavior
3. Clarity about which memory signals are active during rerender

**Root cause of "feels random":** The tool is actually learning. Creators just can't see it. Phase 67 is not about adding new memory — it is about closing that visibility gap and adding one missing behavioral signal (clip duration preference).

**Phase 67 implementation: 3 commits, 2 files.**

No new backend systems. No new AI. No LLM. No embeddings. Only: surface what's already learned, fill one real gap.

---

## 2. EXISTING CREATOR SIGNALS AUDIT

### Complete inventory of all 9 active memory systems

#### System 1: Clip Steering (Keep / Avoid / Rerender)
**File:** `backend/static/js/clip-steering.js`

| Property | Detail |
|---|---|
| Signal type | Explicit creator intent — strongest possible signal |
| Storage | localStorage `clip_steering_v1`, 72h TTL, max 10 per category |
| Data per entry | `start_sec`, `end_sec`, `label`, `ts` |
| Backend use | `clip_lock` → segments in timestamp range promoted to pool front; `clip_exclude` → segments filtered before scoring |
| Render pipeline | Applied at `render_pipeline.py` lines 2321–2399, before final sort |
| Cross-session | YES (72h) |
| Backend sync | YES — sent in every render payload |
| Creator awareness | PARTIAL — Keep/Avoid/Rerender buttons are visible; effect on next render is not explained |

**What's missing:** The duration characteristics of Kept vs Avoided clips are never computed. If a creator consistently Keeps 60–90s clips and Avoids 120s+ clips, that duration preference is not extracted.

---

#### System 2: Creator Taste (Subtitle Style)
**File:** `backend/static/js/creator-taste.js`

| Property | Detail |
|---|---|
| Signal source | Subtitle style in render payload each session |
| Storage | localStorage `ct_taste_v1` |
| Learning model | EMA α=0.85, confidence gates: MIN_SESS=3, MIN_SCORE=1.5, PREF_RATIO=1.5 |
| What's tracked | Per-style EMA score; download rank (rank_1 vs rank_other) |
| UI output | `#ctSubtitleHint`: "Using Clean (recent preference)" inline next to subtitle selector; auto-sets selector when confident |
| Manual override | `sel.dataset.ctManual = '1'` — silences hint when creator manually changes |
| Cross-session | YES |
| Backend sync | NO — localStorage only |

**Status: Works well.** Visual hint exists. Auto-sets correctly. Manual override respected.

---

#### System 3: Creator Feedback (Platform + Variant)
**File:** `backend/static/js/creator-feedback.js`

| Property | Detail |
|---|---|
| Signal source | Platform choice per render; variant type downloaded |
| Storage | localStorage `cl_feedback_v1` |
| Learning model | EMA α=0.85, same confidence gates as Creator Taste |
| What's tracked | Platform EMA per value (tiktok/youtube_shorts/instagram_reels); variant EMA per type |
| UI output | `#cfPlatformHint`: "Using TikTok (recent preference)" inline; auto-sets platform selector |
| Manual override | `sel.dataset.cfManual = '1'` |
| Cross-session | YES |
| Backend sync | NO — localStorage only |

**Status: Works.** Note: Phase 65 added platform → aspect ratio auto-link. When CreatorFeedback auto-sets platform, Phase 65 will also auto-update aspect ratio. These work together correctly.

---

#### System 4: Creator Memory (AI Suggestion Accept/Reject)
**File:** `backend/static/js/creator-memory.js`

| Property | Detail |
|---|---|
| Signal source | Accept/reject of AI suggestions in editor panel (strongerHook, fasterPacing, viralMode, cinematicMode, subtitleCleanup, smartClipPrioritization, removeDeadSpace) |
| Storage | localStorage + backend SQLite (`creator_prefs` table, `PUT /api/creator/preferences`) |
| Learning model | Accept/reject counts per action; aggressiveness score 0–1 |
| Derived taste model | pace (fast/balanced/cinematic), hook (aggressive/moderate/soft), editStyle (viral/cinematic/educational/balanced) |
| Min signals | 5 for basic confidence; 8 for taste model |
| UI output | Personalized confidence text on AI suggestions: "Based on your history, you tend to keep this." / "You've passed on this before." |
| Inspector panel | Existing (not Phase 67 scope — already in advanced UI) |
| Cross-session | YES |
| Backend sync | YES, every 2s debounced |

**Status: Works for AI editor actions.** Not surfaced in the main render flow.

---

#### System 5: Creator DNA
**File:** `backend/static/js/creator-dna.js`

| Property | Detail |
|---|---|
| Signal source | Variant downloads + platform choices (aggregated from CreatorFeedback + CreatorTaste) |
| Storage | localStorage `creator_dna_v1` snapshot |
| Dimensions | hook_forward (0/0.5/1.0), clean_visual (0–1), narrative_structure (0/1) |
| Confidence gates | 10+ total actions (15+ for hook_forward) |
| Backend use | Sent as `creator_dna` in render payload → backend applies `_dna_hook_bonus=3` to hook sort |
| UI output | `#cpDnaHint`: "Using recent creator style" shown as chip in pre-render area when confident |
| Cross-session | YES |
| Backend sync | YES — render payload |

**Status: Works.** The +3 hook-sort bonus is small but real. The "Using recent creator style" chip appears in the pre-render area when DNA is confident.

---

#### System 6: Creator Series
**File:** `backend/static/js/creator-series.js`

| Property | Detail |
|---|---|
| Signal source | All render payloads — tracks preset_id, platform, subtitle_style, logo, structure_bias |
| Storage | localStorage `creator_series_v1`, 50-render sliding window, 30-day TTL |
| Learning model | EMA α=0.82, min 3 renders for detection, DETECT_GATE=0.35, CHIP_GATE=0.55 |
| Derived fingerprint | series_detected (bool), title_prefix, dominant preset/platform/style |
| UI output | `#cpSeriesHint`: "Series" chip with tooltip in pre-render area when confidence ≥ 0.55 |
| Cross-session | YES |
| Backend sync | YES — render payload |

**Status: Works.** The series chip appears for consistent creators. Useful for series production.

---

#### System 7: Creator Presets (Explicit Configuration)
**File:** `backend/static/js/creator-presets.js`

| Property | Detail |
|---|---|
| Signal source | Manual preset save by creator |
| Storage | localStorage `creator_presets_v1` |
| Fields saved per preset | target_platform, multi_variant, subtitle_style, cta_enabled, cta_type, render_profile, add_subtitle, reframe_strategy |
| Events logged | preset_applied, preset_saved, preset_modified |
| Cross-session | YES |
| Backend sync | NO — localStorage only |

**Note:** This is explicit configuration (creator saves manually), not behavioral learning. It is a reference point for memory systems but is not itself a memory signal.

---

#### System 8: Adaptive Memory (Backend)
**File:** `backend/app/ai/adaptive/adaptive_memory.py`

| Property | Detail |
|---|---|
| Signal source | Backend render pipeline — style choices inferred from render payload |
| Storage | `data/adaptive/creator_profiles/default.json` |
| Fields | creator_style_preference, preferred_subtitle_style, preferred_pacing_style, preferred_camera_style, preferred_duration_range, preferred_variant_strategy |
| Confidence model | +0.08 per signal per dimension, max 1.0 |
| Cross-session | YES |
| Backend sync | Local filesystem only |
| Creator visibility | NONE — completely invisible to creator |

**Gap: Creator has no idea this profile exists.** The adaptive profile influences backend AI Director decisions silently.

---

#### System 9: Feedback Learning (Backend)
**File:** `backend/app/ai/feedback/feedback_learning.py`

| Property | Detail |
|---|---|
| Signal source | Every render completion: creator_style, subtitle_style, pacing_style, camera_style, duration_bucket, export/ignore rank |
| Storage | `data/feedback/render_feedback/feedback_memory.json`, max 200 signals |
| Pattern counts | dominant_creator_style, dominant_subtitle_style, dominant_pacing_style, duration_bucket |
| Biases produced | output_ranking_bias (max 0.20), variant_ranking_bias (max 0.15), subtitle/pacing/camera_weighting_bias (max 0.25×scale), retrieval_weighting_bias (max 0.20) |
| Assistive-only | YES — `assistive_only: True` in bias dict |
| Creator visibility | NONE — completely invisible to creator |

**Gap: Creator cannot see what patterns are driving ranking biases.** Combined with Phase 66 explaining signal scores, this creates a partial picture — the scores are explained but the personalisation layer is invisible.

---

## 3. STRONG VS WEAK SIGNALS MATRIX

### Signal strength definition
A **strong signal** is one where creator behavior directly and unambiguously expresses intent. A **weak signal** is one where behavior is indirect, ambiguous, or too infrequent to be reliable alone.

| Signal | Type | Strength | Why |
|---|---|---|---|
| Clip Lock (Keep) | Explicit behavior | **STRONG** | Creator explicitly says "I want this clip" — unambiguous intent |
| Clip Exclude (Avoid) | Explicit behavior | **STRONG** | Creator explicitly says "not this clip" — unambiguous rejection |
| Rerender (after avoid) | Explicit behavior | **STRONG** | Directly reveals dissatisfaction with current selection |
| Subtitle style selection (per render) | Implicit behavior | **MEDIUM** | Consistent across sessions → reliable preference; can vary |
| Platform selection (per render) | Implicit behavior | **MEDIUM** | Usually consistent for a channel; can change per content type |
| Download rank (rank 1 vs alternative) | Implicit behavior | **MEDIUM** | Choosing alternative clip reveals ranking disagreement |
| Variant download (aggressive vs balanced) | Implicit behavior | **MEDIUM** | Download = kept; indirect preference signal |
| AI suggestion accept/reject | Explicit behavior | **MEDIUM** | Direct signal on taste dimension; only in AI editor mode |
| Preset switching frequency | Implicit behavior | **WEAK** | Switching could mean experimentation, not preference |
| Session count | Count only | **WEAK** | Quantity, not quality signal |
| Render profile selection | Implicit behavior | **WEAK** | Often set-and-forget; not a taste signal |

### What's currently missing as a signal

| Missing signal | Why it matters | Where it could be captured |
|---|---|---|
| **Clip duration of Kept clips** | If creator consistently Keeps 60–90s clips and Avoids 120s+ clips, that's a clear clip length preference | Compute `avg(lock_duration)` and `avg(exclude_duration)` from ClipSteering's stored ranges |
| **Score characteristics of Kept clips** | If creator keeps clips with high Hook scores, that reveals hook-forward taste | Phase 66 `ranking_components` are now in DOM — could read from card data |
| **Repeated rerender count** | Multiple rerenders on same upload = strong dissatisfaction signal | Not currently tracked |
| **Preferred hook score threshold** | Implicit in which clips creator Keeps vs Avoids | Derivable from ClipSteering + Phase 66 rankingComponents if co-located |

**Phase 67 focuses on the clip duration signal only** — the most derivable from existing data with no new infrastructure.

---

## 4. MEMORY MODEL

### What should be remembered — per dimension

#### Dimension 1: Clip duration preference (NEW in Phase 67)

**Source:** ClipSteering locked/excluded clip timestamps  
**Signal:** `avg_duration = avg(end_sec - start_sec)` for locked clips over last 72h  
**Derived preference:** If `avg_duration < 70s` → suggests shorter clips; if `avg_duration > 120s` → suggests longer clips  
**Use:** Soft suggestion to adjust `evMinPart` / `evMaxPart` sliders toward observed preference  
**Storage:** Computed on-the-fly from existing ClipSteering localStorage — **no new storage needed**  
**Auto-apply:** NO — suggestion only. Creator sees "You've been keeping 60–80s clips. Adjust range?" with one-click button.

#### Dimension 2: Subtitle style preference (ALREADY EXISTS)

**Source:** `creator-taste.js` → `ct_taste_v1`  
**Signal:** EMA-weighted subtitle style frequency  
**Derived preference:** Top style when sessions ≥ 3  
**Use:** Auto-sets subtitle selector (already does this); shows inline hint  
**Status:** Working. Phase 67 does not change this — only surfaces it in the summary.

#### Dimension 3: Platform preference (ALREADY EXISTS)

**Source:** `creator-feedback.js` → `cl_feedback_v1`  
**Signal:** EMA-weighted platform frequency  
**Derived preference:** Top platform when sessions ≥ 3  
**Use:** Auto-sets platform selector (already does this); shows inline hint  
**Status:** Working. Phase 67 does not change this — only surfaces it in the summary.

#### Dimension 4: Pacing / hook aggressiveness (ALREADY EXISTS)

**Source:** `creator-memory.js` → `cm_prefs_v1` + backend SQLite  
**Signal:** Accept/reject of fasterPacing, strongerHook, viralMode, cinematicMode  
**Derived preference:** taste model → pace (fast/balanced/cinematic), hook (aggressive/moderate/soft)  
**Use:** Personalizes AI suggestion confidence text  
**Status:** Working for AI editor mode. Phase 67 surfaces this in the memory summary.

#### Dimension 5: Variant preference (ALREADY EXISTS)

**Source:** `creator-feedback.js` variant tracking  
**Signal:** EMA-weighted variant download frequency  
**Derived preference:** Most-downloaded variant type  
**Use:** Not currently surfaced to creator (variant hint exists in code but may not display)  
**Phase 67:** Surface in memory summary.

### What should NOT be remembered

| Candidate | Why NOT |
|---|---|
| Exact clip timestamps across upload sessions | Different uploads have different content — timestamp preference from session A doesn't transfer to session B |
| Preferred music type | Too few signals, too subjective |
| Preferred intro/outro | Explicit asset choice — not behavioral learning |
| Render profile (Fast Draft / Balanced / Quality) | Creator sets this explicitly per render; not a taste signal |
| Max clips count | Pure content decision per upload — not learnable |
| CTA text | Content-specific, not style preference |

---

## 5. THRESHOLD RULES

### When to trust a signal

The existing systems use consistent confidence gates. Phase 67 follows the same pattern.

| Dimension | Minimum signals | Confidence threshold | EMA decay (α) | Forget rate |
|---|---|---|---|---|
| Subtitle style | 3 sessions | EMA score ≥ 1.5, ratio ≥ 1.5× | 0.85 | ~15 sessions |
| Platform preference | 3 sessions | EMA score ≥ 1.5, ratio ≥ 1.5× | 0.85 | ~15 sessions |
| Variant preference | Session-independent | EMA score ≥ 1.5, ratio ≥ 1.5× | 0.85 | ~15 sessions |
| Creator DNA | 10+ actions (15+ for hook) | Dimension score ≥ threshold | N/A (sliding window) | 10 actions |
| Clip duration preference (NEW) | 2+ lock entries in window | avg_duration defined on ≥ 2 clips | N/A (raw average) | 72h (ClipSteering TTL) |
| Taste model (pace/hook) | 8 signals | `confident = total >= MIN_TASTE_SIG` | N/A (cumulative) | Never (manual reset only) |

### The "1 Keep ≠ enough" rule

Clip duration preference requires **at least 2 locked clips** in the current 72h window to compute a hint. One Kept clip could be coincidental. Two or more with similar duration indicates a pattern worth surfacing.

The **direction** of the hint:
- `avg_lock_duration < 70s` → "You've been keeping short clips (avg ~Xs). Want to try min=45s max=90s?"
- `avg_lock_duration > 120s` → "You've been keeping longer clips (avg ~Xs). Want to try min=90s max=180s?"
- Duration within 70–120s → no hint (within default range, no nudge needed)

### When to withdraw a hint

| Condition | Action |
|---|---|
| Creator manually adjusts the related field | Withdraw the hint immediately (same `dataset.manual` pattern as existing systems) |
| Session ends and a new upload begins | Clear duration hint (new upload = fresh context) |
| Creator resets preferences | Clear all hints |

---

## 6. SUGGESTION MODEL

### How memory influences the product — three modes

Phase 67 uses mode 2 only (suggestion). Mode 1 (auto-apply) already exists in systems 2 and 3. Mode 3 (silent bias) already exists in systems 8 and 9.

| Mode | Description | Currently used by |
|---|---|---|
| **Mode 1: Auto-apply** | Silently pre-set a control to the learned value | CreatorTaste (subtitle), CreatorFeedback (platform) |
| **Mode 2: Visible suggestion** | Show a hint the creator can accept or dismiss | Phase 67 — clip duration hint, memory summary |
| **Mode 3: Silent bias** | Adjust ranking weights by a small factor | FeedbackLearning, AdaptiveMemory, CreatorDNA |

### Suggestion 1: Clip duration hint (NEW)

**Trigger:** ClipSteering has ≥ 2 locked clips AND avg_duration is outside 70–120s range  
**Location:** Inline in the Advanced fold, near `evMinPart`/`evMaxPart` sliders  
**Format:** `"Keeping ~Xs clips lately. [Apply Xs–Xs range]"` — single-click button  
**On click:** Sets `evMinPart` and `evMaxPart` to the suggested range  
**Dismiss:** Clicking the "×" closes the hint for this session  
**Auto-apply:** NO — always a visible, clickable suggestion  
**Trust principle:** Creator decides. Never silently changes clip length bounds.

### Suggestion 2: Memory summary chip (NEW)

**Trigger:** At least one preference dimension is confident  
**Location:** Pre-render area (same row as existing "DNA active" and "Series" chips)  
**Format:** A compact chip row: `[🧠 Platform: TikTok] [Style: Clean] [Pace: Fast]` — styled as `v3Chip`  
**On click:** Expands to show all active preferences (tooltip or small panel)  
**Auto-apply:** NO — this is purely informational  
**Trust principle:** Tells the creator what's been learned without doing anything.

### Suggestion 3: Rerender memory banner (NEW)

**Trigger:** Creator clicks "Rerender" button on a clip card  
**Location:** Small banner above the new render's clip list, visible for 5 seconds or until first clip appears  
**Format:** `"Memory active: keeping clip 23–89s · excluding 0–45s"`  
**Auto-apply:** N/A — memory is already active (ClipSteering); this just makes it visible  
**Trust principle:** Explains what the engine will do differently in this rerender.

---

## 7. TRUST AND PRIVACY RULES

### Hard limits — things memory must NEVER do

| Rule | Rationale |
|---|---|
| Never auto-apply clip duration changes | Clip bounds affect content selection; wrong guess = wrong output = trust loss |
| Never persist clip timestamp locks beyond their 72h TTL | Timestamps are content-specific; a locked segment from upload A doesn't mean the same timestamp in upload B |
| Never let memory override explicit creator choice in the same session | If creator manually sets min=30s this session, memory hint is suppressed |
| Never show fabricated preferences ("You seem to prefer dramatic hooks") | Only show when a real confidence gate has been met |
| Never surface the memory profile in a surveillance-feeling way | Show preferences, not history ("You prefer TikTok" not "You chose TikTok 7 times this week") |
| Never make memory permanent by default | Provide visible "Reset preferences" option |
| Never infer personal characteristics | Only infer editing style preferences, never personality or demographics |

### Reversibility requirements

Every memory influence must be reversible:

| Influence | How creator reverses it |
|---|---|
| Platform auto-set by CreatorFeedback | Manually change platform pill → auto-set suppressed for this session |
| Subtitle auto-set by CreatorTaste | Manually change subtitle selector → auto-set suppressed for this session |
| Clip duration suggestion | Click dismiss → gone for this session |
| Memory summary chip | Clicking does not apply anything; there is nothing to reverse |
| Rerender banner | Read-only — no reversal needed |
| Backend biases (FeedbackLearning) | Handled by "Reset" button in Creator Memory inspector |

### Privacy posture

| Question | Answer |
|---|---|
| Is any data sent to a remote server? | Only CreatorMemory is synced to backend SQLite (PUT /api/creator/preferences). All other systems are localStorage only. |
| Is any data shared across users? | NO — all profiles are single-user local |
| Is behavior tracked at a per-clip level? | Only clip timestamps in ClipSteering (72h TTL). No per-upload cross-reference. |
| Can creator see everything being stored? | After Phase 67: yes — the memory summary chip surfaces the derived preferences. Raw storage (EMA scores) is not shown. |
| Can creator delete everything? | YES — CreatorMemory has `reset()`. Other systems have `reset()` equivalents. Phase 67 does not add new storage. |

---

## 8. UI RECOMMENDATION

### 8A. Memory summary chip row

The existing `cpDnaHint` and `cpSeriesHint` span elements in `editor-view.js` build a chip row in the pre-render area. Phase 67 adds a `cpMemoryHint` chip that reads across all confident preference dimensions.

**Current chip row (pre-render area):**
```
[DNA active: Using recent creator style] [Series]
```

**After Phase 67:**
```
[TikTok] [Clean style] [Fast pace] [DNA active] [Series]
```

Each chip:
- Labeled with the dimension value (not the source system)
- Tooltip explains the source: "Based on your last 5 renders"
- Clicking shows the full preferences summary in a small panel
- CSS class: `v3Chip v3ChipMemory` — visually consistent with existing chips

**Gate:** Only shown when at least 2 dimensions are confident. One chip alone doesn't warrant a new UI element (the existing DNA/Series chips cover that case).

### 8B. Clip duration hint placement

In the Advanced fold (`qsAdvBody`), below the Min/Max clip length inputs:

```
[Min clip: 70s ▼] [Max clip: 180s ▼]
ℹ Keeping ~65s clips lately. [Apply 45–90s range] [×]
```

The hint line:
- Font size 11px, muted color — same as existing `inspHint` class
- `[Apply Xs–Xs range]` button: sets sliders and dismisses the hint
- `[×]` dismisses without applying
- Never shown if creator has manually adjusted min/max this session

### 8C. Rerender memory banner

**Location:** Temporarily shown above the clip list when a rerender is triggered from a clip card  
**Trigger:** Attached to the "Rerender" button click event (`csKeepAndRerender`)  
**Format:**

```
🔒 Keeping 23–89s (Clip 2)   ✗ Excluding 0–45s (Clip 1)   Memory active
```

**Duration:** Shown for 4 seconds or until the first rerendered clip appears, whichever comes first  
**CSS:** Banner inline, same subtle styling as `clipRecoveredNote` — not alarming, just informative

### 8D. What NOT to add

| Rejected idea | Why |
|---|---|
| "My style profile" settings page | Phase 67 is light — a settings page is a feature, not a nudge |
| Persistent memory icon in the UI | Creates expectation of a feature that's still minimal |
| Explicit "enable/disable memory" toggle | Memory is already on; the disable path is "Reset preferences" (already exists) |
| Memory influence on subtitle style shown in clip card | The clip card already has the explainability layer (Phase 66); adding memory attribution would be additive complexity |
| Memory bar / score history | Feels surveillance-like; contrary to the trust rules |

---

## 9. SAFE ROLLOUT PLAN

### Before Commit 67.1

Verify clip duration data is accessible:
- `ClipSteering.getClipLock()` returns an array of `{ start_sec, end_sec, label, ts }` objects
- Confirm at least one entry exists after using Keep button

### Commit 67.1: `memory(67.1): clip duration preference hint`

**Files:** `backend/static/js/clip-steering.js`, `backend/static/js/editor-view.js`  
**Change 1 (clip-steering.js):** Add `getDurationHint()` — reads locked entries, computes average duration, returns hint object or null  
**Change 2 (editor-view.js):** Show hint below min/max sliders in Advanced fold  

Validation checklist:
- [ ] `getDurationHint()` returns `null` when < 2 lock entries
- [ ] Hint text is correct format: "Keeping ~Xs clips lately. Apply Xs–Xs range"
- [ ] [Apply] button sets `evMinPart` and `evMaxPart` and dismisses hint
- [ ] [×] dismisses without changing values
- [ ] Manual slider adjustment clears the hint for this session
- [ ] Hint not shown when avg_duration is 70–120s (default range — no nudge)
- [ ] No hint for Avoid-only sessions (only locked clips count)
- [ ] No regression in ClipSteering's existing `getPayload()` or `lockClip()`/`excludeClip()`

Stop if: `evMinPart`/`evMaxPart` selects have different value formats than expected (numeric seconds).

---

### Commit 67.2: `memory(67.2): preferences summary chip`

**File:** `backend/static/js/editor-view.js`  
**Change:** Add `_buildMemoryChip()` function; render as `cpMemoryHint` chip in pre-render chip row

Validation checklist:
- [ ] Chip appears only when ≥ 2 preference dimensions are confident
- [ ] Shows correct labels: platform name, subtitle style name, pace (from getTasteModel)
- [ ] No chip when only 1 dimension is confident (defer to existing DNA/Series chips)
- [ ] Chip is removed if preferences reset
- [ ] Tooltip shows "Based on your recent renders" — not specific counts
- [ ] Existing `cpDnaHint` and `cpSeriesHint` chips unaffected
- [ ] No JS error when CreatorTaste, CreatorFeedback, or CreatorMemory is not yet initialized

---

### Commit 67.3: `memory(67.3): rerender memory banner`

**File:** `backend/static/js/render-ui.js`  
**Change:** In `csKeepAndRerender()`, inject a temporary memory-active banner before triggering rerender

Validation checklist:
- [ ] Banner appears when "Rerender" is clicked from a clip card
- [ ] Banner correctly names the Kept clip time range and the Excluded ranges
- [ ] Banner auto-dismisses after 4 seconds OR when first rerendered clip card appears
- [ ] Banner does not appear when no ClipSteering entries are active
- [ ] No regression in the rerender flow itself (`csKeepAndRerender` still calls `startRender` correctly)
- [ ] No banner when ClipSteering entries are empty

---

## 10. COMMIT PLAN

| # | Commit message | Files | Change description | Lines |
|---|---|---|---|---|
| 1 | `memory(67.1): clip duration preference hint` | `clip-steering.js`, `editor-view.js` | Add `getDurationHint()` to ClipSteering; show inline hint below min/max sliders | ~25 lines |
| 2 | `memory(67.2): preferences summary chip` | `editor-view.js` | Add `_buildMemoryChip()` reading Taste/Feedback/Memory; render as pre-render chip | ~20 lines |
| 3 | `memory(67.3): rerender memory banner` | `render-ui.js` | Inject temporary banner on rerender showing active clip steering entries | ~15 lines |

**Total: 3 commits, 3 files, ~60 lines. Zero new backend systems. Zero new localStorage keys.**

---

## 11. DEFINITION OF DONE

Phase 67 is complete when:

- [ ] `ClipSteering.getDurationHint()` returns a correct suggestion when ≥ 2 locked clips with consistent duration exist
- [ ] Duration hint appears below min/max clip sliders in Advanced fold
- [ ] Clicking "Apply" correctly updates `evMinPart` / `evMaxPart`
- [ ] Duration hint is absent when < 2 lock entries exist or avg is within 70–120s
- [ ] Memory summary chip appears in pre-render area when ≥ 2 dimensions are confident
- [ ] Chip shows correct labels for platform, subtitle style, and pace preference
- [ ] Rerender banner appears briefly after "Rerender" is clicked and names the active clip ranges
- [ ] All hints are dismissible and respect manual overrides
- [ ] No auto-apply of any new memory signals — suggestions only
- [ ] Zero regressions in ClipSteering, Creator Taste, Creator Feedback, DNA, Series
- [ ] No new backend storage, no new API endpoints, no new localStorage keys

### Creator experience after Phase 67

Creator renders, gets clips, avoids a long one, keeps two short ones, rerenders:

```
[TikTok] [Clean style] [DNA active]    ← memory summary chip

Rerender triggered...
🔒 Keeping 45–85s (Clip 2, Clip 3)  ✗ Excluding 110–160s (Clip 1)

Clips appear...

--- Advanced fold ---
Min clip: 70s   Max clip: 180s
ℹ Keeping ~65s clips lately. [Apply 45–90s range] [×]
```

Creator now sees: the tool noticed a pattern, shows what memory is active during rerender, offers a concrete suggestion. They can accept the range suggestion or dismiss it. Nothing is forced. Everything is explained.

Creator no longer asks: "Why does the tool keep giving me edits I don't like?"

---

## What Phase 67 does NOT change

| Item | Status |
|---|---|
| Clip ranking algorithm | Unchanged |
| Clip selection engine | Unchanged |
| CreatorTaste auto-set behavior (subtitle) | Unchanged |
| CreatorFeedback auto-set behavior (platform) | Unchanged |
| ClipSteering lock/exclude backend behavior | Unchanged |
| CreatorDNA, CreatorSeries existing chips | Unchanged |
| FeedbackLearning backend biases | Unchanged |
| Any Phase 63–66 wins | Unchanged |

## What Phase 67 defers

| Item | Why deferred |
|---|---|
| Clip score preference from Keep/Avoid (Hook-heavy vs speech-heavy) | Requires reading Phase 66 rankingComponents from clip card DOM at Keep-time — architectural dependency |
| Long-term duration preference across uploads | ClipSteering timestamps are content-specific; cross-upload duration memory needs upload fingerprinting |
| Creator memory settings page ("Reset all") | Exists in creator-memory.js already; Phase 67 does not redesign UI |
| Feedback Learning visibility (backend pattern summary) | Backend-side; requires new API endpoint — Phase 68 candidate |
| Memory confidence decay / forgetting UI | "Learned X sessions ago" metadata — Phase 68 candidate |

---

*Phase 67 plan based on live code audit of clip-steering.js, creator-taste.js, creator-feedback.js, creator-memory.js, creator-dna.js, creator-series.js, adaptive_memory.py, feedback_learning.py, render_pipeline.py, editor-view.js.*  
*Branch: `feature/ai-output-upgrade` · Plan date: 2026-05-19*

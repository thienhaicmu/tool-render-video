# Story Mode AI — Super-Prompt & Length Backlog

> Living backlog for the Story Mode "brain" (the super-prompt that generates the
> StoryPlan). Created 2026-07-13 after the deep AI audit + super-prompt review.
> **Status: work-in-progress — the idea-mode LENGTH approach is NOT finalised.**

---

## 1. What shipped (committed, green)

### The 3 specialised super-prompts (s14) — DONE
One generic prompt used to serve every use-case, blurring the AI's role. Split into
three role-specialised builders in `story_prompts_v2.py`, selected by `(source,
has_base_video)` in `story_director_v2.run_super_plan`:

| Prompt | Trigger | Role |
|--------|---------|------|
| **P1** `build_super_story_prompt` | paste, no video | Adapt an EXISTING story → SVG (faithful) |
| **P2** `build_super_video_prompt` | paste, base video | Narrate + overlay characters OVER a base video (no scene design; `source_audio` focus) |
| **P3** `build_super_idea_prompt` | idea | Screenwriter: WRITE a story of a target length, then storyboard |

- Full StoryPlan schema kept in all three (per product decision — the fields help the
  model understand its role; do NOT strip them).
- Wiring: `has_base_video`/`base_video_dur` threaded through
  `generate_story_plan_v2 → run_super_plan`; `story_pipeline_v2` passes the real base
  video presence (render path); `/api/story/plan` gained `use_video` (Review can opt
  into P2 when the FE supports it — base-video feature not yet merged).

### Earlier length/quality fixes (committed)
- Bug "3-min idea → 29s cụt ngủn": `cap_visuals` REMAPS beats instead of deleting them
  (never truncates the story); idea length enforcement.
- P-A SVG cleanup (dropped dead image-gen fields); P-B reuse example + visual target;
  P-C per-beat budget.

---

## 2. The idea-mode LENGTH problem (OPEN)

**Symptom:** user asks for a 3-min (180s) video from a thin idea → AI writes ~49s.

**Root causes found (all real prompt bugs, not "LLM limitation"):**
1. Conflicting dai/ngan signals ("fill 180s" vs "COMPLETE story / no filler / short
   sentences"). 2. Per-beat budget said "short sentences" → thin beats. 3. Length was
   an abstract number, not a fillable structure.

**Levers added to P3 (measured on gpt-4o, idea "Nữ tổng tài", 180s target):**

| Version | Lever | est_sec | % of 180s | avg chars/beat |
|---------|-------|--------:|----------:|---------------:|
| s9 (original) | — | 49 | 27% | 55 (thin) |
| s14 | 3-prompt + length brief | 69.5 | 39% | — |
| s15 | RICH beats (~10s / full paragraph) | 102 | 57% | 139 ✅ |
| s16 | five-act beat quota | 76 | 42% | 127 |
| **s17 ×1.8** | **length compensation factor** | **131–138** | **73–77%** | 123–160 ✅ |
| s17 ×2.4 | over-compensation | 91–113 | 51–63% | — |

**Findings:**
- Better prompts help a LOT: 49s → ~135s (×2.75). The thin-scene problem is FIXED
  (beats 55 → 130–160 chars).
- There is a practical CEILING (~135s ≈ 75%) for a THIN idea in ONE call. Pushing the
  compensation past ~1.8× BACKFIRES (the model gives up on an unrealistic target).
- `STORY_IDEA_LENGTH_FACTOR` (default **1.8**) tunes the compensation.
- UX note: the FE shortfall banner (F-UX2) only fires at >30% drift; 135s is 25% under
  → within tolerance, no banner.
- Measurement caveat: **n=1 per config is noisy** (s15 102s vs s16 76s is likely
  variance). Real tuning needs n≥3 per config.

---

## 3. OPEN DECISIONS (need product sign-off)

- [ ] **Compensation factor value.** Default is 1.8 (~135s, best measured, stable). Is
      ~75% + no-banner acceptable, or push differently? (Higher backfires.)
- [ ] **Thin-idea policy.** A 1-line idea genuinely lacks 3 min of plot. Options:
      (a) accept ~135s, (b) prompt the user to enrich the idea, (c) allow ONE optional
      expansion call (rejected so far — "1 call only"), (d) banner for the gap.
- [ ] Whether the compensation heuristic is desirable at all, or revert to s15/s16
      (~100s, no "aim-high").

---

## 4. TODO (not started)

- [ ] Re-measure each config with **n≥3** (cache-cleared) to separate signal from
      noise before locking the factor. Extend `ai_eval/ab_story_plan.py` to cover
      idea mode + duration (currently paste-only).
- [ ] **P-D** — split temperature per mode (P1 adapt ~0.3 fidelity / P3 idea ~0.5
      creative); currently all 0.4.
- [ ] **P-E** — expand `emotion`/`pose` vocab (only if `svg_char` supports more).
- [ ] **P2 in Review** — wire the FE to send `use_video` (blocked on the base-video
      feature merging; backend already supports it).
- [ ] Confirm richer per-beat narration doesn't hurt TTS pacing / one-image-hold feel
      (a 150-char beat ≈ 10s on one Ken Burns move).

---

## 5. Key files

- `backend/app/features/render/ai/llm/story_prompts_v2.py` — the 3 prompts + length levers (`SUPER_PROMPT_VERSION`).
- `backend/app/features/render/ai/llm/story_director_v2.py` — `run_super_plan` routing.
- `backend/app/features/render/ai/llm/__init__.py` — `generate_story_plan_v2` dispatch.
- `backend/app/features/render/engine/pipeline/story_pipeline_v2.py` — render wiring.
- `backend/ai_eval/structural_story.py` + `ab_story_plan.py` — judge-free scorers / runner.
- Env: `STORY_IDEA_LENGTH_FACTOR` (idea length compensation, default 1.8).

# Audit — Story v1 dead-code (2026-07-10)

> Read-only consumer enumeration for the legacy Story v1 path, per the Backward
> Compat Protocol + "strict-but-evidenced dead code" rule. **Nothing removed** —
> this is the evidence base + a proposed phased removal for approval. Append-only:
> new findings go in new files, never edit this in place.

## Method

`grep` over `app/` + `tests/` (excluding `.pyc` and `.pytest-data` logs) for every
v1 symbol; classified each as LIVE (has a production caller / API consumer) or DEAD
(only self-references + tests). Cross-checked the FE (`frontend/src`) for API usage.

## Key correction vs the first pass

Earlier notes called the whole v1 tree "orphaned". The audit found **shared files
where only PART is dead**, and things that became LIVE in later phases:

- `StoryCharacter` (in `domain/story_plan.py`) is **LIVE** — the
  `/api/story/character/reference-sheet` endpoint uses it, and the FE Phase 5
  CharactersPanel calls that endpoint ("Ref sheet" button).
- `story_repo` + the story DB tables (0018–0021) are **LIVE** — Phase 4 Q3
  (`_generate_reference_sheets`) and the reference-sheet endpoint use them.
- `safe_filename` / `stable_seed` (in `stages/story/context.py`) are **LIVE** — the
  v2 pipeline imports `safe_filename`.
- `clamp_tier` (in `visual/story_decision.py`) is **LIVE** — v2 `story_image` imports it.

## The single thread keeping v1 reachable

The **entire** v1 chain is reachable through exactly ONE production entry point:

```
POST /api/story/analyze  (router.analyze_chapter)
   → analyze_story()              [llm/__init__.py]
   → run_story_intelligence()     [story_director.py v1]
   → story_chunker + story_prompts(v1) + story_parser(v1) → StoryBible
```

`analyze_story` has one other caller — `generate_story_plan` (v1 P2) — but
**`generate_story_plan` itself has NO production caller** (grep: only its own log
lines). So the P2 planning sub-tree (`generate_story_plan`, `run_story_planning`)
is already fully dead with no entry point at all.

FE usage of `/api/story/analyze`: **none** (`grep frontend/src` = 0). It backed the
old "Bible review (Duyệt #1)" screen, which the v2 super-plan flow (`/api/story/plan`)
replaced.

## DEAD inventory (no production caller — tests only)

| Symbol / file | Evidence |
|---|---|
| `ai/vision/qa.py` (whole module) | **zero** production importers (grep empty); only tests + a `StoryRenderContext.vision_qa` dataclass field (itself dead) |
| `story_image.generate_shot_image` | only tests (`test_story_image.py`); v2 uses `generate_visual_image` |
| `llm/generate_story_plan` (v1) | no production caller |
| `story_director.run_story_planning` | only via dead `generate_story_plan` + tests |
| `story_director.run_story_intelligence` | only via `analyze_story` (whose only live caller is `/analyze`) |
| `llm/story_chunker.py` | imported only by `story_director.py` (v1) |
| `llm/story_prompts.py` (v1) | imported only by `story_director.py` (v1) |
| `llm/story_parser.py` (v1) | imported only by `story_director.py` (v1) |
| `StoryRenderContext` (context.py) | only self + tests (keep `safe_filename`/`stable_seed`) |
| `story_plan.py`: `StoryBible`, `StoryPlan`(v1), `StoryScene`, `Shot`, `StoryEnvironment` | v1 director/parser + tests (keep `StoryCharacter`) |
| `story_decision.decide_shot_asset` (uses `Shot`) | v1-only (keep `clamp_tier`) |
| `story_voice_cast.apply_voice_cast` (v1, takes a bible) | v2 uses `apply_voice_cast_v2` (keep `cast_voices` — shared) |

## LIVE — MUST PRESERVE

- Endpoints: `/api/story/plan`, `/visual/preview`, `/narration/preview`,
  `/character/reference-sheet` (all in the same router as `/analyze`).
- `domain/story_plan.py`: `StoryCharacter`.
- `visual/story_image.py`: `generate_visual_image`, `generate_image_bytes`.
- `visual/story_reference_sheet.py` (Q3 + endpoint).
- `stages/story/context.py`: `safe_filename`, `stable_seed`.
- `visual/story_decision.py`: `clamp_tier`.
- `ai/llm/story_voice_cast.py`: `apply_voice_cast_v2`, `cast_voices`.
- `db/story_repo.py` + story tables (Q3 + reference-sheet).

## BLOCKER — `/api/story/analyze` is a frozen public REST route

`main.py:160` mounts it; it's a documented public route. Removing it is a Frozen
API Contract change → Backward Compat Protocol: FE=none, but external/API clients
are unknown. Requires explicit user approval for a coordinated removal.

## Proposed phased removal (for approval — NOT yet done)

**Gate:** the whole v1 tree only dies once `/analyze` is removed. So step 1 decides
everything.

1. **Decide `/api/story/analyze`.** Remove the endpoint + `StoryAnalyzeRequest` +
   `_persist_bible` from `features/story/router.py` (keep the other 4 endpoints).
   Frozen-API → needs approval. If kept, STOP — the rest stays reachable.
2. **Remove the now-unreachable v1 LLM chain:** `analyze_story`, `generate_story_plan`,
   `_get_story_call_fn`'s v1-only branches (verify), from `llm/__init__.py`; delete
   `story_director.py`, `story_chunker.py`, `story_prompts.py`, `story_parser.py`.
3. **Remove dead vision + image:** delete `ai/vision/qa.py`; remove
   `generate_shot_image` from `story_image.py`.
4. **Prune shared files surgically:** drop `StoryBible/StoryPlan/StoryScene/Shot/
   StoryEnvironment` from `story_plan.py` (keep `StoryCharacter`); `decide_shot_asset`
   from `story_decision.py` (keep `clamp_tier`); `apply_voice_cast` from
   `story_voice_cast.py` (keep v2 + `cast_voices`); `StoryRenderContext` from
   `context.py` (keep `safe_filename`/`stable_seed`).
5. **Delete v1-only tests:** `test_story_analyze_endpoint.py`, `test_story_director.py`,
   `test_story_planning.py`, `test_story_vision_qa.py`, `test_story_plan_roundtrip.py`;
   prune the `generate_shot_image` / `Shot` / `StoryBible` cases from
   `test_story_image.py`, `test_story_decision.py`, `test_story_voice_cast.py`.
6. **Full pytest** before/after; `py_compile`; confirm the 4 kept endpoints still 200.

**Risk:** HIGH (frozen API + broad multi-file delete). **Rollback:** git revert; each
step is independently revertible if done as separate commits.

## Recommendation

Sound to remove — the tree is provably single-threaded through `/analyze` and the FE
doesn't use it. But it's a frozen-API removal + a large delete, so it wants its own
approved change (steps 1→6 as separate commits), not folded into a feature phase.

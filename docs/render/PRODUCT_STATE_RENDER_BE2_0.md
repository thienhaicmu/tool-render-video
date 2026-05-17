# PRODUCT STATE — RENDER-BE2.0: Source Identity & Smart Output Naming

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): source identity and smart output naming`
**Status:** Shipped

---

## Summary

Improved creator experience around source identity and output naming. Output files now carry
human-readable names derived from the content rather than technical slugs. The fallback chain
ensures every render has a meaningful name even when no AI hook is present.

---

## Goals and Delivery

| Part | Goal | Status |
|------|------|--------|
| A | Local video renders directly from source path (no copying) | Already correct — confirmed in audit |
| B | YouTube download behavior unchanged | Unchanged |
| C | Preserve original source filename in output names | Done — `source['title']` used as P2 |
| D | AI hook title as primary output filename when available | Done — `_hook_applied_text` used as P1 |
| E | Fallback chain: AI hook → source title → `render_{job_id[:8]}` | Done |
| F | Safe filename sanitizer (human-readable, not ugly slug) | Done — `_safe_output_name()` |
| G | Consistent naming across filesystem / review panel / history / best export / runtime hero | Done — single `_output_stem` drives all surfaces |

---

## Implementation

**File changed:** `backend/app/orchestration/render_pipeline.py`

### New helpers (module level)

```python
def _safe_output_name(text: str) -> str:
    """Human-readable safe filename stem. Preserves case and apostrophes."""
```

- Strips leading/trailing whitespace
- Replaces Windows-forbidden chars (`\ / : * ? " < > |`) with `-`
- Normalises newlines/tabs to spaces
- Collapses consecutive dashes or spaces
- Strips leading/trailing dashes and spaces
- Truncates at 80 chars (word boundary when possible)
- Preserves case, apostrophes, parentheses, ampersands — anything safe on all platforms

```python
def _smart_output_stem(hook_text: str, source_title: str, job_id: str) -> str:
    """Fallback chain: AI hook → source title → render_{job_id[:8]}."""
```

- Priority 1 (`hook_text`): `payload.hook_applied_text` — the AI-generated hook headline applied to subtitles
- Priority 2 (`source_title`): `source['title']` — YouTube video title, editor session title, or humanised local filename stem
- Priority 3 (hardcoded): `render_{job_id[:8]}` — always non-empty

### Stem computation

```python
_output_stem = _smart_output_stem(_hook_applied_text, source.get("title", ""), job_id)
```

Computed once after source resolution, before the edit-trim block. Captured by the
`_process_one_part` closure and reused by `auto_best_export`. `_hook_applied_text` is
available at this point (set at line ~1093).

### Output file naming

**Before:**
```
{source['slug']}_part_001.mp4   # e.g. why-you-re-failing-the-truth_part_001.mp4
rank_01_part_001.mp4            # best export
```

**After:**
```
{_output_stem}_part_001.mp4     # e.g. Why You're Failing - The Truth_part_001.mp4
{_output_stem}_rank_01.mp4      # best export
```

Temp/working files (`raw_part`, `srt_part`, `ass_part`, `translated_srt_part`, `full_srt`)
continue to use `source['slug']` — they are internal and never shown to the user.

---

## Fallback Examples

| Source | hook_applied_text | Output stem |
|--------|-------------------|-------------|
| YouTube "How To Build Wealth" | "You're Broke Because of THIS" | `You're Broke Because of THIS` |
| YouTube "How To Build Wealth" | *(empty)* | `How To Build Wealth` |
| Local `interview_final_v2.mp4` | *(empty)* | `interview final v2` |
| Local `interview_final_v2.mp4` | "The Moment Everything Changed" | `The Moment Everything Changed` |
| Any source | *(both empty)* | `render_a1b2c3d4` |

---

## Constraints Honored

- No pipeline rewrite — only two targeted edits inside `run_render_pipeline`
- No YouTube flow changes — download, slug computation, full_srt naming all unchanged
- Resume/retry safe — `final_part` existence check uses the same `_output_stem` computed
  from the same payload, so resumed jobs find their previously rendered files
- No duplicate naming systems — `slugify()` still used for temp files; `_safe_output_name`
  only applied to user-visible output paths

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/orchestration/render_pipeline.py` | `import re`; `_safe_output_name()`; `_smart_output_stem()`; `_output_stem` computation; `final_part` / `part_name` renamed; `auto_best_export` dst renamed |
| `docs/render/PRODUCT_STATE_RENDER_BE2_0.md` | This file |

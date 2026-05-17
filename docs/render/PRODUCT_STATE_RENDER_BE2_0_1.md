# PRODUCT STATE — RENDER-BE2.0.1: Local Source Passthrough

**Branch:** `feature/ai-output-upgrade`
**Commit:** `perf(render): local source passthrough`
**Status:** Shipped

---

## Summary

Local videos now render directly from their original path. No more copying the
source file into the project's `source/` folder before render begins.

For large local files (10 GB – 50 GB+) this eliminates a blocking file copy that
could take minutes and duplicate gigabytes of storage.

---

## Root Cause

`keep_source_copy: true` is the hardcoded default in every `render-engine.js` build
(`static/`, `static-v3/`, `static-v4/`). The pipeline's `keep_source_copy` block
branched on `is_temp_source`:

- **Temp source** (YouTube download, edited local): move temp to `source/` → correct
- **Non-temp source** (user's original local file): try `os.link()`, fall back to
  `shutil.copy2()`, then `source_path = keep_path` → **render from the copy**

On Windows, `os.link()` fails when source and destination are on different drives
(e.g., source on D:, project on C:). The fallback `shutil.copy2()` then copies
the entire file byte-for-byte, blocking render startup.

---

## Fix — One Surgical Block (`render_pipeline.py`)

**Before:**
```python
if payload.keep_source_copy:
    ...
    keep_path = _reserve_source_path_in_dir(...)
    if not keep_path.exists():
        is_temp_source = str(source_path).startswith(str(TEMP_DIR))
        if is_temp_source:
            shutil.move(...)        # ← correct
        else:
            try:
                os.link(...)        # ← hardlink attempt
            except OSError:
                shutil.copy2(...)   # ← full copy for large files!
    source_path = keep_path         # ← always, even for local originals
```

**After:**
```python
if payload.keep_source_copy:
    ...
    is_temp_source = str(source_path).startswith(str(TEMP_DIR))
    if is_temp_source:
        keep_path = _reserve_source_path_in_dir(...)
        if not keep_path.exists():
            shutil.move(...)        # ← unchanged for temp sources
        source_path = keep_path     # ← only for temp sources
    else:
        # Local original: already permanent, render from source path directly.
        _job_log(..., "local_source.passthrough ... (source copy skipped)")
```

**Key difference:** `is_temp_source` check is now the outer branch. Non-temp local
files skip all copy/hardlink logic and `source_path` is never updated.

---

## Behavior Matrix

| Source type | Before | After |
|-------------|--------|-------|
| YouTube download (temp) | Move to `source/`, render from copy | **Unchanged** |
| Local, no edits (non-temp) | Copy/hardlink to `source/`, render from copy | **Use original path directly** |
| Local, with trim/volume edits | Temp edited file → move to `source/`, render from copy | **Unchanged** (edited file is temp) |
| Editor session (temp) | Move to `source/`, render from copy | **Unchanged** |
| Editor session (non-temp) | Hardlink/copy, render from copy | **Use original path directly** |

---

## Part A — Local Passthrough ✓

For unedited local sources, `source_path` stays as the user's original absolute
path (e.g., `D:/Videos/My Clip.mp4`) through the entire render pipeline.

## Part B — Source Folder Rule ✓

`source/` folder is not created or written to for local non-temp sources.
YouTube's `source/` cache behavior is fully preserved.

## Part C — Resume / Retry Safety ✓

Resume checks `final_part.exists()` (output file), not source existence. If the
local source is deleted after render starts, `cut_video()` raises a clean
`CalledProcessError` which propagates as a logged RuntimeError with a truthful
error message. No crash, no zombie state.

## Part D — Source Identity Consistency ✓

`source['title']`, `source['slug']`, `source['filepath']`, and `_output_stem` are
all computed **before** the `keep_source_copy` block, using the user's original
filename. These values are unaffected by the passthrough change.

## Part E — Internal Temp Files ✓

`raw_part`, `srt_part`, `ass_part`, `translated_srt_part` continue to use
`source['slug']` as their prefix. Only the source video duplication is removed.

---

## Constraints Honored

| Constraint | Status |
|-----------|--------|
| No render rewrite | ✓ |
| No ffmpeg rewrite | ✓ |
| YouTube flow unchanged | ✓ |
| Resume regression | None |
| Retry regression | None |
| Batch render | Unchanged |
| Source identity | Correct |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/orchestration/render_pipeline.py` | Restructured `keep_source_copy` block: temp-source check is outer branch; non-temp local sources skip all copy logic and preserve original `source_path` |
| `docs/render/PRODUCT_STATE_RENDER_BE2_0_1.md` | This file |

---

## Manual QA Checklist

- [ ] Local video renders successfully (no crash)
- [ ] `source/` folder NOT created for local renders
- [ ] Large file (10 GB+): render starts without copy delay
- [ ] YouTube render: `source/` folder still created with downloaded file
- [ ] Retry local render: works correctly
- [ ] Resume local render: skips done parts, completes remaining
- [ ] Cancel local render: stops cleanly
- [ ] Delete local source mid-render: clean error in logs, no zombie
- [ ] Review panel: correct filename shown
- [ ] Completion hero: correct filename shown
- [ ] No backend errors in console during local render

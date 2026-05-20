# PHASE UX-1A-R2 — Video Editor Reduction + VideoLocal Render Audit

**Scope:** Tab reduction analysis + VideoLocal render path deep review
**Status:** Audit only. No implementation. No redesign.
**Date:** 2026-05-20
**Source of truth:** PHASE_UX1A_VIDEO_EDITOR_AUDIT.md + full code read (render_pipeline.py, render.py, editor-view.js, render-config.js, render-engine.js)

---

## 1. Executive Summary

### Part A — Tab Reduction

The current 6-tab structure (Story / Subtitles / Words / Audio / Export / AI) has three tabs that are consistently low-use and do not justify standalone tab real estate: **Words**, **Audio**, and **AI**. Merging these into a **4-tab model** is feasible without regression, but requires carefully updating the `setInspectorTab()` function and its side-effect calls.

**Realistic 4-tab target:**
```
Edit | Subtitles | Export | More
```

- **Edit** absorbs: Story + Words + AI (all editorial concerns)
- **Subtitles** unchanged
- **Export** stays but gets cleaned of non-render concerns
- **More** absorbs: Audio + Render Settings + Editor Performance + Batch Queue

This reduces cognitive load at the tab level. The Export tab's internal overload problem is a **separate, harder problem** that is not solved by tab count reduction alone.

### Part B — VideoLocal Render

**The stated premise is incorrect.** Current code does NOT copy the local source video. The render reads directly from the original file path. A `source/` folder is only created when the creator applies trim edits — and even then, the trimmed intermediate is **moved** (zero-copy), not duplicated.

What IS created:
- A temp session directory (always, for the preview)
- A browser-safe H264 preview transcode (only when source is not H264+AAC mp4/mov)
- A trimmed intermediate in `source/` (only when trim is applied)

The H264 preview transcode **cannot be skipped** — it exists for Electron's Chromium browser compatibility. The render pipeline does not use it.

---

## 2. Recommended Tab Reduction Model

### Current: 6 tabs

| Tab | Internal ID | Use Frequency |
|---|---|---|
| Story | `mode` | HIGH — trim and quick styles every session |
| Subtitles | `subtitle` | MODERATE — most creators visit once per project |
| Words | `text` | LOW — AI narration rare; text layers power-user only |
| Audio | `audio` | LOW — defaults work for most creators |
| Export | `performance` | HIGH — but grossly overloaded |
| AI | `ai` | LOW — conversational AI for power users |

### Recommended: 4 tabs

```
┌──────┬───────────┬────────┬──────┐
│ Edit │ Subtitles │ Export │ More │
└──────┴───────────┴────────┴──────┘
```

| New Tab | Contains | Source Tabs |
|---|---|---|
| **Edit** | Trim, Quick Styles, AI Edit Actions, AI Conversational, Text Layers, Edit History, Creator Memory | Story + Words + AI |
| **Subtitles** | Unchanged | Subtitles |
| **Export** | QS Bar, Presets, Max clips, Advanced fold | Export (cleaned) |
| **More** | Audio, AI Narration, Render Settings, Editor Performance, Batch Queue | Audio + parts of Export |

### What this accomplishes

- Creator working on editorial decisions (trim, style, AI) has one tab
- Creator configuring render output has one tab (Export — still complex, but focused)
- Rarely-needed settings are in More (a known pattern; creators accept a "More" bucket)
- Subtitle control is still distinct (enough controls to justify a tab)
- Tab count drops from 6 → 4 without removing any controls

### What this does NOT solve

- The Export tab's internal overload (three preset systems, buried duration controls, Aspect Ratio in Advanced)
- The subtitle-QS-bar disconnect (still present, both tabs still exist separately)
- Decision fatigue within Export (requires a separate phase)

---

## 3. Tab-by-Tab Audit

### 3.1 Story Tab (internal: `mode`) — KEEP, RENAME

**Content:** Trim, Quick Styles, AI Edit Actions (collapsed), Edit History (collapsed), Creator Memory panel

**Usage assessment:** HIGH. Every creator session starts here. Trim is used frequently. Quick Styles (Viral/Cinematic/Aggressive/Balanced) is the primary creative lever for most creators. AI Edit Actions are used when something needs fixing. Edit History and Creator Memory are passive reference.

**Verdict:** Keep. Rename from "Story" to "Edit" (task-based language).

**Safe merge candidates:** Words tab and AI tab content can move here without confusion — they are all editorial actions.

**Friction in current form:**
- "Story" is a conceptual name that doesn't tell creator what to do here
- AI Edit Actions collapsed by default while Quick Styles are visible creates uneven AI discoverability
- Creator Memory panel at the bottom is passive — creator doesn't know it's there

---

### 3.2 Subtitles Tab (internal: `subtitle`) — KEEP

**Content:** Auto subtitle toggle, Style dropdown (5), Font select (8), Size slider, Color/Highlight pickers, Y/X Position sliders, Outline slider, Static preview, AI Fix Subs button, Translate option

**Usage assessment:** MODERATE. Most creators configure this once per project. The controls are specialized enough that a dedicated tab is justified.

**Verdict:** Keep. The tab has enough controls that embedding them elsewhere would create a wall of options in that destination.

**Cannot merge into Export:** Export is already overloaded. Adding 9 subtitle controls to Export would make it worse.

**Cannot merge into Edit:** Edit tab is for timeline/clip decisions. Subtitle style is an output decision, not an edit decision. Putting them in the same tab creates conceptual noise.

**Friction in current form (carried from UX-1A):** Two preview systems, X Position exposed, Style dropdown vs visual cards, QS Bar disconnect. These are separate issues from tab structure.

---

### 3.3 Words Tab (internal: `text`) — MERGE INTO EDIT

**Content:** AI Narration section, Text Layers collapsible group

**Usage assessment:** LOW.
- AI Narration: off by default, requires voice profile setup, rarely used
- Text Layers: power feature for creator branding; when no layers exist, the tab shows only AI Narration

**When is this tab actually needed?**
- Creator adding custom text overlays (branding, captions, titles)
- Creator enabling AI voice narration

**Verdict:** Merge into Edit tab. Moving `data-insp-panel="text"` sections to `data-insp-panel="mode"` requires:
- Changing 2 HTML attribute values
- Removing the Words tab `<button>` from the tabbar
- Updating `validTabs` array in `setInspectorTab()`
- Updating `tabTitles` map
- Moving the `if (activeTab === 'text')` block in `setInspectorTab()` to fire on `'mode'` tab activation instead

**Specific dependency:** When the Words tab is activated, `EditorTextRuntime.onTabActivate()` is called AND text-layers group is auto-opened if layers exist. After merge, this must happen when the Edit tab is activated instead — but auto-opening text layers on Edit tab entry would be jarring. Solution: fire `EditorTextRuntime.onTabActivate()` on Edit tab, but do NOT auto-open text-layers group unless the creator clicked the Text Layers area specifically.

**Risk:** LOW. No functional logic is coupled to "text" being a standalone tab.

---

### 3.4 Audio Tab (internal: `audio`) — MERGE INTO MORE

**Content:** Source Audio (volume slider), BGM (toggle + volume + file + fade controls), Loudness normalization

**Usage assessment:** LOW. Source audio volume is rarely changed. BGM is off by default — some creators enable it. Loudness normalization is always on and never changed.

**Verdict:** Move to a "More" tab alongside Render Settings. Audio is not a primary editorial concern — it's a technical output parameter.

**Specific dependency:** When the Audio tab is activated, two things happen:
```js
if (activeTab === 'audio') {
  evSetInspGroupOpen('audio', true);
  EditorAudioRuntime.onTabActivate();
}
```
`EditorAudioRuntime.onTabActivate()` likely initializes the audio system lazily. If Audio moves to "More" tab, this trigger must move too: `if (activeTab === 'more')`.

**Risk:** MEDIUM. If `EditorAudioRuntime.onTabActivate()` is not called when the creator first opens More tab, audio controls may appear but not be fully initialized. Must verify what `onTabActivate()` does before moving.

---

### 3.5 Export Tab (internal: `performance`) — KEEP, CLEAN INTERNALS

**Content:** Quick Presets, Market & Target, Creator Presets bar, QS Bar, Max clips, Advanced fold (aspect ratio, profile, duration, CTA, assets, batch mode), Batch Queue section, Render Settings (collapsed), Editor Performance section

**Usage assessment:** HIGH for QS Bar, Max clips. LOW for Batch Queue, Render Settings, Editor Performance.

**Verdict:** Keep. Rename internal ID from `performance` to `export` (minor: the button already says "Export"). The content overload is real but is a separate issue from tab count.

**What can move OUT of Export tab:**
- Render Settings → More tab
- Editor Performance → More tab
- Batch Queue → More tab (or remove entirely if Batch Mode URL textarea in Advanced fold is sufficient)

These three moves reduce Export tab length significantly without touching any form inputs or IDs.

**Risk of moving Render Settings out:** MEDIUM. `evSetInspGroupOpen('performance', true)` fires when `activeTab === 'performance'` — this auto-expands Render Settings when Export tab is opened. If Render Settings moves to More tab, this auto-expand must stop (the creator chose Export, not More). The auto-expand behavior may be unexpected anyway — most creators don't need Render Settings to be auto-expanded.

---

### 3.6 AI Tab (internal: `ai`) — MERGE INTO EDIT

**Content:** Conversational editing input, example prompt buttons

**Usage assessment:** LOW. The AI tab is powerful but obscure. Most creators don't know it exists. The example prompts (make intro stronger, too slow, clean subtitles, more energy, less jumpy) are good quality.

**Verdict:** Merge into Edit tab. Place the conversational panel at the bottom of Edit tab, below AI Edit Actions. This way:
- Creator in Edit tab sees: Trim → Quick Styles → AI Edit Actions → [conversational panel at bottom]
- The flow is natural: named styles → targeted actions → freeform chat

**Specific dependency:** `data-insp-panel="ai"` on the `convPanel` div. Change to `data-insp-panel="mode"`. Remove `<button data-insp-tab="ai">AI</button>` from tabbar. Update `validTabs` and `tabTitles` in `setInspectorTab()`.

**No runtime dependency exists** for the AI tab — no `if (activeTab === 'ai')` block in `setInspectorTab()`. This makes it the safest merge.

**Risk:** LOW.

---

## 4. Safe Merge Opportunities

Listed by ascending implementation risk.

### 4.1 AI Tab → Edit Tab (LOWEST RISK)

**What changes:**
- `index.html`: `data-insp-panel="ai"` → `data-insp-panel="mode"` on convPanel div
- `index.html`: remove `<button class="insp-tab" data-insp-tab="ai" ...>AI</button>`
- `editor-view.js` `setInspectorTab()`: remove `'ai'` from `validTabs`; remove `'ai': 'AI'` from `tabTitles`

**No JS side effects to update.** No runtime initialization on tab switch. Safest merge in the list.

### 4.2 Words Tab Content → Edit Tab (LOW RISK)

**What changes:**
- `index.html`:
  - `data-insp-panel="text"` on `evSectionNarration` → `data-insp-panel="mode"`
  - `data-insp-panel="text"` on `inspCollapsedGroup` (Text Layers) → `data-insp-panel="mode"`
  - Remove `<button class="insp-tab" data-insp-tab="text" ...>Words</button>`
- `editor-view.js` `setInspectorTab()`:
  - Remove `'text'` from `validTabs`
  - Remove `'text': 'Words'` from `tabTitles`
  - Move the `if (activeTab === 'text')` block to fire on `if (activeTab === 'mode')`
  - Adjust text-layers auto-open: do NOT auto-open the group on Edit tab activation (it would surprise creator every time they switch to Edit tab). Only auto-open when creator specifically clicks into text area.

**Specific JS to update:**
```js
// Current (editor-view.js ~2674):
if (activeTab === 'text') {
  if (typeof EditorTextRuntime !== 'undefined') EditorTextRuntime.onTabActivate();
  const hasLayers = typeof _ev !== 'undefined' && Array.isArray(_ev.textLayers) && _ev.textLayers.length > 0;
  evSetInspGroupOpen('text-layers', hasLayers);
}
```
→ Move `EditorTextRuntime.onTabActivate()` call to `if (activeTab === 'mode')` block, but keep `evSetInspGroupOpen('text-layers', hasLayers)` conditional on creator deliberately expanding the section.

### 4.3 Render Settings + Editor Performance → More Tab (LOW-MEDIUM RISK)

**What changes:**
- `index.html`:
  - Change `data-insp-panel="performance"` on the Render Settings `inspCollapsedGroup` → `data-insp-panel="more"`
  - Change `data-insp-panel="performance"` on the Editor Performance `evSection` → `data-insp-panel="more"`
  - Add new `<button data-insp-tab="more">More</button>` to tabbar
- `editor-view.js`:
  - Add `'more'` to `validTabs`
  - Add `'more': 'More'` to `tabTitles`
  - Move `evSetInspGroupOpen('performance', true)` to fire on `'more'` tab, not `'performance'` tab
  - Move `EditorPerformanceRuntime.onTabActivate()` to fire on `'more'`
  - Move `EditorPerformanceRuntime.onTabDeactivate()` to fire on tab change away from `'more'`

**Risk factor:** The `EditorPerformanceRuntime.onTabActivate()` / `onTabDeactivate()` calls are important — they activate/deactivate performance monitoring behaviors. Moving them to `'more'` tab means the performance runtime won't activate until creator visits More tab. This is acceptable for a "rarely used" tab. But verify that `EditorPerformanceRuntime` does not need to be active from editor open for health monitoring.

### 4.4 Batch Queue → More Tab (MEDIUM RISK)

**What changes:**
- `index.html`: `data-insp-panel="performance"` on `bqSection` → `data-insp-panel="more"`

**Risk factor:** `BatchQueue` module and its DOM methods (`BatchQueue.openFilePicker()`, `BatchQueue.onDrop()`, `BatchQueue.submit()`) address the section by `bqSection` ID, not by tab. Moving the section is safe as long as the ID is preserved. The drag-over behavior uses ondragover/ondragleave which are attribute-bound, not tab-bound.

---

## 5. Dangerous Merge Opportunities

These should NOT be done without dedicated analysis and testing.

### 5.1 Audio Tab → Export Tab (DANGEROUS)

**Why dangerous:** Export tab is already overloaded. Adding Source Audio, BGM controls, and Loudness toggle to Export would make the tab the single most complex panel in the product. Reject.

### 5.2 Subtitles Tab → Export Tab (DANGEROUS)

**Why dangerous:** Subtitle controls (9 visible controls + preview) added to Export would make Export unmanageable. The QS Bar subtitle pill already bridges the two. Merging the full controls would create a wall of settings. Reject.

### 5.3 Export Tab → Edit Tab (DANGEROUS)

**Why dangerous:** Completely different mental models. Edit tab is timeline/clip decisions. Export tab is output configuration. Creator who is trimming a clip should not see aspect ratio and platform pills. This would collapse the product's conceptual model. Reject.

### 5.4 Audio → Edit Tab (QUESTIONABLE)

Putting volume and BGM next to trim and quick styles creates a confusing mix. Audio mix is an output concern, not an editorial concern. Wrong destination.

### 5.5 Removing "More" Tab and Collapsing into Export

If all low-use items (audio, render settings, performance, batch) stay in Export, the tab count doesn't change but Export gets even more complex. The goal of a "More" tab is to create a known dumping ground for things creators rarely need. This is a standard UX pattern (e.g., "Settings" in apps) and is acceptable as a destination.

---

## 6. Current VideoLocal Render Flow

### 6.1 Step-by-Step (Current Code)

```
User selects local video file
  ↓
startRender() [render-engine.js]
  → validates outputDir and localVideoPath
  → builds base payload
  → POST /api/render/prepare-source
       {source_mode: "local", source_video_path: "/path/to/file.mp4", ...}
  ↓
prepare_source() [render.py:356]
  → work_dir = TEMP_DIR / "preview" / session_id
  → work_dir.mkdir(parents=True, exist_ok=True)
  → src = Path(source_video_path).expanduser().resolve()
  → validates src.exists()
  → _probe_video_duration(src) → duration
  → _ensure_h264_preview(src, work_dir, duration)
      → _is_browser_safe_preview(src):
          checks: container in (mp4, mov) AND codec in (h264, avc, avc1) AND audio in (aac, mp3)
          IF TRUE → return src unchanged (no transcode)
          IF FALSE → transcode to work_dir/preview_h264.mp4 (crf=28, 1280px max, veryfast)
  → _save_session(session_id, {
        "video_path": str(src),           ← ORIGINAL path
        "preview_path": str(preview_path), ← src or transcoded path
        ...
    })
  → returns {session_id, duration, title, export_dir: work_dir / "exports"}
  ↓
openEditorView(sessionId, exportDir, ...)
  → _ev.sessionId = sessionId
  → _ev.exportDir = exportDir  [TEMP_DIR/preview/<session_id>/exports/]
  → loads preview video via GET /api/render/preview-video/<session_id>
      → serves preview_path (H264 transcode or original if browser-safe)
  ↓
Creator configures, clicks ▶ Start Render
  ↓
startRenderFromEditor() [editor-view.js:2178]
  → reads all inspector controls
  → output_dir resolution:
      raw = payload.output_dir || _ev.exportDir
      if leaf is 'video_output' or 'video_out': use raw
      else: raw + '/video_output'
  → forces: payload.output_mode = 'manual', payload.channel_code = ''
  → payload.edit_session_id = _ev.sessionId
  → POST /api/render/start
  ↓
run_render_pipeline() [render_pipeline.py]
  → edit_session_id = payload.edit_session_id
  → sess = load_session(edit_session_id)
  → source_path = Path(sess["video_path"])  ← ORIGINAL LOCAL FILE
  → source["filepath"] = str(source_path)
  ↓
  → checks trim/volume:
      IF needs_trim or needs_volume:
          edited_path = TEMP_DIR/job_id/edited_<stem>.mp4
          runs FFmpeg trim/volume
          source_path = edited_path  [now in TEMP_DIR]
          source["filepath"] = str(edited_path)
  ↓
  → keep_source_copy check:
      is_temp_source = str(source_path).startswith(str(TEMP_DIR))
      IF is_temp_source (= trim was applied):
          keep_path = output_dir/../source/<slug>.mp4
          shutil.move(edited_path → keep_path)  [MOVE, not copy]
          source_path = keep_path
          _job_log: "Source moved (zero-copy) to: {keep_path}"
      IF NOT is_temp_source (= original local file, no trim):
          _job_log: "local_source.passthrough ... (source copy skipped)"
          source_path remains pointing to ORIGINAL local file
  ↓
  → render proceeds reading from source_path
  ↓
  → finally:
      if cleanup_temp_files: shutil.rmtree(TEMP_DIR/job_id)
      if edit_session_id and success: cleanup_session(session_id)
          → removes TEMP_DIR/preview/<session_id>/
```

---

## 7. Why the "Copy" Exists — Actual Reason from Code

### 7.1 The H264 Preview Transcode

**Reason:** Electron's bundled Chromium cannot play all video formats. On Windows, Chromium in Electron typically cannot play HEVC (H265), MKV containers, AVI, VP9, or AV1. If a creator's source file is in any of these formats (common for `.mkv`, `.avi`, screen recordings, HEVC camera footage), the editor's video player shows nothing.

**The transcode is NOT for the render.** It is purely for browser playback in the editor.

**When it is skipped:** `_is_browser_safe_preview()` returns True when:
```python
container_ok = any(name in container for name in ("mp4", "mov"))
video_ok = video_codec in ("h264", "avc", "avc1")
audio_ok = (not audio_codec) or audio_codec in ("aac", "mp3")
```
Most modern iPhone footage, camera footage exported as H264 mp4, and any content already processed by the tool will be browser-safe. The transcode runs only for exotic formats.

**It is cached:** The `preview_h264.mp4` is created in the session work_dir. On the next render with the same session (if the creator rerenders), the cached preview is reused (`if out.exists() and out.stat().st_size > 0: return out`).

### 7.2 The source/ Folder (Trimmed Intermediate)

**Reason:** When the creator applies trim edits:
1. FFmpeg creates a trimmed file in the job's temp dir (`TEMP_DIR/job_id/edited_<stem>.mp4`)
2. The render reads this trimmed file as input
3. After render, `cleanup_temp_files=True` removes the entire job temp dir
4. Without the move to source/, the trimmed file would be **permanently deleted**
5. The creator expects to find their source content alongside their outputs

**The move (not copy):** When trimmed file is on the same filesystem as the output, `shutil.move()` is a rename — instant, zero I/O, no data duplication. Only if filesystems differ does it fall back to copy+delete.

### 7.3 What the Current Code Does NOT Do

- Does NOT copy the original local video file
- Does NOT move the original local video file
- Does NOT create a source/ folder for untrimmed local renders
- Does NOT use the H264 preview transcode as render input

**The premise of the question — "VideoLocal render copies local video" — does not match current code.** This may have been true in an earlier version, or the observed behavior may have been the preview transcode (which is visually similar to a copy but serves a different purpose).

---

## 8. Dependency Graph for VideoLocal Path

### 8.1 What reads `sess["video_path"]`

```
render_pipeline.py:1963
  source_path = Path(sess["video_path"])
```

This is the only place. The session's `video_path` field always points to the original local file for VideoLocal mode. Nothing else reads this field.

### 8.2 What reads `source_path` after resolution

```
source_path → used as input_path for:
  ├─ _probe_video_duration(source_path)           [line 1969]
  ├─ detect_scenes(str(source_path))              [line 2279]
  │    └─ _scene_cache keyed on source_path string
  ├─ score_segments / build_segments              [line 2298]
  ├─ _transcription_cache_get(str(source_path))   [line ~2400]
  │    └─ transcript cache keyed on source_path string
  ├─ cut_video(input_path=str(source_path), ...)  [per-part]
  ├─ render_part_smart(input_path=str(source_path), ...) [per-part]
  └─ thumbnail extraction [source_path]
```

### 8.3 Cache Key Structure

Both scene and transcription caches are keyed on:
```python
_render_cache_key(source_path_string, st.st_mtime, st.st_size, ...)
```

**Critical:** If `source_path` changes between renders (e.g., original → trimmed copy), cache keys will NOT match. The second render with trim will miss all caches from the first (untrimmed) render. This is correct behavior — the content changed — but it means trimmed renders don't benefit from prior scene detection cache.

**If someone tried to prevent the source/ move** and kept the trimmed file in temp: when temp is cleaned, the trimmed file disappears but the cache key no longer has a valid file to match. Cache reads would fail gracefully (file not found → return None). No crash risk.

### 8.4 What Depends on the source/ Folder Existing

1. **Upload pipeline** (if active): may expect to find source content in the channel's source/ directory. For VideoLocal in manual mode, upload pipeline is not used, so this dependency is inactive.
2. **Creator expectation**: creator may manually look in the output folder and expect to see their source. If using trim and no source/ folder, the trimmed version is gone.
3. **Resume job**: `payload.resume_job_id` path — if a render is resumed, the pipeline needs to find `source_path`. A resumed render from an editor session would re-read `sess["video_path"]` (original path) again. The source/ folder is NOT needed for resume.

---

## 9. Direct Render Feasibility (Without H264 Preview)

### 9.1 Can the preview transcode be skipped entirely?

**NO.** The preview transcode is what makes the editor video player work. Without it:
- Creator picks an HEVC .mp4 or .mkv file
- `prepare-source` completes immediately (no transcode)
- Editor opens, video element fails to load
- Creator sees a black video frame
- Editor is functionally unusable for that source format

The H264 preview transcode is a hard requirement for Electron's Chromium video playback compatibility.

### 9.2 Can the preview transcode be made async (start editor before it finishes)?

**YES — but requires frontend changes.** Currently, `prepare-source` blocks until transcode completes. For a 1-hour video, this could take 5-10 minutes at `veryfast`.

A faster UX would be: return session_id immediately, transcode in background, poll for readiness. The editor could open in a "loading" state while the preview video becomes available.

This is a non-trivial change (requires async transcode job tracking) but would significantly improve the experience for large files. Outside the scope of this audit.

### 9.3 Can the source/ folder creation be skipped?

**YES — for untrimmed VideoLocal renders: it already is skipped.** No code change needed.

**For trimmed renders:** Skipping the source/ move means the trimmed file lives in `TEMP_DIR/job_id/` and is deleted when `cleanup_temp_files=True` runs. This would be acceptable if:
- Creator doesn't need to archive their trimmed source
- Creator can re-apply trim and rerender if needed

**Risk of removing source/ for trimmed renders:** MEDIUM. The trimmed source is a user-generated artifact (their edit). Silently deleting it may surprise creators who expect to find it in their output folder. Not a crash risk, but a user expectation problem.

### 9.4 Can `keep_source_copy` default to False for VideoLocal?

**YES — with caveats.** For local untrimmed: already a no-op (passthrough). Setting False for trimmed would lose the trimmed source after render. This is the only behavior change.

The safest approach: keep `keep_source_copy=True` (current default). The behavior is already correct for VideoLocal untrimmed (no copy). Only trimmed files are affected, and the move to source/ is zero-I/O on same filesystem.

---

## 10. Risk Assessment

### Part A — Tab Reduction

| Change | Risk | Reason |
|---|---|---|
| Remove AI tab (merge to Edit) | LOW | No runtime tab-switch side effects |
| Remove Words tab (merge to Edit) | LOW | EditorTextRuntime.onTabActivate() must move; minimal risk |
| Move Render Settings to More | MEDIUM | Auto-expand + EditorPerformanceRuntime.onTabActivate() must move |
| Move Audio to More | MEDIUM | EditorAudioRuntime.onTabActivate() must move; audio lazy-init must still fire |
| Move Batch Queue to More | LOW | ID-based, not tab-based |
| Remove Editor Performance from Export | LOW | Just changes data-insp-panel attribute |
| Adding "More" tab | LOW | New tab added to validTabs/tabTitles; no existing code breaks |

**The single highest-risk operation in the merge plan:** Forgetting to move `EditorAudioRuntime.onTabActivate()` when Audio moves to More tab. This call initializes the audio system. If not called, BGM and volume controls appear but don't respond correctly.

**Specific JS function that must be updated:**
```js
// editor-view.js: setInspectorTab()
if (activeTab === 'audio') {         // ← must become 'more'
  evSetInspGroupOpen('audio', true);
  EditorAudioRuntime.onTabActivate();
}
```

### Part B — VideoLocal Render

| Concern | Risk | Finding |
|---|---|---|
| Source copy for untrimmed render | NONE | Already skipped. No code change needed. |
| H264 preview transcode | NONE | Required for browser compatibility. Cannot remove. |
| Source/ folder for trimmed render | LOW | Move (not copy). Zero I/O cost on same FS. Already correct. |
| Source path stability | LOW | Original path is always used; cache keys stable. |
| Session cleanup on success | LOW | Already implemented correctly. |
| Trim changes cache miss behavior | LOW | Correct behavior — trimmed content IS different from original. |

---

## 11. Recommended Scope Boundary

### What to do in a Tab Reduction Phase

**Do in one phase (low risk, high value):**
1. Merge AI tab into Edit tab — pure attribute change + validTabs update
2. Merge Words tab into Edit tab — attribute change + EditorTextRuntime trigger move
3. Add "More" tab definition to JS + HTML
4. Move Editor Performance section to More tab
5. Rename "Story" → "Edit" in tab button text (tabTitles map update only)

**Do in a second phase (medium risk):**
1. Move Audio to More tab + update EditorAudioRuntime.onTabActivate() trigger
2. Move Render Settings to More tab + update EditorPerformanceRuntime trigger
3. Move Batch Queue to More tab

**Do NOT do (separate scope):**
1. Export tab internal restructuring (three preset systems, buried duration controls) — separate, larger scope
2. Subtitle QS bar / Subtitle tab reconnection — separate scope
3. Subtitle visual preview improvement — separate scope

### What NOT to do about VideoLocal

No changes needed to the VideoLocal render flow. The current behavior is already correct:
- No copy of original local file
- H264 preview transcode exists for compatibility (not removable without browser/Electron change)
- Trim creates a move (not copy) to source/ folder — minimal I/O
- Cache keying is source-path based — stable for untrimmed, correctly cache-missing for trimmed

**If the user perceives a "copy" happening:** they are likely seeing the H264 preview transcode (`TEMP_DIR/preview/<session_id>/preview_h264.mp4`) which appears to be a copy but is a browser-safety re-encode. This file is deleted when the render succeeds (`cleanup_session_fn`).

**What COULD improve VideoLocal startup for large files:** Async H264 preview transcode (return session_id immediately, transcode in background). This would require frontend loading state changes and background task tracking. Medium risk, significant UX improvement for large files. Recommend for a future phase if creators report slow editor loading for large HEVC or MKV files.

---

*End of Audit — PHASE UX-1A-R2*
*Next step if approved: UX-1B (Implementation Plan) starting with tab reduction Phase A (low-risk merges).*

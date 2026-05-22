# PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md

**Status**: 4G.1 SHIPPED — styles.py extracted; 4G.2–4G.7 pending  
**Date**: 2026-05-22  
**Branch**: `restructure/output-timeline-architecture`

---

## 1. Current `subtitle_engine.py` State

**File**: `backend/app/services/subtitle_engine.py`  
**Lines**: 1,970  
**Module-level hard imports**: `whisper`, `TimelineMap`, `bin_paths`, `threading`, `subprocess`, `re`, `logging`, `os`, `time`, `dataclasses.dataclass`, `pathlib.Path`  
**Top-level global state**: `_MODEL_CACHE`, `_MODEL_CACHE_LOCK`, `_MODEL_TRANSCRIBE_LOCKS`, `_WHISPER_CACHE_DIR`, `WORD_MIN_GAP_SEC`, `WORD_MIN_DURATION_SEC`, `WORD_MERGE_SHORTER_THAN_SEC`, `_HL_OPEN`, `_HL_CLOSE`, `_PRESETS`, `_STYLE_ALIASES`, `_DEFAULT_PRESET_ID`, `_PRESET_MOTION_FX`, `_MOTION_FX_DEFAULT`, `BOUNCE_FX`, `_WIDE_CHARS`, `_NARROW_CHARS`, `_HOOK_EMPHASIS_WORDS`, `_EMPH_CONTRAST`, `_EMPH_EMOTIONAL`, `_EMPH_URGENCY`, `_NUMBER_RE`, `_INTEL_*`, `_PUNCT_PAUSE_RE`, `_CLAUSE_STARTERS`, `_PREVIEW_ASPECT_RES`, `_PREVIEW_FONTS_DIR`

**Public functions (13 confirmed callers from outside)**:
`srt_to_ass_bounce`, `srt_to_ass_karaoke`, `slice_srt_by_time`, `slice_srt_to_text`, `slice_srt_to_output_timeline`, `has_audio_stream`, `apply_market_line_break_to_srt`, `apply_market_hook_text_to_srt`, `apply_hook_subtitle_format`, `resolve_hook_overlay_text`, `subtitle_emphasis_pass`, `parse_srt_blocks`, `write_srt_blocks`, `resegment_srt_for_readability`, `transcribe_to_srt`, `extract_audio_for_transcription`, `format_srt_timestamp`, `get_whisper_model`, `normalize_subtitle_style_id`, `render_subtitle_preview`, `apply_subtitle_execution_hints`, `_hex_to_ass` (deferred from render_pipeline.py)

---

## 2. Why This Split Is Lower Risk Than `render_pipeline` But Still Sensitive

**Lower risk factors**:
- `subtitle_engine.py` has no closures over render-job local state — all functions take explicit arguments
- The module has identifiable clusters: each section has a clear `# ---` separator comment
- Existing test coverage for the slice/output-timeline path (`test_slice_srt_to_output_timeline.py`)
- No thread-pool state (unlike render_pipeline's ThreadPoolExecutor)
- No cancel events or job lifecycle coupling

**Still sensitive factors**:
- Hard `import whisper` at line 9 — if Whisper is not installed, the entire module fails to load. Any extracted module containing whisper must handle optional import.
- `_MODEL_CACHE`, `_MODEL_CACHE_LOCK`, `_MODEL_TRANSCRIBE_LOCKS` are module-level singletons — they must live in exactly one place (transcription.py) and must not be re-initialized by other modules
- Timing correctness is a hard invariant — `slice_srt_by_time`, `slice_srt_to_output_timeline`, and the `ass-before-setpts` contract must be preserved exactly; any off-by-one in timestamp conversion breaks subtitle sync
- `_PRESETS` table contains hard-coded ASS color/style values — no value may change during extraction
- `_STYLE_ALIASES` backward-compat table must survive intact for old job configs
- `_HL_OPEN`/`_HL_CLOSE` (private Unicode PUA codepoints) are shared across emphasis, ASS escaping, and the karaoke pipeline — must be defined once and imported everywhere

---

## 3. Full Function Inventory by Cluster

### Cluster A — Styles / Presets (~220 lines: 29–44, 427–681)

| Symbol | Type | Notes |
|---|---|---|
| `_compute_subtitle_scale(play_res_x, play_res_y)` | fn | Font/outline/shadow scale from resolution |
| `_compute_margin_v(play_res_x, play_res_y)` | fn | Bottom margin from aspect ratio |
| `BOUNCE_FX` | const | Legacy backward-compat string — must remain exported |
| `_PRESET_MOTION_FX` | dict | Per-preset pop-in animation tags |
| `_MOTION_FX_DEFAULT` | const | Fallback animation tag |
| `_get_motion_fx(preset_id)` | fn | Look up motion fx for preset |
| `ASSPreset` | dataclass | Immutable style descriptor (21 fields) |
| `_PRESETS` | dict | 11 canonical presets |
| `_STYLE_ALIASES` | dict | 5 backward-compat alias mappings |
| `_DEFAULT_PRESET_ID` | const | "tiktok_bounce_v1" |
| `_HL_OPEN`, `_HL_CLOSE` | const | PUA Unicode highlight delimiters (shared with readability + ass_core) |
| `normalize_subtitle_style_id(style_id)` | fn | Lowercase → alias → fallback |
| `get_subtitle_preset(style_id)` | fn | Return ASSPreset from _PRESETS |
| `build_ass_style_line(preset, ...)` | fn | ASS Style line + line_fx tag from preset |

### Cluster B — SRT Core (~190 lines: 65–254 + _run_with_retry)

| Symbol | Type | Notes |
|---|---|---|
| `format_srt_timestamp(seconds)` | fn | seconds → HH:MM:SS,mmm |
| `parse_srt_timestamp(ts)` | fn | HH:MM:SS,mmm → seconds |
| `_parse_srt_blocks(srt_path)` | fn | Internal parser (text joined as single string) |
| `parse_srt_blocks(srt_path)` | fn | Public round-trip parser (preserves newlines) |
| `write_srt_blocks(blocks, srt_path)` | fn | Write parsed blocks back to SRT |
| `slice_srt_by_time(...)` | fn | Slice SRT by time range + optional playback speed |
| `slice_srt_to_output_timeline(...)` | fn | Delegates to slice_srt_by_time with TimelineMap.effective_speed |
| `slice_srt_to_text(...)` | fn | Extract plain text for time range (no file write) |
| `_run_with_retry(command, retries, wait_sec)` | fn | Generic subprocess retry — shared with transcription and ass_core |

`slice_srt_to_output_timeline` depends on `TimelineMap` from `app.domain.timeline` — the only domain import. This dependency is correct per the layer rules.

### Cluster C — ASS Core (~370 lines: 684–717, 806–1046, 1218–1315)

| Symbol | Type | Notes |
|---|---|---|
| `_ass_time(seconds)` | fn | seconds → H:MM:SS.cc ASS format |
| `_ass_escape_text(text)` | fn | Escape for ASS Dialogue Text; resolves _HL_OPEN/_HL_CLOSE markers |
| `_ass_highlight_tags(market)` | fn | Market-specific ASS inline color tags |
| `_hex_to_ass(hex_color, alpha)` | fn | CSS #RRGGBB → ASS &HAABBGGRR |
| `_safe_filter_path(p)` | fn | Escape path for ffmpeg filter value |
| `srt_to_ass_bounce(srt_path, ass_path, ...)` | fn | Main ASS converter — bounce/viral styles |
| `srt_to_ass_karaoke(srt_path, ass_path, ...)` | fn | Karaoke-style ASS converter |
| `burn_subtitle_onto_video(...)` | fn | Burn ASS onto video via ffmpeg |
| `_PREVIEW_ASPECT_RES` | dict | Resolution map per aspect ratio |
| `_PREVIEW_FONTS_DIR` | const | Bundled fonts directory path |
| `render_subtitle_preview(...)` | fn | Render PNG preview frame with style applied |

Dependencies: `styles.py` (ASSPreset, get_subtitle_preset, build_ass_style_line, _compute_margin_v, _compute_subtitle_scale, _HL_OPEN, _HL_CLOSE), `srt_core.py` (parse_srt_timestamp, _parse_srt_blocks, _run_with_retry), `readability.py` (_break_by_visual_width used inside srt_to_ass_bounce)

### Cluster D — Readability (~500 lines: 729–803, 1475–1899)

| Symbol | Type | Notes |
|---|---|---|
| `_WIDE_CHARS`, `_NARROW_CHARS` | frozenset | Character width estimation constants |
| `_approx_visual_width(text)` | fn | Estimate rendered width in em units |
| `_break_by_visual_width(text, max_em, max_lines)` | fn | Insert newlines to keep lines in max_em; used by ass_core |
| `_is_cjk(text)` | fn | CJK/Hangul/Hiragana/Katakana detection |
| `_emphasis_level(preset_id)` | fn | Returns "strong"/"medium"/"subtle"/"minimal"/"word_only" |
| `_EMPH_CONTRAST`, `_EMPH_EMOTIONAL`, `_EMPH_URGENCY` | frozenset | Emphasis vocabulary sets |
| `_HOOK_EMPHASIS_WORDS` | frozenset | Hook/emphasis word set (shared with text_transforms) |
| `_NUMBER_RE` | regex | Match monetary/percentage/multiplier patterns |
| `_should_emphasize(token, level)` | fn | Determine if token deserves emphasis |
| `_uppercase_emphasis_words(text)` | fn | Uppercase emphasis-class words |
| `_insert_emphasis_markers(text, market, level)` | fn | Wrap tokens with _HL_OPEN/_HL_CLOSE |
| `_semantic_wrap_block(text, max_em)` | fn | Midpoint wrap with orphan/widow avoidance |
| `_INTEL_MAX_WPS`, `_INTEL_MAX_WORDS`, etc. | const | Readability tuning (env-overridable) |
| `_PUNCT_PAUSE_RE`, `_CLAUSE_STARTERS` | const/frozenset | Phrase boundary detection |
| `_find_phrase_split(words, max_words)` | fn | Find best semantic split index |
| `_split_block_semantic(text, start, end, ...)` | fn | Recursively split SRT block |
| `resegment_srt_for_readability(srt_path, ...)` | fn | CapCut-style reading comfort re-segmentation |
| `subtitle_emphasis_pass(blocks, preset_id, ...)` | fn | Unified emphasis pass (entry point) |

Dependencies: `styles.py` (get_subtitle_preset, normalize_subtitle_style_id, _HL_OPEN, _HL_CLOSE)

### Cluster E — Text Transforms (~350 lines: 1091–1136, 1317–1473, 1902–1970)

| Symbol | Type | Notes |
|---|---|---|
| `resolve_hook_overlay_text(...)` | fn | Resolve hook text from explicit or first SRT block |
| `apply_market_line_break_to_srt(srt_path, market_payload)` | fn | Re-wrap to market word count policy; deferred import from market_subtitle_policy |
| `apply_market_hook_text_to_srt(srt_path, hook_text, ...)` | fn | Replace opening subtitle hook zone |
| `format_hook_subtitle(text)` | fn | Format one subtitle block for visual impact |
| `apply_hook_subtitle_format(srt_path, max_hook_blocks)` | fn | Apply impact formatting to opening blocks |
| `apply_subtitle_execution_hints(blocks, subtitle_execution)` | fn | Consume AI subtitle execution metadata; pure dict processing, no timing mutation |

Dependencies: `srt_core.py` (_parse_srt_blocks, format_srt_timestamp), `readability.py` (_HOOK_EMPHASIS_WORDS)

### Cluster F — Transcription (~210 lines: 1–27 + 47–425)

| Symbol | Type | Notes |
|---|---|---|
| `_MODEL_CACHE`, `_MODEL_CACHE_LOCK`, `_MODEL_TRANSCRIBE_LOCKS` | module state | Must be module-level singletons in transcription.py — never initialized in other modules |
| `_WHISPER_CACHE_DIR` | const | Project-local Whisper model cache dir |
| `WORD_MIN_GAP_SEC`, `WORD_MIN_DURATION_SEC`, `WORD_MERGE_SHORTER_THAN_SEC` | const | Word normalization bounds |
| `get_whisper_model(model_name)` | fn | Thread-safe model load+cache |
| `_get_transcribe_lock(model_name)` | fn | Per-model threading.Lock creation |
| `_transcribe_with_retry(model, audio_path, ...)` | fn | Whisper transcribe with retry |
| `_ensure_ffmpeg_in_path_for_whisper()` | fn | Add FFmpeg bin dir to PATH for Whisper |
| `has_audio_stream(video_path)` | fn | Deferred-import delegate to render_engine._has_audio_stream — **cross-module coupling** |
| `extract_audio_for_transcription(video_path, wav_path, ...)` | fn | Extract 16kHz WAV via ffmpeg |
| `transcribe_to_srt(video_path, srt_path, ...)` | fn | Main transcription entry point |
| `_write_word_level_srt(result, srt_path)` | fn | Write word-level SRT from Whisper result |
| `_write_segment_level_srt(result, srt_path)` | fn | Write segment-level SRT |

Dependencies: `srt_core.py` (format_srt_timestamp, _run_with_retry), `app.services.render.ffmpeg_helpers._has_audio_stream` (resolve coupling — see §12)

---

## 4. Target Module Tree

```
backend/app/services/subtitles/
├── __init__.py                 ← re-exports all public names (built incrementally)
├── styles.py                   ← ASSPreset, preset table, aliases, compute helpers (~220 lines)
├── srt_core.py                 ← timestamps, SRT parse/write, slice, _run_with_retry (~190 lines)
├── readability.py              ← visual width, line-break, emphasis, resegment (~500 lines)
├── ass_core.py                 ← ASS formatting, srt_to_ass_bounce/karaoke, burn, preview (~370 lines)
├── text_transforms.py          ← market/hook text transforms, AI hints (~350 lines)
└── transcription.py            ← Whisper model cache, audio extraction, transcribe_to_srt (~210 lines)
```

Shim retained:

```
backend/app/services/subtitle_engine.py  ← ~70-line re-export shim (built in Phase 4G.6)
```

**Estimated total**: 1,840 lines across modules + ~70-line shim ≈ original 1,970 lines

---

## 5. Module Responsibility Map

| Module | Owns | Does NOT own |
|---|---|---|
| `styles.py` | ASSPreset definition, preset table, style resolution, compute helpers | Timestamp parsing, file I/O, Whisper |
| `srt_core.py` | Timestamp format/parse, SRT parse/write, slice-by-time, output timeline, `_run_with_retry` | ASS conversion, style presets, Whisper |
| `readability.py` | Visual width estimation, line-break, emphasis vocabulary, `subtitle_emphasis_pass`, resegmentation | Style definitions, ASS header generation, file reading |
| `ass_core.py` | ASS header/dialogue generation, `srt_to_ass_bounce`, `srt_to_ass_karaoke`, burn, preview | Readability logic, Whisper, SRT slicing |
| `text_transforms.py` | Market/hook text mutations on SRT blocks, AI execution hint consumption | Style rendering, transcription, readability resegmentation |
| `transcription.py` | Whisper model singleton, model locking, audio extraction, `transcribe_to_srt` | ASS conversion, SRT slicing, style definitions |

---

## 6. Dependency Direction Rules

```
styles.py           → [no subtitle deps]
srt_core.py         → app.domain.timeline (TimelineMap only)
readability.py      → styles.py
ass_core.py         → styles.py + srt_core.py + readability.py
text_transforms.py  → srt_core.py + readability.py (_HOOK_EMPHASIS_WORDS)
transcription.py    → srt_core.py (format_srt_timestamp, _run_with_retry)
                    → app.services.render.ffmpeg_helpers (_has_audio_stream — deferred)
```

Full dependency DAG (no cycles):

```
TimelineMap (domain)
    ↑
srt_core.py
    ↑               ↑
styles.py       transcription.py
    ↑               
readability.py  
    ↑       ↑       
ass_core.py   text_transforms.py
```

**FORBIDDEN**:
- `styles.py` may not import from any other subtitle module
- `srt_core.py` may not import from `styles.py`, `ass_core.py`, `readability.py`, `text_transforms.py`, or `transcription.py`
- `transcription.py` may not import from `ass_core.py`, `styles.py`, or `readability.py`
- Any circular import is a blocker

---

## 7. Backward Compatibility Strategy

`subtitle_engine.py` becomes a pure re-export shim after all modules are extracted:

```python
# subtitle_engine.py — compatibility shim (Phase 4G.6+)
# All callers of app.services.subtitle_engine continue to work without changes.

from app.services.subtitles.styles import (
    ASSPreset, BOUNCE_FX, get_subtitle_preset, normalize_subtitle_style_id,
    build_ass_style_line, _PRESETS, _STYLE_ALIASES, _DEFAULT_PRESET_ID,
    ...
)
from app.services.subtitles.srt_core import (
    format_srt_timestamp, parse_srt_timestamp,
    parse_srt_blocks, write_srt_blocks, _parse_srt_blocks,
    slice_srt_by_time, slice_srt_to_output_timeline, slice_srt_to_text,
    _run_with_retry,
)
from app.services.subtitles.readability import (
    subtitle_emphasis_pass, resegment_srt_for_readability,
    _break_by_visual_width, _approx_visual_width,
    _HOOK_EMPHASIS_WORDS, ...
)
from app.services.subtitles.ass_core import (
    srt_to_ass_bounce, srt_to_ass_karaoke, burn_subtitle_onto_video,
    render_subtitle_preview, _hex_to_ass, _ass_time, _ass_escape_text,
    ...
)
from app.services.subtitles.text_transforms import (
    apply_market_line_break_to_srt, apply_market_hook_text_to_srt,
    apply_hook_subtitle_format, format_hook_subtitle,
    resolve_hook_overlay_text, apply_subtitle_execution_hints,
)
from app.services.subtitles.transcription import (
    get_whisper_model, transcribe_to_srt, extract_audio_for_transcription,
    has_audio_stream, WORD_MIN_GAP_SEC, WORD_MIN_DURATION_SEC, ...
)
```

**Shim policy**: Do NOT remove `subtitle_engine.py` after extraction. Keep it until all 13+ callers are explicitly migrated. Caller migration is Phase 4G.7+.

---

## 8. Timing Invariants

These MUST be bit-identical before and after extraction:

| Invariant | Owner after extraction | Test coverage |
|---|---|---|
| `slice_srt_by_time()` — timestamps subtract `start_sec`, divide by `playback_speed` | `srt_core.py` | `test_slice_srt_to_output_timeline.py` |
| `slice_srt_to_output_timeline()` — divides by `timeline.effective_speed` via `slice_srt_by_time` | `srt_core.py` | `test_slice_srt_to_output_timeline.py` |
| `format_srt_timestamp()` — must round-trip with `parse_srt_timestamp()` | `srt_core.py` | New: `test_subtitle_srt_core.py` |
| `_ass_time()` — centisecond precision, `H:MM:SS.cc` format | `ass_core.py` | New: `test_subtitle_ass_core.py` |
| Legacy path: ASS timestamps are in source-clip seconds (ass-before-setpts) | `ass_core.py` | Existing: `test_composite_overlays.py` (indirect) |
| Overlay path: ASS timestamps are in output seconds (slice_srt_to_output_timeline) | `srt_core.py` | `test_slice_srt_to_output_timeline.py` |

**Critical**: `slice_srt_by_time()` signature, parameter defaults, and return dict schema must not change. `render_pipeline.py` calls it with all parameters.

---

## 9. ASS/Subtitle Rendering Invariants

These must survive the extraction unchanged:

1. **`srt_to_ass_bounce` vf_chain hook**: `render_pipeline.py` passes the ASS path directly to FFmpeg `ass=` filter; the file content must be byte-identical.
2. **`_ass_escape_text` resolves `_HL_OPEN`/`_HL_CLOSE`**: These PUA codepoints are internal delimiters injected by `_insert_emphasis_markers` and resolved in `_ass_escape_text`. Both functions must share the same codepoints.
3. **`srt_to_ass_karaoke` fallback to `srt_to_ass_bounce`**: When segment-level SRT is detected, `srt_to_ass_karaoke` calls `srt_to_ass_bounce` — both must be co-located in `ass_core.py` or `srt_to_ass_karaoke` must import `srt_to_ass_bounce`.
4. **Margin computation**: `_compute_margin_v` and `_compute_subtitle_scale` are called from `srt_to_ass_bounce`, `srt_to_ass_karaoke`, and `build_ass_style_line`. All must import from the same definition in `styles.py`.
5. **`burn_subtitle_onto_video` uses `_run_with_retry`**: Must import from `srt_core.py`. Behavior and retry count semantics must not change.

---

## 10. Style/Preset Invariants

These must not change in any extraction phase:

1. **Preset IDs are externally serialized**: job configs, render payloads, API requests use preset ID strings (e.g., `"viral_bold"`, `"tiktok_bounce_v1"`). Any rename breaks existing jobs.
2. **`_STYLE_ALIASES` backward-compat table**: 5 old IDs (`"viral_clean_montserrat"`, etc.) map to canonical IDs. Must stay intact.
3. **`BOUNCE_FX` legacy constant**: old code may import it directly. Must remain a module-level export from both `styles.py` and the `subtitle_engine.py` shim.
4. **ASSPreset field order**: the dataclass field order is frozen. Adding new fields requires `field(default=...)` to maintain backward-compat deserialization if presets are ever stored.
5. **`_DEFAULT_PRESET_ID = "tiktok_bounce_v1"`**: any caller that passes `style_id=None` gets this preset. Must not change.

---

## 11. Transcription/Whisper Risk Analysis

`transcription.py` is the highest-risk extraction target:

| Risk | Description | Mitigation |
|---|---|---|
| Hard `import whisper` | If Whisper not installed, entire original module fails. After extraction, only `transcription.py` fails — all other modules import cleanly. | In `transcription.py`: wrap with `try: import whisper\nexcept ImportError: whisper = None`. Guard all uses with `if whisper is None: raise ImportError(...)` |
| `_MODEL_CACHE` singleton | Must be exactly one copy in one module. Two modules with `_MODEL_CACHE = {}` would create two independent caches, causing double-loading. | `_MODEL_CACHE`, `_MODEL_CACHE_LOCK`, `_MODEL_TRANSCRIBE_LOCKS` live ONLY in `transcription.py`. Never import them from outside. |
| `_WHISPER_CACHE_DIR.mkdir()` at module load | Creates directory on import. Acceptable for production but noise in tests. | Test isolation: monkeypatch `_WHISPER_CACHE_DIR` before import, or use tmpdir. |
| Concurrent model load | `_MODEL_CACHE_LOCK` held during model load (30–60s on CPU). All callers block. | No change required — this is the existing behavior. Document in test strategy that no real model loads in unit tests. |
| `has_audio_stream()` coupling | Calls `from app.services.render_engine import _has_audio_stream` (deferred). After extraction, must be updated to `from app.services.render.ffmpeg_helpers import _has_audio_stream`. | Fix the import path during Phase 4G.6. Covered by `test_probe_unification.py` (3 existing tests). |

---

## 12. Cross-Module Coupling Audit

### Found coupling: `subtitle_engine.has_audio_stream` → `render_engine._has_audio_stream`

**Location**: `subtitle_engine.py:280–289`

```python
def has_audio_stream(video_path: str) -> bool:
    from app.services.render_engine import _has_audio_stream   # ← deferred import
    return _has_audio_stream(video_path)
```

**Analysis**: The deferred import (inside function body) prevents a circular import at module load time. This is correctly implemented. However, it couples `subtitle_engine` to the `render_engine` shim.

**Resolution** (Phase 4G.6, not now): Change the deferred import to target the actual implementation:

```python
def has_audio_stream(video_path: str) -> bool:
    from app.services.render.ffmpeg_helpers import _has_audio_stream
    return _has_audio_stream(video_path)
```

This bypasses the shim and imports directly from the extracted module — correct per the dependency direction rules.

**Risk**: Low. `_has_audio_stream` signature and behavior are unchanged. The only risk is if `ffmpeg_helpers` imports from `subtitle_engine` (it does not — confirmed by audit).

**Test coverage**: `test_probe_unification.py` has 4 tests for `subtitle_engine.has_audio_stream`. These tests use monkeypatching and must continue to pass after the import path change.

### No other active cross-module couplings found

All other imports in `subtitle_engine.py`:
- `app.domain.timeline.TimelineMap` — correct direction (domain → no deps)
- `app.services.bin_paths.get_ffmpeg_bin` — utility layer, no cycle risk
- `app.services.market_subtitle_policy` — deferred import inside `apply_market_line_break_to_srt`, correct
- `app.services.render_engine._has_audio_stream` — documented above

---

## 13. Proposed Sub-Phases

| Sub-phase | Extract | Dependencies | Risk | Lines |
|---|---|---|---|---|
| **4G.1** | `styles.py` | None (pure data) | Low | ~220 |
| **4G.2** | `srt_core.py` | `app.domain.timeline` only | Low | ~190 |
| **4G.3** | `readability.py` | `styles.py` | Medium-Low | ~500 |
| **4G.4** | `ass_core.py` | `styles.py` + `srt_core.py` + `readability.py` | Medium | ~370 |
| **4G.5** | `text_transforms.py` | `srt_core.py` + `readability.py` | Medium-Low | ~350 |
| **4G.6** | `transcription.py` + shim | `srt_core.py` + ffmpeg_helpers fix | High | ~210 |
| **4G.7** | Import audit + caller migration | All modules stable | Low | — |

**Rationale for ordering**: Each phase only depends on modules extracted in prior phases. `styles.py` and `srt_core.py` are the foundation — zero subtitle-internal deps. Readability depends on styles. ASS core depends on all three foundations. Transcription is last because of the Whisper singleton risk and the `has_audio_stream` import fix.

**Inter-phase rule**: Each phase must:
1. Create the new module
2. Add all functions to `subtitles/__init__.py` re-exports
3. Add backward-compat re-exports to `subtitle_engine.py` shim
4. Write test file for the new module
5. Run full test suite — must not exceed 8 known failures

---

## 14. First Implementation Phase Recommendation

**Start with Phase 4G.1 — Extract `styles.py`.**

Reasons:
- Zero internal dependencies — only standard Python (dataclasses, typing)
- The `ASSPreset` dataclass and `_PRESETS` table are the most clearly-bounded cluster
- No file I/O, no subprocess, no threading, no optional dependencies
- Any mistake is immediately caught by the existing tests that import `srt_to_ass_bounce` (which uses the presets)
- Sets up the import pattern for all subsequent phases
- Creates the `subtitles/` package skeleton needed by all phases

**Phase 4G.1 scope**:
- Create `backend/app/services/subtitles/` package
- Create `backend/app/services/subtitles/__init__.py`
- Create `backend/app/services/subtitles/styles.py` with all Cluster A content
- Add `styles.py` exports to `subtitles/__init__.py`
- Add re-export block to `subtitle_engine.py` (shim for styles)
- Write `backend/tests/test_subtitle_styles.py`
- Verify: `from app.services.subtitle_engine import get_subtitle_preset, ASSPreset, BOUNCE_FX` still works

---

## 15. Test Strategy

### Existing tests (keep passing)

| File | Tests | What they cover |
|---|---|---|
| `test_slice_srt_to_output_timeline.py` | — | `slice_srt_to_output_timeline()` output-timeline conversion |
| `test_probe_unification.py` | 4 | `has_audio_stream()` delegation to render_engine |
| `test_market_subtitle_linebreak.py` | — | `apply_market_line_break_to_srt()` |
| `test_subtitle_guards.py` | — | `_run_with_retry()` |
| `test_subtitle_transcription_adapters.py` | — | `parse_srt_blocks()` round-trip |
| `test_ai_phase17_dynamic_subtitles.py` | 12 | `apply_subtitle_execution_hints()` |

### New tests per module

| Test file | Module | Minimum assertions |
|---|---|---|
| `test_subtitle_styles.py` | `styles.py` | ASSPreset fields unchanged; preset IDs in _PRESETS; alias resolution; default preset; BOUNCE_FX value unchanged; old import path still works |
| `test_subtitle_srt_core.py` | `srt_core.py` | Timestamp format/parse roundtrip; parse/write SRT roundtrip; slice_srt_by_time at speed=1.0; slice_srt_by_time at speed=1.15; slice_srt_to_output_timeline delegates correctly; old import path works |
| `test_subtitle_readability.py` | `readability.py` | _approx_visual_width known values; _break_by_visual_width at max_em; subtitle_emphasis_pass no timing mutation; resegment_srt_for_readability output count; old import path works |
| `test_subtitle_ass_core.py` | `ass_core.py` | _ass_time precision; _ass_escape_text braces/backslashes; srt_to_ass_bounce creates valid ASS header (mock subprocess); srt_to_ass_karaoke fallback; old import path works |
| `test_subtitle_text_transforms.py` | `text_transforms.py` | resolve_hook_overlay_text explicit/SRT paths; apply_market_hook_text_to_srt safe no-op on empty; apply_subtitle_execution_hints fallback on None; old import path works |
| `test_subtitle_transcription.py` | `transcription.py` | Module imports without whisper if not installed; get_whisper_model cache (mock); _run_with_retry retry count; has_audio_stream delegates correctly; old import path works |
| `test_subtitle_engine_compat.py` | shim | All 22 public names importable from `app.services.subtitle_engine`; same object identity as from `app.services.subtitles.*` |

### Test isolation rules

- **No real Whisper model loads** in any test. Mock `whisper.load_model`.
- **No real FFmpeg subprocess calls** in unit tests. Mock `_run_with_retry` / `subprocess.run`.
- **Timing precision tests** use exact float comparison with tolerance ≤ 0.001s.
- **ASS golden string tests** check for substring patterns, not full file content — ASS header line order is stable but shouldn't be over-specified.

---

## 16. Mock/Patch Migration Strategy

Existing tests mock `subtitle_engine` symbols via the old path:

```python
# existing (before extraction)
from app.services.subtitle_engine import _run_with_retry
```

After extraction, these continue to work because the shim re-exports the symbol. No changes needed to existing tests during any Phase 4G sub-phase.

When callers are eventually migrated (Phase 4G.7+), mock paths update to:

```python
from app.services.subtitles.srt_core import _run_with_retry
```

Or mock the module directly:

```python
monkeypatch.setattr("app.services.subtitles.srt_core._run_with_retry", mock_fn)
```

**Rule**: Mocking `app.services.subtitle_engine._run_with_retry` and mocking `app.services.subtitles.srt_core._run_with_retry` are different patch targets. Tests that use the shim path will still work because the shim imports the object, but the mock may not propagate to the implementation module. This is the standard shim-import mock isolation issue — document per test and verify as part of Phase 4G test validation.

---

## 17. Docs Sync Strategy

| Doc | What needs updating | When |
|---|---|---|
| `CURRENT_RENDER_ARCHITECTURE.md` | Add `services/subtitles/` to system tree | Per sub-phase as modules are added |
| `RENDER_BOUNDARIES.md` | No changes needed (render layer ownership unchanged) | Not needed |
| `TIMELINE_SEMANTICS.md` | No changes needed (timing contracts are same) | Not needed |
| `MIGRATION_HISTORY.md` | New entry per sub-phase | Per sub-phase commit |
| `TECHNICAL_DEBT_REPORT.md` | H2 `subtitle_engine.py` god file — mark RESOLVED when shim complete | Phase 4G.6 |
| `SCORECARD.md` | `subtitle_engine.py at 1970 lines` — update post-split | Phase 4G.6 |
| `BRUTAL_REVIEW_SUMMARY.md` | God file section — update | Phase 4G.6 |

---

## 18. What Must NOT Change

1. **All 22+ public symbols** currently exported from `subtitle_engine.py` must remain importable from `app.services.subtitle_engine` throughout all phases.
2. **`slice_srt_by_time()` signature, defaults, return dict schema** — not one field may change.
3. **`slice_srt_to_output_timeline()` must continue to call `slice_srt_by_time` with `apply_playback_speed=True`** — the overlay path depends on this behavior.
4. **`_PRESETS` table values** — no ASS color, font, size, or boundary value may change.
5. **`_STYLE_ALIASES` table** — no removal or remapping. Old job configs may contain removed alias IDs.
6. **`_HL_OPEN = ""` / `_HL_CLOSE = ""`** — these codepoints are injected by `_insert_emphasis_markers` and resolved by `_ass_escape_text`. If they diverge between modules (e.g., two copies with different values), emphasis highlighting silently breaks. They must be defined in exactly one module (`styles.py`) and imported by all other modules that use them.
7. **Whisper model cache** — `_MODEL_CACHE` is a process-level singleton. No extraction may create a second instance. Only `transcription.py` defines it.
8. **No `whisper` import at the top of any module except `transcription.py`** — other modules must not hard-import Whisper.
9. **`has_audio_stream()` must remain a public name** in `subtitle_engine.py` shim — `render_pipeline.py` imports it from there.
10. **`_run_with_retry` stays identical** — same retry semantics, same exception re-raise behavior.

---

## 19. Phase 4G.1 Prompt Recommendation

The first implementation sub-phase should be provided with the following context:

```
Phase 4G.1 — Extract subtitle styles to services/subtitles/styles.py

Target: extract Cluster A (styles/presets) from subtitle_engine.py into a new module.

Source range: lines 21–22 (_HL_OPEN, _HL_CLOSE), lines 29–44 (_compute_subtitle_scale,
_compute_margin_v), lines 427–681 (BOUNCE_FX, _PRESET_MOTION_FX, _MOTION_FX_DEFAULT,
_get_motion_fx, ASSPreset, _PRESETS, _STYLE_ALIASES, _DEFAULT_PRESET_ID,
normalize_subtitle_style_id, get_subtitle_preset, build_ass_style_line)

Actions:
1. Create backend/app/services/subtitles/__init__.py (empty or minimal)
2. Create backend/app/services/subtitles/styles.py with the above symbols verbatim
3. In subtitle_engine.py, add a re-export block at bottom for all styles symbols
   (do NOT delete anything from subtitle_engine.py yet)
4. Write backend/tests/test_subtitle_styles.py with: preset IDs in _PRESETS,
   normalize_subtitle_style_id alias resolution, BOUNCE_FX value unchanged,
   ASSPreset is frozen dataclass, old import path works (same object identity)
5. Run: python -m compileall app && python -m pytest tests/test_subtitle_styles.py
   tests/test_subtitle_engine_compat.py -v

Constraints:
- Do NOT delete anything from subtitle_engine.py — only add re-exports
- Do NOT move transcription.py functions in this phase
- Do NOT change any ASS color values, preset IDs, or alias mappings
- Test baseline must remain 8 known failures
```

---

## 20. Definition of Done

Phase 4G planning (4G.0) is done when:

- [x] `PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md` exists and is committed
- [x] All 6 clusters audited with full function inventory
- [x] Target module tree with dependency DAG is documented
- [x] Cross-module coupling (`has_audio_stream` → `render_engine._has_audio_stream`) is documented with resolution plan
- [x] Whisper singleton risk is documented
- [x] `_HL_OPEN`/`_HL_CLOSE` shared constant risk is documented
- [x] `_run_with_retry` placement decision is documented (lives in `srt_core.py`)
- [x] Sub-phase order is justified (styles → srt_core → readability → ass_core → text_transforms → transcription → shim)
- [x] Test strategy is documented per module
- [x] What must NOT change is documented
- [x] Phase 4G.1 prompt recommendation is written
- [x] MIGRATION_HISTORY.md updated (4G.0 planning entry)
- [x] TECHNICAL_DEBT_REPORT.md H2 and PHASE_4A_BACKEND_MODULARIZATION_PLAN.md updated
- [x] No backend code changed
- [x] Committed and pushed

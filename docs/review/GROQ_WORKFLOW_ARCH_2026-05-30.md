# Groq Workflow & Architecture Update — 2026-05-30

**Branch:** `restructure/output-timeline-architecture`  
**Baseline tests:** 7589 passed, 1 pre-existing failure, 2 skipped  
**Prior relevant doc:** `RESTRUCTURE_PHASE_A5_A7_2026-05-28.md`

---

## 1. Tổng quan thay đổi

Session này thực hiện 3 nhóm thay đổi lớn trên nhánh hiện tại:

| Phase | Mô tả | Risk |
|-------|-------|------|
| A–B | Groq AI segment selection — backend pipeline | MEDIUM |
| C | Performance: motion_crop early exit, parallel analysis, PartContext | HIGH/MEDIUM |
| D–E–F | AI domain interfaces, Whisper warmup, UI mapping, integration tests | MEDIUM/LOW |

---

## 2. Workflow mới: Configure → Groq → Auto Render

### Luồng đầy đủ

```
[User] Configure
   ├── Aspect ratio (9:16 / 16:9 / 1:1 / 3:4 / 4:5)
   ├── Duration min/max (sec)
   ├── Output count
   ├── Quality / FPS
   ├── Subtitle style (min font 72px)
   ├── Translation settings
   ├── Groq API key (gsk_...) + Groq segment selection toggle
   └── Output directory

[POST /api/render/process]  ← RenderRequest với groq_analysis_enabled=True
   │
   ▼
[pipeline_pre_render.py] — run_pre_render_scenes()
   │
   ├── PARALLEL PRE-RUN (nếu cần cả scene detection + transcription)
   │   ├── Thread 1: detect_scenes()      ← scenedetect / TransNetV2
   │   └── Thread 2: transcribe_to_srt()  ← Whisper (faster-whisper)
   │   └── Kết quả → shared LRU cache → sequential blocks dưới đọc cache hit (instant)
   │
   ├── Scene detection block (cache hit → 0ms)
   ├── Phase 45: Early transcription (skip nếu parallel đã làm, hoặc cache hit)
   ├── Phase 46: Content analysis (từ SRT)
   │
   └── [groq_stage.py] — run_groq_segment_selection()
       ├── Đọc full_srt
       ├── Gọi Groq API (llama-3.1-8b-instant, ~1-3s, free tier)
       │   └── Prompt: chọn đúng output_count segments, min_sec ≤ duration ≤ max_sec
       ├── Parse response → List[GroqSegment]
       ├── Filter: score ≥ groq_min_quality_score (default 0.6)
       └── Convert → scored[] dicts (với clip_name, groq_title, groq_reason, source="groq")
           └── Replaces local heuristic scored[] nếu thành công
               └── Fallback: giữ local scored[] nếu Groq fail/unavailable

[pipeline_render_loop.py] — parallel part rendering
   │
   ├── Với mỗi segment từ scored[]:
   │   └── [part_renderer.py] — process_one_part()
   │       ├── Output filename:
   │       │   ├── Nếu clip_name có → "{clip_name}.mp4"  ← Groq natural name
   │       │   │   (e.g. "Bí quyết tăng view nhanh.mp4")
   │       │   │   Collision guard: nếu file đã tồn tại → "{clip_name}_{001}.mp4"
   │       │   └── Fallback → "{output_stem}_part_{001}.mp4"
   │       ├── FFmpeg cut (start → end)
   │       ├── Motion-aware crop:
   │       │   ├── Early exit: sample 24 frames → nếu không có face → dùng pixel-diff (fast)
   │       │   └── Full: MediaPipe face/pose + CSRT tracker + optical flow
   │       ├── Subtitle burn-in (min 72px font)
   │       └── QA validation (qa_pipeline.py — không bao giờ bypass)
   │
   └── Output: List[OutputClip] với clip_name, groq_title, groq_reason, viral_score...

[UI — StepResults]
   ├── Clip card: title từ groq_title || clip_name || "Clip 01"
   ├── "Groq AI" badge vàng (khi source == "groq")
   ├── groq_reason hiển thị italic
   └── Download filename = clip_name (e.g. "Bí quyết tăng view nhanh.mp4")
```

---

## 3. Files mới tạo

| File | Mục đích |
|------|----------|
| `app/ai/analysis/groq/__init__.py` | Export `select_segments`, `GroqSegment` |
| `app/ai/analysis/groq/prompts.py` | Build Groq prompt: constraints output_count, min/max sec, clip_name |
| `app/ai/analysis/groq/parser.py` | Parse JSON response → `List[GroqSegment]`, `sanitize_clip_name()` |
| `app/ai/analysis/groq/client.py` | AI-safe entry point (try/except → None), reuse `GroqProvider` |
| `app/orchestration/groq_stage.py` | Pipeline stage: đọc SRT → gọi Groq → convert → replace scored[] |
| `app/orchestration/parallel_analysis.py` | Parallel scene detection + transcription (ThreadPoolExecutor, max 2 workers) |
| `app/orchestration/context.py` | `PartContext` typed dataclass: `from_dict()`, `to_dict()`, composite score |
| `tests/test_groq_pipeline.py` | 41 integration tests: parser, PartContext, scored dict shape, domain imports |

---

## 4. Files sửa

| File | Thay đổi | Risk tier |
|------|----------|-----------|
| `app/core/config.py` | Thêm `GROQ_API_KEY`, `GROQ_DEFAULT_MODEL`, `GROQ_REQUEST_TIMEOUT`, `GROQ_MAX_SRT_CHARS` | LOW |
| `app/models/schemas.py` | Thêm 5 fields vào `RenderRequest`: `groq_analysis_enabled`, `groq_model`, `groq_content_language`, `groq_min_quality_score`, `groq_selection_strategy` (tất cả default False/None) | HIGH |
| `app/orchestration/pipeline_pre_render.py` | Parallel pre-run block + extend Phase 45 trigger cho `groq_analysis_enabled` | MEDIUM |
| `app/orchestration/stages/part_renderer.py` | Output filename: dùng `clip_name` từ Groq khi có (collision guard) | CRITICAL |
| `app/services/render/ffmpeg_helpers.py` | `_PROBE_CACHE`: `dict` → `OrderedDict` + eviction khi > 500 entries (LRU) | HIGH |
| `app/services/motion_crop.py` | Fix 16:9 dimension bug; thêm `_has_subject_in_sample()` early exit (24-frame sample) | CRITICAL |
| `app/services/subtitle_engine.py` (styles) | Font size minimum: 24px → 72px cho tất cả aspect ratios | MEDIUM |
| `app/services/subtitle_transcription_adapters.py` | Expose `warmup_fw_model(model_name)` public | MEDIUM |
| `app/main.py` | Startup: thêm Whisper model pre-load thread (env `WARMUP_WHISPER_MODEL`, default `small`) | HIGH |
| `app/ai/analysis/__init__.py` | Thêm `select_segments`, `GroqSegment` exports | LOW |
| `app/ai/director/__init__.py` | Public API: `create_ai_edit_plan`, schema types | LOW |
| `app/ai/platform/__init__.py` | Public API: `plan_platform_adaptation` | LOW |
| `app/ai/quality/__init__.py` | Public API: `evaluate_render_quality`, schema types | LOW |
| `app/ai/quality_gate/__init__.py` | Public API: `apply_quality_gate`, `apply_segment_quality_gate` | LOW |
| `frontend/src/types/api.ts` | `RenderRequest` +5 Groq fields; `JobPart` +`clip_name`, `groq_title`, `groq_reason`, `source` | MEDIUM |
| `frontend/src/features/.../render/types.ts` | `ConfigState` +`groqEnabled`, `groqModel`, `groqContentLanguage` | MEDIUM |
| `frontend/src/features/.../RenderWorkflow.tsx` | Defaults + payload mapping Groq fields | MEDIUM |
| `frontend/src/features/.../StepConfigure.tsx` | Groq section trong AI tab (toggle, model, language, note) | MEDIUM |
| `frontend/src/features/.../StepResults.tsx` | "Groq AI" badge, title từ `groq_title`/`clip_name`, download với tên tự nhiên | MEDIUM |
| `tests/test_subtitle_styles.py` | Cập nhật stale expectations (6 presets mới + 3 aliases mới + auto_scale flag) | LOW |

---

## 5. Kiến trúc AI module (5 domains)

```
app/ai/
├── analysis/          ← Domain 1: segment selection, cloud providers
│   ├── __init__.py    ← PUBLIC: select_segments, GroqSegment, HybridAnalyzer, ...
│   ├── groq/          ← Groq cloud: prompts, parser, client
│   └── cloud/         ← OpenAI, GroqProvider base
│
├── director/          ← Domain 2: edit plan orchestration
│   ├── __init__.py    ← PUBLIC: create_ai_edit_plan, AIEditPlan, ...
│   └── ai_director.py ← 4,631 lines (CRITICAL — không touch nếu không có plan)
│
├── platform/          ← Domain 3: per-clip platform adaptation hints
│   ├── __init__.py    ← PUBLIC: plan_platform_adaptation
│   └── platform_adapter.py
│
├── quality/           ← Domain 4: render quality evaluation
│   ├── __init__.py    ← PUBLIC: evaluate_render_quality, AIRenderQualityEvaluation
│   └── quality_evaluator.py
│
└── quality_gate/      ← Domain 5: quality-gated influence (Phase 59D)
    ├── __init__.py    ← PUBLIC: apply_quality_gate, apply_segment_quality_gate
    └── quality_gate_engine.py
```

**Rule:** Import từ `app.ai.<domain>` (public interface), không import trực tiếp từ sub-module nội bộ.

---

## 6. Performance improvements

| Cải thiện | Trước | Sau | Ghi chú |
|-----------|-------|-----|---------|
| Scene detection + transcription | Sequential (~60-90s) | Parallel (~30-60s) | Tiết kiệm 30-90s/job khi cả 2 đều cần |
| motion_crop subject tracking | Luôn dùng MediaPipe | Sample 24 frames trước → skip nếu không có face | Tiết kiệm 5-20s/clip khi video không có người |
| ffprobe probe cache | `dict` (unbounded) | `OrderedDict` LRU (max 500) | Ngăn memory leak trên job dài |
| Whisper model load | Lazy (mỗi job lần đầu tốn 5-15s) | Pre-load tại startup (background) | Job đầu tiên không bị delay |

---

## 7. Contracts giữ nguyên (không break)

- **Contract 1** — `result_json`: `output_rank_score`, `is_best_output`, `is_best_clip` vẫn có mặt
- **Contract 2** — `RenderRequest` fields mới đều default `False`/`None` → backward compat với stored jobs
- **Contract 3** — Tất cả AI modules: `select_segments()`, `warmup_fw_model()`, `_has_subject_in_sample()` đều `try/except → return False/None`
- **Contract 4/5** — Stage names frozen: `QUEUED → DOWNLOADING → RENDERING → DONE`, part names frozen
- **Contract 6** — `_emit_render_event` signature không thay đổi
- **Contract 7** — `data/app.db` không touched
- **Contract 8** — `qa_pipeline.py` không bypass

---

## 8. Kiến trúc Groq module

```
app/ai/analysis/groq/
├── __init__.py      ← export: select_segments, GroqSegment
├── prompts.py       ← build_segment_prompt(srt, count, min_sec, max_sec, lang)
│                       → (system_prompt, user_prompt)
│                       Hard constraints: EXACTLY count segments, duration bounds, clip_name
├── parser.py        ← parse_segment_response(raw, count, min_sec, max_sec, video_dur)
│                       → Optional[List[GroqSegment]]
│                       3-strategy JSON extraction: direct → markdown fence → first array
│                       sanitize_clip_name(): strip /\:*?"<>| giữ nguyên dấu cách + tiếng Việt
└── client.py        ← select_segments(...) → Optional[List[GroqSegment]]
                        AI-safe: try/except → None
                        Reuse GroqProvider từ app/ai/analysis/cloud/
```

### GroqSegment dataclass
```python
@dataclass
class GroqSegment:
    start: float      # seconds
    end: float        # seconds
    score: float      # 0.0–1.0
    clip_name: str    # "Bí quyết tăng view nhanh" — dùng làm output filename
    title: str        # display title
    reason: str       # lý do chọn segment này
```

### clip_name → output filename flow
```
Groq returns:  clip_name = "Bí quyết tăng view nhanh"
groq_stage:    seg["clip_name"] = "Bí quyết tăng view nhanh"
part_renderer: final_part = output_dir / "Bí quyết tăng view nhanh.mp4"
               (collision guard: nếu file tồn tại → "Bí quyết tăng view nhanh_001.mp4")
UI:            download attribute = "Bí quyết tăng view nhanh.mp4"
```

---

## 9. Parallel analysis architecture

```
parallel_analysis.py — run_parallel_analysis()
│
├── _do_parallel = auto_detect_scene AND need_transcription AND NOT resume
│
├── [YES] ThreadPoolExecutor(max_workers=2)
│   ├── Thread A: _scene_worker()
│   │   ├── check scene_cache_get()  → cache hit: return immediately
│   │   ├── detect_scenes()          → populate scene_cache_put()
│   │   └── return _SceneResult
│   │
│   └── Thread B: _transcription_worker()
│       ├── check resume condition
│       ├── check transcription_cache_get() → cache hit: copy SRT
│       ├── transcribe_with_adapter()       → populate transcription_cache_put()
│       └── return _TranscriptionResult
│
└── [NO] Run whichever single operation is needed (no thread overhead)

Return: ParallelAnalysisResult
  .scenes, .scene_ms, .scene_cache_hit, .scene_error
  .full_srt_available, .transcription_ms, .transcription_cache_hit, .transcription_error
  .scene_ok (property)
  .transcription_ok (property)
```

**Integration point:** `pipeline_pre_render.py:84-130` — chạy TRƯỚC sequential blocks, populate shared LRU cache → sequential blocks nhận cache hit (instant).

---

## 10. Test coverage mới

| Test class | Cases | Covers |
|-----------|-------|--------|
| `TestSanitizeClipName` | 7 | FS-invalid chars, Vietnamese, spaces, truncate |
| `TestParseSegmentResponse` | 9 | JSON strategies, duration bounds, video bounds, sort, clip |
| `TestPartContext` | 9 | Round-trip, extra keys, defaults, composite, is_high_motion |
| `TestGroqStageToDictShape` | 6 | Required fields, score scaling, clip_name, source="groq" |
| `TestParallelAnalysisResult` | 3 | Defaults, properties |
| `TestAIDomainInterfaces` | 6 | Domain __init__.py imports, __all__ exports |
| `TestWhisperWarmup` | 2 | Graceful failure when unavailable |
| **Total** | **41** | |

---

## 11. Known gaps / future work

| Gap | Mô tả | Priority |
|-----|-------|----------|
| Groq streaming | Hiện tại: single HTTP call. Future: stream tokens để giảm latency | LOW |
| Multi-ratio batching | Mỗi job hiện chỉ 1 aspect ratio. Multi-ratio cần schema + UI thay đổi lớn | MEDIUM |
| parallel_analysis heartbeat | Khi transcription chạy trong thread B, không có progress update lên UI | LOW |
| clip_name uniqueness | Groq có thể trả 2 segments cùng clip_name. Collision guard chỉ check file existence, không check in-flight segments | LOW |
| Electron deep link | `WARMUP_WHISPER_MODEL` env var cần được set trong Electron startup script | LOW |

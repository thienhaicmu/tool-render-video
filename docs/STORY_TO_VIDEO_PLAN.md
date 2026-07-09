# STORY_TO_VIDEO_PLAN.md — AI Story-to-Video Studio

> **Trạng thái:** PLAN — chờ duyệt. Chưa viết dòng code nào.
> **Nguồn:** Review toàn bộ Content Mode (`render_format="content"`) dựa trên
> implementation thật + chuỗi quyết định sản phẩm với chủ dự án (2026-07-09).
> **Nguyên tắc:** khi docs và code mâu thuẫn → **tin code**; đọc file ở trạng
> thái hiện tại trước khi sửa. Line/tier dưới đây là ảnh chụp lúc lập plan.
>
> Đây là mode render **thứ 4** (`render_format="story"`), thêm y hệt cách
> `recap` và `content` đã thêm — **composition, KHÔNG sửa** `render_pipeline.py`
> (clips), `recap_pipeline.py`, `content_pipeline.py`.

---

## 0. Mục tiêu

Biến Content Studio thành nền tảng **Story-to-Video**: nhận **nguyên một chương
truyện** (tiên hiệp / kiếm hiệp / ngôn tình / kinh dị / fantasy, nhiều nghìn từ),
AI hiểu sâu → tự dựng Storyboard → chia Shot → sinh lời kể + hình ảnh nhất quán →
render thành video hoàn chỉnh. Con người kiểm soát ở 3 cổng duyệt.

### Stack đã khoá

| Thành phần | Quyết định |
|-----------|-----------|
| Text (hiểu/plan/lời kể/prompt/QA) | **GPT** — GPT-5/o3 (reasoning), GPT-4o (mid), GPT-4o-mini (volume) |
| Ảnh | **gpt-image-1 tiered** (low/med/high) + ảnh tham chiếu nhân vật |
| Video | ❌ Không sinh video — **chỉ ảnh + hiệu ứng** (Ken Burns/zoom/pan) |
| Vision QA | **GPT-4o vision** |
| TTS | **Gemini (VI)** + **ElevenLabs (EN/JP)** + edge-tts fallback; giọng AI-cast |
| Thời lượng | Tự động theo độ dài truyện (Σ TTS thật + pause + transition) |
| Series/chương | Tùy chọn + Character DB xuyên chương |
| Ngôn ngữ | VI / EN / JP |
| Duyệt | #1 Story Bible · #2 Storyboard · #3 Ảnh (tùy chọn) |

---

## 1. Nguyên tắc thiết kế (bất biến trong mọi phase)

1. **Mode riêng, không đụng path cũ.** `render_format="story"` + `run_story`
   mới; dispatch thêm 1 nhánh ở `routers/_common.process_render` (nơi `content`
   dispatch). Tái dùng engine bằng composition.
2. **Sacred Contracts giữ nguyên** (CLAUDE.md):
   - #1 result_json 3 alias key (`output_rank_score`/`is_best_output`/`is_best_clip`).
   - #2 field mới trong `RenderRequest` default disabled/rỗng.
   - #3 mọi module `features/render/ai/**` catch hết → **return None, never raise**.
   - #4/#5 stage/part names **frozen** — Story tái dùng enum sẵn, **không thêm stage**.
   - #6 `_emit_render_event` signature frozen. #7 chỉ ghi DB qua repo. #8 qa_pipeline không bypass.
3. **DB additive-only** — chỉ ADD TABLE/COLUMN nullable/defaulted. Không DROP/RENAME/type-change.
4. **AI optional-dep an toàn** — ElevenLabs/openai SDK lazy-import; thiếu key/SDK → fallback, không fail startup.
5. **Tái dùng tối đa seam đã có** — visual provider seam, TTS seam, decision/budget,
   content_scene_render, content_assembler, qa_pipeline, pin/asset store.
6. **Mỗi phase độc lập test được**; CRITICAL/HIGH cần Planner analysis + explicit
   approval + full pytest baseline (Render Edit Protocol).

---

## 2. Kiến trúc tổng thể

```
FRONTEND
  Story Studio (MỚI, tách khỏi Content Studio)
    Input → Duyệt#1 Story Bible → Duyệt#2 Storyboard → (Duyệt#3 Ảnh) → Monitor
        │  /api/story/*  (mirror /api/content/*)
BACKEND
  render_format="story" → run_story (story_pipeline.py, mirror run_content)
    AI PIPELINE (call_fn provider-agnostic — tái dùng dispatch)
      Chunk → Understand → Extract(→DB) → Scene → Shot → Narration →
      PromptGen → AssetDecision → VisionQA
    VISUAL SEAM (tái dùng): gpt-image-1 (ref-conditioned) · local/pin
    TTS SEAM (tái dùng + mở rộng): Gemini · ElevenLabs · edge · xtts
    RENDER ENGINE (tái dùng): scene compose · Ken Burns · subtitle · concat+xfade · QA · NVENC
DATA (SQLite additive)
  jobs + story_plan_json (mới)
  story_series · characters · environments · relationships · story_timeline · chapter_summary
  content_assets/ (ảnh tham chiếu bền — đã có)
```

---

## 3. Data model

### 3.1 `domain/story_plan.py` (superset của ContentPlan, pure dataclass)

```
StoryPlan
  schema_version:int
  series_id:str = ""            # link Character DB (rỗng = truyện lẻ)
  chapter_no:int = 0
  language:str                  # vi|en|ja
  art_style:str                 # anime|wuxia|romance|realistic|inkwash|...
  aspect_ratio:str
  story_bible: StoryBible       # tái dùng + mở rộng (characters, environments, hook, cta, timeline)
  scenes: list[StoryScene]

StoryScene  (kế thừa tinh thần ContentScene)
  index:int, scene_title:str, role:str, setting_ref:str
  emotion:str, characters:list[str]
  transition_out:str            # scene-boundary transition
  shots: list[Shot]             # ← TẦNG MỚI

Shot
  index:int, sid:str
  shot_type:str                 # establishing|medium|close_up|insert|action
  narration:str, speaker:str    # "" speaker = narrator
  emotion:str, reading_speed:float, pause_before/after:float
  est_duration_sec:float
  camera:str                    # zoom_in|zoom_out|pan_left|pan_right|still (→ hiệu ứng)
  composition:str, lighting:str
  characters:list[str], environment_ref:str
  asset_type:str                # ai_image|local|pin
  quality_tier:str              # low|medium|high (gpt-image-1)
  visual_prompt:str, negative_prompt:str
  visual_source:str, visual_path:str   # pin/local override (tái dùng cơ chế CS-E)
  transition_out:str            # shot-boundary (default cut)
  subtitle_style:str
```

- `from_json`/`to_json` **defensive** như `content_plan.py` — blob thiếu/lạ không raise.
- **Tái dùng** `StoryBible` + `BibleCharacter` từ `content_plan.py`, thêm `environments[]`.
- **Không** phá `ContentPlan` — StoryPlan là type riêng.

### 3.2 DB — Story Memory (migrations additive, bắt đầu 0017)

| Migration | Nội dung |
|-----------|----------|
| `0017_jobs_add_story_plan_json.py` | `ALTER TABLE jobs ADD COLUMN story_plan_json TEXT` (nullable) — mirror 0015 |
| `0018_add_story_series_table.py` | `story_series(id, title, language, art_style, world_setting, created_at, updated_at)` |
| `0019_add_story_characters_table.py` | `characters(id, series_id, name, canonical_desc, reference_image_path, voice_engine, voice_id, age, gender, created_at)` + index `series_id` |
| `0020_add_story_environments_table.py` | `environments(id, series_id, name, canonical_desc, reference_image_path)` |
| `0021_add_story_graph_tables.py` | `relationships(series_id, char_a, char_b, type)` + `story_timeline(series_id, chapter_no, event, characters_json, order_no)` + `chapter_summary(series_id, chapter_no, rolling_summary, created_at)` |

- FK `series_id → story_series(id)` với `ON DELETE CASCADE` (theo pattern migration 0003).
- Truyện lẻ (`series_id=""`) không ghi các bảng này → không bắt buộc.
- Reference image → `APP_DATA_DIR/content_assets` (đã "never pruned").

---

## 4. Roadmap chia phase (dependency-ordered)

> Mỗi phase: **Mục tiêu · File+Tier · DB · Test · DoD · Rủi ro.**
> Cổng bắt buộc: mọi phase chạm CRITICAL/HIGH cần **Planner analysis riêng +
> explicit approval + full pytest baseline** trước khi Developer chạm code.

### Sơ đồ phụ thuộc
```
P0 Scaffold (domain + DB + repo)        [LOW + HIGH-DB]
   ↓
P1 Story Intelligence AI                [HIGH]  ── /api/story/analyze (plan-only, testable)
   ↓
P2 Planning AI (scene→shot→narration)   [HIGH]  ── superset StoryPlan
   ↓
P3 Asset gen (gpt-image-1 + ref + QA)   [HIGH]
   ↓                          ↘
P4 TTS multi-engine (ElevenLabs+Gemini) [MEDIUM/HIGH]  (song song P3)
   ↓
P5 Orchestrator run_story (render)      [CRITICAL]  ⭐ Render Edit Protocol
   ↓
P6 Wire surface + models                [HIGH]
   ↓
P7 Frontend Story Studio                [LOW-FE]
   ↓
P8 Consistency/quality polish (tùy chọn)[HIGH]
```

---

### PHASE 0 — Scaffold (nền, an toàn nhất)
- **Mục tiêu:** dựng domain + DB + repo, **chưa wire vào render**.
- **File + Tier:**
  - `domain/story_plan.py` — MỚI, **LOW** (dataclass thuần, defensive).
  - `db/migration_steps/0017..0021_*.py` — MỚI, **HIGH (DB)** (additive).
  - `db/story_repo.py` — MỚI, **HIGH** (CRUD series/characters/environments/graph, dùng `db_conn`).
  - `db/jobs_repo.py` — SỬA additive: `update_story_plan/get_story_plan` (mirror recap/content helpers), **HIGH**.
- **DB:** 0017–0021.
- **Test:** `test_story_plan_roundtrip.py` (from/to_json defensive, blob lỗi không raise);
  `test_migration_0017_0021.py` (additive, DB cũ retrofit không mất dữ liệu);
  `test_story_repo.py` (CRUD + FK cascade + truyện lẻ series_id="").
- **DoD:** py_compile sạch; full pytest = baseline + test mới xanh; DB mới init OK, DB cũ migrate OK.
- **Rủi ro:** Thấp. DB additive-only là điểm cần review kỹ.

### PHASE 1 — Story Intelligence AI
- **Mục tiêu:** đọc hiểu chương dài → StoryBible + Character/Environment DB. Có
  endpoint `POST /api/story/analyze` (plan-only, không render) để test độc lập.
- **File + Tier (tất cả `features/render/ai/**` = HIGH, Sacred #3):**
  - `ai/llm/story_chunker.py` — MỚI, **LOW** (rule-based cửa sổ trượt; tái dùng `_fit_script`).
  - `ai/llm/story_prompts.py` — MỚI, **HIGH** (understanding/extraction/env prompts; format-safe như content_prompts).
  - `ai/llm/story_parser.py` — MỚI, **HIGH** (return None on fail).
  - `ai/llm/story_director.py` — MỚI, **HIGH** (orchestrate map-reduce; `call_fn` provider-agnostic; text-tier router).
  - `ai/llm/__init__.py` — SỬA additive: `analyze_story()` dispatcher, **HIGH**.
  - `features/story/router.py` — MỚI, **MEDIUM** (`/api/story/analyze`, mirror content/router `/plan`).
- **DB:** ghi `characters/environments/chapter_summary` (nếu có series_id).
- **Test:** `test_story_understanding.py` (chương dài → bible đầy đủ, không truncate);
  `test_story_parser_returns_none.py` (rác → None); `test_story_chunker.py`;
  `test_story_crosschapter.py` (series có canon cũ → đọc lại).
- **DoD:** chương ~12k từ VI/EN/JP → StoryBible + characters/environments hợp lệ;
  import-time không fail khi thiếu SDK; Sacred #3; full pytest baseline.
- **Rủi ro:** TB (chất lượng AI + chi phí). Kill-switch chunk/multipass qua env.

### PHASE 2 — Planning AI (Storyboard + Shot)
- **Mục tiêu:** từ understanding → StoryPlan đầy đủ (scenes→shots→narration→prompt).
- **File + Tier:**
  - `ai/llm/story_prompts.py` — SỬA: scene-segmentation, **shot-planner**, narration, visual-prompt templates, **HIGH**.
  - `ai/llm/story_parser.py` — SỬA: parse scene/shot/narration → StoryPlan, **HIGH**.
  - `ai/llm/story_director.py` — SỬA: pipeline B1→B2→C1→C2 + inject character canon (tái dùng CU-6 `inject_character_fragments`), **HIGH**.
  - `features/render/engine/visual/decision.py` — SỬA additive: `decide_provider` nhận `shot_type` → asset_type/tier, **HIGH**.
  - `domain/story_plan.py` — SỬA: helpers `estimated_total_sec`, `narration_audit`, transition-planner 2 tầng (shot=cut/scene=fade), **LOW**.
  - `features/story/router.py` — SỬA: `/api/story/plan` trả StoryPlan đầy đủ + cost estimate (mirror content `/estimate`), **MEDIUM**.
- **Test:** `test_shot_planner.py` (1 scene đối thoại → N shot hợp lệ);
  `test_story_plan_narration.py` (khớp duration); `test_transition_planner.py` (2 tầng);
  `test_decision_shot_type.py`.
- **DoD:** chương → StoryPlan (scenes→shots) hợp lệ, blob cũ load được (additive);
  cost estimate chạy read-only; full pytest baseline.
- **Rủi ro:** TB. Shot Planner là lõi chất lượng — cần ai_eval nếu có harness.

### PHASE 3 — Asset Generation (ảnh + consistency + QA)
- **Mục tiêu:** sinh ảnh mỗi shot nhất quán nhân vật + Vision QA.
- **File + Tier:**
  - `features/render/engine/visual/provider_ai_image.py` — SỬA: nhánh `gpt-image-1`
    + **nhận ảnh tham chiếu** (character reference) + tier low/med/high, **HIGH**.
  - `features/render/engine/visual/provider_reference_sheet.py` — MỚI, **HIGH**
    (sinh Character Reference Sheet 1 lần/nhân vật → pin vào content_assets).
  - `features/render/ai/vision/qa.py` — MỚI, **HIGH** (Vision QA: so ảnh vs canonical →
    verdict → regen bounded; Sacred #3 return None/pass on error).
  - `features/render/engine/visual/__init__.py` — SỬA additive: branch provider mới, **HIGH**.
  - `features/story/router.py` — SỬA: `/api/story/visual/preview|pin` (tái dùng CM-1 guard + CM-12 pin), **MEDIUM**.
- **DB:** `characters.reference_image_path` cập nhật.
- **Test:** `test_gpt_image_reference.py` (nhận ref → giữ nhân vật, fallback khi thiếu key);
  `test_reference_sheet.py`; `test_vision_qa.py` (reject→regen bounded, error→pass).
- **DoD:** shot có nhân vật → ảnh dùng reference; Vision QA reject→regen; thiếu key →
  fallback local (không raise); budget guard chặn spend; full pytest baseline.
- **Rủi ro:** TB-cao (chi phí ảnh + QA). Budget cap + tier bắt buộc. Vision QA là AI mới.

### PHASE 4 — TTS multi-engine (song song P3)
- **Mục tiêu:** định tuyến TTS theo ngôn ngữ + Voice Casting AI + đa giọng nhân vật.
- **File + Tier:**
  - `features/render/engine/audio/tts_elevenlabs.py` — MỚI, **MEDIUM** (provider ElevenLabs, lazy SDK, None on fail).
  - `features/render/engine/audio/tts.py` — SỬA additive: route `language→engine`
    (vi→gemini, en/ja→elevenlabs, fallback edge), thêm `elevenlabs` vào dispatch, **MEDIUM**.
  - `ai/llm/story_voice_cast.py` — MỚI, **HIGH** (Voice Casting AI: canon → voice_id per engine/ngôn ngữ; Sacred #3).
  - `features/story/router.py` — SỬA: `/api/story/narration/preview` (mirror content), **MEDIUM**.
- **DB:** `characters.voice_engine/voice_id`.
- **Test:** `test_tts_routing.py` (vi→gemini, en/ja→elevenlabs, lỗi→edge);
  `test_elevenlabs_provider.py` (thiếu key→None); `test_voice_cast.py`.
- **DoD:** đọc VI (Gemini) + EN/JP (ElevenLabs) ra audio hợp lệ; thiếu key → edge fallback;
  giọng nhân vật khác nhau; full pytest baseline.
- **Rủi ro:** TB (chi phí ElevenLabs ở EN/JP; quota). Fallback edge miễn phí bắt buộc.

### PHASE 5 — Orchestrator `run_story` ⭐ (CRITICAL)
- **Mục tiêu:** render end-to-end tái dùng engine — StoryPlan → video.
- **File + Tier:**
  - `features/render/engine/pipeline/story_pipeline.py` — MỚI, **CRITICAL**
    (`run_story` mirror `run_content`; owns JobStage/JobPartStage; shot = part row).
  - `features/render/routers/_common.py` — SỬA: nhánh `elif render_format=="story": run_story(...)`, **MEDIUM**.
  - `features/render/engine/stages/story/*.py` — MỚI (decompose ngay từ đầu như CM-6):
    `context.py`, `shot_stage.py` (compose 1 shot: TTS→ảnh→hiệu ứng→subtitle→mux),
    `assembly_stage.py` (concat 2 tầng — tái dùng `content_assembler`), `finalize_stage.py`. **LOW/MEDIUM**.
  - Tái dùng: `content_scene_render` (ken_burns/camera đã có), `content_assembler`,
    `qa_pipeline`, `pipeline_setup`, `render_events`.
- **Bất biến (không đổi):** stage sequence
  `STARTING→ANALYZING→SEGMENT_BUILDING→RENDERING/RENDERING_PARALLEL→WRITING_REPORT→DONE`;
  part `QUEUED→RENDERING→DONE/FAILED`; result_json 3 alias key; QA gate không nuốt
  exception; partial-success; `close_thread_conn()` finally.
- **Ràng buộc GPU:** asset-gen (Phase 3) tách khỏi encode (NVENC) trên timeline —
  không chạy diffusion/song song vượt NVENC semaphore (ảnh gen qua API nên nhẹ GPU-local,
  nhưng vẫn giữ semaphore cho encode).
- **Test:** `test_run_story_dispatch.py` (route đúng, clips/recap/content không đổi);
  `test_run_story_e2e.py` (chương ngắn → video qua QA gate, ffprobe A/V);
  `test_run_story_resume.py` (đọc lại story_plan_json khi resume — mirror CM-3);
  `test_run_story_partial.py` (1 shot fail → partial success).
- **DoD:** **Render Edit Protocol đầy đủ** (baseline trước → edit tối thiểu → full pytest
  = baseline); e2e render thật; Sacred #1/#4/#5/#8 giữ nguyên.
- **Rủi ro:** CAO (CRITICAL — owns state machine). Đây là integration rủi ro nhất.

### PHASE 6 — Wire surface + models
- **Mục tiêu:** mở `render_format="story"` + field Story qua wire (Sacred #2).
- **File + Tier:**
  - `models/render.py` — SỬA: `RenderFormat=Literal["clips","recap","content","story"]`
    + field Story (`story_*`, default rỗng/disabled), **HIGH (Sacred #2)**.
  - `models/render_public.py:FE_FACING_FIELDS` — SỬA: thêm field Story vào wire, **HIGH**.
  - `models/render_field_groups.py` — SỬA: nhóm field Story, **MEDIUM**.
  - `routes/jobs.py` — SỬA: expose `story_plan_json` trong job read (FE review), **MEDIUM**.
- **Test:** `test_render_format_story_backcompat.py` (payload cũ → vẫn "clips");
  `test_story_fields_default.py` (field mới default disabled — Sacred #2);
  `test_public_surface_story.py`.
- **DoD:** field Story default rỗng; replay payload cũ bit-identical; full pytest baseline.
- **Rủi ro:** TB (Sacred #2 — additive-only verify).

### PHASE 7 — Frontend Story Studio
- **Mục tiêu:** UI riêng — Input → Duyệt#1 Bible → Duyệt#2 Storyboard → (Duyệt#3 Ảnh) → Monitor.
- **File + Tier:** `frontend/src/features/story-studio/**` — MỚI, **LOW-FE**
  (tái dùng pattern Content: undo/redo, preview/pin, cost panel, monitor, Timeline).
  - `InputPhase.tsx` (chương + ngôn ngữ + series + art style + aspect + tier/budget + subtitle + bgm + output).
  - `BibleReview.tsx` (Character Manager: canon + reference sheet approve/regen).
  - `StoryboardEditor.tsx` (scene→shot grid + shot timeline 2 cấp + edit narration/hiệu ứng/transition).
  - `AssetReview.tsx` (tùy chọn — approve/regen ảnh).
  - `StoryMonitor.tsx` (tái dùng ContentMonitor).
  - `api/story.ts`.
- **Test:** `tsc -b` sạch; mỗi file <400 dòng; build vite cập nhật `static-v2`.
- **DoD:** duyệt/edit storyboard mượt; 3 cổng duyệt hoạt động; build OK.
- **Rủi ro:** Thấp (FE). Lưu ý CLAUDE.md: FE đang rebuild — ưu tiên backend trước.

### PHASE 8 — Consistency/quality polish (tùy chọn, sau khi chạy thật)
- Relationship/Timeline graph (A4) consume; multi-voice tinh chỉnh; BGM Mood AI;
  Continuity Checker; ai_eval cho Shot Planner. **HIGH**, làm khi có nhu cầu đo được.

---

## 5. Bảng tổng hợp phase

| Phase | Nội dung | Tier cao nhất | Deps | Ưu tiên |
|-------|----------|--------------|------|---------|
| P0 | Scaffold domain+DB+repo | HIGH-DB | — | P0 |
| P1 | Story Intelligence AI | HIGH | P0 | P0 |
| P2 | Planning (scene→shot) | HIGH | P1 | P0 |
| P3 | Asset gen + Vision QA | HIGH | P2 | P1 |
| P4 | TTS multi-engine | MEDIUM/HIGH | P0 | P1 (∥P3) |
| P5 | Orchestrator run_story | **CRITICAL** | P2,P3,P4 | P1 |
| P6 | Wire surface + models | HIGH | P5 | P1 |
| P7 | Frontend Story Studio | LOW-FE | P6 | P2 |
| P8 | Quality polish | HIGH | P7 | P3 |

**Critical path:** P0→P1→P2→P3→P5→P6 (P4 song song). P5 là điểm rủi ro cao nhất.

---

## 6. Risk register

| Rủi ro | Mức | Xử lý |
|--------|-----|-------|
| P5 chạm state machine (Sacred #4/#5) | Cao | Render Edit Protocol đầy đủ; run_story tách riêng, không sửa content/recap/clips pipeline |
| Chi phí ảnh + Vision QA + ElevenLabs bùng | Cao | Budget cap + tier + cost preflight (tái dùng CM-1/estimate); QA chỉ shot có nhân vật |
| Consistency nhân vật (gpt-image-1 ref yếu hơn IP-Adapter) | TB | Character Reference Sheet + inject canon (CU-6) + seed; seam mở để nâng lên local sau |
| Chương quá dài truncate/token | TB | Chunk + map-reduce; kill-switch env |
| ElevenLabs/Gemini quota/lỗi | TB | edge-tts fallback miễn phí bắt buộc |
| AI raise giữa render (Sacred #3) | Cao | Mọi module ai/** return None; test rác→None |
| DB destructive | Cao | Additive-only; test retrofit DB cũ |
| Field mới auto-enable job cũ (Sacred #2) | TB | Default rỗng/disabled; test backcompat |

---

## 7. Quyết định — ĐÃ CHỐT (2026-07-09, "theo đề xuất")

1. **Duyệt #3 (Ảnh)** — ✅ tùy chọn, **mặc định ẩn** sau cờ để luồng nhanh.
2. **A4 Relationship/Timeline graph** — ✅ **hoãn P8**, chỉ làm khi truyện đa tuyến cần.
3. **Word-by-word subtitle** — ✅ **mặc định tắt** cho Story (chương dài, Whisper mỗi shot rất chậm).
4. **Nhịp kể toàn cục** (thay thời lượng) — ✅ **có** 1 hệ số reading_speed (chậm/vừa/nhanh).
5. **gpt-image-1 tier mặc định** — ✅ **medium** shot thường, **high** hero/close-up, **low** establishing.

---

## 8. Checklist Sacred Contract (áp cho Story)

| Contract | Áp dụng |
|----------|---------|
| #1 result_json 3 alias key | `finalize_stage` ghi đủ 3 key |
| #2 field default disabled | `story_*` rỗng, format vẫn "clips" |
| #3 AI return None | story_director/parser/vision/voice_cast không raise |
| #4 stage names frozen | tái dùng enum, không thêm stage |
| #5 part status frozen | mỗi shot = 1 part, dùng enum sẵn |
| #6 `_emit_render_event` frozen | chỉ gọi |
| #7 app.db sole authority | chỉ ghi qua story_repo/jobs_repo |
| #8 qa_pipeline không bypass | output cuối qua `_validate_render_output` |

---

## 9. Thứ tự build đề xuất (checkpoint duyệt sau mỗi phase)

P0 → **duyệt** → P1 → **duyệt** → P2 → **duyệt** → P3 ∥ P4 → **duyệt** →
**P5 (Render Edit Protocol + full pytest)** → **duyệt** → P6 → **duyệt** → P7 → P8.

Mỗi phase: `py_compile` sau mỗi file Python + pytest focused; phase chạm
CRITICAL/HIGH → **full pytest** + Planner analysis + explicit approval trước khi code.

---

## 10. Trạng thái triển khai

| Phase | Trạng thái | Ngày | Ghi chú |
|-------|-----------|------|---------|
| P0 | ✅ DONE | 2026-07-09 | `domain/story_plan.py` (Scene→Shot, defensive) + migrations 0017–0021 (story_plan_json col + story_series/characters/environments/relationships/story_timeline/chapter_summary) + `db/story_repo.py` + `jobs_repo.update_story_plan/get_story_plan`. Baseline **2609 → 2629 passed** (0 regression); 20 test mới: `test_story_plan_roundtrip` (7), `test_migration_0017_story_plan_json` (4), `test_migration_0018_0021_story_tables` (4), `test_story_repo` (5). Chưa wire vào render (đúng scope P0). Chưa commit. |
| P1 | ✅ DONE | 2026-07-09 | Story Intelligence AI (GPT-centric, map-reduce). MỚI: `ai/llm/story_chunker.py` (cửa sổ trượt + overlap), `story_prompts.py` (digest + reduce, format-safe, prompt v1), `story_parser.py` (defensive, fence/salvage → None on fail), `story_director.py` (`run_story_intelligence` provider-agnostic `call_fn`, map-reduce, merge fallback khi reduce fail), `features/story/router.py` (`POST /api/story/analyze` + persist Character/Environment DB + chapter_summary khi có series_id). SỬA additive: `ai/llm/__init__.py` (`analyze_story` dispatcher + `_get_story_call_fn` bind `_call_<p>_content`, default provider openai, fallback chain), `main.py` (mount story_router). Baseline **2629 → 2650 passed** (0 regression); 21 test mới: chunker (5), parser (6), director (5), endpoint/dispatch (5). Bug sửa: chunker sàn cap 1000→100. Sacred #3 giữ (mọi path return None). Chưa wire vào render (đúng scope). Chưa commit. |
| P2 | ✅ DONE | 2026-07-09 | Planning AI (storyboard scene→shot→narration→visual prompt). SỬA additive: `story_prompts.py` (+`build_storyboard_prompt` grounded bible, format-safe), `story_parser.py` (+`parse_storyboard_response` → list[StoryScene], lọc shot rỗng), `story_director.py` (+`run_story_planning` map theo chunk + `inject_character_canon` CU-6 analogue), `ai/llm/__init__.py` (+`generate_story_plan` dispatcher — chạy analyze_story trước nếu chưa có bible), `domain/story_plan.py` (+`reindex` dense index + seed sid), `features/story/router.py` (+`POST /api/story/plan`). Baseline **2650 → 2660 passed** (0 regression); 10 test mới: planning/parser/inject (7), endpoint (3). Bug sửa: parser lọc shot narration rỗng trong scene. **Scoping:** `decision.py` (shot_type→tier) DỜI sang P3 (nơi budget/asset-gen dùng). quality_tier/transition mặc định đã áp ở domain loader (theo shot_type / 2-tier cut-fade). Chưa wire vào render. Chưa commit. |
| P3 | ✅ DONE | 2026-07-09 | Asset gen. MỚI: `engine/visual/story_image.py` (gpt-image-1 tiered low/med/high + **reference-image edit** cho consistency + cache), `story_reference_sheet.py` (Character Reference Sheet → pin durable content_assets), `story_decision.py` (shot→asset_type/tier + BudgetTracker downgrade, tái dùng Content budget), `features/render/ai/vision/qa.py` (Vision QA GPT-4o, **fail-open** Sacred #3, chỉ reject khi NO rõ ràng). SỬA: `features/story/router.py` (+`POST /api/story/character/reference-sheet` gen+pin). Baseline **2660 → 2685 passed** (0 regression); 25 test mới (offline, mock SDK): story_image (7), decision (7), vision_qa (6), reference_sheet (7 incl endpoint). Bug test sửa: cache isolation (uuid prompt) + budget math. **Scoping:** mode-isolation — KHÔNG sửa `provider_ai_image.py` (Content); Story dùng module riêng (`SceneVisualRequest` không mang tier/reference). Chưa wire vào render (P5). Chưa commit. |
| P4 | ✅ DONE | 2026-07-09 | TTS multi-engine + Voice Casting. MỚI: `engine/audio/tts_elevenlabs.py` (provider ElevenLabs, lazy SDK, raise→fallthrough edge chain), `ai/llm/story_voice_cast.py` (Voice Casting tất định — engine theo ngôn ngữ + voice pool rotate theo gender, `apply_voice_cast` stamp character; Sacred #3 never raise). SỬA additive: `engine/audio/tts.py` (+branch `elevenlabs` mirror gemini + helper `resolve_story_tts_engine`: vi→gemini, en/ja→elevenlabs, edge fallback, override `STORY_TTS_ENGINE_OVERRIDE`), `features/story/router.py` (+`POST /api/story/narration/preview` route engine theo ngôn ngữ + serve audio). Baseline **2685 → 2701 passed** (0 regression); 16 test mới: voice_cast (6), tts routing/provider (6), narration endpoint (4). Env: `ELEVENLABS_API_KEY`, `STORY_ELEVEN_MODEL`, `STORY_GEMINI/ELEVEN_VOICES_*`. Chưa wire vào render (P5). Chưa commit. |
| P5 | ✅ DONE | 2026-07-09 | **Orchestrator `run_story`** (CRITICAL — Render Edit Protocol đầy đủ: baseline **2701** trước → edit → full pytest **2713** = baseline+12, 0 regression). MỚI: `pipeline/story_pipeline.py` (`run_story` mirror run_content, owns JobStage/JobPartStage, shot=part; `_build_transitions` 2-tier pure; resolve plan override→persisted→AI; serial render loop, budget, partial-success), `stages/story/` (`context.py`, `shot_stage.py` — TTS cast→gpt-image-1→Vision QA→compose, Shot duck-types content scene helpers; `assembly_stage.py` — concat 2-tier + fallback + single-shot copy; `finalize_stage.py` — QA gate Sacred #8 + result_json Sacred #1). SỬA additive: `models/render.py` (+`story` literal + 5 field inert Sacred #2), `routers/_common.py` (+`_validate_story_source` + dispatch `elif story: run_story`). Guard tests cập nhật (render_format literal +story, field count 165→170, field_groups +story group, public surface BE-only+5). 12 test mới: dispatch/Sacred#2/validation/transition. Tái dùng verbatim: content_scene_render, content_assembler, qa_pipeline, pipeline_setup, render_events. **Khuyến nghị:** runtime /verify với OPENAI_API_KEY (như Content W5-2). Chưa commit. |
| P6 | ✅ DONE | 2026-07-09 | Wire surface (MT-3 coordinated migration). SỬA additive: `models/render_public.py` (5 story field → `FE_FACING_FIELDS`, `RenderRequestPublic` extra=forbid nhận được), `frontend/src/types/api.ts` (interface RenderRequest +5 story field + `'story'` vào union render_format ở RenderRequest & HistoryItem), `routes/jobs.py` (+`GET /{job_id}/story-plan` reattach/polling fallback, mirror content-plan). Guard tests cập nhật: public surface count (FE 85→90, BE 85→80, total 170), MT-3 TS-drift guard xanh, test_story_dispatch flip → FE-facing. Baseline **2713 → 2720 passed** (0 regression); 7 test mới: wire surface (4) + story-plan job read (3). FE giờ submit được story render qua `/api/render/process` (extra=forbid chấp nhận story field). Chưa commit. |
| P7 | ✅ DONE | 2026-07-09 | Frontend Story Studio (LOW-FE). MỚI: `api/story.ts` (client + types khớp StoryPlan). **UI redesign (2026-07-09, sau feedback "không match design system"):** rebuild theo đúng design language Content Studio — `StoryStudio.css` (@import ContentStudio.css → cs- classes/tokens), tách file theo pattern: `types.ts`, `InputPhase.tsx` (SectionCard/Field/RatioPreview + validation: char count, save-folder required hint, disabled CTA, art-style datalist, reading-pace seg, subtitle toggle), `BiblePhase.tsx` (character/environment cards + reference-sheet), `StoryboardPhase.tsx` (scene/shot cards + audit badge + edit narration/prompt), `StoryStudio.tsx` (orchestrator: useI18n vi, useRenderStore, 4-step StoryStepper, output-dir prefill + electron pathExists validate). SỬA additive (wiring): `uiStore.ts` (+`story-studio` ActivePanel), `App.tsx` (lazy + PANEL_MAP), `Sidebar.tsx` (nav), `translations.ts` (+`nav_story`). `tsc -b` **sạch**; `npm run build` OK. Map ngôn ngữ→voice_language locale khớp TTS routing. Không đụng backend (pytest 2723). Chưa commit. |
| P8 | ✅ DONE (Vision QA regen) | 2026-07-09 | **Vision QA regen loop** (hạng mục đã hứa ở P3/P5). SỬA additive story-only: `story_image.py` (+`variant` param → nudge prompt + cache key → regen ra ảnh khác thật), `stages/story/shot_stage.py` (+bounded QA loop: generate→QA→reject thì regen variant khác, cap `STORY_QA_MAX_RETRY`=2; QA fail-open giữ candidate cuối). Baseline **2720 → 2723 passed** (0 regression); 3 test mới: variant distinct/cache + retry-cap env. **Deferred (tùy chọn tương lai):** parallel shot render (rủi ro concurrency budget — serial an toàn), BGM mix, relationship/timeline graph consume (cần A4), per-shot preview/pin UI. Chưa commit. |

---

## 11. Tổng kết initiative (P0→P8, 2026-07-09)

Story-to-Video backend + wire + UI **hoàn chỉnh end-to-end**, mọi phase 0 regression, mọi Sacred Contract giữ nguyên. Test tăng **2609 → 2723** (+114). `tsc -b` + `npm run build` sạch.

**Còn lại trước production:** (1) runtime /verify render thật 1 chương với `OPENAI_API_KEY` + `ELEVENLABS_API_KEY` (môi trường build offline nên chưa render ffmpeg/AI thật — như Content đã làm W5-2); (2) commit (đang giữ commit-lock theo yêu cầu user).

**Deferred optional:** parallel shot render, BGM mix, story graph (A4), per-shot preview/pin UI, ai_eval cho Shot Planner.

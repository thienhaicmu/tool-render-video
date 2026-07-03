# CONTENT_MODE_SPEC.md — AI Content Mode (Script → AI Narration → Video)

> Status: **PLAN — chờ duyệt.** Chưa có dòng code nào được viết.
> Risk tier tổng thể: **HIGH** (thêm `render_format` value + migration DB +
> AI module + dispatch). Theo protocol trong CLAUDE.md phải duyệt plan này
> trước khi implement.
>
> Quyết định sản phẩm đã chốt (2026-07-03):
> 1. **Visual v1 = nền do user chọn + chữ động** (offline 100%, tái dùng
>    tối đa engine). Không stock/AI-image, không cần source video.
> 2. **AI scope v1 = MVP director cốt lõi** — scene split, narration,
>    emotion, reading-speed, pause, subtitle-style, timeline. Các chiều
>    visual/bgm/camera/transition/animation chỉ **LƯU dạng gợi ý** trong
>    ContentPlan, chưa consume vào render.

---

## 1. Nguyên tắc thiết kế

Content Mode là **mode render thứ 3**, thêm y hệt cách Recap Mode đã được
thêm (Phase R2). Recap là bản mẫu (template) chính xác:

| Thành phần | Recap (đã có) | Content (thêm mới, mirror) |
|---|---|---|
| Discriminator | `render_format="recap"` | `render_format="content"` |
| Orchestrator riêng | `pipeline/recap_pipeline.py:run_recap` | `pipeline/content_pipeline.py:run_content` |
| Dispatch | `routers/_common.py:241` | thêm 1 nhánh cùng chỗ |
| Domain plan (pure dataclass) | `domain/recap_plan.py:RecapPlan` | `domain/content_plan.py:ContentPlan` |
| LLM dispatcher | `ai/llm/__init__.py:select_recap_plan` (:277) | `select_content_plan` (cùng file) |
| Parser | `ai/llm/recap_parser.py` | `ai/llm/content_parser.py` |
| Prompts | `ai/llm/recap_prompts.py` | `ai/llm/content_prompts.py` |
| Provider impl | `providers/{gemini,openai,claude}.py:select_recap_plan` | `select_content_plan` cùng 3 file |
| DB column (additive) | `recap_plan_json` (migration 0012) | `content_plan_json` (migration **0015**) |
| DB helpers | `jobs_repo.update_recap_plan/get` | `update_content_plan/get` |

**Ràng buộc bắt buộc:** KHÔNG sửa `render_pipeline.py` (clips) và KHÔNG sửa
`recap_pipeline.py`. Content Mode tái dùng engine bằng **composition**, đúng
như recap_pipeline làm — không duplicate pipeline.

---

## 2. Phát hiện kiến trúc mấu chốt — "không có source video"

Clip Mode và Recap Mode đều **cắt clip từ frame của video gốc**
(`stages/part_cut.py:run_cut_stage` → `render_part_from_source`). Content
Mode **không có gì để cắt**. Hệ quả:

- Content Mode **KHÔNG** dùng được `pipeline_render_loop.run_render_loop` /
  `part_renderer.process_one_part` (toàn bộ path đó xoay quanh cắt segment
  `{start,end}` từ source).
- Thay vào đó Content cần **1 mảnh engine mới nhỏ**: dựng "base clip" từ
  **nền (color/ảnh/video-loop)** thay cho frame source. Đây là code engine
  **duy nhất** thực sự mới.

Mảnh mới này **không viết từ đầu** — nó mô phỏng
`stages/recap_title_card.py:make_act_title_card`, vốn đã dựng 1 video clip từ
"still + drawtext + `anullsrc` audio" bằng FFmpeg lavfi. Content chỉ đổi
nguồn nền và gắn audio TTS thật thay cho silence.

### Bản đồ tái sử dụng engine (reuse map)

| Khối engine | Đường dẫn | Content dùng thế nào |
|---|---|---|
| TTS / narration | `audio/tts.py`, `audio/timed_narration.py` | **Tái dùng** — sinh giọng đọc từ narration của mỗi scene. Ở Content, TTS **LÀ** track audio (không mix đè lên source). |
| Subtitle (ASS/CapCut) | `subtitle/generator/ass*.py`, `subtitle/processing/styles.py` | **Tái dùng** — render phụ đề động từ narration + timeline. |
| Text overlay | `overlay/text_overlay.py` | **Tái dùng** — title / lower-third. |
| Concat nhiều scene → 1 video | `stages/recap_assembler.py:concat_clips`, `probe_av_spec` | **Tái dùng** — ghép các scene clip thành output cuối. |
| QA gate (Sacred Contract #8) | `pipeline/qa_pipeline.py:_validate_render_output` | **Tái dùng** — validate output trước DONE. |
| FFmpeg / NVENC semaphore | `encoder/ffmpeg_helpers.py` | **Tái dùng** — encode base clip (giữ nguyên NVENC semaphore). |
| Nhạc nền mix | `audio/mixer.py` | **Tái dùng (phase sau)** — bgm là hint ở v1. |
| Motion / Ken Burns | `motion/*` | **Không dùng ở v1** (nền tĩnh). Sẵn sàng cho slideshow phase sau. |
| Setup / output dir / config | `pipeline/pipeline_setup.py`, `pipeline_config.py` | **Tái dùng** — như recap_pipeline import chúng. |

---

## 3. Danh sách file — thêm mới & sửa (kèm risk tier)

### 3.1 File THÊM MỚI (đa số LOW — code mới, không đụng path cũ)

| File | Vai trò | Tier |
|---|---|---|
| `domain/content_plan.py` | `ContentPlan` dataclass (pure, defensive from_json/to_json — mirror recap_plan.py) | LOW |
| `ai/llm/content_prompts.py` | Prompt templates cho AI Content Director | HIGH¹ |
| `ai/llm/content_parser.py` | `parse_content_plan_response` → ContentPlan; **return None khi lỗi** | HIGH¹ |
| `pipeline/content_pipeline.py` | `run_content(...)` orchestrator; mirror `run_recap` contract | HIGH¹ |
| `stages/content_scene_render.py` | Dựng base clip từ nền + gắn TTS + subtitle cho 1 scene (mô phỏng recap_title_card) | MEDIUM |
| `stages/content_background.py` | Chuẩn hoá nền: `color=` lavfi / `-loop 1` ảnh / loop video → clip theo aspect ratio & duration | MEDIUM |
| `db/migration_steps/0015_jobs_add_content_plan_json.py` | Additive column `content_plan_json TEXT` | HIGH (DB) |
| `docs/CONTENT_MODE_SPEC.md` | Chính tài liệu này | — |
| `tests/test_content_mode_*.py` | Test plan §11 | — |

¹ HIGH vì nằm dưới `features/render/ai/**` — **Sacred Contract #3 tuyệt đối:
mọi hàm phải catch hết exception và `return None`, không bao giờ raise.**

### 3.2 File SỬA (đều additive — không xoá/không đổi field cũ)

| File | Thay đổi | Tier |
|---|---|---|
| `models/render.py:29` | `RenderFormat = Literal["clips","recap","content"]` + validator cho phép `"content"` | HIGH (Sacred Contract #2) |
| `models/render.py` | Thêm field Content (default an toàn — xem §7) | HIGH (SC #2) |
| `models/render_public.py:FE_FACING_FIELDS` | Thêm field Content vào wire surface | HIGH |
| `models/render_field_groups.py` | Nhóm field Content (nếu cần group hoá) | MEDIUM |
| `routers/_common.py:~241` | Thêm nhánh `elif render_format=="content": run_content(...)` | MEDIUM |
| `ai/llm/__init__.py` | `select_content_plan()` dispatcher + `_impl_for_provider` mapping | HIGH |
| `ai/llm/providers/{gemini,openai,claude}.py` | `select_content_plan()` từng provider | HIGH |
| `db/jobs_repo.py` | `update_content_plan()` / `get_content_plan()` (mirror recap helpers ~:205) | HIGH |
| `routes/jobs.py` | Expose `content_plan_json` trong job read (nếu FE cần review plan) | MEDIUM |
| `frontend/...` | Tab **Content** + form nhập script (xem §9) | MEDIUM (FE) |

---

## 4. `ContentPlan` — cấu trúc (v1)

Pure dataclass, mirror `recap_plan.py`: mọi field có default an toàn,
`from_json` defensive (drop key lạ, không raise), `to_json` deterministic.

```
ContentPlan
  schema_version: int = 1
  topic: str                 # AI-detected: history|tech|finance|...
  tone: str                  # documentary|storytelling|news|...
  audience: str              # general|kids|business|...
  language: str              # vi|en|...
  total_target_sec: float    # tổng thời lượng ước lượng
  subtitle_style: str        # gợi ý: capcut|word_by_word|minimal|...
  bgm_mood: str              # HINT-only v1 (epic|calm|news|...)
  scenes: list[ContentScene]

ContentScene
  index: int
  role: str                  # hook|intro|explain|example|conclusion|cta
  narration: str             # lời đọc (AI-authored) — nguồn TTS + phụ đề
  emotion: str               # normal|excited|calm|suspense|epic|...
  reading_speed: float = 1.0 # 0.90..1.20
  pause_before: float = 0.0  # giây
  pause_after: float = 0.0   # giây
  emphasis: list[str] = []   # từ/cụm cần nhấn (v1: lưu, dùng nhẹ ở subtitle)
  est_duration_sec: float    # AI ước lượng; engine tinh chỉnh theo TTS thực
  # ── HINT-only v1 (lưu, CHƯA consume vào render) ──
  visual_hint: str = ""      # "nên dùng footage chiến trường"
  camera_hint: str = ""      # zoom_in|pan|still|...
  transition_hint: str = ""  # fade|cut|slide|...
  animation_hint: str = ""   # highlight|popup|lower_third|...
```

**Ràng buộc duration:** AI ước lượng `est_duration_sec`, nhưng **duration
thật của scene = duration của file TTS** (đo bằng ffprobe, như
`timed_narration.py` đang làm) + `pause_before/after`. AI chỉ định hướng độ
dài, không quyết định cứng.

---

## 5. AI Content Director — MVP scope

`select_content_plan(script, payload, provider)` → `ContentPlan | None`.

**AI phải làm (v1):** đọc toàn bộ script → xác định topic/tone/audience →
**chia scene theo ngữ nghĩa** (không theo số ký tự) → viết narration từng
scene → gán emotion + reading_speed + pause → gợi ý subtitle_style → ước
lượng timeline. Visual/bgm/camera/transition/animation trả về dạng **hint
string** (lưu vào ContentPlan, chưa render).

**Sacred Contract #3:** `content_parser` + mọi provider impl **catch tất cả,
return None**. `run_content` coi `None` = job FAIL sạch (không có fallback
"đọc thẳng script" ở v1 để tránh output rác — có thể thêm fallback tối giản
sau).

---

## 6. `run_content` — luồng pipeline

Mirror contract của `run_recap` (cùng signature → wrapper cancel/failure/
metrics/close_thread_conn trong `_common.process_render` áp dụng nguyên):

```
run_content(job_id, payload, cancel_event, ...):
  1. setup_render_pipeline + prepare_output_dir        [reuse]
  2. script = payload.content_script (không prepare_render_source — no video)
  3. emit STARTING → RUNNING → ANALYZING               [reuse render_events, stage names FROZEN]
  4. plan = select_content_plan(script, ...)           [new AI]
        None → raise → job FAILED sạch (SC #3)
  5. update_content_plan(job_id, plan.to_json())        [new DB helper]
  6. SEGMENT_BUILDING: map scenes → "parts" (mỗi scene = 1 part row, SC #5 status names FROZEN)
  7. RENDERING_PARALLEL: với mỗi scene:
        a. TTS narration → mp3 + đo duration           [reuse tts/timed_narration]
        b. background clip (color/ảnh/video) @ duration [new content_background]
        c. subtitle ASS từ narration + timing          [reuse subtitle generator]
        d. burn subtitle + overlay + gắn audio TTS      [new content_scene_render, mô phỏng recap_title_card]
  8. WRITING_REPORT: concat_clips(scenes) → 1 output    [reuse recap_assembler]
  9. _validate_render_output(output)                    [reuse qa_pipeline — SC #8]
 10. upsert_job(DONE) + result_json với 3 alias key bắt buộc
     (output_rank_score / is_best_output / is_best_clip — SC #1)
```

**Stage names (SC #4) và part status (SC #5) giữ nguyên** — Content chỉ tái
dùng đúng các enum hiện có, không thêm stage mới.

---

## 7. Sacred Contract #2 — field defaults an toàn

Field Content thêm vào `RenderRequest` phải default về trạng thái **disabled/
rỗng** để payload lịch sử replay không đổi hành vi:

```python
content_script: str = ""              # rỗng → không phải content job
content_background_kind: str = "color"  # color|image|video (an toàn nhất: color)
content_background_value: str = "#000000"  # màu / path
content_bgm_path: str = ""            # rỗng = không bgm
# subtitle_style / voice / language / aspect_ratio: DÙNG LẠI field sẵn có,
# không tạo field trùng.
```

`render_format` default vẫn `"clips"` — job cũ không có `render_format` vẫn
chạy clips. Chỉ khi FE gửi `render_format="content"` + `content_script` thì
Content Mode mới kích hoạt.

**Wire surface (MT-3):** field Content phải thêm vào **CẢ HAI**
`models/render.py` (internal) **VÀ** `models/render_public.py:FE_FACING_FIELDS`
(88→+N). Replay path vẫn dùng full `RenderRequest` — bit-identical.

---

## 8. DB migration 0015 (additive-only)

```
0015_jobs_add_content_plan_json.py
  ALTER TABLE jobs ADD COLUMN content_plan_json TEXT   -- nullable, no default
```

Tuân thủ luật additive-only (chỉ ADD COLUMN nullable). Mirror `0012`. Không
DROP/RENAME/type-change. DB cũ retrofit qua migration; DB mới có sẵn qua
`init_db`.

---

## 9. UI — Tab Content

Thêm tab **Content** cạnh Clip / Recap. Form v1:

- Paste script / import `.txt` / `.md`
- Chọn: Voice, Language, Aspect ratio, Subtitle style — **dùng lại control
  sẵn có**
- Chọn nền: màu / upload ảnh / upload video loop (`content_background_*`)
- (tuỳ chọn) upload bgm
- Nút **Generate Content Plan** → gọi render với `render_format="content"`
- Màn **Review AI Plan** (đọc `content_plan_json`) → **Render**

Không đụng logic tab Clip/Recap.

---

## 10. Thứ tự build theo phase (đề xuất)

- **P1 — Scaffold LOW-risk (an toàn nhất):** `content_plan.py` +
  `content_prompts.py` + `content_parser.py` + migration 0015 + jobs_repo
  helpers + `select_content_plan` dispatcher/provider stubs. Chưa wire vào
  render. Test: unit từng khối. → **checkpoint duyệt.**
- **P2 — Engine mới:** `content_background.py` + `content_scene_render.py`
  (1 scene → clip). Test: render 1 scene ra file hợp lệ (ffprobe: có video +
  audio + duration>0).
- **P3 — Orchestrator:** `content_pipeline.py:run_content` + nhánh dispatch
  trong `_common.py` + `render_format="content"` trong models. Test:
  end-to-end 1 script ngắn → output qua QA gate.
- **P4 — Wire surface + UI:** render_public fields + tab Content FE.
- **P5 (sau):** consume visual/bgm/camera hints; Ken Burns slideshow;
  fallback narration.

Mỗi phase: `py_compile` sau mỗi file Python + `pytest` focused; P3 chạm dispatch
→ **full pytest** (HIGH tier).

---

## 11. Test strategy

- `test_content_plan_roundtrip.py` — from_json/to_json defensive, blob lỗi
  không raise, key lạ bị drop.
- `test_content_parser_returns_none.py` — input rác → `None` (SC #3).
- `test_content_mode_dispatch.py` — `render_format="content"` route tới
  `run_content`, `"clips"`/`"recap"` không đổi.
- `test_render_format_backcompat.py` — payload không có `render_format` /
  casing lạ → vẫn `"clips"` (SC #2).
- `test_content_scene_render.py` — 1 scene → clip có A/V, duration≈TTS.
- `test_migration_0015.py` — additive, DB cũ retrofit không mất dữ liệu.
- **Full suite** phải giữ nguyên baseline count sau khi thêm (P3).

---

## 12. Sacred Contract compliance checklist

| Contract | Áp dụng cho Content |
|---|---|
| #1 result_json 3 alias key | `run_content` finalize phải ghi đủ 3 key |
| #2 field default False/disabled | §7 — script="", format vẫn "clips" |
| #3 AI return None | content_parser + providers không raise |
| #4 stage names frozen | tái dùng enum, không thêm stage |
| #5 part status frozen | mỗi scene = 1 part, dùng enum sẵn |
| #6 `_emit_render_event` frozen | chỉ gọi, không đổi signature |
| #7 app.db sole authority | chỉ ghi qua jobs_repo helpers |
| #8 qa_pipeline không bypass | output cuối qua `_validate_render_output` |

---

## 13. Điểm cần bạn xác nhận khi duyệt

1. Tên field: `content_script`, `content_background_kind/value`,
   `content_bgm_path` — OK hay đổi tên?
2. v1 chỉ **1 nền cho cả video** hay cho phép **nền khác nhau mỗi scene**
   (user chọn tay)? Đề xuất: 1 nền cho v1, per-scene ở P5.
3. Khi AI trả `None` (fail): job **FAILED sạch** (đề xuất) hay cần fallback
   "đọc thẳng script không chia scene"?
4. Provider mặc định cho Content: Gemini (như spec) — xác nhận.
```

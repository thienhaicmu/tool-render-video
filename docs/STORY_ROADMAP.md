# STORY_ROADMAP — Kế hoạch tổng tối ưu Story Mode v2

> Ngày lập: **2026-07-10**. Viết từ source hiện tại (Story v2: Super-Prompt +
> Cue Sheet). Khi tài liệu và code mâu thuẫn: **tin code**. Đây là **plan tổng
> (master roadmap)** — bổ từng phase xuống Developer sau khi user duyệt riêng
> từng phase. Không phase nào bắt đầu code khi chưa có "go ahead".

## 0. Bối cảnh & nguyên tắc

**Luồng Story v2 hiện tại** (`engine/pipeline/story_pipeline_v2.py`):

```
1 super-plan call (gpt-4o)  → StoryPlan v2 (characters/settings/visuals/timeline)
apply_voice_cast_v2         → gán engine+voice/nhân vật (rule-based, no AI)
N images (gpt-image-1, ≤15) → mỗi Visual 1 ảnh, cache theo nội dung
synthesize_timeline (TTS)   → mỗi beat 1 clip audio (VI→Gemini, EN/JP→ElevenLabs)
build_cues (deterministic)  → CUE SHEET tuyệt đối = f(contract + dur TTS thật + seed)
render_one_cue (CPU libx264)→ Ken Burns từng cue, SERIAL
assemble_shots (xfade)      → nối clip
qa_pipeline (Sacred #8)     → DONE
```

**Nguyên tắc bất biến khi thực thi mọi phase:**

- **Sacred Contract #2** — không thêm field bật-mặc-định vào `RenderRequest`.
  Ưu tiên env-gate + field trong `StoryPlan` (persisted trong `story_plan_json`,
  không phải wire surface).
- **Sacred Contract #3** — mọi module AI/visual/TTS/nhạc `return None` / best-effort,
  không raise. Một asset hỏng → degrade, không giết job.
- **Sacred Contract #8** — mọi bước bổ sung audio/ảnh phải chạy TRƯỚC QA để file
  giao được validate ở trạng thái cuối. Không bao giờ bypass QA.
- **Chi phí phẳng theo độ dài** — giữ nguyên triết lý "ít ảnh mạnh, tái dùng qua
  camera focus". Mọi tối ưu chi phí không được phá tính này.
- **Offline-first** — không phụ thuộc dịch vụ cloud bắt buộc; AI degrade mềm.

**Driver chi phí thực tế:** ảnh `gpt-image-1` ≈ 80–90% hoá đơn/video
(≤15 ảnh × ~$0.04–0.07 ≈ $0.6–1). Super-plan gpt-4o ≈ $0.05. ElevenLabs (EN/JP)
đáng kể; Gemini (VI) rẻ. FFmpeg CPU: miễn phí nhưng SERIAL → chậm.

---

## 1. Đồ thị phụ thuộc & thứ tự phase

```
Phase 1 (Q1 nhạc nền)         ── độc lập, khởi động ngay
Phase 2 (C1+C2 ảnh multi-provider + draft/final)
      └─ mở khoá → Phase 5 UI regenerate draft (dùng provider rẻ)
Phase 3 (tốc độ: song song cue + ảnh)   ── độc lập, nhưng đụng CRITICAL
Phase 4 (nhất quán: Q3 reference-sheet + dọn dead-code v1/v2)
      └─ phải quyết số phận đường v1 (/analyze, reference-sheet) TRƯỚC
Phase 5 (UI/UX): cost estimate · voice preview · filmstrip · regenerate
      └─ phụ thuộc Phase 2 cho phần "regenerate bằng draft rẻ"
Phase 6 (chất lượng nâng cao): Q2 vision-QA · Q4 double-encode · Q5 word-timing
      └─ Q2 phụ thuộc Phase 4 (reference-sheet); Q4 nên sau Phase 3
```

**Thứ tự khuyến nghị:** 1 → 2 → 5(phần độc lập) → 3 → 4 → 6.
Lý do: Phase 1 tăng chất lượng cảm nhận ngay, rủi ro vừa. Phase 2 cắt chi phí lớn
nhất và mở khoá UX (Phase 5). Phase 3 (tốc độ) đụng CRITICAL nên làm khi đã ổn
định. Phase 4/6 là chất lượng chuyên sâu, cần đường v1 được dọn trước.

---

## PHASE 1 — Nhạc nền per-scene do AI plan (Q1)  ✅ SẴN SÀNG DUYỆT

**Mục tiêu:** AI gán mood nhạc cho từng cảnh; nhạc chuyển theo cảnh, duck dưới
lời kể. Nạp thư viện nhạc free (CC0 + CC-BY) qua script.

**Rủi ro:** MEDIUM–HIGH (đụng prompt HIGH-tier + mixer + orchestrator).

**Tái dùng sẵn có:** `BGM_DIR/{mood}/*.mp3`, `_pick_bgm_file(mood)`
(`core/config.py`), `mix_with_bgm(duck=True)` (`engine/audio/mixer.py`).
Content mode đã dùng đúng pattern này (1 mood/cả video).

**Kiến trúc:**
```
AI super-plan → mỗi Visual thêm "bgm_mood" (chọn từ danh sách cố định)
build_cues    → plan.bgm_scenes(): gộp cue cùng visual → [(mood, start, end)]
build_scene_bgm_track → mỗi window: _pick_bgm_file(mood) → loop/trim + afade → concat
                        → 1 track nhạc khớp timeline (hàm MỚI trong mixer.py)
mix_with_bgm(duck=True) → duck nhạc dưới narration [hàm ĐÃ CÓ]
QA gate       → validate file cuối (đã có nhạc)
```

**Thay đổi theo file:**

| File | Tier | Thay đổi |
|------|------|----------|
| `domain/story_plan_v2.py` | LOW | + `Visual.bgm_mood: str=""` (additive; `_visual_from` đọc thêm) · + `StoryPlan.bgm_scenes()` gộp cue theo visual_id |
| `ai/llm/story_prompts_v2.py` | HIGH | + `"bgm_mood"` vào `_SCHEMA` (raw constant, an toàn brace) + 1 rule chọn mood · bump `SUPER_PROMPT_VERSION` s1→s2 |
| `engine/audio/mixer.py` | MEDIUM | **thêm** `build_scene_bgm_track(segments, total_sec, out)` (loop+trim+afade+concat, best-effort). Không sửa hàm cũ |
| `engine/pipeline/story_pipeline_v2.py` | MEDIUM | sau `assemble_shots`, TRƯỚC `_finalize`: build track → `mix_with_bgm(duck=True)` thay `final_out` tại chỗ · gate `STORY_AUTO_BGM` (default 1) · emit `story.bgm.ready` |
| `core/config.py` | LOW | + `STORY_BGM_MOODS` (danh sách mood dùng chung prompt + script) |
| `scripts/fetch_free_bgm.py` | mới | tải ~15–25 track CC0+CC-BY vào `BGM_DIR/{mood}/` + `ATTRIBUTION.txt`, idempotent |
| `tests/test_story_bgm_*.py` | mới | `bgm_scenes()` gộp đúng · `build_scene_bgm_track` fallback khi thiếu file · prompt chứa field mới |

**Bộ mood cố định:** `tense · calm · epic · sad · romantic · mysterious · action ·
hopeful · dark · default`. AI chọn 1/visual; unknown → `default`.

**Bản quyền:** CC0 (không cần ghi công) + CC-BY (ghi vào `ATTRIBUTION.txt`; user
nên đưa credit vào mô tả video). Không đụng nội dung Content-ID.

**Test gate:** focused `test_story_bgm_*` + `test_run_story_v2_e2e` +
`test_story_plan_v2` + `test_super_parser_v2` + `test_ffmpeg_helpers`; khuyến nghị
full suite (đụng prompt HIGH).

**Rollback:** `STORY_AUTO_BGM=0` → về hành vi cũ hoàn toàn.

---

## PHASE 2 — Ảnh multi-provider + draft/final (C1 + C2)  ← ĐÒN BẨY CHI PHÍ LỚN NHẤT

**Mục tiêu:** cắt 70–95% chi phí ảnh. Provider rẻ (Pollinations/Flux-schnell/SDXL)
cho **draft** ở màn Review; `gpt-image-1` cho **final** chỉ khi user duyệt.

**Rủi ro:** HIGH (đụng `visual/story_image.py` + orchestrator + endpoint preview).

**Ý chính:**
- Trừu tượng hoá provider ảnh: `story_image.generate_visual_image` nhận `provider`/
  `tier`. Tái dùng `visual/provider_pollinations.py` (đã có, free).
- Endpoint `/api/story/visual/preview` + vòng render "draft" dùng provider rẻ;
  `story_plan_override` mang cờ "đã chốt" → render final gọi gpt-image-1.
- Giữ nguyên cache key (thêm `provider` vào key).

**Mở khoá:** Phase 5 (nút "🔄 đổi ảnh" trong Review dùng draft rẻ).

**Phụ thuộc:** không. Nên làm ngay sau Phase 1.

**Test gate:** `test_story_visual_*`, `test_story_generate_images_v2`, e2e.

---

## PHASE 3 — Tốc độ: song song hoá render cue + sinh ảnh

**Mục tiêu:** giảm wall-time. Hiện `_generate_images` và vòng render cue đều SERIAL.

**Rủi ro:** **CRITICAL** phần render loop (đụng JobStage/JobPartStage state machine
trong orchestrator) → theo **Render Edit Protocol** (Planner + duyệt rõ + full
pytest before/after).

**Ý chính:**
- Render cue: `ThreadPoolExecutor` (CPU libx264, KHÔNG NVENC → không tranh chấp
  GPU). Giữ thứ tự part_no, giữ nguyên emit part-status (Sacred #5).
- Sinh ảnh: bounded-parallel 2–3 luồng gpt-image-1, vẫn emit `story.visual.ready`.

**Phụ thuộc:** nên sau Phase 2 (tránh double-churn `story_image.py`).

**Test gate:** **full pytest** before/after (CRITICAL); so khớp số test baseline.

---

## PHASE 4 — Nhất quán nhân vật (Q3) + dọn dead-code v1/v2

**Mục tiêu:** khoá consistency nhân vật qua ảnh reference-sheet (không chỉ text),
đồng thời quyết số phận đường v1.

**Rủi ro:** HIGH. **Chặn:** phải quyết TRƯỚC — đường v1 (`/api/story/analyze`
StoryBible, `/character/reference-sheet`, `story_director.py`, `qa.py`,
`generate_shot_image`) hiện lơ lửng: FE chỉ gọi `/plan` (v2). Hoặc (a) **nối**
reference-sheet vào flow v2 (giải Q3), hoặc (b) **dọn** theo chuẩn dead-code.

**Ý chính (nếu nối):**
- Trước khi sinh ảnh: auto-gen reference-sheet cho nhân vật chính (+1 ảnh/nhân vật)
  → fill `plan.render.refs` → gpt-image-1 image-edit điều kiện hoá theo ref.
- One-off render: hiện `refs` rỗng → consistency yếu; đây là điểm vá.

**Phụ thuộc:** cần khảo sát consumer đường v1 (Planner enumerate) trước khi xoá.

**Test gate:** `test_story_reference_sheet`, `test_story_voice_cast`, e2e.

### ✅ Đã làm (2026-07-10) — Q3 nối reference-sheet vào v2
`_generate_reference_sheets` chạy trước image gen, điền `plan.render.refs[cid]` cho
mỗi nhân vật trong visuals (chỉ provider=gpt_image; Free bỏ qua). Series pin/reuse
qua `story_repo`; reference-sheet content-addressed cache (sinh 1 lần/nhân vật).
Env `STORY_REFERENCE_SHEETS` (default on). 6 test mới; full pytest 2822.

### ✅ ĐÃ LÀM (verified 2026-07-11) — dead-code v1 đã xóa sạch
Việc "dọn dead-code v1" đã được **thực thi** (không còn HOÃN). Đối chiếu code hiện tại:
- `story_director.py` / `story_prompts.py` / `story_parser.py` / `story_chunker.py` (v1)
  và `ai/vision/qa.py` → **đã xóa** (chỉ còn `.pyc` mồ côi trong `__pycache__`, vô hại).
- Endpoint `POST /api/story/analyze` + `analyze_story` / `run_story_intelligence` →
  **đã gỡ** (grep toàn `backend/app` = 0). `run_story` v1 không còn.
- `domain/story_plan.py` giờ **chỉ còn `StoryCharacter`** (LIVE — dùng bởi
  `/character/reference-sheet` + Q3). Toàn bộ `StoryBible`/`StoryScene`/`Shot`/… đã bỏ.

> ⚠️ Doc lỗi thời: `docs/audit-2026-07-10/v1-story-deadcode.md` mô tả `/analyze`
> "còn mounted" và đề xuất removal chưa làm — **đã lỗi thời**, xem addendum cuối file
> đó. Router Story hiện tại: `/plan`, `/visual/*`, `/character/reference-sheet` +
> `/character/master`, `/narration/*`, `/voices`, `/projects*`, `/assets*` — **không**
> có `/analyze`.

---

## PHASE 5 — UI/UX Story Studio

**Mục tiêu:** trải nghiệm + kiểm soát chi phí trực quan. UI sinh động.

**Rủi ro:** LOW–MEDIUM (frontend). Làm được ngay không cần duyệt nặng.

**Hạng mục:**
- **Cost estimate trước render**: map `image_count/beat_count/estimated_total_sec`
  (đã có từ `/plan`) → "~N ảnh · ~$X · ~Y phút" ở nút Render.
- **Regenerate từng Visual** trong Review (nút "🔄 đổi ảnh") — dùng draft rẻ
  (Phase 2). Preview Ken Burns bằng CSS transform khi hover (không tốn render).
- **Voice preview per-nhân vật**: đã có `/narration/preview`.
- **Filmstrip monitor**: reveal ảnh lần lượt (event `story.visual.ready` đã có),
  progress theo cue, skeleton shimmer, "đang lồng tiếng beat k/N".
- **Cost guardrail**: ước tính > ngưỡng → cảnh báo + gợi ý hạ ceiling/dùng draft.

**Phụ thuộc:** phần "regenerate draft" chờ Phase 2; các phần khác độc lập.

---

## PHASE 6 — Chất lượng nâng cao

| Mục | Nội dung | Tier | Phụ thuộc |
|-----|----------|------|-----------|
| Q2 | Vision-QA ảnh optional + regen `variant` (env-gated, chỉ tier high/beat hook) | HIGH | Phase 4 (reference-sheet) |
| Q4 | Bỏ double-encode: render timeline 1 filtergraph hoặc xfade stream-copy nơi được | HIGH | Phase 3 |
| Q5 | Word-timing full-subtitle: Whisper align per-beat fill `beat_audio.words` | MEDIUM | — |

---

## 2. Chỉ số thành công (đo trước/sau)

- **Chi phí/video** (USD): trước ~$0.6–1 → sau Phase 2 mục tiêu <$0.15 (draft) / ảnh
  final chỉ cho bản chốt.
- **Wall-time/video**: đo trước/sau Phase 3 (kỳ vọng giảm ~40–60% nhờ song song).
- **Chất lượng cảm nhận**: Phase 1 (có nhạc) + Phase 4 (nhân vật nhất quán) —
  đánh giá định tính qua ai_eval nếu áp dụng.
- **Regression**: mỗi phase giữ nguyên số test baseline; Sacred Contracts nguyên vẹn.

## 3. Trạng thái

| Phase | Trạng thái | Ghi chú |
|-------|-----------|---------|
| 1 — Nhạc nền Q1 | **✅ ĐÃ TRIỂN KHAI (2026-07-10)** | per-scene bgm_mood (prompt s2) · `build_scene_bgm_track` + duck · thư viện nhạc CC0/CC-BY đóng gói trong `assets/bgm` (bundled, git-tracked, khỏi tải lại) · env `STORY_AUTO_BGM` |
| 2 — Ảnh C1+C2 | **✅ ĐÃ TRIỂN KHAI (2026-07-10)** | multi-provider `story_image` (gpt_image \| pollinations free) · draft/final split: Review tự sinh storyboard FREE, final theo `story_image_provider` (mặc định premium, Sacred #2) · UI toggle free/premium + cost hint · field trên RenderRequest + wire surface + TS. Full suite 2814 pass |
| 3 — Tốc độ | **✅ ĐÃ TRIỂN KHAI (2026-07-10)** | song song hóa sinh ảnh + render cue (ThreadPoolExecutor; work trong thread, thu trên main thread → không lock, worker DB-free) · `-threads` cap + textfile per-cue chống race · env `STORY_RENDER_WORKERS`(2)/`STORY_IMAGE_WORKERS`(3), =1 rollback serial · JobStage/PartStage giữ nguyên · full pytest 2816 pass |
| 4 — Nhất quán nhân vật (Q3) | **✅ ĐÃ TRIỂN KHAI (2026-07-10)** | auto reference-sheet điền `plan.render.refs` → gpt-image-1 image-edit giữ nhân vật nhất quán · CHỈ khi provider=gpt_image (Free bỏ qua) · env `STORY_REFERENCE_SHEETS` (default on) · series pin/reuse · reference-sheet content-addressed cache (sinh 1 lần). Full pytest 2822. **Dọn dead-code v1 = ✅ ĐÃ LÀM** (verified 2026-07-11 — v1 tree xóa sạch, `/analyze` đã gỡ; xem dưới) |
| 5 — UI/UX | **✅ ĐÃ TRIỂN KHAI (2026-07-10)** | Phase 2 đã có cost estimate + regenerate draft; Phase 5 thêm: (A) nghe thử giọng per-nhân vật (`previewNarration`), (B) Ken Burns hover preview, (C) reveal + shimmer sinh động, (D) cost guardrail. Thuần FE, `tsc -b` xanh. Cần `npm run build` để vào static-v2 |
| 6 — Chất lượng nâng cao | **Q4 ✅ (2026-07-10)** · Q2/Q5 ⏳ | Q4: cue intermediate near-lossless (`STORY_CUE_CRF`=15/`STORY_CUE_PRESET`=veryfast) → xfade re-encode là pass chất lượng duy nhất, bỏ hình phạt double-encode; KHÔNG single-filtergraph (giữ partial-success + Phase 3 parallel). Q2 vision-QA + Q5 word-timing chưa làm |
| SVG — Offline chibi art | **✅ MERGED main (2026-07-11)** | Thay/đặt-mặc-định **SVG procedural chibi** cho gpt-image → render **$0, offline**. Phase 0.5/A/B/C (`svg_char`/`svg_scene`/`svg_presets` + `svg_raster` resvg-py) · **library-pick** (`STORY_LIBRARY_PICK`: catalog vào super-prompt → AI xuất `CharacterDef.asset`/`SettingDef.asset` slug → render dùng đúng file) · **N4** overlay emotion+pose per-beat · **matching mạnh** (fuzzy char đối xứng bg, `best_asset` chấm điểm theo `description` + nới scope) · provider `svg` = FE default (gpt-image thành premium opt-in, Sacred #2 nguyên). Kho **511 asset** tái lập qua `backend/scripts/gen_svg_library.py` (56 archetype). Full pytest 2999 |

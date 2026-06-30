# Recap / Review Film Mode — Design Spec

> **Status: DESIGN — chưa implement.** Viết 2026-06-29 theo yêu cầu review.
> Mục tiêu: thêm chế độ tạo **1 video recap/review phim dài**, AI chia chương
> (act), AI tự chọn cảnh + tự quyết độ dài, áp dụng narration **rewrite/reaction**
> liên mạch, kèm **UI "live build"** xem AI dựng recap theo thời gian thực.
>
> Khi code: tin code, theo Render Edit Protocol cho mọi file CRITICAL.

## 0. Quyết định sản phẩm đã chốt
- Output: **1 video dài, chia chương (act)** — mở → thân → cao trào → kết, có thẻ tiêu đề chương.
- Độ dài: **AI tự quyết hoàn toàn, co giãn theo độ dài phim** (phim 1–2 tiếng → recap dài tương ứng). **KHÔNG ép trần cứng** kiểu 30 phút; chỉ có "guard chống chạy loạn" rất rộng (recap không vượt độ dài phim gốc). Không có ô người dùng ép phút.
- Chọn cảnh: **AI tự chọn toàn bộ** (người dùng chỉ cấu hình + render).
- Narration: tái dùng **rewrite** và **reaction** (đã có) ở quy mô toàn recap.
- UI: **Live build timeline + kịch bản** chảy realtime qua WebSocket.
- **Tỉ lệ khung: mặc định 16:9 ngang** (review phim, giữ khung gốc).
- **Thẻ act: frame phim làm mờ + tiêu đề chương đè lên** (điện ảnh).
- **Burn phụ đề narration trên recap: CÓ** (chữ narrator hiện dưới màn hình, đồng bộ voice).

## 1. Khoảng trống so với hiện tại
Pipeline hiện tại = N clip ngắn rời, mỗi segment 1 file, `target_duration` ≤ 350s,
narration tính per-clip. Recap cần: chọn cảnh **chronological phủ cả phim** → **concat
1 output dài** → narration **liên mạch** → **act/chapter**. Đây là một **render mode mới**,
tách nhánh, gated bởi field `render_format` (mode `clips` giữ nguyên 100%).

---

## 2. Workflow & Kiến trúc

### 2.1 Component map (thành phần & liên kết)

```
┌───────────────────────────── FRONTEND (React) ─────────────────────────────┐
│ StepConfigure.tsx        RenderWorkflow.tsx          RecapLiveView.tsx (mới) │
│  • mode clips|recap        • build payload             • timeline act/scene  │
│  • panel cấu hình recap    • render_format="recap"     • script realtime     │
└───────────┬─────────────────────────┬───────────────────────────▲──────────┘
            │ POST /api/render/process │ GET /api/jobs/{id}         │ WS recap.*
            ▼                          ▼ (poll fallback)            │ events
┌───────────────────────────── BACKEND (FastAPI) ────────────────────┴────────┐
│ routers/lifecycle → _common.process_render → jobs/manager (queue)            │
│                                   │                                          │
│                                   ▼  worker thread                           │
│  render_pipeline.run_render_pipeline()                                       │
│     └─ if render_format=="recap"  →  recap_pipeline.run_recap()  (MỚI)       │
│            1. Whisper full SRT (đã có: llm_pipeline)                         │
│            2. ai.llm.select_recap_plan() ───────► RecapPlan (domain mới)     │
│            3. per-scene render (tái dùng stages/part_renderer)               │
│            4. recap_title_card.py  (thẻ act: frame mờ + tiêu đề)             │
│            5. recap_assembler.py   (CONCAT 1 video dài)                      │
│            6. narration recap-scale (rewrite/reaction) + mixer duck+loudnorm │
│            7. burn phụ đề narration (subtitle engine đã có)                  │
│            8. qa_pipeline validate 1 output  →  finalize  →  DONE            │
│                                   │                                          │
│     mọi bước phát _emit_render_event(recap.*) ─► EventBroadcaster ─► WS      │
└──────────────────┬───────────────────────────────────────────────┬─────────┘
                   ▼ recap_plan_json (additive)                      ▼ FFmpeg
              SQLite jobs                                   Whisper · concat · drawtext
```

### 2.2 Luồng end-to-end (sequence)

```
User                FE                  API/Queue        recap_pipeline        AI(LLM)        FFmpeg         WS→UI
 │  chọn recap +cfg  │                     │                  │                  │              │              │
 │──────────────────►│  POST /process     │                  │                  │              │              │
 │                   │────────────────────►│ tạo job (queued) │                  │              │              │
 │                   │◄─ job_id ───────────│                  │                  │              │              │
 │                   │  mở WS /jobs/{id}/ws│──────────────────────────────────────────────────────────────►│ live view sẵn sàng
 │                   │                     │ dispatch worker ►│                  │              │              │
 │                   │                     │                  │ Whisper full SRT │              │  (transcribe)│ recap.transcribe
 │                   │                     │                  │ select_recap_plan│─────────────►│              │
 │                   │                     │                  │◄── RecapPlan ────│              │              │ recap.plan.ready (acts/scenes)
 │                   │                     │                  │ render scene 1..N│ (per scene)  │ cut/crop/sub │ recap.scene.rendered (tô timeline)
 │                   │                     │                  │ narration/scene  │ rewrite/react│              │ recap.narration.scene (script chảy)
 │                   │                     │                  │ act title cards  │              │ drawtext+blur│ recap.act.card
 │                   │                     │                  │ CONCAT + mix     │              │ concat+amix  │ recap.concat.start/done
 │                   │                     │                  │ burn narration sub+ qa          │ subtitle     │ render.complete
 │                   │◄─ poll/WS: DONE + output path ─────────────────────────────────────────────────────►│ video sẵn sàng
```

### 2.3 Luồng stage nội bộ recap_pipeline

```
run_recap(payload, job_id)
  │  STARTING → TRANSCRIBING_FULL        (tái dùng JobStage hiện có)
  ├─ full_srt = whisper(source)
  │  ANALYZING / SEGMENT_BUILDING
  ├─ recap_plan = select_recap_plan(srt, video_duration, tone, narration_mode)
  │     └─ acts[] → scenes[] (chronological, is_climax, narration_intent)
  │  persist recap_plan_json
  │  RENDERING_PARALLEL
  ├─ for scene in flatten(acts):           # scene = "part" → parts[] của WS
  │     render_scene = part_renderer(cut→crop→subtitle)   # tái dùng nguyên
  ├─ for act in acts:
  │     card = recap_title_card(frame_blur + act.title)
  ├─ timeline = [card_1, scene…, card_2, scene…]   # thứ tự act/scene
  ├─ concat_video = recap_assembler.concat(timeline)        # 1 file dài
  │  (narration)
  ├─ narration_track = build_recap_narration(recap_plan, offsets)   # rewrite/reaction
  ├─ mixed = mixer.duck(concat_video, narration_track) + loudnorm
  ├─ mixed = part_reaction_freeze(mixed, climax_points)     # freeze cảnh cao trào
  ├─ final = burn_subtitle(mixed, narration_srt)            # phụ đề narration
  │  WRITING_REPORT
  └─ qa_pipeline.validate(final) → finalize → DONE
```

### 2.4 Vòng đời dữ liệu RecapPlan

```
LLM JSON ──parse──► RecapPlan(dataclass) ──to_json──► jobs.recap_plan_json (DB)
                          │                                   │
                          │ flatten acts→scenes               │ resume/retry: from_json
                          ▼                                   ▼ (bỏ qua gọi LLM lại)
                  render + narration + concat        nạp lại plan đã lưu
```

### 2.5 Luồng event Live-build (WS → UI)

```
_emit_render_event(event="recap.*", …)              RecapLiveView.tsx
   recap.plan.ready   {acts:[{title,beat,scenes:n}]} ─► dựng khung timeline (act blocks)
   recap.scene.rendered {act_i, scene_i, thumb?}     ─► scene block sáng dần
   recap.narration.scene {scene_i, text}             ─► panel script cuộn + chảy chữ
   recap.freeze.marked  {scene_i, hold}              ─► marker ⏸ trên timeline
   recap.act.card       {act_i, title}               ─► chèn card block
   recap.concat.start / recap.concat.done            ─► thanh trạng thái "đang ghép…"
   render.complete (đã có)                           ─► hiện player video recap
```
> WS shape gốc `{job, parts, summary}` **giữ nguyên** (parts[] = scenes, UI tiến độ cũ vẫn chạy);
> các `recap.*` là **event name mới (additive)** trong cùng cấu trúc — không đổi chữ ký `_emit_render_event` (Sacred #6).

---

## 3. Pha R1 — Nền backend: chọn cảnh + RecapPlan  `[HIGH]`

### 3.1 Model (`backend/app/models/render.py`, `render_public.py`)
- `render_format: str = "clips"` — `"clips" | "recap"`. Default `"clips"` (Sacred #2).
  Validator giới hạn 2 giá trị. FE-facing → thêm vào `FE_FACING_FIELDS`.
- **Độ dài AI tự quyết, co giãn theo phim** → KHÔNG thêm field override phút, **KHÔNG ép
  trần cứng**. AI nhận `video_duration` và chọn độ dài recap tương xứng (gợi ý tỉ lệ trong
  prompt, vd ~10–25% runtime — AI tự cân theo nội dung). Guard duy nhất: recap **không
  vượt độ dài phim gốc** + một ceiling chống-chạy-loạn rất rộng `RECAP_RUNAWAY_CAP_SEC`
  (mặc định = độ dài phim, hoặc env nếu cần) chỉ để chặn lỗi pathological, KHÔNG phải bộ
  giới hạn nội dung.
- Recap mặc định `aspect_ratio="16:9"` (field đã có). Khi `render_format=="recap"` và
  người dùng chưa đổi, FE set 16:9; BE tôn trọng giá trị payload.
- Cập nhật 3 test pin field-count (như đã làm cho `narration_mode`): `test_schemas_split_re_export`, `test_render_request_public_surface`, `test_render_field_groups` + TS interface `api.ts`. (Chỉ +1 field `render_format`.)

### 3.2 Domain `RecapPlan` (`backend/app/domain/recap_plan.py` — MỚI, LOW tier)
Pure dataclass, (de)serialise phòng thủ, không I/O — giống `render_plan.py`:
```
RecapPlan
  schema_version: int = 1
  total_target_sec: float = 0.0          # AI-decided, clamp [60, RECAP_MAX]
  acts: list[Act]
Act
  title: str = ""                        # tiêu đề chương (thẻ act)
  beat: str = ""                         # setup|rising|climax|resolution
  scenes: list[RecapScene]
RecapScene
  start: float = 0.0                     # giây trong source
  end: float = 0.0
  title: str = ""                        # nhãn cảnh (tùy chọn)
  narration_intent: str = ""             # AI gợi ý narrator nói gì ở cảnh này
  is_climax: bool = False                # cảnh đủ điều kiện reaction freeze
```
- `to_json` deterministic, `from_json` không bao giờ raise (key lạ bỏ, thiếu về default).
- Persist: cột `recap_plan_json` (nullable) trên bảng `jobs` qua **migration additive** (mới, theo mẫu `0001_jobs_add_render_plan_json.py`). Helpers `get_recap_plan/update_recap_plan` trong `db/jobs_repo.py`.

### 3.3 AI selection (`backend/app/features/render/ai/llm/`)  `[HIGH]`
- `recap_prompts.py` (MỚI): prompt yêu cầu AI:
  - Đọc full SRT + thời lượng phim.
  - Chọn cảnh **theo trình tự thời gian** kể trọn mạch phim (không phải top-viral).
  - **Chia act** (setup/rising/climax/resolution) + tiêu đề chương.
  - Quyết tổng thời lượng recap (trong cap), mỗi scene `narration_intent`.
  - Đánh dấu `is_climax` cho cảnh đỉnh (để reaction freeze).
  - Output JSON đúng schema RecapPlan; `check_srt_truncation` cảnh báo nếu transcript bị cắt.
- `recap_parser.py` (MỚI): parse → RecapPlan, không raise (Sacred #3).
- Dispatcher `select_recap_plan(provider, srt_content, video_duration, target_language, tone, narration_mode, recap_target_minutes, api_key, model, ...)` trong `ai/llm/__init__.py`; impl per-provider (gemini/openai/claude) tái dùng `_call_*` + cache (namespace `*-recap`). Temperature: dùng mức quyết đoán (~0.4) cho chọn cảnh; narration vẫn dùng rewrite temp 0.85 ở R3.

### 3.4 R1 không làm
Chưa render/concat. Chỉ sinh + persist RecapPlan + emit `recap.plan.ready` event. Test: parse RecapPlan, model validation, pin counts.

---

## 4. Pha R2 — Dựng & ghép 1 video dài  `[CRITICAL]`

### 4.1 Nhánh pipeline (`render_pipeline.py`, `pipeline_render_loop.py`, finalize)
Khi `render_format=="recap"`:
1. Whisper full SRT (đã có) → `select_recap_plan` → RecapPlan.
2. Flatten acts→scenes (chronological). **Mỗi scene = 1 "part"** → tái dùng `part_renderer`
   (cut/crop/subtitle) → ánh xạ vào `parts[]` của WS (UI tiến độ hiện có vẫn chạy).
3. **Act title cards**: 1 clip tiêu đề/act, **nền = frame mở đầu act làm mờ** (boxblur)
   + tiêu đề chương drawtext đè lên, ~2s. Sinh bằng stage mới `recap_title_card.py`.
4. **Concat** act-card + scenes thành **1 output dài**. Tất cả render về **cùng spec**
   (WxH theo `aspect_ratio`, mặc định `16:9` cho recap; fps; codec; sample rate) → dùng
   **FFmpeg concat demuxer** (nhanh, hạn chế re-encode). Stage mới `recap_assembler.py`.
5. Finalize **một output** (không phải N) → qa validate clip dài + duration accounting
   (tổng = Σ scene + act cards + freeze). Theo Sacred #8.

### 4.2 NVENC / tài nguyên
Concat demuxer không re-encode nếu spec đồng nhất (an toàn NVENC). Title cards + bất kỳ
re-encode nào dùng cùng quy tắc semaphore hiện hành. Render scene song song như part hiện tại.

### 4.3 Rủi ro CRITICAL
`render_pipeline` sở hữu state machine; thêm nhánh recap phải giữ nguyên đường `clips`.
Theo Render Edit Protocol: pytest baseline → sửa tối thiểu → pytest lại. Cân nhắc đặt
phần lớn logic recap trong module riêng (`pipeline/recap_pipeline.py`) để orchestrator
chỉ rẽ nhánh 1 chỗ.

---

## 5. Pha R3 — Narration quy mô recap  `[HIGH]`

- Narration **liên mạch toàn recap**: với mỗi scene, tái dùng rewrite/reaction nhưng
  có **ngữ cảnh xuyên cảnh** (narrator dẫn chuyển cảnh, nhắc lại mạch). `narration_intent`
  của scene + tone + `narration_mode` (reaction) đẩy vào prompt.
- Reaction lead-in→freeze→payoff áp ở scene `is_climax`.
- Build **1 track narration** căn theo timeline đã concat: tính offset mỗi scene trong
  output cuối, đặt narration scene tại offset → **1 lần mix** (duck original + loudnorm,
  hạ tầng đã có ở `mixer.py`). Freeze stage (`part_reaction_freeze.py`) tái dùng, map
  thời gian theo timeline recap.
- **Burn phụ đề narration: CÓ** (đã chốt). Sinh SRT từ các đoạn narration (timestamp =
  offset trên timeline recap) → burn bằng subtitle engine hiện có khi assemble.

---

## 6. Pha R4 — UI: chọn mode + cấu hình  `[FE]`

- `types.ts`: thêm `renderFormat: 'clips' | 'recap'`. (KHÔNG có override phút — AI quyết.)
- `RenderWorkflow.tsx`: default + payload (`render_format`); khi recap, set `aspect_ratio="16:9"` nếu user chưa đổi.
- `StepConfigure.tsx`: **bộ chọn mode Clip ngắn ↔ Recap/Review**; khi recap hiện panel:
  style narration (rewrite/reaction — tái dùng control hiện có), tone, bật act cards,
  burn phụ đề narration (mặc định bật). Độ dài = AI quyết (không có ô phút).
- `i18n.ts`: chuỗi en/vi.
- Khi `recap`: ẩn/khoá các control chỉ hợp clip ngắn (output_count…) cho gọn.

## 7. Pha R5 — UI: Live build view  `[FE]`

- Component mới (vd `RecapLiveView.tsx`) trong màn rendering của `RenderWorkflow`.
- Nguồn dữ liệu: WebSocket hiện có (`/api/jobs/{id}/ws`, shape `{job,parts,summary}` **giữ nguyên**),
  cộng **event recap.* mới** (additive, không đổi chữ ký `_emit_render_event`):
  - `recap.plan.ready` → vẽ khung act/scene timeline.
  - `recap.scene.selected` / `recap.scene.rendered` → tô dần từng cảnh trên timeline.
  - `recap.narration.scene` → kịch bản narration của cảnh **chảy ra realtime**.
  - `recap.freeze.marked` → marker freeze trên timeline.
  - `recap.concat.start/done` → trạng thái ghép.
- Trực quan: thanh timeline ngang chia act (màu theo beat), từng scene sáng dần khi render
  xong, panel script cuộn theo, progress tổng. Đây chính là cảm giác "stream trực tiếp".
- Fallback: nếu WS lỗi → poll `/api/jobs/{id}` (giữ nguyên đảm bảo hiện có).

---

## 8. Hợp đồng & an toàn
- Sacred #2: `render_format` default `"clips"`; mọi field recap mới default tắt/None.
- Sacred #3: AI recap select + parser + freeze không raise, fallback sạch (recap fail →
  job báo lỗi rõ, không treo).
- Sacred #4/#5: tái dùng JobStage/JobPartStage hiện có (scene = part). Không đổi tên stage;
  nếu cần thêm trạng thái recap → cân nhắc kỹ + audit WS consumer (tránh; ưu tiên dùng lại).
- Sacred #6: chỉ **thêm event name mới**, không đổi chữ ký emit. WS shape `{job,parts,summary}` giữ nguyên.
- Sacred #7/#8: `recap_plan_json` additive; qa validate output recap, không bypass.
- API: chỉ **thêm** field; path đóng băng không đổi.

## 9. Risk tier theo file
| Vùng | File | Tier |
|------|------|------|
| Model | `models/render.py`, `render_public.py`, `render_field_groups.py` + 3 test pin + `api.ts` | HIGH |
| Domain | `domain/recap_plan.py` (mới) | LOW |
| DB | migration `00NN_jobs_add_recap_plan_json.py` (mới), `jobs_repo.py` | HIGH |
| AI | `ai/llm/recap_prompts.py`, `recap_parser.py` (mới), `__init__.py`, providers | HIGH |
| Pipeline | `pipeline/recap_pipeline.py` (mới), `render_pipeline.py` (rẽ nhánh), `pipeline_render_loop.py`, finalize | CRITICAL |
| Assembler | `engine/stages/recap_assembler.py`, `recap_title_card.py` (mới) | CRITICAL/HIGH |
| Narration | `part_voice_mix`/`timed_narration` recap-scale, `mixer` (đã có) | HIGH |
| FE | `types.ts`, `RenderWorkflow.tsx`, `StepConfigure.tsx`, `RecapLiveView.tsx` (mới), `i18n.ts`, `api.ts` | FE |

## 10. Test plan
- R1: `test_recap_plan_parse.py` (parse/clamp/không raise), model validation, pin counts, TS interface parity.
- R2: validate concat demuxer + title card bằng FFmpeg tổng hợp (như đã làm cho freeze/loudnorm); qa duration recap; **full pytest** (CRITICAL).
- R3: narration recap-scale + freeze mapping; mix ffmpeg graph.
- R4/R5: `tsc -b` + vitest; event-driven live view render test (mock WS).

## 11. Quyết định đã chốt (2026-06-29)
1. **Tỉ lệ khung**: mặc định **16:9 ngang** (review phim). FE set khi chọn recap; BE tôn trọng payload.
2. **Thẻ act**: **frame mở đầu act làm mờ (boxblur) + tiêu đề chương đè lên**, ~2s.
3. **Burn phụ đề narration**: **CÓ** (mặc định bật cho recap).
4. **Độ dài**: **thuần AI quyết, co giãn theo phim** (phim 1–2h → recap dài tương ứng). KHÔNG ép trần cứng; chỉ guard recap ≤ độ dài phim gốc. Không có ô ép phút.
5. **Spoiler** (chưa quan trọng): mặc định recap kể trọn mạch (review thường tiết lộ); có thể thêm toggle "no-spoiler" ở pha sau nếu cần.

## 12. Thứ tự build đề xuất
R1 → R2 → R3 (backend chạy được end-to-end) → R4 (bấm được trên app) → R5 (live view).
Mỗi pha: code → py_compile/tsc → pytest/vitest → báo cáo → (commit khi bạn duyệt).

---

## 13. R6 — Episodes (Tập) + per-scene audio mode (2026-06-30)

**Thay đổi cốt lõi so với R1–R5:** recap không còn là *1 video dài duy nhất*.
AI Director giờ điều phối toàn bộ theo đề xuất của người dùng:

1. **Chia tập (episodes)** — AI tự quyết chia 1 phim dài thành **1..N tập** tại
   điểm ngắt tự nhiên của cốt truyện. Mỗi tập = **1 output video riêng** (1 entry
   History, có Sacred #1 keys). Chặn mềm theo độ dài phim (`_episode_range`):
   <40′ → 1 tập · 40–70′ → 1–2 · 70–100′ → 2–3 · >100′ → 3–4. Cap cứng
   `RECAP_MAX_EPISODES` (mặc định 4) enforce ở parser (thừa thì gộp vào tập cuối).
2. **AI tự viết lời recap** (đã có từ content-strategy) — narration soạn sẵn theo
   từng scene, engine chỉ TTS.
3. **narrate vs original** — mỗi scene có `audio_mode`:
   - `"narrate"` (mặc định, đa số): TTS lời AI viết, đè lên clip.
   - `"original"` (vài cao trào/câu thoại đắt mỗi tập): **bỏ narration, để tiếng
     gốc bật full**. `narration` ép rỗng. `part_voice_mix` thoát sớm → audio gốc
     nguyên vẹn (không TTS, không duck). **Tự bật phụ đề** cho scene này để người
     xem hiểu thoại gốc.

**Data model** (`domain/recap_plan.py`, `schema_version=2`):
```
RecapPlan → episodes[] → Episode{title, acts[]} → Act → RecapScene{..., audio_mode}
```
`RecapPlan.acts` giữ lại làm **property phẳng** (back-compat). Blob cũ (top-level
`acts`, không `episodes`) → load thành **1 tập** bọc các acts đó → replay
bit-identical (Sacred #2/#3).

**Pipeline** (`recap_pipeline.py`): `_scored_from_recap_plan` gắn `episode_index`
+ `audio_mode` vào mỗi scene; `_assemble_recap_episodes` gom theo tập → concat
mỗi tập 1 file (`{stem}_recap.mp4` nếu 1 tập, `{stem}_recap_epNN.mp4` nếu nhiều);
QA từng tập (tập lỗi bị bỏ qua = partial success, không fail cả job); `outputs[]`
nhiều entry, tập 1 = best.

**FE** (`RecapLiveView.tsx`): event `recap.plan.ready` thêm `episodes[]` +
`scene_modes[]` (phẳng theo part order) + `original_audio_scenes`. Live view nhóm
act theo tập (header "🎞 Tập N") và đánh dấu scene tiếng-gốc (viền tím + 🔊).

**Env**: `RECAP_MAX_EPISODES` (cap tập, default 4) ·
`GEMINI_RECAP_MAX_TOKENS`/`_THINKING_BUDGET` (đã có từ fix truncation).

> Cập nhật mục §11.4: độ dài vẫn AI quyết, nhưng output giờ là **N tập** thay vì
> 1 video — mỗi tập là một arc tự chứa, kết ở hook.

# Story Mode — Nâng cấp "Beat đa thoại" (Kế hoạch phát triển FE + BE)

> Quy hoạch theo hướng phát triển (không vá). Mục tiêu: một **beat = một khung hình**
> (giữ 1 ảnh) chứa **1..N dòng thoại**, mỗi dòng có giọng/biểu cảm riêng; TTS vẫn theo
> beat; **timing luôn theo TTS thật**. Tất cả **additive + sau cờ**, Sacred Contracts giữ.
> Tạo 2026-07-13.

---

## 0. Nguyên tắc thiết kế (bất biến)

1. **Beat = đơn vị KHUNG HÌNH** (giữ 1 ảnh, 1 Ken Burns). Bên trong chứa **nhiều dòng thoại**.
2. **AI plan** quyết: nhân vật, bối cảnh/visual (trừ video mode), nhạc nền, biểu cảm, **ai nói dòng nào**, nội dung. **KHÔNG** ra timestamp.
3. **Timing = TTS thật**: độ dài beat = tổng độ dài audio các dòng. Video mode: video loop/cắt theo TTS (đã đúng).
4. **2 chế độ giọng** (`voice_mode`): `narrator` (kể chuyện, 1 giọng đọc hết) | `dialogue` (mỗi nhân vật 1 giọng).
5. **Backward-safe tuyệt đối**: plan cũ (`narration`+`speaker_id`, không `lines`) vẫn render bit-identical. Cờ `STORY_MULTILINE_BEATS` (default off khi merge, bật sau khi FE sẵn sàng).
6. **FE + BE đi song song từng phase** — không để lệch contract.

---

## 1. Data model mới (nguồn sự thật)

### Line (mới)
```
Line {
  speaker_id: str          # → CharacterDef.id ∪ "" (narrator)
  text:       str          # lời của dòng này
  emotion:    str          # ∈ EMOTION (biểu cảm dòng này)
  pose:       str          # ∈ POSE (cử chỉ, tùy chọn)
}
```

### Beat (đổi)
```
Beat {
  id, visual_id, focus, bgm_mood, hook, hook_text     # thuộc KHUNG HÌNH — giữ nguyên
  lines: [Line, ...]                                   # MỚI — 1..N dòng thoại
  # ── deprecated nhưng GIỮ để backward-compat ──
  narration, speaker_id, emotion, pose                 # = "dòng đơn" ẩn
  # (motion/transition/bgm_cue/... vẫn derive như Phase 3)
}
```

**Quy tắc đọc (chuẩn hóa 1 chỗ):** `beat.effective_lines()`:
- Nếu `lines` không rỗng → dùng `lines`.
- Ngược lại → `[Line(speaker_id, narration, emotion, pose)]` (beat cũ).
→ Toàn bộ downstream chỉ đọc `effective_lines()`, không đọc thẳng `narration`.

---

## 2. BACKEND — theo tầng (mỗi tầng = 1 phase)

### BE-A · Domain contract — `app/domain/story_plan_v2.py` (HIGH)
- Thêm `@dataclass Line` + `Beat.lines: list[Line]`.
- `_line_from(x)` + `_beat_from`: parse `lines[]`; thiếu → tổng hợp 1 line từ `narration/speaker_id/emotion/pose`.
- `Beat.effective_lines()` (chuẩn hóa).
- `beat_est_sec` = Σ len(line.text)/cps.
- `voice_runs()` → gom theo **line.speaker_id** (speaker đổi trong beat).
- `derive_beat_styling`: char_anchor suy theo **dòng chính/đầu tiên** (giữ logic vị trí cố định/nhân vật).
- `to_json/asdict`: `lines` được serialize (dataclass tự lo).
- **Test**: parse lines, backward-compat (plan cũ), est_sec, voice_runs.

### BE-B · Strict schema + prompt — `story_schema_v2.py` + `story_prompts_v2.py` (HIGH)
- Schema beat (lean): thay `narration/speaker_id/emotion/pose` bằng
  `lines: [{speaker_id, text, emotion, pose}]` + giữ `visual_id/focus/bgm_mood/hook/hook_text`.
- Prompt (P1/P2/P3): dạy **"1 beat = một CẢNH NHỎ; được có 2-4 lượt thoại; mỗi lượt = {speaker,text,emotion}"**. Kể chuyện thuần → `lines` chỉ narrator. Ví dụ 1-shot hội thoại.
- `voice_mode` truyền vào prompt (dialogue → khuyến khích thoại; narrator → mô tả).
- Bump `SUPER_PROMPT_VERSION` (invalidate cache).
- **Test**: schema shape, prompt chứa hướng dẫn lines, backward khi cờ off.

### BE-C · TTS đa dòng — `engine/audio/story_narration.py` (MEDIUM)
- `synthesize_timeline`: mỗi beat → duyệt `effective_lines()`:
  - `voice_mode=dialogue`: mỗi dòng đọc bằng `_voice_for(line.speaker_id)`.
  - `voice_mode=narrator`: mọi dòng dùng giọng narrator.
  - Nối các mp3 dòng → `beat_audio` (1 file/beat, **giữ "TTS theo beat"**).
  - Lưu **`line_timings`** (mốc [start,end] từng dòng trong beat) vào `beat_audio` → phục vụ overlay per-line (BE-E).
- Vẫn song song hóa được ở mức beat (BE-F).
- **Test**: concat đúng thứ tự, dur = tổng, narrator mode 1 giọng, dialogue nhiều giọng.

### BE-D · Voice cast + voice_mode — `story_voice_cast.py` + `models/render*.py` + pipeline (MEDIUM)
- `RenderRequest`/`StoryPlanRequest` thêm `story_voice_mode: str = "dialogue"` (Sacred #2: default an toàn; giá trị hợp lệ narrator|dialogue).
- `apply_voice_cast_v2`: narrator mode → mọi nhân vật trỏ về giọng narrator (nhưng vẫn giữ overlay theo nhân vật).
- Default mode: idea/paste không nhân vật rõ → narrator; có ≥2 nhân vật thoại → dialogue (gợi ý, user override ở FE).

### BE-E · Overlay theo dòng — `stages/story/beat_render.py` + `visuals_stage.py` + `build_cues` (MEDIUM)
- `Cue` mang `line_timings` (speaker/emotion/pose + [start,end] trong cue).
- `render_one_cue`: v1 = overlay speaker **chính** cả cue; v2 = **đổi overlay theo dòng** (enable/disable master theo mốc dòng bằng biểu thức thời gian ffmpeg).
- `_generate_overlay_masters`: sinh master cho **mọi (speaker,emotion,pose)** xuất hiện trong `lines`.
- **Test**: masters đủ, overlay đổi đúng mốc (v2).

### BE-F · Hiệu năng TTS — `story_narration.py` + `story_pipeline_v2.py` (LOW→MEDIUM)
- Chạy TTS **song song theo beat** (ThreadPool, `STORY_TTS_WORKERS`) + **emit progress** mỗi beat → hết "treo" UI.
- (Độc lập với đa thoại; làm sớm để cải thiện UX.)

---

## 3. FRONTEND — theo tầng (song song BE)

### FE-A · Types — `frontend/src/api/story.ts` + `features/story-studio/types.ts`
- Thêm `interface Line { speaker_id; text; emotion; pose? }`.
- `Beat`: thêm `lines?: Line[]` (giữ `narration/speaker_id/emotion` để đọc plan cũ).
- Helper `beatLines(beat): Line[]` (mirror `effective_lines`).
- `StoryPlanRequest`/config: thêm `voice_mode: 'narrator' | 'dialogue'`.

### FE-B · TimelineEditor — `features/story-studio/PlanReview/TimelineEditor.tsx` (trọng tâm FE)
- Mỗi beat hiển thị **danh sách dòng thoại** (thay 1 ô narration):
  - Mỗi dòng: **dropdown chọn nhân vật/narrator** + ô **text** + **select emotion** (+ pose).
  - Nút **＋ thêm dòng**, **✕ xóa**, kéo **sắp thứ tự**.
  - Badge màu theo nhân vật để nhìn nhanh ai nói.
- Beat cũ (chỉ `narration`) → tự hiển thị như **1 dòng narrator** (không vỡ).
- Header beat giữ: chọn `visual_id`, `focus`, `bgm_mood`, hook.

### FE-C · Voice mode + Characters — `InputScreen.tsx` / `PlanReview/CharactersPanel.tsx`
- Toggle **Chế độ giọng**: `Kể chuyện (1 giọng)` | `Hội thoại (mỗi nhân vật 1 giọng)`.
- CharactersPanel: khi `dialogue`, cho **gán/nghe thử giọng** từng nhân vật; khi `narrator`, ẩn.

### FE-D · Narration preview — `api/story.ts` + PlanReview
- `/narration/preview` nhận **cả beat nhiều dòng** (hoặc 1 dòng) → nghe thử cả beat với đúng giọng/chế độ.

### FE-E · Validation/UX
- Cảnh báo dòng rỗng, speaker không tồn tại, beat không có dòng nào.
- Đếm ước lượng độ dài theo tổng ký tự các dòng.

---

## 4. ROADMAP (thứ tự làm, FE+BE khóa contract theo phase)

| Phase | Backend | Frontend | Cờ/Contract | Risk |
|------|---------|----------|-------------|------|
| **P0** | BE-F: TTS song song + progress | StoryMonitor hiện tiến độ TTS | — | LOW — sửa "treo" ngay, độc lập |
| **P1** | BE-A domain `lines[]` + BE-B schema/prompt | FE-A types + `beatLines()` | `STORY_MULTILINE_BEATS` off | HIGH (contract) |
| **P2** | BE-C TTS đa dòng + BE-D voice_mode | FE-B TimelineEditor đa dòng + FE-C voice toggle | bật cờ ở môi trường dev | HIGH |
| **P3** | BE-E overlay theo dòng (v2) | FE-D preview beat + FE-E validation | — | MEDIUM |
| **P4** | Dọn deprecated đường đơn (sau khi ổn định) | polish UI, i18n | bật cờ default | MEDIUM |

**Cổng giữa các phase:** P1 chỉ merge khi FE-A đã đọc được `lines` (kể cả rỗng). P2 chỉ bật cờ khi TimelineEditor sửa được đa dòng. Không bật `STORY_MULTILINE_BEATS` mặc định cho tới hết P3.

---

## 5. Hợp đồng & rủi ro

- **Sacred #2**: `story_voice_mode` + mọi field mới của RenderRequest default an toàn (dialogue là default hành vi mới nhưng chỉ kích hoạt khi plan CÓ `lines`; plan cũ không có `lines` → đường đơn cũ).
- **Schema additive**: `lines[]` thêm mới; beat cũ vẫn parse.
- **Cache**: bump `SUPER_PROMPT_VERSION` + (nếu cần) story schema version.
- **Rollback**: `STORY_MULTILINE_BEATS=0` → prompt/schema/parse về đường đơn, bit-identical.
- **Test bắt buộc**: full pytest cho P1/P2 (đụng contract + pipeline); FE type-check + render TimelineEditor.

---

## 6. Định nghĩa "XONG" mỗi phase

- **P0**: render 30 beat, UI cập nhật tiến độ TTS liên tục, tổng thời gian TTS giảm rõ.
- **P1**: plan có `lines[]` round-trip (BE↔FE), plan cũ vẫn chạy; test full xanh.
- **P2**: 1 beat có A/B/narrator thoại, nghe đúng giọng theo `voice_mode`; TimelineEditor thêm/xóa/sửa dòng.
- **P3**: overlay nhân vật đổi theo dòng đang nói; validation FE hoạt động.
- **P4**: tắt đường đơn cũ (giữ backward parse), UI hoàn thiện.

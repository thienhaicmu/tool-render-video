# Content Studio — Redesign Design Plan

> Kế hoạch thiết kế (chưa code). Bám 100% năng lực backend hiện có + design-system
> sẵn có. North-star: **người dùng NHÌN THẤY AI đang làm gì, theo thời gian thực,
> có animation** — biến "hộp đen AI" thành trải nghiệm trong suốt.
>
> File thật sẽ sửa: `frontend/src/features/content-studio/` (hiện là 1 file
> `ContentStudio.tsx` 709 dòng, toàn inline-style). Không đụng backend.

---

## 1. Nguyên tắc thiết kế

1. **AI-visible (trong suốt):** mọi bước AI làm đều hiện ra UI — hiểu kịch bản →
   lập kế hoạch → chỉnh thời lượng → kiểm tra lời kể → refine → chọn nguồn ảnh →
   sinh ảnh → ghép video. Không còn spinner "AI analyzing…" chung chung.
2. **Design-system-native:** dùng `components/ui/*` + token (`--space/--surface/
   --radius/--accent/--ai-*`) + `motion.css`. Xoá sạch object inline-style `S`.
3. **Animated có mục đích:** animation để *truyền đạt trạng thái AI*, không trang
   trí. Tôn trọng `prefers-reduced-motion` (motion.css đã lo).
4. **Giữ nguyên chức năng:** không bỏ tính năng nào; chỉ đổi cách trình bày +
   thêm lớp hiển thị AI.
5. **Không giao mù:** sau khi code, chạy app chụp màn hình tự kiểm.

---

## 2. Bản đồ NĂNG LỰC BACKEND → TÍNH NĂNG UI (đầy đủ)

| Backend (endpoint / event / field) | Tính năng UI | Hiển thị AI + animation |
|---|---|---|
| `POST /api/content/plan` → ContentPlan | Nút "Lập kế hoạch (AI)" → màn AI Planning | Card "AI Director đang đọc kịch bản" + typing dots |
| ContentPlan.topic/tone/audience/video_style | Header kế hoạch | Badge fade-in |
| ContentPlan.story_bible (setting/hook/cta/characters) | Panel **"AI hiểu gì về nội dung"** | slide-up, character chips |
| ContentPlan.scenes[] | Danh sách scene card sửa được | cascade `clip-card-appear` (stagger) |
| scene.role/emotion/reading_speed/pause | Điều khiển per-scene | segmented + select |
| scene.narration | Textarea lời kể | typing effect khi refine |
| scene.est_duration_sec | Chip thời lượng | count-up |
| scene.visual_prompt/negative_prompt | Ô prompt ảnh | — |
| scene.asset_suggestion | Badge gợi ý nguồn (ai_image/stock…) | AIChip advisory |
| scene.visual_source/path/ken_burns | Nền riêng per-scene | — |
| **`duration_fit`** (/plan resp + `content.timing.fit`) | Banner **"AI đã chỉnh nhịp đọc để vừa Xs"** | thanh before→after animate (`render-fill-glow`) + AIChip **applied** |
| **`narration_audit`** (/plan resp + `content.narration.audit`) | Cờ per-scene: **quá tải / thưa / ok** | border-pulse scene, AIChip **advisory**, filter "chỉ xem scene yếu" |
| **`content.narration.refined`** (WS) | Lời kể được viết lại | typing/diff highlight thay text cũ |
| `POST /api/content/estimate` → cost | Panel **"Chi phí AI ước tính"** | meter cost + bar theo provider count-up; cảnh báo vượt budget |
| `POST /api/content/narration/preview` | Nút 🔊 nghe thử per-scene | waveform/pulse khi phát, hiện "~Xs" |
| `POST /api/content/publish-meta` | Panel SEO title/desc/tags/thumbnail | reveal sau khi render xong |
| Projects CRUD | "Bản nháp gần đây" | chip grid, autosave chip "Đã lưu ✓" fade |
| `POST /api/render/process` (render_format=content) | Bắt đầu render | chuyển sang màn Live |
| WS `content.plan.ready` (scenes + timing/role/emotion) | Timeline scene | scene blocks vẽ theo tỉ lệ dur |
| WS stage: ANALYZING→SEGMENT_BUILDING→RENDERING(_PARALLEL)→WRITING_REPORT→DONE | **AI Activity Feed** (timeline dọc) | mỗi bước slide-in, bước đang chạy `status-pulse` |
| WS parts scene_NNN: QUEUED→RENDERING→DONE/FAILED + message ("synthesizing narration"/"visual resolve failed") | Lưới **Scene Cards** live | mỗi card: mini-progress `progress-shimmer`, đổi trạng thái mượt |
| provider mỗi scene (decide_provider: local/stock/ai_image/ai_video) | Badge nguồn trên scene card | icon + màu theo tier |
| Imagen tier (fast/standard/ultra) + key rotation | Badge "Imagen ultra", toast "đổi key" | thumbnail ảnh fade-in khi sinh xong |
| result `ai_cost` (by_provider, estimated) | Tổng kết chi phí thực | count-up |
| WS `render.complete` + output | Video preview + tải về | success `score-xl-appear` |
| summary (WsProgressSummary) | Vòng % tổng | ConicRing/ScoreRing animate |

> Kết luận: **mọi thứ backend đã phát ra đều có chỗ hiển thị**. Trọng tâm redesign
> là **AI Activity Layer** (mục 4) — hiện chưa được UI khai thác.

---

## 2B. ⭐ NGUỒN & VALIDATION THEO TỪNG MODE (không "validate cho có")

> Đây là yêu cầu cứng: phải **check nguồn của render là gì** rồi validate ĐÚNG
> theo trường hợp — không đòi thứ mode đó không cần.

### "Nguồn" khác nhau theo mode
| Mode | "Nguồn" thực sự là gì | KHÔNG cần |
|------|------------------------|-----------|
| clips | 1 video local (`source_video_path`) hoặc `edit_session_id` | script |
| recap | 1 video local (phim/tập dài) | script |
| **content** | **SCRIPT** (`content_script`) hoặc plan đã duyệt (`content_plan_override`) | **KHÔNG có video nguồn** |

**🐛 Bug gốc hiện tại (BUG-1):** route `/api/render/process` gọi
`_validate_render_source` **mù mode** → luôn đòi `source_video_path`, nên content
luôn `400 "source_video_path is required when source_mode='local'"`. Test không
bắt vì test content gọi thẳng `run_content`/`process_render`, **bỏ qua route**.

### Ma trận validation cần có (case-aware) — pre-submit (FE) + tại route (BE)
| Trường hợp | clips/recap | content |
|-----------|-------------|---------|
| Nguồn rỗng | 400 "cần source_video_path / chọn video" | 400 "cần script (hoặc duyệt plan)" |
| File nguồn không tồn tại | 400 "Source file not found" | (n/a) |
| Nền = image/video nhưng thiếu path | (n/a) | 400 "chọn file nền, hoặc chuyển sang Màu" |
| Nền image/video path không tồn tại | (n/a) | 400 "Background not found: <path>" |
| `output_dir` rỗng | dùng default đã lưu, else 400 | như clips |
| `output_dir` là file / không ghi được / gần đầy đĩa | 400 (N6/N8 đã có) | như clips |
| provider AI (imagen/stock/veo) thiếu key | **cảnh báo mềm** (tự fallback local, không chặn) | như clips |

**Nguyên tắc validation:**
- **2 lớp:** FE validate trước khi gửi (thông báo tiếng Việt, chặn nút) **và** BE
  validate tại route (nguồn sự thật, chống client sai). Không lớp nào "cho có".
- **Fail-fast + rõ ràng:** báo đúng field sai, gợi ý cách sửa — không lỗi mơ hồ,
  không để chạy 60s rồi mới chết.
- **Degrade mềm** những thứ có fallback (provider thiếu key → dùng nền local):
  cảnh báo, không chặn.

### ⚠ Yêu cầu backend (prerequisite duy nhất — nằm NGOÀI UI)
Redesign UI **không đủ** để sửa BUG-1; cần một fix backend nhỏ, case-aware:
`_validate_render_source` phải rẽ theo `render_format`:
- `content` → validate script/plan + nền asset + output_dir (KHÔNG đòi video).
- `clips/recap` → giữ nguyên logic hiện tại.
+ thêm test đi qua **route thật** cho content (đóng đúng lỗ test đã bỏ sót).
> Đây là MEDIUM-tier (`routers/_common.py`) — sẽ làm ở Phase P0 kèm focused pytest,
> vì không có nó thì mọi UI content vẫn 400.

---

## 2C. CHỌN THƯ MỤC (folder picker) + validate

**🐛 BUG-2 + BUG-3:** hiện `Save folder` là **ô text trơn**, không có nút Browse;
buildPayload lấy `output_dir = cfg.outputDir.trim() || 'output'` → nếu để trống,
video rơi vào thư mục **tương đối `output`** của tiến trình backend, user không
biết ở đâu. Các studio khác đã làm đúng.

### Cơ chế đã có trong app (tái dùng, không chế mới)
- Electron: `window.electronAPI.pickDirectory()` → mở dialog OS, trả **path thật**;
  `window.electronAPI.pathExists(path)` → validate; `openPath(path)` → mở thư mục.
  (StepConfigure `pickOutputDir`, DownloadTab đều dùng.)
- Default đã lưu: `getDefaultOutputDir()` / `putDefaultOutputDir()`
  (`/api/settings/output-dir`) — dùng làm giá trị mặc định.

### Thiết kế trường "Thư mục lưu" cho Content
```
Thư mục lưu *   [ D:\Videos\Content ........... ] [📁 Chọn…] [Mở]
                ✓ Thư mục hợp lệ   /  ⚠ Chưa chọn thư mục   /  ✕ Không tồn tại
```
- Nút **Chọn…** → `electronAPI.pickDirectory()` (Electron). **Fallback trình
  duyệt** (ảnh của bạn là bản browser → `electronAPI` undefined): nút disable +
  tooltip "Chỉ khả dụng trong app desktop", user gõ path tay; validate bằng
  `pathExists` nếu có, nếu không thì **để BE validate** (N6/N8 đã trả 400 rõ).
- Mặc định: nạp `getDefaultOutputDir()`; nếu trống → **bắt buộc chọn** trước khi
  render (không âm thầm dùng `output`). Thêm "Đặt làm mặc định" → `putDefaultOutputDir`.
- Không lưu `outputDir` theo draft máy-khác (StepConfigure cố tình loại outputDir
  khỏi preset — Content phải làm y vậy, xem BUG-8).

---

## 2D. TÍNH NĂNG USER CHỌN — liệt kê đầy đủ + validate từng cái

> "chú ý thêm các tính năng User chọn" — mọi lựa chọn phải được **wire đúng
> backend field** + **validate/kèm hệ quả rõ ràng**, không phải nút bấm cho đẹp.

| Lựa chọn | Field wire | Validate / hệ quả cần hiển thị |
|---------|-----------|-------------------------------|
| Tỉ lệ khung | `aspect_ratio` | 9:16/1:1/16:9 — preview khung theo tỉ lệ |
| Thời lượng mục tiêu | `target_duration` | 15–600s; **AI duration-fit** sẽ bám số này (hiện ở AI Insights) |
| Nền: Màu | `content_background_kind=color` + `content_background_value` (hex) | validate hex |
| Nền: Ảnh/Video | kind=image/video + value=path | **bắt buộc path tồn tại** (BUG-4) |
| Nguồn hình (Local/Stock/Imagen/Veo) | `content_visual_provider` | Imagen/Stock/Veo → **cảnh báo cần API key**; Imagen thêm chọn **tier** (fast/standard/ultra) + ước tính chi phí (`/estimate`) |
| Giọng: lang/gender/engine | `voice_language`/`voice_gender`/`tts_engine` | nút 🔊 nghe thử per-scene (đã có endpoint) |
| Phụ đề | `add_subtitle`+`subtitle_style` | style preview |
| Word-by-word | `highlight_per_word` | **cảnh báo "chậm hơn (Whisper mỗi cảnh)"** |
| Nhạc nền | `content_bgm_path` | nếu nhập path → validate tồn tại; auto-duck |
| Thư mục lưu | `output_dir` | mục 2C |
| Tone | (→ `/plan` tone) | free text |
| Per-scene: cảm xúc/tốc độ/dur/visual_prompt/nền riêng/ken_burns | scene fields | validate tốc độ 0.5–2, dur ≥ 0, nền riêng cần path |
| Imagen tier | `CONTENT_IMAGEN_TIER` (env) → **cần đưa lên UI** | chọn fast/standard/ultra ngay trong config |

Điểm mới phải bổ sung vào UI: **Imagen tier selector** (hiện chỉ có ở env) và
**cost preflight** (endpoint `/estimate` đã có, UI chưa gọi).

---

## 3. Kiến trúc màn hình (5 phase, thay vì 3)

```
┌── Compose ──┐   ┌── AI Planning ──┐   ┌── Review ──┐   ┌── Live Render ──┐   ┌── Publish ──┐
│ Script +    │──▶│ (transient)     │──▶│ Plan + AI  │──▶│ AI Activity Feed│──▶│ SEO meta +  │
│ Config      │   │ AI đang nghĩ…   │   │ insights + │   │ + Scene grid +  │   │ video +     │
│ (input)     │   │ (animated)      │   │ scene edit │   │ live progress   │   │ download    │
└─────────────┘   └─────────────────┘   └────────────┘   └─────────────────┘   └─────────────┘
   Stepper:  1 Compose ›  2 Review ›  3 Render        (Planning là micro-state của 1→2)
```

Điểm mới so với hiện tại: tách hẳn **AI Planning** thành một micro-state có
animation (thay vì nút đổi chữ "AI analyzing…"), và biến **Render** thành trung
tâm "AI Activity" thay vì list part khô khan.

---

## 4. ⭐ AI ACTIVITY LAYER — điểm khác biệt cốt lõi

Đây là hồn của yêu cầu "user nhìn thấy AI đang làm gì". Có 3 nơi:

### 4a. AI Planning (giữa Compose → Review)
Thay spinner bằng một **"AI Director console"**:
```
┌─────────────────────────────────────────────┐
│  ◐  AI Content Director                       │   ← icon xoay (spin) + tên
│                                               │
│  ✓ Đọc & hiểu kịch bản (921 ký tự)            │   ← từng dòng slide-in khi
│  ✓ Xác định chủ đề · giọng · khán giả         │      pha AI tiến triển (nếu
│  ◐ Chia cảnh theo ý nghĩa…                    │      có sub-event) — nếu backend
│  ·  Viết lời kể + cảm xúc + nhịp đọc          │      chỉ trả 1 lần, dùng
│                                               │      timeline "kịch bản hoá"
│  [▓▓▓▓▓▓░░░░]  AI đang lập kế hoạch…          │      (progressive reveal).
└─────────────────────────────────────────────┘
```
- Animation: dòng đang chạy có `status-pulse`; dòng xong đổi ✓ (fade). Nút Cancel.
- **Grounding thực tế:** `/plan` là 1 call đồng bộ → không có sub-event. Giải pháp:
  hiển thị timeline "scripted" (các bước cố định) chạy tuần tự bằng animation
  trong lúc chờ response, hoàn tất khi plan về. Trung thực (đây là các bước AI
  thực sự làm bên trong), không giả số liệu.

### 4b. AI Insights (trong Review)
Sau khi plan về, panel **"AI đã làm gì với kịch bản của bạn"** — đọc từ
`duration_fit` + `narration_audit` + story_bible:
```
┌─ AI Insights ──────────────────────────────────────────┐
│ [AI applied] Đã chỉnh nhịp đọc để vừa 90s               │
│              120s ──────▶ 90s   (×1.33 tốc độ)          │  ← bar animate
│ [AI advisory] 1 cảnh quá tải, 1 cảnh thưa               │  ← click → nhảy tới scene
│ [AI understood] Chủ đề: "…" · Nhân vật: [A][B]          │
└────────────────────────────────────────────────────────┘
```
- Mỗi dòng là một `AIChip` + nội dung. `content.narration.refined` (nếu bật) thêm
  dòng "[AI applied] Viết lại lời kể N cảnh".
- Cost preflight (`/estimate`) hiển thị ở đây nếu provider ≠ local:
  "Ước tính chi phí AI: $0.12 — 4 ảnh Imagen, 2 stock".

### 4c. Live AI Activity Feed (trong Render) — quan trọng nhất
Cột trái = **dòng thời gian AI** (từ `liveEvents: WsLogEvent[]`), cột phải =
**lưới scene** (từ `liveParts`):
```
┌── AI Activity ──────────────┐   ┌── Scenes (4) ───────────────────────┐
│ ● Hiểu kịch bản              │   │ ┌─Scene 1─┐ ┌─Scene 2─┐ ┌─Scene 3─┐ │
│ ● Lập kế hoạch (4 cảnh)      │   │ │ 🎙 narr │ │ ✓ done  │ │ 🖼 imagen│ │
│ ● Chỉnh nhịp đọc 120→90s     │   │ │ ▓▓░░ 40%│ │ ████100%│ │ ultra   │ │
│ ◐ Sinh ảnh Imagen — cảnh 3   │◀─ │ │ [local] │ │ [stock] │ │ ▓▓▓░ 70%│ │
│ · Ghép video + nhạc nền      │   │ └─────────┘ └─────────┘ └─────────┘ │
│                              │   │  (card đang chạy: status-pulse)      │
│  [▓▓▓▓▓▓▓░░]  68% tổng        │   └──────────────────────────────────────┘
└──────────────────────────────┘
```
- Mỗi event mới **slide-in** (`panel-slide-up`), item đang active có `status-pulse`.
- Scene card: badge provider (local/stock/ai_image+tier/ai_video), mini-progress
  `progress-shimmer`, message backend ("synthesizing narration"/"visual resolve").
- Khi Imagen sinh xong ảnh → nếu backend expose đường ảnh, thumbnail fade-in.
- Map event→nhãn tiếng Việt/English qua một `EVENT_LABELS` table (i18n).

---

## 5. Thiết kế từng màn (wireframe + component)

### 5.1 Compose (Script + Config) — thay màn trong ảnh
```
┌ Content Studio ──────────────── Stepper[1 Compose › 2 Review › 3 Render] ┐
│ ┌── Script (2/3 width) ─────────────┐ ┌── Configuration (1/3, cuộn) ───┐ │
│ │ [textarea lớn, mono-friendly]      │ │ SectionHeader "Định dạng"      │ │
│ │  ~921 ký tự · ~6 phút đọc          │ │  Tỉ lệ [9:16][1:1][16:9]       │ │
│ │ [Import .txt/.md] [Xoá] [Mẫu ▾]    │ │  Thời lượng [90s] slider       │ │
│ └────────────────────────────────────┘ │ SectionHeader "Hình ảnh"       │ │
│ ┌── Bản nháp gần đây (chips) ────────┐ │  Nguồn [Local▾] → nếu AI:      │ │
│ │ [Draft A ·4c] [Draft B ·6c ✓] …    │ │   Imagen tier [fast/std/ultra] │ │
│ └────────────────────────────────────┘ │   Nền [Màu][Ảnh][Video]        │ │
│                                         │ SectionHeader "Giọng & Phụ đề" │ │
│                                         │  Lang/Gender/Engine · 🔊 test  │ │
│                                         │  Phụ đề [On] style · word×word │ │
│                                         │ SectionHeader "Khác"           │ │
│                                         │  Nhạc nền · Thư mục lưu · Tone  │ │
│                                         └────────────────────────────────┘ │
│                         [ Lập kế hoạch (AI) ⚡ ]  ← Button primary gradient │
└──────────────────────────────────────────────────────────────────────────┘
```
- Cải thiện chính: config **gom nhóm bằng `SectionHeader`** (collapsible) thay vì
  8 field xếp thẳng; script area rộng hơn; thêm "Mẫu" script + ước lượng "phút đọc".
- Component: `Panel`, `SectionHeader`, `Button`, `Toggle`, `Badge`, segmented (CSS).

### 5.2 Review — plan + AI insights + scene editor
```
┌ Review AI Plan ──────────── Stepper[2] ──────────────────────────────────┐
│ Header: <topic> · <video_style> · 4 cảnh · ~90s          [AIChip applied]  │
│ ┌── AI Insights (4b) ───────────────────────────────────────────────────┐ │
│ └───────────────────────────────────────────────────────────────────────┘ │
│ [Lọc: Tất cả | ⚠ Chỉ cảnh yếu]        [＋ Thêm cảnh]   [Nghe cả bài ▷]     │
│ ┌── Scene 1 ───────────────────────────────────────────────[audit: ok]──┐ │
│ │ [title]                              🔊 ↑ ↓ ✕                          │ │
│ │ [narration textarea]                                                   │ │
│ │ Cảm xúc[▾] Tốc độ[1.3] Dur[22s] | Visual prompt[…] [asset: imagen▾]    │ │
│ │ Nền riêng[▾]                                                           │ │
│ └────────────────────────────────────────────────────────[⚠ overloaded]─┘ │
│ …                                                                          │
│ [← Quay lại]                                  [ Duyệt & Render ▶ ]          │
└──────────────────────────────────────────────────────────────────────────┘
```
- Scene card viền/nền phản ánh audit (ok/advisory/overloaded) — dùng `--ai-*`.
- `Card` (hoverable), `AIChip`, `Toggle`, `Button`, nghe thử = pulse + "~Xs".

### 5.3 Live Render — AI Activity (mục 4c) + progress ring
- Top: `ScoreRing`/`ConicRing` % tổng + stage hiện tại (StatusPill).
- Body 2 cột: AI Activity Feed | Scene grid (như 4c).
- Terminal: success → video `<video>` preview + `Button` "Tải về"/"Tạo video mới";
  fail → EmptyState fail + lý do.

### 5.4 Publish (mở rộng từ Monitor hiện tại)
- Sau khi xong: nút "Tạo tiêu đề/mô tả (AI)" → `publish-meta` → 3 field readOnly +
  copy button từng field + thumbnail suggestion. Reveal `panel-slide-up`.

---

## 6. Spec ANIMATION (bám `motion.css` sẵn có + bổ sung tối thiểu)

| Nơi | Animation | Nguồn |
|---|---|---|
| Scene cards xuất hiện | stagger fade+rise | `clip-card-appear` (có sẵn) |
| Bước AI đang chạy | nhấp nháy | `status-pulse` (có sẵn) |
| Mini-progress scene | shimmer | `progress-shimmer` (có sẵn) |
| Panel AI Insights / Publish | trượt lên | `panel-slide-up` (có sẵn) |
| % tổng khi xong | bung nảy | `score-xl-appear` (có sẵn) |
| Thanh duration fit before→after | glow chạy | `render-fill-glow` (có sẵn) |
| Icon AI Director | xoay | `spin` (có sẵn) |
| **MỚI** typing lời kể (refine) | reveal ký tự | keyframe mới `ai-type-caret` (nhỏ) |
| **MỚI** feed item slide-in | trượt trái→phải | tái dùng `panel-slide-up` biến thể |
| **MỚI** thumbnail Imagen fade | opacity 0→1 + scale | keyframe mới `asset-reveal` |

Chỉ thêm **2 keyframe mới** — phần lớn tái dùng. Tất cả bọc `@media (prefers-
reduced-motion: reduce)` (motion.css đã có pattern).

---

## 7. Component inventory

**Tái dùng (từ `components/ui/`):** `Button`, `Card`, `Panel`, `Toggle`,
`SectionHeader`, `ProgressBar`, `StatusPill`, `Badge`, `AIChip`, `EmptyState`,
`ScoreRing`/`ConicRing`.

**Component mới (nội bộ content-studio):**
- `AiDirectorConsole` (4a) — timeline scripted khi planning.
- `AiInsights` (4b) — đọc duration_fit + narration_audit + story_bible + cost.
- `AiActivityFeed` (4c) — render `liveEvents` thành timeline có animation.
- `SceneCard` (dùng ở Review) + `LiveSceneCard` (dùng ở Render).
- `CostEstimatePanel` — gọi `/api/content/estimate`.
- `NarrationAuditBadge`, `ProviderBadge`, `DurationFitBar`.
- `EVENT_LABELS` (i18n map event→nhãn) + `content-studio/animations.css`.

---

## 8. Cấu trúc file (tách 709 dòng → module, đóng nợ TD-M2)

```
features/content-studio/
├── ContentStudio.tsx          # shell + phase router + state (mỏng)
├── ContentStudio.css          # thay object S (class + token)
├── animations.css             # 2 keyframe mới + biến thể
├── types.ts                   # Config, Phase, VoiceCfg
├── useContentDraft.ts         # autosave/draft hook (tách khỏi component)
├── compose/ComposeScreen.tsx  # + ConfigPanel.tsx (SectionHeader groups)
├── planning/AiDirectorConsole.tsx
├── review/ReviewScreen.tsx  · SceneCard.tsx · AiInsights.tsx · CostEstimatePanel.tsx
├── render/RenderScreen.tsx  · AiActivityFeed.tsx · LiveSceneCard.tsx
├── publish/PublishPanel.tsx
└── shared/ AIChip usage, ProviderBadge.tsx, DurationFitBar.tsx, eventLabels.ts
```
API client `api/content.ts`: thêm `estimateContentCost()` (endpoint đã có ở BE).

---

## 8B. 🐛 BUG ĐÃ BIẾT (do làm sơ sài) — redesign PHẢI đóng từng cái

Danh sách bug/gap phát hiện khi rà soát + test thực tế. Redesign không chỉ "đẹp
hơn" — phải **đóng đúng từng lỗi** này (cột "Đóng ở").

| ID | Bug / gap | Bằng chứng | Đóng ở |
|----|-----------|-----------|--------|
| BUG-1 | Content render → `400 source_video_path is required` | `_validate_render_source` mù mode | P0 (BE fix + test route) — mục 2B |
| BUG-2 | Không có nút chọn thư mục (folder picker) | `Save folder` chỉ là `<input text>` | P1 — mục 2C |
| BUG-3 | `output_dir` rỗng → âm thầm dùng `output` tương đối; user không biết video ở đâu | `buildPayload: cfg.outputDir.trim() \|\| 'output'` | P1 — mục 2C (bắt buộc chọn / dùng default đã lưu) |
| BUG-4 | Không validate nền image/video (path rỗng/không tồn tại) trước khi render | chỉ check `!cfg.bgAssetPath.trim()` ở approve, không check tồn tại | P0/P2 — ma trận 2B |
| BUG-5 | Provider AI (Imagen/Stock/Veo) thiếu key → im lặng fallback local, user tưởng có ảnh AI | seam fallback không báo UI | P2 — cảnh báo mềm + cost 2D |
| BUG-6 | Imagen tier (fast/standard/ultra) chỉ đặt qua env, UI không chọn được | chỉ có `CONTENT_IMAGEN_TIER` env | P1 — thêm selector 2D |
| BUG-7 | Cost preflight `/estimate` đã có backend nhưng UI không gọi | endpoint tồn tại, FE thiếu | P3 — `CostEstimatePanel` |
| BUG-8 | Autosave lưu cả `outputDir` (máy-cụ-thể) vào draft | `config: cfg` gồm outputDir | P1 — loại outputDir khỏi draft (như StepConfigure) |
| BUG-9 | Toàn bộ inline-style, off-brand, cramped, không dùng design-system | object `S` 686–709 | P0/P1 — mục 1 |
| BUG-10 | Không thấy AI đang làm gì (chỉ list part khô) | chỉ đọc 1 event `content.plan.ready` | P4/P5 — AI Activity Layer (mục 4) |
| BUG-11 | Word-by-word bật mặc định (chậm) không cảnh báo hệ quả | `wordByWord: true` default | P1 — cảnh báo 2D |
| BUG-12 | Nền default lệch: config `#101820` vs model default `#000000` | so field default | P1 — thống nhất |

> Nguyên tắc: mỗi bug ở trên có **test/verify** đi kèm khi đóng (route test cho
> BUG-1; pre-submit validation test cho BUG-3/4; visual regression/chụp màn cho
> BUG-9/10). "Đóng" nghĩa là có bằng chứng, không phải "trông có vẻ ổn".

---

## 9. Lộ trình triển khai (đề xuất)

| Phase | Nội dung | Rủi ro |
|---|---|---|
| **P0** | **(a) BE fix `_validate_render_source` case-aware + route test (BUG-1,4)** · (b) `ContentStudio.css` + token hoá, thay `Button/Card/Panel/Toggle` (BUG-9) — hết "off-brand" + render được ngay | Thấp (BE: MEDIUM + focused pytest) |
| P1 | Tách file + Compose (SectionHeader groups) + ConfigPanel + **folder picker (2C)** + **Imagen tier selector** + fix draft/outputDir + nền default + cảnh báo word-by-word (BUG-2,3,6,8,11,12) | Thấp |
| P2 | Review + `AiInsights` (duration_fit/audit/story) + `SceneCard` + audit badges + **cảnh báo provider thiếu key** (BUG-5) + validate nền asset (BUG-4) | Thấp-TB |
| P3 | `CostEstimatePanel` (wire `/estimate`, BUG-7) | Thấp |
| P4 | **AI Activity Feed** + LiveSceneCard + ProviderBadge (điểm nhấn) | TB |
| P5 | `AiDirectorConsole` planning + animations.css | TB |
| P6 | Publish panel + copy buttons + video preview | Thấp |
| P7 | Verify: build + `tsc -b` + chạy app chụp từng màn | — |

Mỗi phase build được độc lập; `npm run build` (→ static-v2) + `tsc -b` phải xanh.

---

## 10. Kế hoạch kiểm tra (không giao mù)

1. `tsc -b` (KHÔNG `tsc --noEmit` — theo memory) + `npm run build` xanh.
2. Chạy backend (`run-backend-v2.ps1`) → mở `http://127.0.0.1:8000` → chụp:
   Compose · Planning · Review (có AI insights) · Live Render (feed + scenes) · Publish.
3. Test light/dark + VI/EN + `prefers-reduced-motion`.
4. Test một render content thật để thấy AI Activity Feed chạy với event thực
   (`content.plan.ready` / `content.timing.fit` / `content.narration.audit` /
   per-scene / `render.complete`).

---

## 11. Ràng buộc / không phá vỡ

- **Ngoại lệ backend DUY NHẤT:** fix `_validate_render_source` case-aware (BUG-1,
  mục 2B) — bắt buộc vì không có nó content luôn 400. MEDIUM-tier, additive
  (chỉ rẽ theo `render_format`), + route test. Ngoài mục này: **không đổi backend**.
- Không đổi payload wire (giữ đúng field public đã có).
- Không phá Sacred WS shape `{job, parts, summary}` (chỉ đọc thêm `liveEvents`).
- Không "hạ cấp" chức năng: preview per-scene, draft autosave, publish-meta,
  per-scene background, word-by-word… đều giữ.
- Tôn trọng `prefers-reduced-motion`.

**Tóm tắt 1 câu:** biến Content Studio từ một form inline-style khô khan thành một
trải nghiệm "AI trong suốt" — người dùng thấy AI *đọc → hiểu → lập kế hoạch →
chỉnh → refine → sinh ảnh → ghép* theo thời gian thực, với animation tái dùng
`motion.css` + `AIChip`, dựng bằng design-system sẵn có, không thêm gánh nặng.

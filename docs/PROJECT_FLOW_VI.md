# PROJECT_FLOW_VI

## 1. Tổng quan dự án

**Mức ổn định: Hợp đồng ổn định**

Dự án này là **nền tảng AI rendering intelligence cho video**, dùng FFmpeg làm backend thực thi.

Không nên hiểu dự án chỉ là tool cắt video bằng FFmpeg. Giá trị chính nằm ở việc hệ thống có thể:

- chuẩn bị nguồn video từ YouTube hoặc file local
- mở preview/editor trước khi render
- phát hiện cảnh
- tạo segment
- chấm điểm viral, hook, motion, market
- tạo phụ đề
- dịch phụ đề
- tạo style ASS/karaoke/bounce
- crop/reframe theo motion hoặc subject
- tạo voice narration
- render bằng FFmpeg
- validate output
- xếp hạng clip
- ghi metadata AI vào `result_json`

Input chính:

- YouTube URL
- file video local
- output folder/channel
- cấu hình subtitle, voice, crop, AI, market, render profile

Output chính:

- các clip MP4 đã render
- `render_report.xlsx`
- source archive nếu bật
- best clips nếu bật auto best export
- job logs
- `jobs.result_json`

Creator workflow thực tế:

```text
Chọn source
  -> prepare-source
  -> mở editor preview
  -> chỉnh trim/volume/subtitle/voice/text/motion/AI
  -> submit render
  -> theo dõi job
  -> xem output gallery
  -> chọn clip tốt nhất
```

## 2. Triết lý sản phẩm

**Mức ổn định: Hợp đồng ổn định**

Triết lý đúng của dự án:

```text
AI rendering intelligence platform
        +
FFmpeg execution backend
```

Không phải:

```text
FFmpeg render tool có thêm vài tính năng AI
```

AI trong dự án này theo hướng **metadata-first**:

- AI phân tích trước.
- AI tạo plan trước.
- AI tạo recommendation trước.
- AI giải thích trước.
- Render pipeline vẫn là nơi quyết định thực thi.

AI không được tự ý:

- rewrite FFmpeg command
- sửa timing subtitle tùy tiện
- đổi playback speed ngoài policy
- enqueue job mới ngoài pipeline
- xóa output
- override executor
- biến advisory phase thành execution phase mà không có test

Một số AI influence có thể được áp dụng, nhưng phải là bounded execution: opt-in, có safety gate, có report, và không phá backward compatibility.

## 3. Kiến trúc tổng thể

**Mức ổn định: Hợp đồng ổn định**

```text
Frontend static / Electron
        |
        v
FastAPI routes
        |
        v
SQLite jobs + job_parts
        |
        v
AI Director + render intelligence
        |
        v
Render pipeline
        |
        +--> Subtitle
        +--> Voice
        +--> Motion crop
        +--> FFmpeg
        |
        v
Output clips + result_json
```

Các layer chính:

- `backend/static`: UI static HTML/CSS/JS.
- `backend/app/main.py`: FastAPI app.
- `backend/app/routes`: API route layer.
- `backend/app/models/schemas.py`: schema contract cho request/response.
- `backend/app/services/db.py`: SQLite runtime state.
- `backend/app/services/job_manager.py`: in-process queue.
- `backend/app/orchestration/render_pipeline.py`: render orchestration.
- `backend/app/services/render_engine.py`: FFmpeg render backend.
- `backend/app/services/subtitle_engine.py`: Whisper, SRT, ASS, karaoke/bounce.
- `backend/app/services/motion_crop.py`: motion-aware crop/reframe.
- `backend/app/services/tts_service.py`: Edge TTS.
- `backend/app/services/audio_mix_service.py`: audio mix bằng FFmpeg.
- `backend/app/ai/**`: AI Director và các phase intelligence.
- `desktop-shell/main.js`: Electron desktop shell.

## 4. Flow render đầy đủ

**Mức ổn định: Hợp đồng ổn định**

Flow thực tế:

```text
Input
  -> validation
  -> download/load source
  -> preview session
  -> editor session
  -> queue job
  -> scene detection
  -> segment generation
  -> viral/hook/motion scoring
  -> subtitle transcription
  -> AI Director planning
  -> subtitle slicing/translation/styling
  -> motion crop/reframe
  -> voice/TTS
  -> FFmpeg render
  -> validation
  -> quality evaluation
  -> output ranking
  -> result_json
```

### 4.1 Input validation

File liên quan:

- `backend/app/routes/render.py`
- `backend/app/models/schemas.py`

Validation bảo vệ source mode, output dir, URL/local path, editor session, voice settings, AI flags, subtitle settings.

Rủi ro:

- Nếu nới validation quá rộng, pipeline có thể nhận payload không tương thích.
- Nếu siết validation quá mạnh, payload cũ hoặc UI hiện tại có thể bị gãy.

### 4.2 Download/load source

File liên quan:

- `backend/app/services/downloader.py`
- `backend/app/routes/render.py`

YouTube dùng `download_youtube()`. Local source dùng path có sẵn. Render không được sửa file local gốc.

### 4.3 Preview session

Preview session nằm ở:

```text
TEMP_DIR/preview/{session_id}
```

Session chứa metadata như source path, preview path, duration, title, export dir.

UI dùng session để mở editor và submit render bằng `edit_session_id`.

### 4.4 Scene detection

File:

- `backend/app/services/scene_detector.py`

Scene detection giúp pipeline biết điểm cắt cảnh và tạo segment hợp lý hơn.

### 4.5 Segment generation

File:

- `backend/app/services/segment_builder.py`

Segment phải tôn trọng `min_part_sec`, `max_part_sec`, duration nguồn, và thứ tự xuất clip.

### 4.6 Viral / hook / market scoring

File:

- `backend/app/services/viral_scorer.py`
- `backend/app/services/viral_scoring.py`

Scoring không chỉ để sort clip. Nó là một phần của output intelligence:

- viral score
- hook timing
- motion score
- market score
- retention metadata nếu có

### 4.7 AI Director

File:

- `backend/app/ai/director/ai_director.py`
- `backend/app/ai/director/edit_plan_schema.py`

AI Director tạo `AIEditPlan`. Nếu fail, pipeline tiếp tục render bình thường.

Đây là contract quan trọng.

### 4.8 Subtitle

File:

- `backend/app/services/subtitle_engine.py`
- `backend/app/services/translation_service.py`
- `backend/app/services/market_subtitle_policy.py`

Flow:

```text
full SRT
  -> slice theo part
  -> rebase về 0
  -> dịch nếu bật
  -> style ASS
  -> burn vào video
```

### 4.9 Motion crop

File:

- `backend/app/services/motion_crop.py`
- `backend/app/services/render_engine.py`

Motion crop giúp video dọc/3:4 giữ subject tốt hơn. Nếu tracking không ổn, hệ thống cần fallback về render thường.

### 4.10 Voice/TTS

File:

- `backend/app/services/tts_service.py`
- `backend/app/services/audio_mix_service.py`

Voice có 3 nguồn:

- manual text
- subtitle
- translated subtitle

Voice lỗi thì không nên phá clip đã render.

### 4.11 FFmpeg render

File:

- `backend/app/services/render_engine.py`

FFmpeg là backend thực thi:

- cut
- crop/scale
- burn subtitle
- text overlay
- audio mix
- encode
- probe

Không nên document mọi flag FFmpeg như public API.

### 4.12 Validation và result_json

Sau render, pipeline validate output và ghi `result_json`.

`result_json` là contract cho UI và future agents.

Không được tùy tiện xóa:

- `outputs`
- `segments`
- `output_ranking`
- `best_clip`
- `best_exports`
- `failed_parts`
- `failed_parts_detail`
- `voice_summary`
- `subtitle_translate_summary`
- `ai_director`
- `ai_output_ranking`
- `ai_render_quality_evaluation`
- `ai_ux`

## 5. AI Director hoạt động như thế nào

**Mức ổn định: Thử nghiệm / cần xác minh thêm**

AI Director không phải một model duy nhất. Nó là hệ thống nhiều phase.

Các nhóm module chính:

- analyzers: transcript, hook, emotion, beat, silence, vision
- director: clip selector, camera planner, subtitle planner, render influence
- subtitles: density, emotion, emphasis, execution
- camera: apply guidance, camera quality
- retention/story/timing: logic giữ người xem
- market: tối ưu theo market
- creator: preference, style, feedback, adaptive memory
- output/quality: rank và evaluate output
- explainability: tạo lý do dễ hiểu

Nguyên tắc:

- AI tạo metadata trước.
- AI advisory là mặc định.
- Execution phải opt-in.
- Nếu thiếu dữ liệu, fallback an toàn.
- Không phá pipeline cũ.

## 6. AI Output Intelligence

**Mức ổn định: Triển khai bán ổn định**

Output intelligence gồm:

- viral scoring
- hook scoring
- retention scoring
- market scoring
- motion score
- output ranking
- best clip
- best exports
- quality evaluation
- explainability

Giá trị AI hiện còn bị ẩn nhiều trong `result_json` và logs. UI cần dần làm rõ:

- vì sao clip này tốt nhất
- hook mạnh ở đâu
- market fit thế nào
- subtitle strategy là gì
- camera strategy là gì
- quality warning có nghĩa gì

Không nên biến metadata AI thành noise debug. Nó là product value.

## 7. Subtitle system

**Mức ổn định: Hợp đồng ổn định**

Subtitle là vùng rất dễ gãy.

Điều không được phá:

- full SRT chỉ tạo một lần khi có thể
- per-part SRT phải rebase về 0
- translation lỗi thì fallback text gốc
- ASS style aliases phải giữ
- karaoke thiếu word timing thì fallback
- subtitle-safe region phải tương thích overlay và crop

Premium subtitle không chỉ là có chữ. Nó còn là:

- font
- spacing
- contrast
- motion rhythm
- line break
- keyword emphasis
- consistency giữa các clip

## 8. Motion crop và camera logic

**Mức ổn định: Triển khai bán ổn định**

Motion crop giúp output dọc/3:4 không bị crop sai subject.

File nguy hiểm:

- `backend/app/services/motion_crop.py`
- `backend/app/services/render_engine.py`

Rủi ro:

- crop sai subject
- subtitle bị che
- camera giật
- tracking fail làm render fail
- fallback không chạy

Điều không được phá:

- fallback về standard render
- subtitle-safe framing
- reframe mode compatibility
- validation output sau render

## 9. Voice narration system

**Mức ổn định: Triển khai bán ổn định**

Voice giúp tạo narration cho từng part.

Nguồn voice:

- manual
- subtitle
- translated subtitle

Mix mode:

- `replace_original`
- `keep_original_low`

Điều không được phá:

- voice lỗi không được xóa clip hợp lệ
- mix lỗi phải giữ output gốc
- `VOICE001` vẫn phải có ý nghĩa
- translated subtitle voice phải fallback được

Chất lượng audio cảm nhận bởi creator hiện chưa ngang studio mastering. Cần phân biệt render audio hợp lệ với audio premium.

## 10. UI workflow

**Mức ổn định: Triển khai bán ổn định**

UI nằm trong `backend/static`.

Các file quan trọng:

- `index.html`
- `js/globals.js`
- `js/nav.js`
- `js/render-engine.js`
- `js/render-ui.js`
- `js/editor-view.js`
- `css/app.css`

Flow:

```text
Render setup
  -> prepare source
  -> editor
  -> submit render
  -> monitor
  -> output gallery
  -> center preview
  -> history
```

DOM IDs là contract. Không được đổi bừa.

Nhóm ID nguy hiểm:

- render setup: `source_mode`, `youtube_url`, `manual_output_dir`, `start_render_btn`
- editor: `evVideo`, `evStartBtn`, `evVoice*`, `evSub*`
- monitor: `render_active_panel`, `render_monitor_*`, `rc_*`
- output: `render_output_panel`, `render_output_list`, `cs_preview_video`
- logs: `event_log_render`

UI dễ gãy vì:

- state global
- JS file lớn
- CSS rất lớn và có nhiều override
- WebSocket + polling + DOM + localStorage cùng tham gia state
- nhiều feature chung một page

## 11. Desktop app flow

**Mức ổn định: Thử nghiệm / cần xác minh thêm**

Desktop app là Electron shell.

File chính:

- `desktop-shell/main.js`

Flow:

```text
Electron start
  -> single-instance lock
  -> splash
  -> health check backend
  -> start backend nếu cần
  -> wait ready
  -> load localhost UI
```

Packaged mode có thể dùng:

- `backend-bin/render-backend.exe`
- `ffmpeg-bin/ffmpeg.exe`
- `ffmpeg-bin/ffprobe.exe`

Nếu không có packaged backend, shell fallback sang Python/venv/Uvicorn.

Đóng gói desktop luôn cần verification riêng.

## 12. Product quality và identity

**Mức ổn định: Thử nghiệm / cần xác minh thêm**

Technical render quality hiện tốt hơn creator-perceived quality.

Chất lượng render kỹ thuật: khoảng 7/10.

Chất lượng creator cảm nhận: khoảng 5/10.

Khoảng cách đến từ:

- hook visuals còn có thể template-like
- subtitle premium feel chưa chắc ổn định
- motion crop chưa tự động thành cinematography
- audio mix chưa phải mastering
- intro/outro/branding còn yếu
- AI reasoning chưa đủ visible
- visual consistency giữa batch chưa phải trọng tâm chính

Định vị sản phẩm nên là:

```text
AI chọn, giải thích, và đóng gói các clip sẵn sàng cho creator.
Các điều khiển thủ công dùng để tinh chỉnh lựa chọn của AI.
```

## 13. Những vùng nguy hiểm không được sửa bừa

**Mức ổn định: Hợp đồng ổn định**

### 13.1 `render_pipeline.py`

Trung tâm orchestration. Sửa sai có thể phá toàn bộ render.

Không được phá:

- result JSON
- partial success
- failed parts
- voice/subtitle/motion fallback
- output ranking

### 13.2 `render_engine.py`

Tạo FFmpeg command, codec fallback, burn subtitle, overlays.

Không được phá:

- NVENC/CPU fallback
- ffprobe/probe behavior
- subtitle burn
- text overlay filters

### 13.3 `subtitle_engine.py`

Timing subtitle cực kỳ nhạy.

Không được phá:

- SRT rebase
- ASS aliases
- karaoke fallback
- marker escaping

### 13.4 `motion_crop.py`

Tracking subject/motion dễ lỗi theo video.

Không được phá fallback.

### 13.5 `schemas.py`

API contract. Default values rất quan trọng.

Không được đổi default AI từ false sang true nếu không có lý do và test.

### 13.6 `backend/app/ai/**`

AI phase-based. Nhiều module là advisory-only.

Không được biến advisory thành execution mà không có safety/test.

### 13.7 Static frontend

Không đổi DOM IDs nếu chưa search toàn repo.

### 13.8 `result_json`

Compatibility surface cho UI/history/future agents.

Không xóa alias.

### 13.9 `docs/review/**` và `docs/archive/**`

Theo yêu cầu hiện tại: không sửa.

## 14. Giới hạn đã biết

**Mức ổn định: Triển khai bán ổn định**

Render limitations:

- phụ thuộc FFmpeg/ffprobe
- phụ thuộc codec/hardware
- output quality còn tùy input

Subtitle limitations:

- Whisper có thể sai
- translation có thể mixed language
- karaoke cần word timing tốt

Voice limitations:

- Edge TTS có thể timeout/fail
- audio chưa phải mastering

Motion crop limitations:

- subject tracking có thể fail
- camera motion có thể chưa cinematic

UI limitations:

- state global
- CSS/JS lớn
- DOM ID fragile

Desktop limitations:

- packaged build cần verify
- FFmpeg/bin/backend-bin có thể thiếu
- dependency bootstrap có thể chậm

Scalability limitations:

- local SQLite
- in-process queue
- local FFmpeg contention
- phù hợp local desktop hơn service scale lớn

## 15. Quy trình phát triển chuẩn

**Mức ổn định: Hợp đồng ổn định**

Quy trình chuẩn cho các AI agent sau này:

```text
Inspect
  -> Plan
  -> Patch nhỏ nhất có thể
  -> Test tập trung
  -> py_compile nếu sửa Python
  -> pytest focused
  -> full pytest khi rủi ro lớn
  -> cập nhật tài liệu/audit khi spec hoặc behavior thay đổi, chỉ khi phạm vi task cho phép
```

Quy tắc:

- đọc code trước khi sửa docs
- không rewrite file lớn nếu không cần
- patch nhỏ, reviewable
- giữ backward compatibility
- giữ warnings còn đúng
- đánh dấu `Needs verification` khi chưa chắc
- không sửa `docs/review/**`
- không sửa `docs/archive/**`
- không bao giờ sửa `docs/review/**` hoặc `docs/archive/**` trừ khi user yêu cầu rõ ràng
- không sửa backend/frontend/tests/config nếu task chỉ là docs

Khi sửa behavior:

- phải test focused
- phải nghĩ tới result JSON
- phải nghĩ tới DOM IDs
- phải nghĩ tới render events
- phải nghĩ tới partial success
- phải nghĩ tới AI advisory vs execution

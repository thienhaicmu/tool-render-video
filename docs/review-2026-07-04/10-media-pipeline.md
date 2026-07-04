# 10 — Review Media Pipeline

## 1. Thành phần media

| Khối | Module | Vai trò |
|------|--------|---------|
| Video cut | `stages/part_cut.py` | Cắt segment từ source |
| Encode | `stages/part_render_encode.py` + `encoder/ffmpeg_helpers.py` | NVENC/libx264 |
| Motion crop | `motion/crop.py`, `path.py`, `path_scene.py` | OpenCV subject tracking → khung dọc |
| Audio | `audio/tts.py`, `audio/mixer.py` | TTS narration, mix + duck BGM |
| Subtitle | `subtitle/{generator,processing,transcription,translation}` | ASS/SRT, readability, dịch |
| Overlay | `overlay/text_overlay.py` | drawtext, title/hook overlay |
| Assemble | `stages/recap_assembler.py` (concat) | scenes → 1 video |
| Thumbnail | `thumbnail/` | cover generation |

## 2. FFmpeg an toàn đường dẫn (điểm mạnh production)

CLAUDE.md bắt buộc dùng `safe_filter_path()`, `get_ffmpeg_bin()`,
`get_ffprobe_bin()` — không nối chuỗi path thô vào filter graph. Lý do: path
Windows có space/ngoặc/backslash làm FFmpeg misparse **im lặng** (mất subtitle/
audio). Đây là bài học từ lỗi production thực. Fontconfig fix ở
[main.py:127-138](../../backend/app/main.py#L127-L138) cùng loại — chống Access
Violation của libass.

## 3. Subtitle pipeline (phong phú)

- **Transcription:** Whisper (openai-whisper) + faster-whisper, cả 2 có LRU cache
  cap 2 (`WHISPER_MODEL_CACHE_MAX`) — đóng lỗ pin multi-GB (Issue 7 RESOLVED).
- **Generator:** ASS (kể cả `ass_capcut` style), SRT, timeline.
- **Processing:** `market_policy`, `readability`, `styles`, `text_transforms` —
  điều chỉnh subtitle theo thị trường/khả năng đọc.
- **Translation:** `translation_service.py` dịch subtitle.
- Whisper access **lock-serialised** trong `transcribe_to_srt` → parallel scene
  an toàn (content_pipeline ghi rõ).

## 4. Audio pipeline

- **TTS:** `tts.py` — edge→piper auto-fallback (offline), Gemini TTS. Content
  narration + recap narration.
- **Mixer:** `mix_with_bgm(duck=True)` — nhạc nền ducked dưới narration. Content
  gọi trước QA để file giao được validate với audio cuối
  ([content_pipeline.py:446-462](../../backend/app/features/render/engine/pipeline/content_pipeline.py#L446-L462)).
- **`part_voice_mix.py` (1192 dòng)** — mix voice per-part, phần lớn nhất; xử lý
  narration caption burn, duck, retry TTS.

## 5. Motion-aware crop (CRITICAL)

`motion/crop.py` (OpenCV) tracking subject để crop 16:9 → 9:16 giữ chủ thể trong
khung. Là CRITICAL tier vì (a) raw subprocess không auto-lock NVENC (đã externally
acquire), (b) build_subject_path/scene. Chi tiết NVENC ở doc 08.

## 6. Assemble & concat

`recap_assembler.concat_clips` dùng concat-demuxer stream-copy khi spec khớp
(fps + sample-rate), fallback re-encode khi lệch. Recap probe fps/sr của scene
đầu để sinh act title-card **khớp** → giữ được đường copy nhanh
([recap_pipeline.py:894-911](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L894-L911)).
`_demuxer_output_sane` chống container duration drift.

## 7. Vấn đề

### ⚠ MP-1: Trùng logic concat/assemble giữa 3 mode
- Content & recap đều gọi `concat_clips`; content mode "mượn" recap_assembler.
  Hợp lý (reuse) nhưng ranh giới sở hữu module mờ (assembler nằm trong stages
  nhưng phục vụ 3 orchestrator).
- **Dài hạn:** đưa concat/assemble vào một `media/assembly.py` trung lập.

### ⚠ MP-2: part_voice_mix + asset_planner quá lớn (doc 08 RE-2)
- Ảnh hưởng bảo trì media path.

### ⚠ MP-3: Không có timeline/transition engine tổng quát
- Media pipeline hiện là "cut → encode → concat" tuyến tính; không có timeline
  đa track / transition / animation tổng quát (có `domain/timeline.py` nhưng chưa
  thấy engine tiêu thụ đa track cho render chính). Editor feature (`editing/`) có
  trim/rerender/export nhưng không phải NLE đầy đủ.
- **Ảnh hưởng:** giới hạn khả năng tạo hiệu ứng phức tạp (transition, overlay
  động, sticker). Với mục tiêu short-form thì đủ; với "content creation" tham
  vọng hơn thì thiếu.
- **Dài hạn:** doc 20 — Media Engine / Timeline Engine tách riêng.

## 8. Đánh giá

| Trục | Điểm |
|------|------|
| FFmpeg path safety | 9 |
| Subtitle pipeline | 8 |
| Audio/TTS | 7.5 |
| Motion crop | 7.5 |
| Assemble | 7.5 |
| Timeline/transition generality | 5 |
| **Tổng** | **7.4** |

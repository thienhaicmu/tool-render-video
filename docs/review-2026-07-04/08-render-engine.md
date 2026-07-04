# 08 — Review Render Engine

## 1. Cấu trúc engine

```
engine/
├── pipeline/     orchestrators (render/recap/content) + qa/ranking/cache/finalize
├── stages/       part_renderer + 8 helper, viral_scoring, content_scene_render,
│                 recap_assembler, recap_title_card, part_voice_mix (1192 dòng!)
├── encoder/      ffmpeg_helpers (NVENC_SEMAPHORE), clip_ops
├── motion/       crop.py (OpenCV subject tracking), path.py, path_scene.py
├── audio/        tts, mixer
├── overlay/      text_overlay
├── subtitle/     generator (ass/srt/timeline), processing, transcription, translation
├── visual/       provider seam (local/stock/ai_image/ai_video) + decision + registry
├── preview/ quality/ thumbnail/
```

## 2. Task lifecycle của một part

`part_renderer.py` (372 dòng) là skeleton, delegate 8 helper theo thứ tự:
`context → asset_planner (1104 dòng) → cut → setup → encode → voice_mix (1192)
→ finalize → done`. Mỗi bước là 1 file → **cohesion cao**, dễ test từng stage.

State machine part (Sacred #5): `QUEUED → WAITING → CUTTING → TRANSCRIBING →
RENDERING → DONE` (terminal FAILED/SKIPPED).

## 3. NVENC / GPU protection (điểm mạnh nhất của engine)

[ffmpeg_helpers.py:27-28](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py#L27-L28):
```python
_NVENC_SEM_VALUE = max(1, int(os.getenv("NVENC_MAX_SESSIONS", "3")))
NVENC_SEMAPHORE = threading.Semaphore(_NVENC_SEM_VALUE)
```
- `_run_ffmpeg_with_retry` **auto-acquire** semaphore khi argv chứa codec NVENC
  (`_argv_uses_nvenc`), trừ khi caller đã giữ (`nvenc_externally_held=True`)
  ([:265-276](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py#L265-L276)).
- `motion/crop.py` chạy raw `subprocess.Popen` (không auto-lock) → cả 3 call site
  ở `clip_renderer` acquire semaphore externally, pinned bởi
  `tests/test_nvenc_semaphore_external_acquire.py`.
- **Latent risk (đã ghi CLAUDE.md, không phải bug active):** 2 resolver codec
  (`ffmpeg_helpers._resolve_codec` vs `encoder_helpers.resolve_encoder`) trùng
  logic → pinned parity test; `nvenc_runtime_ready()` mở NVENC probe không
  semaphore (`@lru_cache` ≤2 lần/process).

**Đây là mảng được bảo vệ tốt nhất** — vì NVENC vượt limit làm HỎNG TẤT CẢ session
đang chạy, không chỉ session thừa.

## 4. Thread / batch / resume / cache

- **Parallel:** `pipeline_render_loop` dispatch part qua ThreadPoolExecutor, số
  worker cap theo NVENC session (GPU) hoặc cores (CPU). `resolve_ffmpeg_threads`
  chia core đều cho worker (recap P1 fix — trước đó hardcode threads=1 lãng phí CPU).
- **Resume disk-truth:** part/scene đã pass QA trên đĩa được bỏ qua (content:295,
  recap parts).
- **Cache:** whisper/render/overlay cache, atomic write, TTL — doc 07/15.
- **JOB_SEMAPHORE + `_render_active_count`:** giới hạn job render đồng thời ở cấp
  pipeline (recap import lại từ render_pipeline — coupling ẩn, doc 02).

## 5. QA gate (Sacred #8) — không bao giờ bypass

`qa_pipeline._validate_render_output` ([qa_pipeline.py:63](../../backend/app/features/render/engine/pipeline/qa_pipeline.py#L63)) bắt:
1. File không tồn tại.
2. File < 10 KB (zero-byte/truncated).
3. Không có video stream.
4. Duration = 0.
5. Duration lệch quá tolerance so với `expected_duration` (fix 2026-07-02 chống
   concat-broken episode 15134s vs 295s).
6. Không có audio stream → **warn** (không fail — video có thể chủ đích im lặng).

Cả 3 mode đều gọi gate này trước DONE. **Không có đường vòng.** Xác nhận: content
gọi tại [content_pipeline.py:466](../../backend/app/features/render/engine/pipeline/content_pipeline.py#L466),
recap tại [:755](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L755).

## 6. Vấn đề

### ⚠ RE-1: render_pipeline.py 1934 dòng — God function
- **Root cause:** `run_render_pipeline` (472→~1930) chứa toàn bộ luồng clips
  inline; các stage đã tách helper nhưng orchestration vẫn tập trung.
- **Ảnh hưởng:** Cao cho bảo trì — CRITICAL tier, đổi 3 dòng ảnh hưởng mọi render.
- **Ngắn hạn:** không đụng ngoài kế hoạch (Render Edit Protocol).
- **Dài hạn:** rút các block lớn (transcribe heartbeat, clip_lock filter, finalize)
  thành stage module như recap/content đã làm; tiến tới `run_render_pipeline` chỉ
  còn điều phối ~300 dòng.

### ⚠ RE-2: part_voice_mix 1192 + part_asset_planner 1104 dòng
- **Root cause:** 2 stage helper phình to.
- **Ảnh hưởng:** TB — khó đọc, nhưng cohesion vẫn cao (1 trách nhiệm).
- **Dài hạn:** tách sub-helper theo bước (tts / mix / duck / caption).

### ⚠ RE-3: 2 resolver codec song song
- Đã pinned parity test — rủi ro divergence tương lai. Dài hạn: hợp nhất
  (CRITICAL-tier, plan riêng).

## 7. Đánh giá

| Trục | Điểm |
|------|------|
| GPU/NVENC safety | 9 |
| QA gate | 9 |
| Stage modularity | 7.5 |
| God-file risk | 5 |
| Resume/cache | 8 |
| **Tổng** | **7.7** |

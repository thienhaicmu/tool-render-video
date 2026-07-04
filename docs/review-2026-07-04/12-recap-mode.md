# 12 — Recap Mode (review cực sâu)

`render_format="recap"` — orchestrator `run_recap`
([recap_pipeline.py:254](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L254), 970 dòng).
Đây là mode **AI-tinh-vi nhất** trong hệ thống.

## 1. Workflow đầy đủ

```
source prep
  ├─ (song song) SceneMap worker thread — scenedetect, KHÔNG cần SRT, khởi động
  │              TRƯỚC Whisper để chồng lấp thời gian [:316-335]
  ├─ Whisper transcribe TOÀN video (skip_segment_selection) → full SRT
  ├─ Comprehension stage (hoist) → StoryModel  (pass-1, có WS event riêng)
  ├─ select_recap_plan → pass-2 Editorial (opt-in) → pass-3 scene binding
  ├─ bind_story_beats_to_scenes()            [deterministic]
  ├─ join SceneMap → snap_scenes_to_shots()  [deterministic, RECAP_SNAP...]
  ├─ trim_to_duration_band(runtime)          [deterministic, ép 10-25%]
  ├─ (opt) per-episode narration refinement
  ├─ update_recap_plan(json) + emit recap.plan.ready (scene blocks + story + editorial)
  ├─ coverage check (span%/max_gap% → weak flag)  [diagnostic]
  ├─ run_render_loop — render mỗi scene như "part" (mượn clips loop)
  ├─ assemble ONE output per EPISODE (act title-card chèn giữa) [_assemble_recap_episodes]
  ├─ QA từng episode (expected_duration tolerance) — giữ episode pass
  ├─ repoint job_parts → episode file TRƯỚC khi xóa scene tạm  [Fix A]
  └─ terminal result_json (N episode outputs) → DONE
```

## 2. AI Pipeline — 3 pass Story Intelligence

Chi tiết ở doc 09. Điểm nhấn recap:
- **Transcript → StoryModel** (theme/conflict/characters/emotional curve).
- **StoryModel → EditorialBlueprint** (HOW to tell, no transcript).
- **→ RecapPlan** (episodes→acts→scenes, chronological, act-structured, whole-film).
- `_scored_from_recap_plan` ([:100](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L100))
  flatten episodes→acts→scenes thành "scored" shape mà render loop hiểu, kèm
  **director's intent liên tục** (Previously/Now) để narration flow scene→scene.

## 3. Chunking / context / transcript

- Whisper cho SRT đầy đủ; `resolve_provider_max_srt_chars` + `_fit_seconds_transcript`
  ([prompts.py:44,136](../../backend/app/features/render/ai/llm/prompts.py#L44))
  giới hạn transcript theo provider để không vượt context.
- `check_srt_truncation` cảnh báo khi SRT bị cắt.

## 4. Điểm mạnh riêng của recap

1. **Song song SceneMap ‖ Whisper ‖ LLM** — tối ưu wall-clock thông minh
   (scenedetect chậm hơn nhưng độc lập → chạy nền).
2. **Deterministic guardrails** đóng gap "AI phớt lờ ràng buộc" — snap-to-shots,
   trim-to-band. **Đây là điểm sáng nhất toàn hệ thống về triết lý AI.**
3. **1 output/tập** với title-card, filename từ AI title (FS-safe, chống collision).
4. **audio_mode narrate/original** — scene có thể để audio gốc chạy (không narrate).
5. **Coverage diagnostic** — cảnh báo plan yếu (clustered/big gap) mà không chặn.

## 5. Đánh giá theo checklist

| Câu hỏi | Kết luận |
|---------|----------|
| AI workflow | **Rất mạnh** — 3-pass + deterministic guard |
| Prompt | Có story/editorial/binding prompt riêng; truncation-safe |
| Chunking/context | Đúng — provider-aware SRT budget |
| Transcript | Whisper 1 lần, lock-serialised |
| Recap generation | Tốt — chronological, act-structured, duration-band enforced |
| Timeline generation | scene blocks emit cho FE NLE timeline |
| Render flow | Mượn clips render loop → reuse tốt nhưng coupling ẩn |
| Queue flow | Chung wrapper process_render |
| Export flow | 1 file/episode vào output_dir, repoint parts |

## 6. Vấn đề

### RECAP-1: Coupling ẩn với render_pipeline internals
- Import `JOB_SEMAPHORE`, `_render_active_lock`, `_render_active_count`,
  `PartRenderContext` từ render_pipeline/part_renderer
  ([:63-68](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L63-L68)).
- **Root cause:** reuse clips render loop mà không nâng primitive chung lên.
- **Ảnh hưởng:** TB — đổi render_pipeline có thể vỡ recap; test full suite bắt buộc.
- **Dài hạn:** nâng semaphore/lock/counter + PartRenderContext lên module chung
  (`engine/concurrency.py`).

### RECAP-2: Rất nhiều env flag (doc 09 AI-1)
- 6+ flag chi phối hành vi → khó tái hiện/kiểm thử tổ hợp.

### RECAP-3: PartRenderContext khởi tạo tay ~20 tham số
- [:709-724](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L709-L724)
  điền thủ công nhiều field (nhiều field rỗng cho recap). Dễ lệch khi context đổi.
- **Dài hạn:** factory `PartRenderContext.for_recap(...)`.

### RECAP-4: Trùng `_safe_filename`, `_set_stage`, terminal block với content/clips
- Xem doc 14.

## 7. Điểm

| Trục | Điểm |
|------|------|
| AI workflow | 9 |
| Deterministic guard | 9.5 |
| Parallelism | 8.5 |
| Coupling/bảo trì | 6 |
| Duplicate | 5.5 |
| **Tổng** | **7.7** |

# 03 — Workflow tổng thể

## 1. Vòng đời một job render (chung cho 3 mode)

```
User (FE) ─► POST /api/render/process (RenderRequestPublic, 88 field, extra=forbid)
   │
   ├─ handler mở rộng → RenderRequest (201 field, validators, BE-only defaults)
   ├─ _validate_render_source / _validate_output_dir  (_common.py:181, :93)
   │     · check output_dir tồn tại/ghi được (N6) · check free disk (N8)
   │     · source dedup Layer A (DB scan) + Layer B (recently-cancelled ledger)
   ├─ _queue_render_job → upsert_job(status=queued) → submit_job(...)
   │
   ▼ QUEUE (jobs/manager.py)
   scheduler thread: heap pop (ưu tiên) khi có slot < MAX_CONCURRENT_JOBS
   ├─ _mark_job_running (DB queued→running)
   ├─ record start time (watchdog age-limit)
   └─ executor.submit(_run → process_render)
   │
   ▼ WORKER THREAD  process_render (_common.py:209)
   cancel_registry.register(job_id)
   ├─ render_format == "recap"   → run_recap
   ├─ render_format == "content" → run_content
   └─ else                       → run_render_pipeline
        │  (mỗi stage: update_job_progress + _emit_render_event → WS {job,parts,summary})
        ▼
   Terminal: upsert_job(status=completed/…, stage=DONE, result_json)  [Sacred #1]
   finally: close_thread_conn · RENDER_JOBS_TOTAL/DURATION metrics · unregister
```

## 2. Clip mode — chuỗi stage (Contract #4)

`QUEUED → STARTING → RUNNING → ANALYZING → TRANSCRIBING_FULL → SCENE_DETECTION →
SEGMENT_BUILDING → RENDERING/RENDERING_PARALLEL → WRITING_REPORT → DONE`

Chi tiết ([render_pipeline.py:472-1930](../../backend/app/features/render/engine/pipeline/render_pipeline.py#L472)):
1. Source prep (local file / edit session).
2. Whisper transcribe **1 lần** toàn video (TRANSCRIBING_FULL, có heartbeat progress).
3. Scene detection (`scene_detector.py`).
4. Segment selection: LLM `select_render_plan` → clips + subtitle_policy +
   camera_strategy + audio_plan (một call). Fallback nếu None.
5. `run_render_loop` — parallel part dispatch qua ThreadPoolExecutor, mỗi part
   qua `part_renderer` → 8 helper (context→asset_planner→cut→setup→encode→
   voice_mix→finalize→done).
6. Ranking (`pipeline_ranking`) → viral score → best clip.
7. QA từng output (Sacred #8) → WRITING_REPORT → DONE.

## 3. Recap mode — chuỗi stage đặc thù

Điểm khác biệt lớn ([recap_pipeline.py:295-849](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L295)):
- **SceneMap chạy song song** trên thread nền (scenedetect không cần SRT) khởi
  động **trước** Whisper để chồng lấp thời gian ([:316-335](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L316-L335)).
- **Story Intelligence 3-pass** (doc 09/12): pass-1 Story Understanding →
  pass-2 Editorial Blueprint (opt-in) → pass-3 scene binding.
- Guardrail **tất định** sau LLM: `bind_story_beats_to_scenes`,
  `snap_scenes_to_shots` (snap về shot boundary), `trim_to_duration_band`
  (ép recap về 10-25% runtime vì LLM phớt lờ budget prompt).
- Render mỗi scene như "part" qua **chính** `run_render_loop` của clips.
- Assemble **1 output/tập** (episode) với act title-card chèn giữa.
- Repoint `job_parts.output_file` về file episode trước khi xóa scene tạm.

## 4. Content mode — chuỗi stage

Không có footage nguồn ([content_pipeline.py:154-544](../../backend/app/features/render/engine/pipeline/content_pipeline.py#L154)):
1. ANALYZING: lấy plan — hoặc từ `content_plan_override` (đã duyệt ở màn Review),
   hoặc gọi `select_content_plan` (AI Content Director).
2. SEGMENT_BUILDING: seed part rows theo scene.
3. Pre-pass **quyết định provider visual/scene** (decision tree + budget) UP FRONT.
4. RENDERING(_PARALLEL): mỗi scene = TTS narration → resolve visual → subtitle → mux.
5. WRITING_REPORT: concat scenes → 1 video (`recap_assembler.concat_clips`) →
   mix BGM (ducked) → QA → DONE.

## 5. Workflow "Review" của Content (2 bước)

```
POST /api/content/plan  {script,...} ──► {plan: ContentPlan}   (KHÔNG render)
        ▼ (FE cho user sửa plan)
POST /api/render/process {render_format:"content", content_plan_override:<json>}
        ▼ run_content render TỪ plan đã duyệt (bỏ qua AI call)
```
Đây là workflow tách "planning" khỏi "rendering" — **thiết kế tốt**, cho phép
người dùng kiểm soát trước khi tốn compute.

## 6. Nhận xét workflow

**Đúng:**
- Một điểm vào duy nhất, phân nhánh sạch — dễ suy luận.
- Progress qua WS **và** HTTP polling (fallback bắt buộc cho Electron).
- Cancel/resume/retry được xử lý ở cả 3 mode với cùng contract.

**Thừa/thiếu:**
- **Thừa bước lặp:** khối "terminal result_json + DONE" và "_set_stage" gần như
  y hệt ở 3 orchestrator → nên có `finalize_render_job()` chung (doc 14).
- **Thiếu:** không có bước "preflight cost estimate" hiển thị cho user trước khi
  render content mode dùng provider trả phí (chỉ có budget guard sau khi chạy).
- **Race tiềm ẩn:** dedup source dựa trên "30 job gần nhất" (`list_jobs_page(30,0)`
  tại [_common.py:349](../../backend/app/features/render/routers/_common.py#L349)) —
  nếu >30 job active (không thể vì bounded bởi MAX_CONCURRENT_JOBS) sẽ miss; hiện
  an toàn nhưng phụ thuộc ngầm vào cấu hình.

| Trục | Điểm |
|------|------|
| Rõ ràng luồng | 8 |
| Nhất quán 3 mode | 8 |
| Tối ưu bước | 6 (duplicate finalize) |
| **Tổng** | **7.3** |

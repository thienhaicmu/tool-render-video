# 09 — Review AI Workflow

## 1. Kiến trúc AI

```
features/render/ai/llm/
├── __init__.py        dispatcher: select_render_plan / select_recap_plan /
│                      select_content_plan / select_story_model /
│                      select_editorial_blueprint / select_episode_narration /
│                      generate_publish_meta
├── providers/         gemini.py · openai.py · claude.py  (mỗi provider tự impl)
├── prompts.py         build_render_plan_prompt (+ creator prefs, story block)
├── parser.py          parse_render_plan_response (+ dedup IoU, sanitize)
├── recap_prompts/parser · content_prompts/parser · rewrite_*
├── cache.py · key_pool.py · retry.py · content_quality.py
```

Các AI khác ngoài LLM: **Whisper** (subtitle/transcription), **scene_detector**
(PySceneDetect), **viral_scoring** (rule-based market-aware), **motion/crop**
(OpenCV subject tracking).

## 2. Provider dispatch + fallback (điểm mạnh)

`llm/__init__.py` — mỗi entrypoint:
1. Chuẩn hoá provider, build `chain = [primary] + others` khi
   `LLM_FALLBACK_ENABLED=1` (mặc định ON).
2. Lặp chain, provider trả None → thử tiếp; provider **không có impl** → skip
   (content v1 chỉ Gemini).
3. `resolve_key(provider)` per-provider để fallback dùng đúng key (LOW-1 fix).
4. Bọc `try/except` **lần hai** dù provider đã tự bắt (Sacred #3 defense-in-depth).
5. Emit Prometheus metrics (calls/latency/segments) — never fail render.

**Sacred Contract #3 được tôn trọng tuyệt đối** — không đường nào để exception AI
làm chết render.

## 3. Story Intelligence — recap 3-pass (phần AI tinh vi nhất)

Từ [llm/__init__.py:403-506](../../backend/app/features/render/ai/llm/__init__.py#L403-L506):
- **Pass 1 — Story Understanding** (`select_story_model`): hiểu toàn phim
  (theme, conflict, characters, emotional curve). Gate `RECAP_TWO_PASS=1`.
  Có thể hoist ra `comprehension_stage` (Batch C) để làm stage riêng có WS event.
- **Pass 2 — Editorial Blueprint** (`select_editorial_blueprint`): lên kế hoạch
  KỂ chuyện từ StoryModel (không cần transcript). Gate `RECAP_EDITORIAL_PASS=0`
  (opt-in). Best-effort.
- **Pass 3 — Scene binding** (`select_recap_plan`): chọn scene chronological,
  act-structured, phủ toàn phim.

Callback `on_pass1_done`/`on_pass2_done` bắn WS event giữa các pass ẩn — UI thấy
tiến độ. Failure mỗi pass non-fatal → pass sau degrade.

## 4. Guardrail TẤT ĐỊNH quanh LLM (thiết kế xuất sắc)

Nhận ra "LLM không đáng tin cho ràng buộc cứng", recap áp **deterministic** sau LLM:
- `snap_scenes_to_shots(scene_map, tol)` — snap timestamp AI về shot boundary
  thật (`RECAP_SNAP_TO_SHOTS_ENABLED=1`).
- `trim_to_duration_band(video_duration)` — ép recap về 10-25% runtime vì đo được
  LLM phớt lờ budget prompt (mẫu post-fix vẫn 69% runtime → cap 40s/scene rồi drop
  scene không thiết yếu, không đụng climax/original-audio). `RECAP_TRIM_TO_BAND=1`.
- `bind_story_beats_to_scenes()` — bind plot turn ↔ scene, phục vụ diagnostics.

**Đây là điểm sáng kiến trúc AI:** không tin AI mù quáng, đo lường rồi đóng
gap bằng logic tất định. Ít hệ thống làm được điều này.

## 5. Content AI Director

`select_content_plan` — script → ContentPlan (scenes + narration + emotion/speed/
pause + subtitle-style + visual_hint/prompt). Cho phép user duyệt qua màn Review
(`content_plan_override`). `generate_publish_meta` sinh SEO (title/desc/tags).

## 6. Clip AI — RenderPlan một call

`select_render_plan` yêu cầu provider emit **cả gói** trong 1 call: clips +
subtitle_policy + camera_strategy + audio_plan + overlays. `parser.py` có dedup
theo IoU (`_dedup_overlapping_clips`), sanitize tên, filter+score. Story model
(C.1 Phase 3) inject vào prompt để grounding.

`viral_scoring.py` (742 dòng) — **rule-based, market-aware** (US/EU/JP có hook
pattern/keyword/weight riêng). Không phải LLM → tất định, testable.

## 7. Vấn đề

### ⚠ AI-1: Nhiều env flag điều khiển pass ẩn
- 6+ flag (`RECAP_TWO_PASS`, `RECAP_EDITORIAL_PASS`, `STORY_INTELLIGENCE_HOIST_
  ENABLED`, `RECAP_SNAP_TO_SHOTS_ENABLED`, `RECAP_TRIM_TO_BAND`,
  `RECAP_PER_EPISODE_NARRATION`, `LLM_FALLBACK_ENABLED`...).
- **Root cause:** mỗi cải tiến AI thêm kill-switch để an toàn rollout.
- **Ảnh hưởng:** TB — không gian cấu hình lớn, khó test tổ hợp; hành vi phụ thuộc
  env khó tái hiện bug.
- **Dài hạn:** gom thành 1 "recap intelligence profile" (basic/standard/max) map
  sang tổ hợp flag; giảm bề mặt cấu hình cho user.

### ⚠ AI-2: Chi phí paid provider (Content ai_video/Veo)
- Budget guard tốt (decision.py) nhưng **sau** khi chạy; không preflight estimate
  cho user. Xem doc 06 V-API3.

### ⚠ AI-3: Không có eval harness gắn CI cho chất lượng plan
- Memory ghi có `ai_eval` harness (branch ai-quality-p0) nhưng không thấy chạy
  thường xuyên. Chất lượng plan (viral pick, recap coverage) chỉ đo qua event
  diagnostic (`recap.coverage weak`), không có regression gate.
- **Dài hạn:** golden-set eval chạy nightly để bắt suy giảm prompt.

## 8. Đánh giá

| Trục | Điểm |
|------|------|
| Provider dispatch/fallback | 8.5 |
| AI safety (Sacred #3) | 9.5 |
| Story Intelligence | 8.5 |
| Deterministic guardrails | 9 |
| Config surface | 6 |
| Quality measurement | 6 |
| **Tổng** | **8.0** |

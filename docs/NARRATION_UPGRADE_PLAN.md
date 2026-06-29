# Narration Quality — Review & Upgrade Plan (rewrite · Reaction · recap)

> Viết 2026-07 theo yêu cầu: kiểm chuỗi chất lượng thuyết minh
> (nội dung đúng → khớp rewrite → TTS đọc đúng → Reaction ra sao), review nguyên
> lý hoạt động, và lên plan nâng cấp 3 tính năng. Đọc từ code thật.

## TRẠNG THÁI (cập nhật 2026-07)
- ✅ **N1** — QA ngôn ngữ narration (dịch text sai ngôn ngữ trước TTS). Commit `a392472a`.
- ✅ **N2** — hết overlap "nhè nhè" (concat no-overlap, cắt segment đúng slot). Commit `a392472a`.
- ✅ **N4** — reaction_intensity (low/medium/high) + verify interleave. Commit `8eb5248d`.
- ✅ **N5** — recap continuity (truyền intent scene trước) + coverage check. Commit `5369de82`.
- ✅ **N3** — gộp segment liền kề → ngữ điệu liền mạch. Commit `553587cd`.
- 🟡 **N6** — *cache* select_recap_plan (`gemini-recap`) + rewrite (`gemini-rewrite`) **đã có sẵn** (bền 72h);
  *batch rewrite* (N part → 1 call) **HOÃN**: refactor HIGH-risk, lợi ích (rate-limit/chi phí)
  đã được throttle + cache + retry giải quyết. Làm sau khi thực sự cần, theo plan riêng.
- 🔧 Trước đó: fix gibberish fallback (`3db6f43a`) + throttle rate-limit rewrite (`5cec8096`).

---

## PHẦN 1 — Nguyên lý hoạt động hiện tại (data flow)

### 1.1 rewrite (clips, voice_source="ai_rewrite")
```
Whisper SRT (per-part slice)
  → parse_srt_blocks → format_segments_for_prompt ("[s - e] text")
  → ai.llm.rewrite_subtitle(provider, srt_segmented, clip_dur, target_language, tone,
        content_type, hook_type, clip_title, part_idx/total_parts, narration_mode, editorial_hint)
     → build_rewrite_prompt (dịch + viết lại theo word-budget=dur/60*WPM, tone table)
     → LLM (temp 0.85) → parse_rewrite_response → [{start,end,text}]   (clip-relative giây)
  → synthesize_timed_narration:
        mỗi segment → TTS (edge/piper/xtts) → _atempo_fit (1.0–1.25 nếu quá slot)
        → _concat_with_pads: adelay theo start + amix(normalize=0)  (1 file mp3 [0, clip_dur])
  → mix_narration_audio: atempo theo speed + duck (keep_original_low) + loudnorm
  → (recap) burn narration SRT
```
File: [part_voice_mix.py](../backend/app/features/render/engine/stages/part_voice_mix.py),
[rewrite_prompts.py](../backend/app/features/render/ai/llm/rewrite_prompts.py),
[timed_narration.py](../backend/app/features/render/engine/audio/timed_narration.py),
[mixer.py](../backend/app/features/render/engine/audio/mixer.py).

### 1.2 Reaction (narration_mode="reaction")
Cùng đường rewrite, KHÁC ở **prompt persona** + **schema segment**:
- Prompt yêu cầu: tìm cao trào → `kind:"voice"` (reactor dẫn) trước, `kind:"original"`
  (im, để tiếng gốc) ở cao trào, `freeze_after`/`freeze_text` để câu giờ.
- `timed_narration` bỏ qua `original` (im) → tiếng gốc phát ở đó (mix normalize=0 = full).
- `part_reaction_freeze` chèn freeze-frame + caption tại `freeze_after` (map source/speed).

### 1.3 recap (render_format="recap")
```
Whisper full SRT → ai.llm.select_recap_plan → RecapPlan (acts → scenes, is_climax, narration_intent)
  → _scored_from_recap_plan: mỗi scene = "part", editorial_hint = "[Recap Act i/n — title (beat)] intent"
  → run_render_loop render từng scene (đi qua đúng đường rewrite/Reaction ở trên, có editorial_hint)
  → recap_title_card (thẻ act) + recap_assembler (concat 1 video) + burn narration SRT
```

---

## PHẦN 2 — Kiểm chuỗi chất lượng (trả lời câu hỏi của bạn)

| Mắt xích | Hiện trạng | Vấn đề |
|----------|-----------|--------|
| **Nội dung thuyết minh có chuẩn/tốt?** | Prompt rất chi tiết (word-budget, tone table, hook). Temp 0.85. | **KHÔNG có QA nội dung** — không kiểm coherence, không kiểm đúng ngôn ngữ, không kiểm độ dài. LLM trả gì đọc nấy. |
| **Có đúng theo nội dung rewrite?** | TTS đọc **đúng** `segment.text`. | Nhưng nếu text **quá dài** so với slot → `_atempo_fit` cap 1.25× **vẫn tràn** → khi `_concat_with_pads` amix, audio segment i **đè lên** segment i+1 → **2 giọng chồng nhau = "nhè nhè"/líu**. ⚠️ Lỗi thật. |
| **Thuyết minh (TTS) có đúng?** | edge/piper/xtts đọc text. | (a) **Không đảm bảo ngôn ngữ**: nếu rewrite trả nhầm tiếng nguồn (success, không None) → đọc sai ngôn ngữ, fallback dịch KHÔNG kích hoạt (chỉ chạy khi None). (b) **Mỗi segment TTS riêng** → ngữ điệu **đứt đoạn** ở ranh giới câu (góp phần "nhè nhè"). |
| **Reaction ra nội dung sao?** | Reactor dẫn (voice) → im → tiếng gốc ở cao trào. | Phụ thuộc LLM tuân schema; **không verify** thực sự có interleave (có thể phủ kín như rewrite thường). Freeze map `source/speed` **bỏ qua micro-trim** → lệch nhẹ. |
| **recap** | AI chọn cảnh chronological + act. | **Không verify coverage** (cảnh có phủ đủ mạch, có khoảng trống lớn?). Continuity giữa scene chỉ dựa `editorial_hint` (mềm) — chưa truyền tóm tắt scene trước vào scene sau. |

### Tổng kết lỗi/nhược điểm (ưu tiên)
1. 🔴 **Segment overrun → overlap "nhè nhè"** (timed_narration `_concat_with_pads`): text dài → tràn slot → chồng giọng.
2. 🔴 **Không đảm bảo ngôn ngữ output** (rewrite success nhưng sai tiếng → đọc gibberish; fallback hiện chỉ lo None).
3. 🟠 **Không có QA/repair nội dung narration** (độ dài/ngôn ngữ/coherence) trước khi TTS.
4. 🟠 **Ngữ điệu đứt đoạn** do TTS từng micro-segment rời.
5. 🟡 **Reaction**: không verify interleave + freeze lệch micro-trim.
6. 🟡 **recap**: không verify coverage + continuity mềm.

---

## PHẦN 3 — Plan nâng cấp chi tiết (theo pha)

### N1 — QA + repair nội dung narration  `[HIGH, rewrite_parser/ part_voice_mix]`
Một bước kiểm + sửa NGAY SAU khi có segments rewrite, TRƯỚC khi TTS:
- **Ngôn ngữ**: phát hiện ngôn ngữ output (heuristic ký tự / `langdetect` nếu có) ≠ voice_language
  → dịch lại sang voice_language (`translate_text`) hoặc đánh dấu repair. Áp cho **cả output success**, không chỉ None.
- **Độ dài/fit**: với mỗi segment, ước số từ vs `(end-start)*WPM`. Nếu vượt ngưỡng (vd >1.3×)
  → **trim câu** về budget (cắt theo ranh giới câu) hoặc **split** thành sub-segment trong slot.
- Emit event `narration_qa` (per part): {lang_ok, overruns, repaired} để bạn THẤY chất lượng.
- File: `rewrite_parser.py` (thêm `validate_and_repair_segments`), gọi trong `part_voice_mix` sau rewrite.
- Test: segment quá dài → bị trim; output sai ngôn ngữ → dịch lại; success đúng → no-op.

### N2 — Hết overlap "nhè nhè" (concat không chồng giọng)  `[HIGH, timed_narration]`
Trong `_concat_with_pads`: đảm bảo audio mỗi segment **không tràn** sang segment kế:
- Tính `slot_i = next_start - start_i` (hoặc clip_end cho segment cuối).
- Nếu audio segment > slot → **atrim cứng về slot** (kèm fade-out 50ms) HOẶC **đẩy start kế tiếp**
  (sequence back-to-back, mất đồng bộ timestamp nhưng không chồng giọng — chọn theo chế độ).
- Kết hợp N1 (đã trim text) để hiếm khi phải cắt audio.
- Test: 2 segment sát nhau + audio dài → output không overlap (probe).

### N3 — Ngữ điệu liền mạch  `[MEDIUM, timed_narration]`
- Gộp các segment liền kề (gap < ngưỡng) thành **1 lần TTS** rồi cắt lại theo mốc → ít ranh giới reset ngữ điệu.
- Hoặc chế độ "continuous": TTS cả cụm câu 1 lần, đặt theo offset câu đầu.
- Test: số lần gọi TTS giảm; tổng thời lượng khớp.

### N4 — Reaction nâng cấp  `[HIGH, rewrite_prompts/ part_reaction_freeze]`
- **Verify interleave**: sau parse, nếu reaction KHÔNG có `original`/gap (phủ kín như rewrite)
  → log/repair (ép tạo khoảng trống ở cảnh cao trào) hoặc cảnh báo.
- **Freeze chính xác**: cộng bù micro-trim + intro offset khi map thời gian (hiện chỉ /speed).
- **reaction_intensity** (field tùy chọn): điều tiết mật độ chen + số freeze.
- Test: prompt reaction tạo ≥1 original window; freeze timing khớp sau trim.

### N5 — recap chất lượng  `[HIGH, recap_parser/ recap_pipeline]`
- **Verify coverage**: cảnh chronological, không gap > X% runtime; tổng ≈ total_target_sec; nếu lệch → repair/log.
- **Continuity**: truyền **tóm tắt scene trước** (1 câu) vào `editorial_hint` scene sau → narrator nối mạch.
- **Act pacing**: cân thời lượng giữa act (tránh act lệch).
- Test: plan thiếu cảnh giữa → flag; editorial_hint scene k chứa context scene k-1.

### N6 — Hiệu suất & chi phí  `[MEDIUM]`
- rewrite cache (đã có) + throttle (đã có). Thêm: **batch** rewrite nhiều part trong 1 call khi cùng job (giảm số call LLM → đỡ rate-limit, nhanh hơn).
- recap: cache select_recap_plan theo hash SRT (giống llm_plan cache).
- Đo: thêm metric `narration_qa_repairs_total`, `narration_overruns_total`.

---

## Thứ tự đề xuất (impact ↓)
**N2 + N1** (hết "nhè nhè" + đảm bảo ngôn ngữ/độ dài) → **N4** (Reaction đúng chất) →
**N5** (recap mạch lạc) → **N3** (ngữ điệu) → **N6** (tối ưu chi phí).
Mỗi pha: code → py_compile → pytest (full cho HIGH) → commit. Đường clips/recap tách như hiện tại.

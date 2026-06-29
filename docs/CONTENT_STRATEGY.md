# Content Strategy — AI Director Contract

> Canonical (2026-07, theo định nghĩa của chủ dự án). Nguyên tắc tối thượng:
> **AI Director tạo nội dung (RenderPlan); Render Engine CHỈ thực thi, tuyệt đối
> không tự sáng tạo nội dung.** Mọi quyết định về nội dung, cấu trúc, nhịp kể,
> thông điệp thuộc AI.

## Đầu vào của AI
Transcript (Whisper) · timestamp · speaker · scene · metadata video · Creator
Context · User Intent → AI phân tích → **RenderPlan** theo chiến lược người dùng chọn.

## RenderPlan (AI trả về, không trả video)
Tối thiểu: danh sách clip · timeline · lý do chọn clip · script · hook · CTA ·
subtitle · voice-over · camera strategy · subtitle strategy · BGM strategy ·
hiệu ứng đề xuất · mức nhấn cảm xúc. Render Engine dựng đúng theo đây.

---

## 1. REWRITE — tạo video MỚI hoàn toàn
**Mục tiêu:** transcript chỉ là tư liệu; AI viết kịch bản mới, video ra là sản phẩm mới.
- AI đọc TOÀN BỘ transcript → hiểu chủ đề/nhân vật/cảm xúc/tình tiết/điểm tò mò.
- AI **viết lại toàn bộ**: hook mới, cách dẫn mới, **thứ tự nội dung mới**, voice-over mới, CTA mới.
- AI **chọn lại clip** minh hoạ + sắp xếp timeline mới.
- Output: kịch bản mới · clip list · thứ tự clip · VO · subtitle · hook · CTA · hiệu ứng.

## 2. RECAP — rút gọn, GIỮ nguyên cốt truyện
**Mục tiêu:** ngắn hơn nhưng đúng câu chuyện. KHÔNG tạo câu chuyện khác.
- AI đọc toàn bộ → xác định mở đầu/diễn biến/cao trào/kết.
- Loại bỏ lặp/lan man/nghỉ/thông tin phụ; GIỮ trình tự sự kiện, nhân vật, bối cảnh.
- AI **viết lời tóm tắt** (ngắn hơn, mạch lạc cả phim).
- Output: scene quan trọng · nội dung tóm tắt · thời lượng từng đoạn · hook · CTA.
- Engine chỉ cắt ghép theo timeline AI, **giữ trình tự**.

## 3. REACTION — quan điểm người sáng tạo là CHÍNH
**Mục tiêu:** trọng tâm là bình luận của creator; clip gốc chỉ minh hoạ.
- AI hiểu toàn bộ → phân tích điều đáng bàn/tranh cãi/khen/chê/hài/bất ngờ.
- AI tạo nhận xét/bình luận/phân tích/đánh giá/cảm xúc.
- AI quyết định **thời điểm chèn clip gốc** + tạo timeline mới.
- Output: script bình luận · điểm chèn clip · thời điểm zoom · highlight · hook · CTA · subtitle.

---

## Trạng thái triển khai vs spec (gap analysis 2026-07)

| Chiến lược | Hiện tại | Khoảng cách tới spec |
|-----------|----------|----------------------|
| **Recap** | `select_recap_plan` chọn scene + 1 câu intent; **rewrite RIÊNG từng scene** (chỉ thấy mảnh) → rời rạc; transcript bị cắt cụt | AI phải **đọc trọn phim** + **tự viết lời tóm tắt** (toàn cục) → engine TTS thẳng. *Đang làm: Phase 1.* |
| **Reaction** | per-clip: dẫn → tiếng gốc; AI không soạn timeline bình luận tổng | AI soạn **script bình luận** + **điểm chèn clip** + timeline; clip minh hoạ. *Phase 2.* |
| **Rewrite** | per-PART: viết lại transcript của từng clip (giữ thứ tự) | AI viết **kịch bản mới** + **chọn lại + sắp xếp lại clip** toàn video. *Phase 3.* |
| Hạ tầng | RenderPlan domain (clips/subtitle/camera/audio/overlays) + recap_pipeline (cắt→concat→TTS→qa) | Tái dùng recap_pipeline làm **executor chung** cho cả 3 (timeline AI → dựng). |

### Nguyên tắc khi sửa
- Bỏ mọi cơ chế tool "tự quyết nội dung" (cắt cụt transcript, ép merge/độ dài, ép interleave) — đó là việc AI.
- Chỉ giữ guard **kỹ thuật**: không crash (Sacred #3), JSON hợp lệ, không chồng tiếng/clip vật lý, qa output.
- AI đọc **trọn transcript** (model context lớn — Gemini 2.5 Flash ~1M token đủ cho phim 2-3h).

### Lộ trình
- **Phase 1 — Recap:** full transcript + AI tự viết narration per scene + engine TTS thẳng (bỏ rewrite per-scene). Giữ trình tự (recap).
- **Phase 2 — Reaction:** AI soạn timeline bình luận (script + điểm chèn clip) → executor chung.
- **Phase 3 — Rewrite:** AI soạn kịch bản mới + reorder clip → executor chung.

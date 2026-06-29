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

## ⚙️ KIẾN TRÚC THỰC THI (chốt 2026-07 — đọc kỹ)
Ba chiến lược chạy theo **2 cơ chế khác nhau**:

- **AI rewrite + Reaction → MODE CLIP** (`render_format="clips"`, mặc định).
  AI cắt clip theo nội dung (select_render_plan) rồi **LÀM LẠI VOICE** trên từng
  clip đã cắt (rewrite = viết lại lời; reaction = lời bình luận + chèn tiếng gốc).
  KHÔNG có pipeline riêng, KHÔNG reorder toàn video. Việc của AI ở đây =
  **prompt tạo voice output đúng cho từng clip**.
- **Recap → MODE RIÊNG** (`render_format="recap"`, recap_pipeline). Workflow
  khác hẳn: AI đọc trọn phim → chọn cảnh theo trình tự → tự viết lời tóm tắt →
  ghép 1 video dài. (Phase 1 đã xong.)

> Trọng tâm chung: **AI làm thật kỹ ở phần prompt để ra output đúng mong muốn.**
> Render Engine chỉ thực thi.

## Trạng thái triển khai (2026-07)

| Chiến lược | Cơ chế | Trạng thái |
|-----------|--------|-----------|
| **Recap** | MODE RIÊNG (recap_pipeline) | ✅ Phase 1: AI đọc trọn phim + tự viết lời tóm tắt + engine TTS thẳng. |
| **AI rewrite** | MODE CLIP — làm lại voice/clip | Hoạt động; việc còn lại = **tinh prompt** cho lời dịch/viết lại tự nhiên, đúng nội dung clip. |
| **Reaction** | MODE CLIP — voice bình luận/clip | Hoạt động; việc còn lại = **tinh prompt** cho bình luận tự nhiên (đỡ cứng), nhịp dẫn→tiếng gốc hợp lý. |

### Nguyên tắc khi sửa
- Bỏ mọi cơ chế tool "tự quyết nội dung" (cắt cụt transcript, ép merge/độ dài, ép interleave) — đó là việc AI.
- Chỉ giữ guard **kỹ thuật**: không crash (Sacred #3), JSON hợp lệ, không chồng tiếng/clip vật lý, qa output.
- AI đọc **trọn transcript** (model context lớn — Gemini 2.5 Flash ~1M token đủ cho phim 2-3h).

### Lộ trình
- **Phase 1 — Recap (xong):** mode riêng; AI đọc trọn phim + tự viết lời tóm tắt; engine TTS thẳng.
- **Tiếp theo — tinh PROMPT (mode clip):** KHÔNG làm pipeline holistic cho rewrite/reaction.
  Chúng giữ mode clip (làm lại voice trên clip AI đã cắt). Việc còn lại là **làm prompt
  thật kỹ** để output voice đúng mong muốn:
  - rewrite: lời dịch/viết lại tự nhiên, bám đúng nội dung clip, fit thời lượng.
  - reaction: bình luận tự nhiên (đỡ cứng), AI tự quyết nhịp dẫn → chừa tiếng gốc cao trào.

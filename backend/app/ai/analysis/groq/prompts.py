"""
prompts.py — Prompt templates for Groq segment selection.

Versioned here so prompts evolve independently of the API client.
"""
from __future__ import annotations

_SYSTEM = (
    "Bạn là AI chuyên phân tích transcript video để tạo clip ngắn viral. "
    "Nhiệm vụ: chọn đúng số đoạn được yêu cầu, đúng thời lượng, trả về JSON hợp lệ. "
    "KHÔNG giải thích, KHÔNG thêm văn bản ngoài JSON."
)

_USER_TEMPLATE = """\
Transcript ({language}):
{srt_content}

RÀNG BUỘC BẮT BUỘC (vi phạm = kết quả bị từ chối):
1. Trả về ĐÚNG {output_count} đoạn — không hơn, không kém
2. Mỗi đoạn: end - start phải từ {min_sec}s đến {max_sec}s
3. Các đoạn KHÔNG chồng nhau (start của đoạn sau >= end của đoạn trước)
4. clip_name: tên tự nhiên mô tả nội dung, tối đa 60 ký tự
   — Được phép: chữ cái (kể cả tiếng Việt), số, dấu cách, dấu gạch ngang
   — KHÔNG dùng: / \\ : * ? " < > | và ký tự xuống dòng
5. score: số thực 0.0–1.0 (1.0 = xuất sắc nhất)

Ưu tiên chọn: hook mạnh ở đầu đoạn, thông tin có giá trị cao, khoảnh khắc thú vị/cảm xúc.
Bỏ qua: intro, outro, quảng cáo, đoạn im lặng dài, nội dung lặp lại.

Trả về JSON array (chỉ JSON, không gì thêm):
[
  {{
    "start": 45.2,
    "end": 102.8,
    "score": 0.92,
    "clip_name": "Bí quyết tăng view nhanh",
    "title": "Bí quyết tăng view nhanh nhất 2025",
    "reason": "Hook mạnh ngay giây đầu, kỹ thuật cụ thể có thể áp dụng ngay"
  }}
]"""

# Hard cap: prevent excessive token cost on very long transcripts.
MAX_SRT_CHARS = 12_000


def build_segment_prompt(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    language: str = "auto",
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for Groq segment selection."""
    truncated = srt_content[:MAX_SRT_CHARS]
    if len(srt_content) > MAX_SRT_CHARS:
        truncated += "\n... [transcript truncated]"

    user = _USER_TEMPLATE.format(
        language=language,
        srt_content=truncated,
        output_count=output_count,
        min_sec=int(min_sec),
        max_sec=int(max_sec),
    )
    return _SYSTEM, user

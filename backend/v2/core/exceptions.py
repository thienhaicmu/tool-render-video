"""
exceptions.py — Custom exceptions cho v2.

Quy tắc:
- Mỗi domain có exception gốc riêng
- Stage exceptions kế thừa từ domain exception
- Luôn truyền message rõ ràng, không raise Exception("lỗi")
- AI modules: bắt tất cả exceptions nội bộ, không để raise lên pipeline
"""


# ── Base ──────────────────────────────────────────────────────────────────────

class V2Error(Exception):
    """Base exception cho toàn bộ v2."""


# ── Download domain ───────────────────────────────────────────────────────────

class DownloadError(V2Error):
    """Base exception cho domain download."""

class InvalidUrlError(DownloadError):
    """URL không hợp lệ hoặc không được hỗ trợ."""

class DownloadFailedError(DownloadError):
    """yt-dlp download thất bại."""


# ── Render domain ─────────────────────────────────────────────────────────────

class RenderError(V2Error):
    """Base exception cho domain render."""

class ValidateError(RenderError):
    """Source file không hợp lệ (không tồn tại, không có audio, v.v.)."""

class TranscribeError(RenderError):
    """Whisper transcription thất bại."""

class GroqSelectError(RenderError):
    """Groq segment selection thất bại — pipeline fallback sang local scorer."""

class SceneDetectError(RenderError):
    """Scene detection thất bại."""

class PartRenderError(RenderError):
    """FFmpeg render 1 part thất bại."""

    def __init__(self, part_index: int, reason: str) -> None:
        self.part_index = part_index
        self.reason = reason
        super().__init__(f"Part {part_index} failed: {reason}")

class QaError(RenderError):
    """Output file không pass QA validation."""

    def __init__(self, output_path: str, reason: str) -> None:
        self.output_path = output_path
        self.reason = reason
        super().__init__(f"QA failed [{output_path}]: {reason}")


# ── System ────────────────────────────────────────────────────────────────────

class CancelledError(V2Error):
    """Job bị cancel bởi user."""

class ConfigError(V2Error):
    """Config thiếu hoặc không hợp lệ (ví dụ: thiếu GROQ_API_KEY)."""

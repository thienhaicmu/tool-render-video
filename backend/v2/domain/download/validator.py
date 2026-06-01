"""
validator.py — Validate và phân loại URL trước khi download.
"""
from __future__ import annotations

from urllib.parse import urlparse

from v2.core.exceptions import InvalidUrlError

_YOUTUBE_HOSTS = frozenset({
    "youtube.com", "youtu.be", "m.youtube.com",
    "www.youtube.com", "youtube-nocookie.com",
})
_FACEBOOK_HOSTS = frozenset({
    "facebook.com", "fb.watch", "m.facebook.com", "www.facebook.com",
})
_INSTAGRAM_HOSTS = frozenset({
    "instagram.com", "instagr.am", "www.instagram.com",
})

SUPPORTED_SOURCES = frozenset({"youtube", "facebook", "instagram"})


def validate_url(url: str) -> str:
    """Validate và normalize URL. Raise InvalidUrlError nếu không hợp lệ."""
    url = url.strip()
    if not url:
        raise InvalidUrlError("URL không được để trống")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise InvalidUrlError(f"URL phải bắt đầu bằng http:// hoặc https://: {url!r}")
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            raise InvalidUrlError(f"URL không hợp lệ (thiếu domain): {url!r}")
    except Exception as exc:
        raise InvalidUrlError(f"URL không parse được: {url!r}") from exc
    return url


def detect_source(url: str) -> str:
    """Phát hiện nguồn video từ URL. Trả về: 'youtube' | 'facebook' | 'instagram' | 'unknown'."""
    try:
        host = (urlparse(url.strip()).hostname or "").lower()
    except Exception:
        return "unknown"

    host = host.removeprefix("www.")

    if host in _YOUTUBE_HOSTS or host.endswith(".youtube.com"):
        return "youtube"
    if host in _FACEBOOK_HOSTS or host.endswith(".facebook.com"):
        return "facebook"
    if host in _INSTAGRAM_HOSTS or host.endswith(".instagram.com"):
        return "instagram"
    return "unknown"


def validate_supported_url(url: str) -> str:
    """Validate URL và kiểm tra nguồn được hỗ trợ. Raise InvalidUrlError nếu không hợp lệ."""
    url = validate_url(url)
    source = detect_source(url)
    if source not in SUPPORTED_SOURCES:
        raise InvalidUrlError(
            f"Nguồn không được hỗ trợ: {url!r}. "
            f"Hỗ trợ: {', '.join(sorted(SUPPORTED_SOURCES))}"
        )
    return url

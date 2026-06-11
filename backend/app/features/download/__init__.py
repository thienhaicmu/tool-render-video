# Feature: platform video downloader
# Supports: YouTube, TikTok, Instagram, Facebook, Douyin (via yt-dlp adapters)
from .engine.acquire import acquire, get_adapter  # noqa: F401
from .service import detect_platform  # noqa: F401

# Feature: platform video downloader
# Supports: YouTube, TikTok, Instagram, Facebook, Douyin (via yt-dlp adapters)
from .service import download_video, get_adapter  # noqa: F401

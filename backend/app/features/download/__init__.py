# Feature: platform video downloader
# Supports: YouTube, TikTok, Instagram, Facebook (via yt-dlp).
#
# The live download path is app.features.download.engine.download_video
# (wired in router.py). The former service.py/adapters adapter-chain was
# unused dead code and removed 2026-06-18 — see
# docs/audit-2026-06-06/DOWNLOAD_REVIEW_FIXES_2026-06-18.md.
from app.features.download.engine import download_video, get_video_info  # noqa: F401

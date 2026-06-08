def get_tiktok_opts() -> dict:
    """yt-dlp options for TikTok — prefers no-watermark download_addr source."""
    return {
        "format": (
            "download_addr-0/download_addr"
            "/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=1080]+bestaudio"
            "/best[height<=1080]/best"
        ),
        "extractor_args": {
            "tiktok": {
                "api_hostname": "api22-normal-c-useast2a.tiktokv.com",
            }
        },
    }

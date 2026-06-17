from functools import lru_cache
from urllib.parse import urlparse

_DOMAIN_MAP: dict[str, str] = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "m.youtube.com": "youtube",
    "tiktok.com": "tiktok",
    "vm.tiktok.com": "tiktok",
    "vt.tiktok.com": "tiktok",
    "instagram.com": "instagram",
    "instagr.am": "instagram",
    "facebook.com": "facebook",
    "fb.watch": "facebook",
    "m.facebook.com": "facebook",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "t.co": "twitter",
    "bilibili.com": "bilibili",
    "b23.tv": "bilibili",
    "reddit.com": "reddit",
    "redd.it": "reddit",
    "vimeo.com": "vimeo",
    "dailymotion.com": "dailymotion",
    "twitch.tv": "twitch",
    "nicovideo.jp": "nicovideo",
}

ALLOWED_DOMAINS = frozenset(_DOMAIN_MAP.keys())


@lru_cache(maxsize=1024)
def detect_platform(url: str) -> str:
    # Perf-opt Phase 3 (D9): up to 7 sites call detect_platform per
    # download flow (router validate + dedup + start, engine.get_video_info
    # + download_video, batch route, _run_download). The result depends
    # only on the URL host, so memoising on the full URL string is safe
    # and skips the urlparse + map lookup on every subsequent hit.
    try:
        host = (urlparse(url).hostname or "").lower()
        host = host.removeprefix("www.").removeprefix("m.")
        return _DOMAIN_MAP.get(host, "other")
    except Exception:
        return "other"


def is_allowed_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
        host = host.removeprefix("www.").removeprefix("m.")
        return host in ALLOWED_DOMAINS
    except Exception:
        return False

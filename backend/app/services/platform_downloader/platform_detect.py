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


def detect_platform(url: str) -> str:
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

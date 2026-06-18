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


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _platform_for_host(host: str) -> str:
    """Map a hostname to a platform.

    Matches exactly OR as a subdomain (``host`` ends with ``.<base>``) so
    legit subdomains like ``music.youtube.com`` resolve correctly. The
    leading-dot requirement keeps lookalike hosts (``youtube.com.evil.com``)
    from matching, so this stays SSRF-allowlist-safe.
    """
    if not host:
        return "other"
    plat = _DOMAIN_MAP.get(host)
    if plat:
        return plat
    for d, name in _DOMAIN_MAP.items():
        if host.endswith("." + d):
            return name
    return "other"


@lru_cache(maxsize=1024)
def detect_platform(url: str) -> str:
    # Perf-opt Phase 3 (D9): up to 7 sites call detect_platform per download
    # flow. The result depends only on the URL host, so memoising on the full
    # URL string is safe and skips the urlparse + lookup on every hit.
    return _platform_for_host(_host_of(url))


def is_allowed_url(url: str) -> bool:
    # Consistent with detect_platform (same matching) — a URL is allowed iff it
    # resolves to a known platform.
    return _platform_for_host(_host_of(url)) != "other"

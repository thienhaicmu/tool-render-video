"""Regression tests for the 2026-06-18 download-feature review fixes.

Covers the unit-testable parts of the 10 findings:
  #1  quality -> format mapping (engine._quality_to_format)
  #3  router in-flight dedup helpers (single + batch share one reservation)
  #9  cookie_extractor host filter keeps subdomains, rejects lookalikes
  #10 platform_detect resolves subdomains, blocks allowlist-bypass hosts
"""
from __future__ import annotations

import pytest


# ── #1 quality -> format ──────────────────────────────────────────────────────

def test_quality_to_format_caps_height():
    from app.features.download.engine.engine import _quality_to_format
    assert "height<=720" in _quality_to_format("720p")
    assert "height<=480" in _quality_to_format("480p")
    assert "height<=1080" in _quality_to_format("1080p")


def test_quality_to_format_accepts_arbitrary_heights():
    # Per-video quality picker can offer any resolution the source exposes.
    from app.features.download.engine.engine import _quality_to_format
    assert "height<=2160" in _quality_to_format("2160p")
    assert "height<=1440" in _quality_to_format("1440p")
    assert "height<=360" in _quality_to_format("360p")


# ── quality fallback to best (download won't error on unavailable quality) ────

def test_quality_fallback_triggers_on_format_error():
    from app.features.download.engine.engine import _should_quality_fallback
    err = Exception("ERROR: Requested format is not available")
    assert _should_quality_fallback("youtube", "1080p", err, cancelled=False) is True


def test_quality_fallback_skips_when_best_already():
    from app.features.download.engine.engine import _should_quality_fallback
    err = Exception("Requested format is not available")
    assert _should_quality_fallback("youtube", "best", err, cancelled=False) is False


def test_quality_fallback_skips_tiktok_and_cancel_and_other_errors():
    from app.features.download.engine.engine import _should_quality_fallback
    fmt_err = Exception("Requested format is not available")
    net_err = Exception("Connection timed out")
    assert _should_quality_fallback("tiktok", "720p", fmt_err, cancelled=False) is False
    assert _should_quality_fallback("youtube", "720p", fmt_err, cancelled=True) is False
    assert _should_quality_fallback("youtube", "720p", net_err, cancelled=False) is False


# ── height/fps resolution (no more 0p in the UI) ──────────────────────────────

def test_resolve_dimensions_prefers_top_level():
    from app.features.download.engine.engine import _resolve_dimensions
    h, f = _resolve_dimensions({"height": 1080, "fps": 30})
    assert h == 1080 and f == 30.0


def test_resolve_dimensions_falls_back_to_requested_streams():
    from app.features.download.engine.engine import _resolve_dimensions
    # top-level height missing (the Facebook 0p case) — derive from the
    # actually-downloaded streams.
    info = {
        "height": 0,
        "requested_downloads": [{"height": 360, "fps": 25}],
        "requested_formats": [{"height": 360}, {"height": 0}],
    }
    h, f = _resolve_dimensions(info)
    assert h == 360 and f == 25.0


def test_resolve_dimensions_handles_strings_and_missing():
    from app.features.download.engine.engine import _resolve_dimensions
    h, f = _resolve_dimensions({"height": "720", "fps": "29.97"})
    assert h == 720 and round(f, 2) == 29.97
    # nothing usable + no file → (0, 0.0), never raises
    assert _resolve_dimensions({}) == (0, 0.0)


def test_quality_to_format_best_is_uncapped():
    from app.features.download.engine.engine import _quality_to_format
    fmt = _quality_to_format("best")
    assert "height<=" not in fmt
    # unknown/empty fall back to best (uncapped)
    assert _quality_to_format("garbage") == fmt
    assert _quality_to_format("") == fmt


# ── #10 platform_detect ───────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://music.youtube.com/watch?v=x", "youtube"),
    ("https://www.youtube.com/watch?v=x", "youtube"),
    ("https://m.youtube.com/watch?v=x", "youtube"),
    ("https://vm.tiktok.com/abc/", "tiktok"),
    ("https://sub.x.com/i/status/1", "twitter"),
    ("https://evil.com/x", "other"),
    # allowlist-bypass attempts must NOT resolve to a platform
    ("https://youtube.com.evil.com/x", "other"),
    ("https://notyoutube.com/x", "other"),
])
def test_detect_platform_subdomains_and_bypass(url, expected):
    from app.features.download.engine.platform_detect import detect_platform
    assert detect_platform(url) == expected


@pytest.mark.parametrize("url,allowed", [
    ("https://music.youtube.com/x", True),
    ("https://youtube.com.evil.com/x", False),
    ("https://evil.com/x", False),
])
def test_is_allowed_url_consistent_with_detect(url, allowed):
    from app.features.download.engine.platform_detect import is_allowed_url
    assert is_allowed_url(url) is allowed


# ── #9 cookie host filter ─────────────────────────────────────────────────────

@pytest.mark.parametrize("host,keep", [
    (".youtube.com", True),
    ("www.youtube.com", True),
    ("music.youtube.com", True),
    ("accounts.google.com", True),
    (".google.com", True),
    ("evil.com", False),
    ("notyoutube.com", False),
    ("youtube.com.evil.com", False),
])
def test_is_youtube_auth_host(host, keep):
    from app.features.download.engine.cookie_extractor import _is_youtube_auth_host
    assert _is_youtube_auth_host(host) is keep


# ── #3 router in-flight dedup ─────────────────────────────────────────────────

def test_reserve_inflight_dedups_same_url():
    from app.features.download import router

    url = "https://www.youtube.com/watch?v=dedup-test"
    router._release_inflight(url, router._INFLIGHT_URLS.get(url) or "")  # clean slate
    try:
        jid1, new1 = router._reserve_inflight(url)
        jid2, new2 = router._reserve_inflight(url)
        assert new1 is True and new2 is False
        assert jid1 == jid2  # batch/single share the one reservation
    finally:
        router._release_inflight(url, jid1)
    # After release a fresh reservation gets a new id
    jid3, new3 = router._reserve_inflight(url)
    try:
        assert new3 is True and jid3 != jid1
    finally:
        router._release_inflight(url, jid3)


def test_release_inflight_only_owner():
    from app.features.download import router

    url = "https://www.youtube.com/watch?v=owner-test"
    jid, _ = router._reserve_inflight(url)
    try:
        # A non-owner release must not clear the reservation.
        router._release_inflight(url, "some-other-job")
        assert router._INFLIGHT_URLS.get(url) == jid
    finally:
        router._release_inflight(url, jid)
    assert url not in router._INFLIGHT_URLS

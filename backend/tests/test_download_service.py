"""Tests for app.features.download.service and app.features.download.adapters.base."""
from __future__ import annotations

import pytest

from app.features.download.adapters.base import DownloadAdapter
from app.features.download.adapters.youtube import YouTubeAdapter
from app.features.download.adapters.tiktok import TikTokAdapter
from app.features.download.adapters.generic import GenericAdapter
from app.features.download.service import get_adapter


# ---------------------------------------------------------------------------
# get_adapter — URL routing
# ---------------------------------------------------------------------------

def test_get_adapter_youtube_url_returns_youtube_adapter():
    adapter = get_adapter("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert isinstance(adapter, YouTubeAdapter)


def test_get_adapter_youtu_be_url_returns_youtube_adapter():
    adapter = get_adapter("https://youtu.be/dQw4w9WgXcQ")
    assert isinstance(adapter, YouTubeAdapter)


def test_get_adapter_tiktok_url_returns_tiktok_adapter():
    adapter = get_adapter("https://www.tiktok.com/@user/video/123456789")
    assert isinstance(adapter, TikTokAdapter)


def test_get_adapter_vm_tiktok_url_returns_tiktok_adapter():
    adapter = get_adapter("https://vm.tiktok.com/abcdef/")
    assert isinstance(adapter, TikTokAdapter)


def test_get_adapter_unknown_url_returns_generic_adapter():
    adapter = get_adapter("https://totally-unknown-platform.example.com/video/123")
    assert isinstance(adapter, GenericAdapter)


def test_get_adapter_twitter_url_returns_generic_adapter():
    adapter = get_adapter("https://twitter.com/user/status/12345")
    assert isinstance(adapter, GenericAdapter)


# ---------------------------------------------------------------------------
# DownloadAdapter ABC
# ---------------------------------------------------------------------------

def test_download_adapter_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        DownloadAdapter()  # type: ignore[abstract]


def test_download_adapter_platform_name_strips_adapter_suffix():
    """The base class property strips 'Adapter' and lowercases."""
    # We cannot instantiate DownloadAdapter directly, but we can test the
    # property through a concrete subclass that does not override it.
    # GenericAdapter overrides platform_name, so create a minimal concrete class.
    class _TestAdapter(DownloadAdapter):
        def supports(self, url: str) -> bool:
            return True
        def download(self, url, output_dir, *, quality="best", cancel_event=None, context="download"):
            return {}

    adapter = _TestAdapter()
    # class name is '_TestAdapter' → strip 'Adapter' → '_Test' → lower '_test'
    assert adapter.platform_name == "_test"


# ---------------------------------------------------------------------------
# YouTubeAdapter.supports
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=abc",
    "https://youtu.be/abc",
    "https://m.youtube.com/watch?v=abc",
    "https://music.youtube.com/watch?v=abc",
])
def test_youtube_adapter_supports_youtube_urls(url):
    assert YouTubeAdapter().supports(url) is True


def test_youtube_adapter_does_not_support_tiktok():
    assert YouTubeAdapter().supports("https://www.tiktok.com/@user/video/123") is False


# ---------------------------------------------------------------------------
# TikTokAdapter.supports
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.tiktok.com/@user/video/12345",
    "https://vm.tiktok.com/abcde/",
    "https://vt.tiktok.com/xyz/",
])
def test_tiktok_adapter_supports_tiktok_urls(url):
    assert TikTokAdapter().supports(url) is True


def test_tiktok_adapter_does_not_support_youtube():
    assert TikTokAdapter().supports("https://www.youtube.com/watch?v=abc") is False


# ---------------------------------------------------------------------------
# GenericAdapter.supports
# ---------------------------------------------------------------------------

def test_generic_adapter_supports_any_url():
    assert GenericAdapter().supports("https://totally-random.example.com/video") is True
    assert GenericAdapter().supports("") is True


# ---------------------------------------------------------------------------
# platform_name properties
# ---------------------------------------------------------------------------

def test_youtube_adapter_platform_name():
    assert YouTubeAdapter().platform_name == "youtube"


def test_tiktok_adapter_platform_name():
    assert TikTokAdapter().platform_name == "tiktok"


def test_generic_adapter_platform_name():
    assert GenericAdapter().platform_name == "generic"

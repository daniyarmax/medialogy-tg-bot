import pytest

from app.core.exceptions import UnsupportedPlatformError
from app.downloader.platform_detector import ALL_ALLOWED_HOSTS, Platform, detect_platform


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", Platform.youtube),
        ("https://youtu.be/dQw4w9WgXcQ", Platform.youtube),
        ("https://www.youtube.com/shorts/abc123", Platform.youtube),
        ("https://www.instagram.com/reel/abc123/", Platform.instagram),
        ("https://www.tiktok.com/@user/video/12345", Platform.tiktok),
        ("https://www.facebook.com/watch/?v=12345", Platform.facebook),
        ("https://fb.watch/abc123/", Platform.facebook),
        ("https://twitter.com/user/status/12345", Platform.twitter),
        ("https://x.com/user/status/12345", Platform.twitter),
        ("https://www.reddit.com/r/videos/comments/abc123/", Platform.reddit),
        ("https://v.redd.it/abc123", Platform.reddit),
    ],
)
def test_detect_platform_recognizes_supported_hosts(url: str, expected: Platform) -> None:
    assert detect_platform(url) == expected


def test_detect_platform_rejects_unsupported_host() -> None:
    with pytest.raises(UnsupportedPlatformError):
        detect_platform("https://example.com/video")


def test_detect_platform_rejects_url_with_no_host() -> None:
    # Real case this guards: a user typing plain text ("extract audio")
    # instead of sending a link deserves a clearer message than the
    # generic "unsupported platform" one.
    with pytest.raises(UnsupportedPlatformError) as exc_info:
        detect_platform("not-a-url")
    assert "doesn't look like a link" in exc_info.value.user_message


def test_all_allowed_hosts_covers_every_platform() -> None:
    assert "youtube.com" in ALL_ALLOWED_HOSTS
    assert "tiktok.com" in ALL_ALLOWED_HOSTS
    assert "reddit.com" in ALL_ALLOWED_HOSTS

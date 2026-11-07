"""Maps a URL's host to one of the platforms this bot actually supports.

Deliberately an explicit allowlist rather than "anything yt-dlp can extract"
(yt-dlp supports 1000+ sites) — this keeps the attack surface and legal
scope limited to what requirement A actually asks for, and feeds
`app.core.security.validate_source_url`'s `allowed_hosts` parameter.
"""

import enum
from urllib.parse import urlsplit

from app.core.exceptions import UnsupportedPlatformError


class Platform(str, enum.Enum):
    youtube = "youtube"
    instagram = "instagram"
    tiktok = "tiktok"
    facebook = "facebook"
    twitter = "twitter"
    reddit = "reddit"


PLATFORM_HOSTS: dict[Platform, frozenset[str]] = {
    Platform.youtube: frozenset({"youtube.com", "youtu.be"}),
    Platform.instagram: frozenset({"instagram.com"}),
    Platform.tiktok: frozenset({"tiktok.com"}),
    Platform.facebook: frozenset({"facebook.com", "fb.watch"}),
    Platform.twitter: frozenset({"twitter.com", "x.com"}),
    Platform.reddit: frozenset({"reddit.com", "redd.it"}),
}

ALL_ALLOWED_HOSTS: frozenset[str] = frozenset(
    host for hosts in PLATFORM_HOSTS.values() for host in hosts
)


def _host_matches(host: str, bases: frozenset[str]) -> bool:
    return any(host == base or host.endswith(f".{base}") for base in bases)


def detect_platform(url: str) -> Platform:
    """Return the `Platform` a URL belongs to, or raise `UnsupportedPlatformError`."""
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        # Distinct from "a real URL, just an unsupported site" - this is
        # typically plain text (a typo, a stray word) with no scheme/host
        # at all, which needs a clearer nudge than the generic message.
        raise UnsupportedPlatformError(
            f"URL has no host: {url!r}",
            user_message="That doesn't look like a link. Please send a direct URL.",
        )

    for platform, bases in PLATFORM_HOSTS.items():
        if _host_matches(host, bases):
            return platform

    raise UnsupportedPlatformError(f"Host {host!r} is not a supported platform")

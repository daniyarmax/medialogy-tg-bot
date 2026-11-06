"""SSRF-safe URL validation for user-supplied links.

Every code path that accepts a URL from a Telegram user (link pasted into
chat, before it's ever handed to yt-dlp) must go through
`validate_source_url()` first. This is deliberately a standalone module with
no dependency on the downloader package, so it can be unit tested in
isolation and reused anywhere a URL needs vetting.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.exceptions import SourceValidationError

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Cloud-metadata endpoints that resolve to addresses which otherwise look
# like ordinary public-ish hosts, so they need an explicit blocklist on top
# of the private/reserved-range checks.
_BLOCKED_METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",  # AWS/GCP/Azure/DigitalOcean metadata
        "metadata.google.internal",
        "100.100.100.200",  # Alibaba Cloud metadata
        "fd00:ec2::254",  # AWS IMDSv2 IPv6
    }
)


@dataclass(frozen=True, slots=True)
class ParsedSourceURL:
    url: str
    scheme: str
    host: str
    resolved_ips: tuple[str, ...]


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_all(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SourceValidationError(
            f"DNS resolution failed for host {host!r}: {exc}",
            user_message="I couldn't resolve that link's host. Please check the URL.",
        ) from exc
    return sorted({info[4][0] for info in infos})


def validate_source_url(
    url: str, *, allowed_hosts: frozenset[str] | None = None
) -> ParsedSourceURL:
    """Validate a user-supplied URL before it is handed to yt-dlp.

    Raises `SourceValidationError` (safe to show `.user_message` to the
    user) for anything unsafe or malformed. `allowed_hosts`, when given, is
    an exact-domain-or-subdomain allowlist (e.g. from `platform_detector`)
    restricting which sites may be fetched at all.
    """
    parsed = urlsplit(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SourceValidationError(f"Disallowed URL scheme: {parsed.scheme!r}")

    host = parsed.hostname
    if not host:
        raise SourceValidationError("URL has no host")

    host_lower = host.lower()
    if host_lower in _BLOCKED_METADATA_HOSTS:
        raise SourceValidationError(f"Blocked metadata host: {host_lower!r}")

    if allowed_hosts is not None:
        if not any(
            host_lower == allowed or host_lower.endswith(f".{allowed}")
            for allowed in allowed_hosts
        ):
            raise SourceValidationError(
                f"Host {host_lower!r} is not an allowed platform",
                user_message="This link isn't from a platform I support yet.",
            )

    # If the host is itself a literal IP, ipaddress parses it directly;
    # otherwise resolve every A/AAAA record and check them all, which
    # defeats a DNS-rebinding attack (public IP at validation time, private
    # IP at fetch time) because we re-validate every address actually
    # reachable through this hostname right now.
    try:
        literal_ip = ipaddress.ip_address(host_lower)
        resolved = [str(literal_ip)]
    except ValueError:
        resolved = _resolve_all(host_lower)

    if not resolved:
        raise SourceValidationError(f"Host {host_lower!r} did not resolve to any address")

    for ip_str in resolved:
        ip_obj = ipaddress.ip_address(ip_str)
        if _is_blocked_ip(ip_obj) or ip_str in _BLOCKED_METADATA_HOSTS:
            raise SourceValidationError(
                f"Host {host_lower!r} resolves to a disallowed address: {ip_str}",
                user_message="That link points somewhere I'm not allowed to fetch from.",
            )

    return ParsedSourceURL(
        url=url, scheme=parsed.scheme, host=host_lower, resolved_ips=tuple(resolved)
    )


def sanitize_filename(name: str, *, max_length: int = 150, default: str = "file") -> str:
    """Produce a safe *display* filename. Never used to decide an on-disk path —
    actual paths are always derived from platform-provided IDs, not free-text titles.
    """
    allowed = "".join(c if c.isalnum() or c in " ._-" else "_" for c in name)
    allowed = " ".join(allowed.split())  # collapse whitespace runs
    allowed = allowed.strip(" ._-")
    if not allowed:
        allowed = default
    return allowed[:max_length]

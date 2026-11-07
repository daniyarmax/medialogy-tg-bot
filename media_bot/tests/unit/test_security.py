import socket

import pytest

from app.core.exceptions import SourceValidationError
from app.core.security import escape_html, sanitize_filename, validate_source_url


def _fake_getaddrinfo(ip: str):
    def _inner(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _inner


def test_rejects_non_http_schemes() -> None:
    for scheme_url in ("ftp://example.com/file", "file:///etc/passwd", "gopher://example.com"):
        with pytest.raises(SourceValidationError):
            validate_source_url(scheme_url)


def test_rejects_literal_loopback() -> None:
    with pytest.raises(SourceValidationError):
        validate_source_url("http://127.0.0.1:8080/admin")


def test_rejects_literal_private_range() -> None:
    with pytest.raises(SourceValidationError):
        validate_source_url("http://10.0.0.5/")


def test_rejects_literal_link_local_metadata_ip() -> None:
    with pytest.raises(SourceValidationError):
        validate_source_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_known_metadata_hostname() -> None:
    with pytest.raises(SourceValidationError):
        validate_source_url("http://metadata.google.internal/computeMetadata/v1/")


def test_rejects_dns_rebinding_hostname_resolving_to_private_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("10.1.2.3"))
    with pytest.raises(SourceValidationError):
        validate_source_url("http://attacker-controlled.example.com/video")


def test_accepts_valid_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("142.250.1.1"))
    result = validate_source_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.scheme == "https"
    assert result.host == "www.youtube.com"
    assert result.resolved_ips == ("142.250.1.1",)


def test_allowed_hosts_rejects_unlisted_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    with pytest.raises(SourceValidationError):
        validate_source_url(
            "https://evil.example.com/video", allowed_hosts=frozenset({"youtube.com"})
        )


def test_allowed_hosts_accepts_subdomain_of_listed_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("142.250.1.1"))
    result = validate_source_url(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", allowed_hosts=frozenset({"youtube.com"})
    )
    assert result.host == "www.youtube.com"


def test_sanitize_filename_strips_dangerous_characters() -> None:
    assert sanitize_filename("my/../../etc/passwd; rm -rf *") == "my_.._.._etc_passwd_ rm -rf"


def test_sanitize_filename_falls_back_on_empty_result() -> None:
    assert sanitize_filename("???///") == "file"


def test_escape_html_escapes_tags_and_ampersands() -> None:
    # A title like this would otherwise make Telegram's HTML parser reject
    # the whole message with "can't parse entities" - confirmed the real
    # failure mode this guards against.
    assert escape_html("<script>alert(1)</script> & Chill") == (
        "&lt;script&gt;alert(1)&lt;/script&gt; &amp; Chill"
    )


def test_escape_html_leaves_plain_text_unchanged() -> None:
    assert escape_html("Me at the zoo") == "Me at the zoo"

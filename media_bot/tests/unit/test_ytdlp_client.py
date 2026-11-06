import asyncio
import socket
from pathlib import Path

import pytest

from app.core.exceptions import (
    DownloadFailedError,
    FileTooLargeError,
    NetworkTimeoutError,
    SourceValidationError,
)
from app.downloader import ytdlp_client
from tests.unit.conftest import FakeProcess, make_subprocess_exec_stub


def _fake_getaddrinfo(host, port, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.1.1", 0))]


@pytest.fixture(autouse=True)
def _mock_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


async def test_download_streams_progress_and_returns_result_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    video_id = "dQw4w9WgXcQ"
    result_file = tmp_path / f"{video_id}.mp4"
    result_file.write_bytes(b"fake video bytes")

    stdout_lines = [
        b"MBOT_PROGRESS 1000 10000 NA 500 18\n",
        b"MBOT_PROGRESS 5000 10000 NA 500 9\n",
        f"{result_file}\n".encode(),
    ]
    fake_process = FakeProcess(stdout_lines=stdout_lines, stderr=b"", returncode=0)
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", make_subprocess_exec_stub(fake_process)
    )

    seen_updates = []
    result_path = await ytdlp_client.download(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        format_selector="18",
        dest_dir=tmp_path,
        video_id=video_id,
        max_filesize_mb=1900,
        progress_cb=seen_updates.append,
    )

    assert result_path == result_file
    assert len(seen_updates) == 2
    assert seen_updates[0].percent == pytest.approx(10.0)
    assert seen_updates[1].percent == pytest.approx(50.0)


async def test_download_raises_file_too_large_on_max_filesize_rejection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_process = FakeProcess(
        stdout_lines=[], stderr=b"File is larger than max-filesize, aborting", returncode=1
    )
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", make_subprocess_exec_stub(fake_process)
    )

    with pytest.raises(FileTooLargeError):
        await ytdlp_client.download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            format_selector="18",
            dest_dir=tmp_path,
            video_id="dQw4w9WgXcQ",
            max_filesize_mb=10,
        )


async def test_download_raises_network_timeout_error_from_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_process = FakeProcess(stdout_lines=[], stderr=b"ERROR: timed out", returncode=1)
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", make_subprocess_exec_stub(fake_process)
    )

    with pytest.raises(NetworkTimeoutError):
        await ytdlp_client.download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            format_selector="18",
            dest_dir=tmp_path,
            video_id="dQw4w9WgXcQ",
            max_filesize_mb=1900,
        )


async def test_download_rejects_url_outside_platform_allowlist_without_spawning_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = False

    async def _fail_if_called(*args, **kwargs):
        nonlocal spawned
        spawned = True
        raise AssertionError("yt-dlp should never be invoked for a rejected URL")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fail_if_called)

    with pytest.raises(SourceValidationError):
        await ytdlp_client.download(
            "https://evil.example.com/video",
            format_selector="18",
            dest_dir=tmp_path,
            video_id="whatever",
            max_filesize_mb=1900,
        )
    assert spawned is False


async def test_download_raises_when_no_output_file_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_process = FakeProcess(stdout_lines=[], stderr=b"", returncode=0)
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", make_subprocess_exec_stub(fake_process)
    )

    with pytest.raises(DownloadFailedError):
        await ytdlp_client.download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            format_selector="18",
            dest_dir=tmp_path,
            video_id="dQw4w9WgXcQ",
            max_filesize_mb=1900,
        )

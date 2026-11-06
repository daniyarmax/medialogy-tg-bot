import asyncio
import json
import socket

import pytest

from app.core.exceptions import DownloadFailedError, NetworkTimeoutError, UnsupportedPlatformError
from app.downloader import metadata as metadata_module
from app.downloader.platform_detector import Platform
from tests.unit.conftest import FakeProcess, make_subprocess_exec_stub

SAMPLE_JSON = json.dumps(
    {
        "id": "dQw4w9WgXcQ",
        "title": "Sample Video",
        "duration": 212,
        "uploader": "Sample Uploader",
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg",
        "formats": [
            {
                "format_id": "18",
                "ext": "mp4",
                "height": 360,
                "width": 640,
                "filesize": 12_345_678,
                "vcodec": "avc1",
                "acodec": "mp4a",
                "format_note": "360p",
            },
            {
                "format_id": "140",
                "ext": "m4a",
                "height": None,
                "width": None,
                "filesize_approx": 3_000_000,
                "vcodec": "none",
                "acodec": "mp4a",
                "format_note": "audio only",
            },
        ],
    }
).encode()


def _fake_getaddrinfo(host, port, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.1.1", 0))]


@pytest.fixture(autouse=True)
def _mock_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


async def test_probe_metadata_parses_successful_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_process = FakeProcess(communicate_result=(SAMPLE_JSON, b""), returncode=0)
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", make_subprocess_exec_stub(fake_process)
    )

    result = await metadata_module.probe_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.video_id == "dQw4w9WgXcQ"
    assert result.title == "Sample Video"
    assert result.platform == Platform.youtube
    assert result.duration_seconds == 212
    assert len(result.formats) == 2
    video_fmt = next(f for f in result.formats if f.format_id == "18")
    assert video_fmt.has_video is True
    assert video_fmt.resolution == "640x360"
    audio_fmt = next(f for f in result.formats if f.format_id == "140")
    assert audio_fmt.has_video is False
    assert audio_fmt.has_audio is True


async def test_probe_metadata_rejects_unsupported_platform() -> None:
    with pytest.raises(UnsupportedPlatformError):
        await metadata_module.probe_metadata("https://example.com/video")


async def test_probe_metadata_raises_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_process = FakeProcess(communicate_result=(b"", b"ERROR: Video unavailable"), returncode=1)
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", make_subprocess_exec_stub(fake_process)
    )

    with pytest.raises(DownloadFailedError):
        await metadata_module.probe_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


async def test_probe_metadata_raises_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class HangingFakeProcess(FakeProcess):
        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(10)
            return (b"", b"")

    fake_process = HangingFakeProcess()
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", make_subprocess_exec_stub(fake_process)
    )

    with pytest.raises(NetworkTimeoutError):
        await metadata_module.probe_metadata(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ", timeout_seconds=0.05
        )
    assert fake_process.killed is True

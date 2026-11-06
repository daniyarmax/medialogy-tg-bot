from pathlib import Path

import pytest

from app.core.exceptions import FFmpegError
from app.processor.media_info import probe

FIXTURES = Path(__file__).parent.parent / "fixtures" / "media"


async def test_probe_video_fixture_reports_video_and_audio_streams() -> None:
    info = await probe(FIXTURES / "sample_video.mp4")

    assert info.has_video is True
    assert info.audio is not None
    assert info.audio.codec_name == "aac"
    assert info.duration_seconds is not None
    assert 2.5 < info.duration_seconds < 3.5


async def test_probe_audio_only_m4a_fixture() -> None:
    info = await probe(FIXTURES / "sample_audio.m4a")

    assert info.has_video is False
    assert info.audio is not None
    assert info.audio.codec_name == "aac"
    assert info.audio.sample_rate == 44100


async def test_probe_audio_only_mp3_fixture() -> None:
    info = await probe(FIXTURES / "sample_audio.mp3")

    assert info.has_video is False
    assert info.audio is not None
    assert info.audio.codec_name == "mp3"


async def test_probe_raises_ffmpeg_error_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FFmpegError):
        await probe(tmp_path / "does-not-exist.mp4")

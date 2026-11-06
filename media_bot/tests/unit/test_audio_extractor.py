from pathlib import Path

import pytest

from app.processor.audio_extractor import extract_audio, needs_reencode
from app.processor.media_info import AudioStreamInfo, probe

FIXTURES = Path(__file__).parent.parent / "fixtures" / "media"


# --- needs_reencode: pure logic, no ffmpeg involved ---


def test_needs_reencode_false_when_codec_matches_and_no_bitrate_requested() -> None:
    src = AudioStreamInfo(codec_name="mp3", sample_rate=44100, channels=2, bit_rate=128_000)
    assert needs_reencode(src, "mp3", None) is False


def test_needs_reencode_false_when_requested_bitrate_at_or_above_source() -> None:
    src = AudioStreamInfo(codec_name="aac", sample_rate=44100, channels=2, bit_rate=128_000)
    assert needs_reencode(src, "m4a", 128) is False
    assert needs_reencode(src, "m4a", 125) is False  # within 5% slack of 128


def test_needs_reencode_true_when_requested_bitrate_is_a_real_downgrade() -> None:
    src = AudioStreamInfo(codec_name="aac", sample_rate=44100, channels=2, bit_rate=256_000)
    assert needs_reencode(src, "m4a", 96) is True


def test_needs_reencode_true_when_codec_does_not_match_target() -> None:
    src = AudioStreamInfo(codec_name="mp3", sample_rate=44100, channels=2, bit_rate=128_000)
    assert needs_reencode(src, "flac", None) is True


def test_needs_reencode_ignores_bitrate_for_lossless_targets() -> None:
    src = AudioStreamInfo(codec_name="flac", sample_rate=44100, channels=2, bit_rate=900_000)
    assert needs_reencode(src, "flac", 64) is False  # bitrate is meaningless for flac


# --- extract_audio: real ffmpeg subprocess calls against checked-in fixtures ---


async def test_extract_audio_strips_video_and_converts_to_mp3(tmp_path: Path) -> None:
    dest = tmp_path / "out.mp3"
    result = await extract_audio(
        FIXTURES / "sample_video.mp4", target_format="mp3", dest=dest, bitrate_kbps=128
    )

    assert result == dest
    assert dest.exists()
    info = await probe(dest)
    assert info.has_video is False
    assert info.audio is not None
    assert info.audio.codec_name == "mp3"
    assert 2.5 < (info.duration_seconds or 0) < 3.5


async def test_extract_audio_copy_path_is_lossless_and_fast_for_matching_codec(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "out.m4a"
    result = await extract_audio(FIXTURES / "sample_audio.m4a", target_format="m4a", dest=dest)

    assert result == dest
    before = await probe(FIXTURES / "sample_audio.m4a")
    after = await probe(dest)
    assert after.audio is not None
    assert after.audio.codec_name == "aac"
    # Stream copy preserves duration and bitrate essentially exactly (no
    # transcode drift), unlike a real re-encode which would shift bitrate.
    assert abs((after.duration_seconds or 0) - (before.duration_seconds or 0)) < 0.1
    assert after.audio.bit_rate == before.audio.bit_rate


async def test_extract_audio_to_flac_is_lossless(tmp_path: Path) -> None:
    dest = tmp_path / "out.flac"
    await extract_audio(FIXTURES / "sample_audio.mp3", target_format="flac", dest=dest)

    info = await probe(dest)
    assert info.audio is not None
    assert info.audio.codec_name == "flac"


async def test_extract_audio_to_opus_forces_48khz_sample_rate(tmp_path: Path) -> None:
    dest = tmp_path / "out.opus"
    await extract_audio(FIXTURES / "sample_audio.mp3", target_format="opus", dest=dest)

    info = await probe(dest)
    assert info.audio is not None
    assert info.audio.codec_name == "opus"
    assert info.audio.sample_rate == 48000


async def test_extract_audio_to_wav_is_pcm(tmp_path: Path) -> None:
    dest = tmp_path / "out.wav"
    await extract_audio(FIXTURES / "sample_audio.mp3", target_format="wav", dest=dest)

    info = await probe(dest)
    assert info.audio is not None
    assert info.audio.codec_name == "pcm_s16le"


async def test_extract_audio_preserves_progress_updates(tmp_path: Path) -> None:
    dest = tmp_path / "out.mp3"
    updates = []
    await extract_audio(
        FIXTURES / "sample_video.mp4",
        target_format="mp3",
        dest=dest,
        bitrate_kbps=128,
        progress_cb=updates.append,
    )
    assert len(updates) > 0
    assert updates[-1].percent is not None
    assert updates[-1].percent >= 90.0

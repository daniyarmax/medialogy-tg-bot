"""Proves `audio_extractor` doesn't buffer the source file in memory -
peak RSS of the ffmpeg subprocess should stay flat whether it's
processing 10 seconds or 2 hours of audio. Not part of the default test
run (excluded via `testpaths` in pyproject.toml); run explicitly with
`pytest tests/load -v`.

Generates its own synthetic audio on demand (silence/tone via ffmpeg
lavfi) rather than downloading or checking in a large real file.
"""

import asyncio
import subprocess
from pathlib import Path

import psutil
import pytest

from app.processor.audio_extractor import extract_audio

pytestmark = pytest.mark.load


def _generate_synthetic_audio(path: Path, duration_seconds: int) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={duration_seconds}",
            "-c:a", "pcm_s16le", str(path),
        ],
        check=True,
        capture_output=True,
    )


async def _measure_peak_ffmpeg_rss(src: Path, dest: Path) -> int:
    """Runs extract_audio while polling this process's ffmpeg child for
    peak RSS, returning the highest value observed.
    """
    peak_rss = 0
    stop = False

    async def monitor() -> None:
        nonlocal peak_rss
        me = psutil.Process()
        while not stop:
            for child in me.children(recursive=True):
                try:
                    if "ffmpeg" in child.name().lower():
                        peak_rss = max(peak_rss, child.memory_info().rss)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            await asyncio.sleep(0.1)

    monitor_task = asyncio.create_task(monitor())
    try:
        await extract_audio(src, target_format="mp3", dest=dest, bitrate_kbps=128)
    finally:
        stop = True
        await monitor_task

    return peak_rss


async def test_audio_extraction_memory_is_flat_regardless_of_duration(tmp_path: Path) -> None:
    short_src = tmp_path / "short.wav"
    long_src = tmp_path / "long.wav"
    _generate_synthetic_audio(short_src, 10)
    _generate_synthetic_audio(long_src, 2 * 60 * 60)  # 2 hours

    short_rss = await _measure_peak_ffmpeg_rss(short_src, tmp_path / "short.mp3")
    long_rss = await _measure_peak_ffmpeg_rss(long_src, tmp_path / "long.mp3")

    print(f"\nshort (10s) peak ffmpeg RSS: {short_rss / 1024 / 1024:.1f}MB")
    print(f"long (2h) peak ffmpeg RSS: {long_rss / 1024 / 1024:.1f}MB")

    # The point: memory must not scale with duration. A 2-hour file is
    # ~720x longer than the 10s one - if ffmpeg were buffering the whole
    # thing, RSS would be proportionally huge (hundreds of MB to GBs for
    # 2 hours of even modest-bitrate audio). Streaming keeps it flat.
    assert long_rss < 200 * 1024 * 1024, f"peak RSS {long_rss} exceeded 200MB ceiling"
    assert long_rss < short_rss * 5 + 50 * 1024 * 1024, (
        f"long-file RSS ({long_rss}) scaled with duration relative to short-file RSS ({short_rss})"
    )

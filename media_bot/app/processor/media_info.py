"""Probes a local media file's streams/duration via ffprobe — the
denominator for every progress-percent calculation in `ffmpeg.py`, and the
source of truth for the copy-vs-reencode decision in `audio_extractor.py`.
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import FFmpegError


@dataclass(frozen=True, slots=True)
class AudioStreamInfo:
    codec_name: str | None
    sample_rate: int | None
    channels: int | None
    bit_rate: int | None


@dataclass(frozen=True, slots=True)
class VideoStreamInfo:
    codec_name: str | None
    width: int | None
    height: int | None


@dataclass(frozen=True, slots=True)
class MediaInfo:
    path: Path
    duration_seconds: float | None
    format_name: str | None
    audio: AudioStreamInfo | None
    video: VideoStreamInfo | None
    has_video: bool
    tags: dict[str, str]


async def probe(path: Path, *, timeout_seconds: float = 30.0) -> MediaInfo:
    """Run `ffprobe` on a local file and parse its JSON output.

    Raises `FFmpegError` (safe `.user_message`) if ffprobe fails, times out,
    or the file has no audio stream at all.
    """
    args = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise FFmpegError(f"ffprobe timed out on {path}") from exc

    if process.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path}: {stderr.decode(errors='replace')[-2000:]}")

    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise FFmpegError(f"ffprobe returned unparsable JSON for {path}") from exc

    fmt = raw.get("format", {})
    streams = raw.get("streams", [])

    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    has_video = video_stream is not None

    audio_info = None
    if audio_stream is not None:
        audio_info = AudioStreamInfo(
            codec_name=audio_stream.get("codec_name"),
            sample_rate=int(audio_stream["sample_rate"]) if audio_stream.get("sample_rate") else None,
            channels=audio_stream.get("channels"),
            bit_rate=int(audio_stream["bit_rate"]) if audio_stream.get("bit_rate") else None,
        )

    video_info = None
    if video_stream is not None:
        video_info = VideoStreamInfo(
            codec_name=video_stream.get("codec_name"),
            width=video_stream.get("width"),
            height=video_stream.get("height"),
        )

    duration_raw = fmt.get("duration") or (audio_stream or {}).get("duration")

    return MediaInfo(
        path=path,
        duration_seconds=float(duration_raw) if duration_raw is not None else None,
        format_name=fmt.get("format_name"),
        audio=audio_info,
        video=video_info,
        has_video=has_video,
        tags={k: str(v) for k, v in fmt.get("tags", {}).items()},
    )

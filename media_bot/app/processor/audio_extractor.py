"""Extracts/converts the audio track of a media file into one of the five
formats the bot offers: MP3, WAV, M4A, FLAC, OPUS.

The central design decision is `needs_reencode`: when the source audio is
already in the target codec at an acceptable bitrate, we stream-copy
(`-c:a copy`) instead of transcoding — near-instant, and strictly lossless
compared to re-encoding something that's already in the right format.
"""

from collections.abc import Callable
from pathlib import Path

from app.core.exceptions import FFmpegError
from app.processor import media_info
from app.processor.ffmpeg import FFmpegProgress, run_ffmpeg
from app.processor.media_info import AudioStreamInfo

ENCODER_FOR_FORMAT: dict[str, str] = {
    "mp3": "libmp3lame",
    "wav": "pcm_s16le",
    "m4a": "aac",
    "flac": "flac",
    "opus": "libopus",
}

# Bitrate only means something for lossy codecs; wav/flac are always lossless.
_LOSSY_FORMATS = frozenset({"mp3", "m4a", "opus"})

_DEFAULT_BITRATE_KBPS: dict[str, int] = {"mp3": 192, "m4a": 192, "opus": 128}

# libopus only accepts a handful of sample rates; 48kHz is the universally
# supported one, so OPUS output is always resampled to it if needed.
_FORCED_SAMPLE_RATE: dict[str, int] = {"opus": 48000}

_ACCEPTABLE_SOURCE_CODECS: dict[str, frozenset[str]] = {
    "mp3": frozenset({"mp3"}),
    "wav": frozenset({"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le"}),
    "m4a": frozenset({"aac"}),
    "flac": frozenset({"flac"}),
    "opus": frozenset({"opus"}),
}


def needs_reencode(
    src: AudioStreamInfo, target_format: str, target_bitrate_kbps: int | None
) -> bool:
    """Pure decision function — independently testable without invoking ffmpeg."""
    acceptable = _ACCEPTABLE_SOURCE_CODECS.get(target_format, frozenset())
    if src.codec_name not in acceptable:
        return True

    if target_format in _LOSSY_FORMATS and target_bitrate_kbps is not None:
        src_bitrate_kbps = (src.bit_rate or 0) / 1000
        # A requested bitrate at or above the source's own bitrate can be
        # satisfied by a plain copy (re-encoding wouldn't add quality that
        # isn't there); a *lower* request is an explicit ask to shrink the
        # file and requires an actual re-encode. 5% slack absorbs rounding
        # noise in the reported source bitrate.
        if target_bitrate_kbps < src_bitrate_kbps * 0.95:
            return True

    return False


async def extract_audio(
    src: Path,
    *,
    target_format: str,
    dest: Path,
    bitrate_kbps: int | None = None,
    timeout_seconds: float = 3600.0,
    progress_cb: Callable[[FFmpegProgress], None] | None = None,
) -> Path:
    """Extract/convert `src`'s audio track into `dest` (format inferred from
    `dest`'s extension, which must match `target_format`).
    """
    if target_format not in ENCODER_FOR_FORMAT:
        raise FFmpegError(f"Unsupported audio target format: {target_format!r}")

    info = await media_info.probe(src)
    if info.audio is None:
        raise FFmpegError(f"{src} has no audio stream to extract")

    reencode = needs_reencode(info.audio, target_format, bitrate_kbps)

    dest.parent.mkdir(parents=True, exist_ok=True)

    args = ["-i", str(src), "-vn", "-map_metadata", "0"]

    if not reencode:
        args += ["-c:a", "copy"]
    else:
        args += ["-c:a", ENCODER_FOR_FORMAT[target_format]]

        effective_bitrate = bitrate_kbps or _DEFAULT_BITRATE_KBPS.get(target_format)
        if effective_bitrate is not None and target_format in _LOSSY_FORMATS:
            args += ["-b:a", f"{effective_bitrate}k"]

        forced_rate = _FORCED_SAMPLE_RATE.get(target_format)
        if forced_rate is not None:
            args += ["-ar", str(forced_rate)]

        if target_format == "mp3":
            args += ["-id3v2_version", "3"]

    args.append(str(dest))

    await run_ffmpeg(
        args,
        total_duration_seconds=info.duration_seconds,
        timeout_seconds=timeout_seconds,
        progress_cb=progress_cb,
    )

    if not dest.exists():
        raise FFmpegError(f"ffmpeg reported success but output file {dest} was not created")

    return dest

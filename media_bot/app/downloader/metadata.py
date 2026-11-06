"""Probes a URL for title/duration/available-formats via yt-dlp, without
downloading anything. Kept as a distinct subprocess call from the actual
download (see `ytdlp_client.download`) so the bot can show a quality-picker
before committing to fetching any bytes.
"""

import asyncio
import json
from dataclasses import dataclass, field

from app.core.exceptions import DownloadFailedError, NetworkTimeoutError
from app.core.security import validate_source_url
from app.downloader.platform_detector import ALL_ALLOWED_HOSTS, Platform, detect_platform


@dataclass(frozen=True, slots=True)
class FormatOption:
    format_id: str
    ext: str
    height: int | None
    resolution: str | None
    filesize_bytes: int | None
    vcodec: str | None
    acodec: str | None
    format_note: str | None

    @property
    def has_video(self) -> bool:
        return bool(self.vcodec) and self.vcodec != "none"

    @property
    def has_audio(self) -> bool:
        return bool(self.acodec) and self.acodec != "none"


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    video_id: str
    title: str
    platform: Platform
    duration_seconds: int | None
    uploader: str | None
    thumbnail_url: str | None
    formats: list[FormatOption] = field(default_factory=list)


def _format_from_raw(raw: dict) -> FormatOption:
    height = raw.get("height")
    width = raw.get("width")
    resolution = f"{width}x{height}" if width and height else raw.get("resolution")
    filesize = raw.get("filesize") or raw.get("filesize_approx")
    return FormatOption(
        format_id=str(raw.get("format_id")),
        ext=raw.get("ext", ""),
        height=height,
        resolution=resolution,
        filesize_bytes=filesize,
        vcodec=raw.get("vcodec"),
        acodec=raw.get("acodec"),
        format_note=raw.get("format_note"),
    )


async def probe_metadata(url: str, *, timeout_seconds: float = 30.0) -> MediaMetadata:
    """Validate `url`, then run `yt-dlp -J --no-playlist` and parse its JSON output.

    Raises `UnsupportedPlatformError`/`SourceValidationError` (from the
    validation step) or `DownloadFailedError`/`NetworkTimeoutError` (from
    the probe itself) — all safe to surface via `.user_message`.
    """
    platform = detect_platform(url)
    validate_source_url(url, allowed_hosts=ALL_ALLOWED_HOSTS)

    args = ["yt-dlp", "-J", "--no-playlist", "--no-warnings", url]
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
        raise NetworkTimeoutError(f"Probing {url!r} timed out after {timeout_seconds}s") from exc

    if process.returncode != 0:
        raise DownloadFailedError(
            f"yt-dlp probe failed for {url!r}: {stderr.decode(errors='replace')[-2000:]}"
        )

    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise DownloadFailedError(f"yt-dlp returned unparsable JSON for {url!r}") from exc

    formats = [_format_from_raw(f) for f in raw.get("formats", [])]

    return MediaMetadata(
        video_id=str(raw.get("id")),
        title=raw.get("title", "Untitled"),
        platform=platform,
        duration_seconds=raw.get("duration"),
        uploader=raw.get("uploader"),
        thumbnail_url=raw.get("thumbnail"),
        formats=formats,
    )

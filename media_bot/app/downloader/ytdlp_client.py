"""Runs the actual yt-dlp download as a subprocess, streaming straight to
disk (never buffered in Python memory) with line-oriented progress parsing.

Resumability: yt-dlp's own `--continue` + `.part` file mechanism handles
range-request resume; a retried task reusing the same deterministic output
path will pick up where it left off rather than restarting from scratch.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import DownloadFailedError, FileTooLargeError, NetworkTimeoutError
from app.core.security import validate_source_url
from app.downloader.platform_detector import ALL_ALLOWED_HOSTS

_PROGRESS_MARKER = "MBOT_PROGRESS"


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    downloaded_bytes: int | None
    total_bytes: int | None
    speed_bytes_per_sec: float | None
    eta_seconds: int | None

    @property
    def percent(self) -> float | None:
        if self.downloaded_bytes is None or not self.total_bytes:
            return None
        return min(100.0, (self.downloaded_bytes / self.total_bytes) * 100)


def _parse_na(value: str) -> float | None:
    if value == "NA" or not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_progress_line(line: str) -> ProgressUpdate | None:
    if not line.startswith(_PROGRESS_MARKER):
        return None
    parts = line.split()
    if len(parts) != 6:
        return None
    _, downloaded, total, total_estimate, speed, eta = parts
    downloaded_v = _parse_na(downloaded)
    # `total_bytes` is only known once the server reports Content-Length;
    # `total_bytes_estimate` (derived from an average bitrate) fills in
    # when it isn't. Either is good enough for a progress percentage.
    total_v = _parse_na(total) or _parse_na(total_estimate)
    return ProgressUpdate(
        downloaded_bytes=int(downloaded_v) if downloaded_v is not None else None,
        total_bytes=int(total_v) if total_v is not None else None,
        speed_bytes_per_sec=_parse_na(speed),
        eta_seconds=(lambda v: int(v) if v is not None else None)(_parse_na(eta)),
    )


async def download(
    url: str,
    *,
    format_selector: str,
    dest_dir: Path,
    video_id: str,
    max_filesize_mb: int,
    socket_timeout_seconds: int = 30,
    progress_cb: Callable[[ProgressUpdate], None] | None = None,
) -> Path:
    """Download `url` with yt-dlp, selecting `format_selector` (a format_id
    from `probe_metadata`, or a yt-dlp format expression).

    `video_id` (the platform-provided ID, not the free-text title) becomes
    the on-disk filename — this is what keeps filenames immune to
    attacker-controlled title strings; see `app.core.security.sanitize_filename`
    for the *display* name shown to the user instead.
    """
    validate_source_url(url, allowed_hosts=ALL_ALLOWED_HOSTS)

    dest_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(dest_dir / f"{video_id}.%(ext)s")

    args = [
        "yt-dlp",
        url,
        "-f", format_selector,
        "-o", output_template,
        "--no-playlist",
        "--newline",
        "--progress",  # force progress output even though stdout isn't a TTY
        "--progress-template",
        f"download:{_PROGRESS_MARKER} %(progress.downloaded_bytes)s "
        f"%(progress.total_bytes)s %(progress.total_bytes_estimate)s "
        f"%(progress.speed)s %(progress.eta)s",
        "--continue",
        "--retries", "10",
        "--fragment-retries", "10",
        "--socket-timeout", str(socket_timeout_seconds),
        "--max-filesize", f"{max_filesize_mb}M",
        "--no-warnings",
        "--print", "after_move:filepath",
    ]

    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    assert process.stdout is not None

    result_path: Path | None = None
    async for raw_line in process.stdout:
        line = raw_line.decode(errors="replace").strip()
        if not line:
            continue
        update = _parse_progress_line(line)
        if update is not None:
            if progress_cb is not None:
                progress_cb(update)
            continue
        candidate = Path(line)
        found = candidate if candidate.is_absolute() else dest_dir / candidate.name
        if found.exists():
            result_path = found

    stderr_bytes = await process.stderr.read() if process.stderr else b""
    returncode = await process.wait()

    if returncode != 0:
        stderr_text = stderr_bytes.decode(errors="replace")
        lowered = stderr_text.lower()
        if "timed out" in lowered or "timeout" in lowered:
            raise NetworkTimeoutError(f"yt-dlp timed out: {stderr_text[-2000:]}")
        if "max-filesize" in lowered or "file is larger than max-filesize" in lowered:
            raise FileTooLargeError(f"yt-dlp rejected oversized file: {stderr_text[-2000:]}")
        raise DownloadFailedError(f"yt-dlp exited {returncode}: {stderr_text[-2000:]}")

    if result_path is None or not result_path.exists():
        raise DownloadFailedError(
            f"yt-dlp reported success but no output file was found for {video_id!r}"
        )

    return result_path

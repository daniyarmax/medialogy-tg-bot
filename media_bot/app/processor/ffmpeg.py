"""Low-level FFmpeg subprocess runner shared by every processing operation
(audio extraction today; any future video/audio transform later). FFmpeg
itself streams disk-to-disk internally — this module's job is only to not
break that by ever reading the media into Python memory, and to turn
FFmpeg's `-progress` key=value stream into percent-complete updates.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from app.core.exceptions import FFmpegError, ProcessingTimeoutError

_SIGTERM_GRACE_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class FFmpegProgress:
    out_time_seconds: float | None
    speed: float | None
    total_duration_seconds: float | None = None

    @property
    def percent(self) -> float | None:
        if self.out_time_seconds is None or not self.total_duration_seconds:
            return None
        return min(100.0, (self.out_time_seconds / self.total_duration_seconds) * 100)


def _parse_progress_block(block: dict[str, str]) -> tuple[float | None, float | None]:
    out_time_us = block.get("out_time_us") or block.get("out_time_ms")
    out_time_seconds = float(out_time_us) / 1_000_000 if out_time_us and out_time_us != "N/A" else None

    speed_raw = block.get("speed", "").rstrip("x")
    speed = float(speed_raw) if speed_raw and speed_raw != "N/A" else None

    return out_time_seconds, speed


async def run_ffmpeg(
    args: list[str],
    *,
    total_duration_seconds: float | None = None,
    timeout_seconds: float = 3600.0,
    progress_cb: Callable[[FFmpegProgress], None] | None = None,
) -> None:
    """Run `ffmpeg -y -progress pipe:1 <args>` to completion.

    `args` must be the full set of ffmpeg arguments after the implicit
    `-y -progress pipe:1 -nostats` prefix (inputs, filters, codec options,
    and the output path) — always as a list, never a shell string, so
    there is no shell-injection surface from a filename/title.
    """
    full_args = ["ffmpeg", "-y", "-progress", "pipe:1", "-nostats", *args]

    process = await asyncio.create_subprocess_exec(
        *full_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    assert process.stdout is not None

    async def _consume_stdout() -> None:
        current_block: dict[str, str] = {}
        assert process.stdout is not None
        async for raw_line in process.stdout:
            line = raw_line.decode(errors="replace").strip()
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key == "progress":
                out_time_seconds, speed = _parse_progress_block(current_block)
                if progress_cb is not None:
                    progress_cb(
                        FFmpegProgress(
                            out_time_seconds=out_time_seconds,
                            speed=speed,
                            total_duration_seconds=total_duration_seconds,
                        )
                    )
                current_block = {}
                continue
            current_block[key] = value

    try:
        await asyncio.wait_for(
            asyncio.gather(_consume_stdout(), process.wait()), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=_SIGTERM_GRACE_SECONDS)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        raise ProcessingTimeoutError(
            f"ffmpeg exceeded the {timeout_seconds}s processing time limit and was stopped"
        )

    if process.returncode != 0:
        stderr = await process.stderr.read() if process.stderr else b""
        raise FFmpegError(f"ffmpeg exited {process.returncode}: {stderr.decode(errors='replace')[-2000:]}")

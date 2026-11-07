"""Pre-flight disk-space checks. Called twice per task per the plan: once
with a loose safety margin before a download/extraction starts (we don't
reliably know the exact output size yet), and again right before the
ffmpeg/upload stage once the actual source file size is known.
"""

import shutil
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import DiskSpaceError


def check_disk_space(path: Path, required_bytes: int = 0, *, safety_factor: float = 1.5) -> None:
    """Raise `DiskSpaceError` if `path`'s filesystem doesn't have enough
    free space for `required_bytes` (scaled by `safety_factor`) or the
    configured `MIN_FREE_DISK_MB` floor, whichever is larger.
    """
    settings = get_settings()
    path.mkdir(parents=True, exist_ok=True)

    usage = shutil.disk_usage(path)
    min_free_bytes = settings.limits.min_free_disk_mb * 1024 * 1024
    needed = max(int(required_bytes * safety_factor), min_free_bytes)

    if usage.free < needed:
        raise DiskSpaceError(
            f"Only {usage.free / 1024 / 1024:.0f}MB free at {path}, needed ~{needed / 1024 / 1024:.0f}MB"
        )

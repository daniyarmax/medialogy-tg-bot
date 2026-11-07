from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.exceptions import DiskSpaceError
from app.services.disk_guard import check_disk_space


def _usage(free_bytes: int):
    class _Usage:
        total = free_bytes * 2
        used = free_bytes
        free = free_bytes

    return _Usage()


def test_check_disk_space_passes_when_plenty_free(tmp_path: Path) -> None:
    with patch("shutil.disk_usage", return_value=_usage(100 * 1024 * 1024 * 1024)):
        check_disk_space(tmp_path, required_bytes=1024 * 1024)  # 1MB needed, 100GB free


def test_check_disk_space_raises_when_below_required(tmp_path: Path) -> None:
    with patch("shutil.disk_usage", return_value=_usage(10 * 1024 * 1024)):  # 10MB free
        with pytest.raises(DiskSpaceError):
            check_disk_space(tmp_path, required_bytes=1024 * 1024 * 1024)  # need 1GB


def test_check_disk_space_raises_when_below_min_free_floor_even_with_tiny_requirement(
    tmp_path: Path,
) -> None:
    # Even a 1-byte requirement should still enforce MIN_FREE_DISK_MB.
    with patch("shutil.disk_usage", return_value=_usage(1024)):  # 1KB free
        with pytest.raises(DiskSpaceError):
            check_disk_space(tmp_path, required_bytes=1)


def test_check_disk_space_creates_missing_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir"
    assert not target.exists()
    with patch("shutil.disk_usage", return_value=_usage(100 * 1024 * 1024 * 1024)):
        check_disk_space(target)
    assert target.exists()

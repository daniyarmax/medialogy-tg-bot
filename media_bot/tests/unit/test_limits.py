from app.core.limits import (
    disk_space_message,
    duration_exceeded_message,
    file_too_large_message,
    processing_timeout_message,
)


def test_file_too_large_message_shows_both_sizes_in_mb() -> None:
    msg = file_too_large_message(200 * 1024 * 1024, 50 * 1024 * 1024)
    assert "200MB" in msg
    assert "50MB" in msg


def test_duration_exceeded_message_shows_minutes_and_hour_limit() -> None:
    msg = duration_exceeded_message(7200, 18000)  # 120 min vs 5h limit
    assert "120 minutes" in msg
    assert "5.0-hour" in msg


def test_processing_timeout_message_shows_minutes() -> None:
    msg = processing_timeout_message(3600)
    assert "60 minutes" in msg


def test_disk_space_message_is_nonempty() -> None:
    assert len(disk_space_message()) > 0

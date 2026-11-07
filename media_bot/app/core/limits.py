"""Centralizes the user-facing wording for every configurable limit, so a
file-too-large message reads the same whether it's hit by the download
path or the audio-extraction path, and so tuning the wording only ever
means editing one file.
"""


def file_too_large_message(actual_bytes: int, limit_bytes: int) -> str:
    return (
        f"That file is {actual_bytes / 1024 / 1024:.0f}MB, which exceeds the "
        f"{limit_bytes / 1024 / 1024:.0f}MB limit. Try a lower quality or a shorter clip."
    )


def duration_exceeded_message(duration_seconds: float, limit_seconds: int) -> str:
    return (
        f"That's {duration_seconds / 60:.0f} minutes long, which exceeds the "
        f"{limit_seconds / 3600:.1f}-hour limit I can process."
    )


def disk_space_message() -> str:
    return "I'm low on storage right now — please try again in a bit."


def processing_timeout_message(limit_seconds: int) -> str:
    return (
        f"Processing took longer than {limit_seconds // 60} minutes and was stopped. "
        "Try a shorter clip or a lower quality."
    )

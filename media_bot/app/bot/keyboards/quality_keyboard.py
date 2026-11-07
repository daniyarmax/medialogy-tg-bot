"""Builds the quality-picker keyboard shown after a video URL is probed.

Modern platforms (YouTube especially) frequently no longer serve
pre-muxed video+audio formats — most video-only streams need a separate
best-audio stream merged in via ffmpeg. `curate_video_formats` dedupes by
height (there are often 3-4 near-duplicate formats per resolution) and
`format_selector_for` decides whether the chosen format needs `+bestaudio`.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.downloader.metadata import FormatOption

CALLBACK_PREFIX = "dlfmt"
MAX_QUALITY_OPTIONS = 6


def _human_size(num_bytes: int | None) -> str:
    if not num_bytes:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.0f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}TB"


def _codec_compat_priority(vcodec: str | None) -> int:
    """Lower is more compatible. H.264 (avc1) muxes into MP4 cleanly and
    plays everywhere; VP9/AV1 remuxed into MP4 (not re-encoded) is valid
    per spec but several real players — including, confirmed live, the
    Telegram desktop client on macOS — render it as a black screen with
    audio only. Preferring avc1 avoids that without the cost of a real
    re-encode.
    """
    if not vcodec:
        return 2
    vcodec = vcodec.lower()
    if vcodec.startswith("avc1") or vcodec.startswith("h264"):
        return 0
    return 1


def curate_video_formats(
    formats: list[FormatOption], *, max_bytes: int | None = None
) -> list[FormatOption]:
    """Pick the single best format per resolution: prefer H.264 (avc1) for
    playback compatibility, then the largest file at that resolution.

    `max_bytes`, when given, drops any format whose *known* size already
    exceeds it - rejecting an oversized quality before the user can even
    pick it, rather than downloading it first and failing afterward. A
    format with no reported size is kept (yt-dlp's own `--max-filesize`
    and the post-download check remain the safety net for that case).
    """
    best_by_height: dict[int, FormatOption] = {}
    for fmt in formats:
        if not fmt.has_video or fmt.height is None:
            continue
        if max_bytes is not None and fmt.filesize_bytes and fmt.filesize_bytes > max_bytes:
            continue
        current = best_by_height.get(fmt.height)
        if current is None:
            best_by_height[fmt.height] = fmt
            continue

        current_priority = _codec_compat_priority(current.vcodec)
        fmt_priority = _codec_compat_priority(fmt.vcodec)
        if fmt_priority < current_priority or (
            fmt_priority == current_priority
            and (fmt.filesize_bytes or 0) > (current.filesize_bytes or 0)
        ):
            best_by_height[fmt.height] = fmt

    ordered = sorted(best_by_height.values(), key=lambda f: f.height or 0, reverse=True)
    return ordered[:MAX_QUALITY_OPTIONS]


def format_selector_for(fmt: FormatOption) -> str:
    """The yt-dlp format-selector string to actually request this quality."""
    return format_selector_for_id(fmt.format_id, fmt.has_audio)


def format_selector_for_id(format_id: str, has_audio: bool) -> str:
    """Same as `format_selector_for`, but from the bare fields worth
    round-tripping through FSM state (we don't need to carry the whole
    `FormatOption` across the probe -> callback boundary).
    """
    return format_id if has_audio else f"{format_id}+bestaudio"


def build_quality_keyboard(formats: list[FormatOption]) -> InlineKeyboardMarkup:
    curated = curate_video_formats(formats)
    rows = []
    for fmt in curated:
        label = f"{fmt.height}p"
        size = _human_size(fmt.filesize_bytes)
        if size:
            label += f" · ~{size}"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"{CALLBACK_PREFIX}:{fmt.format_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)

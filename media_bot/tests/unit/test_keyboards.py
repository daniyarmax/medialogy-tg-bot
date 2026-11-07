from app.bot.keyboards.audio_format_keyboard import (
    AUDIO_FORMATS,
    build_audio_format_keyboard,
    build_bitrate_keyboard,
    needs_bitrate_choice,
)
from app.bot.keyboards.main_menu import build_main_menu_keyboard
from app.bot.keyboards.quality_keyboard import (
    curate_video_formats,
    format_selector_for_id,
)
from app.downloader.metadata import FormatOption


def _fmt(**kwargs) -> FormatOption:
    defaults = dict(
        format_id="1", ext="mp4", height=None, resolution=None, filesize_bytes=None,
        vcodec=None, acodec=None, format_note=None,
    )
    defaults.update(kwargs)
    return FormatOption(**defaults)


def test_curate_video_formats_picks_largest_filesize_per_height() -> None:
    formats = [
        _fmt(format_id="a", height=720, filesize_bytes=1000, vcodec="avc1"),
        _fmt(format_id="b", height=720, filesize_bytes=5000, vcodec="avc1"),
        _fmt(format_id="c", height=480, filesize_bytes=800, vcodec="avc1"),
    ]
    curated = curate_video_formats(formats)

    by_height = {f.height: f.format_id for f in curated}
    assert by_height[720] == "b"
    assert by_height[480] == "c"


def test_curate_video_formats_prefers_avc1_over_vp9_even_if_smaller() -> None:
    # Live-verified bug: a VP9 stream remuxed (not re-encoded) into MP4
    # played as audio-only/black-screen on a real Telegram desktop client.
    # avc1 (H.264) must win even when the VP9 alternative has a larger file.
    formats = [
        _fmt(format_id="244", height=480, filesize_bytes=20_000_000, vcodec="vp9"),
        _fmt(format_id="135", height=480, filesize_bytes=8_000_000, vcodec="avc1.4d401f"),
    ]
    curated = curate_video_formats(formats)
    assert len(curated) == 1
    assert curated[0].format_id == "135"


def test_curate_video_formats_falls_back_to_vp9_when_no_avc1_available() -> None:
    formats = [
        _fmt(format_id="244", height=480, filesize_bytes=20_000_000, vcodec="vp9"),
        _fmt(format_id="243", height=360, filesize_bytes=10_000_000, vcodec="vp9"),
    ]
    curated = curate_video_formats(formats)
    assert {f.format_id for f in curated} == {"244", "243"}


def test_curate_video_formats_excludes_audio_only_and_unknown_height() -> None:
    formats = [
        _fmt(format_id="audio", height=None, vcodec="none", acodec="aac"),
        _fmt(format_id="video", height=360, vcodec="avc1"),
    ]
    curated = curate_video_formats(formats)
    assert [f.format_id for f in curated] == ["video"]


def test_curate_video_formats_sorts_descending_and_caps_length() -> None:
    formats = [_fmt(format_id=str(h), height=h, vcodec="avc1") for h in range(100, 100 + 10 * 100, 100)]
    curated = curate_video_formats(formats)
    heights = [f.height for f in curated]
    assert heights == sorted(heights, reverse=True)
    assert len(curated) <= 6


def test_format_selector_for_id_appends_bestaudio_for_video_only() -> None:
    assert format_selector_for_id("134", has_audio=False) == "134+bestaudio"


def test_format_selector_for_id_uses_bare_id_when_muxed() -> None:
    assert format_selector_for_id("18", has_audio=True) == "18"


def test_build_main_menu_keyboard_has_expected_buttons() -> None:
    keyboard = build_main_menu_keyboard()
    all_text = {btn.text for row in keyboard.keyboard for btn in row}
    assert all_text == {
        "🎬 Download Video",
        "🎵 Extract Audio",
        "📁 My Downloads",
        "⚙️ Settings",
        "❓ Help",
    }


def test_build_audio_format_keyboard_covers_all_formats() -> None:
    keyboard = build_audio_format_keyboard()
    callback_data = {btn.callback_data for row in keyboard.inline_keyboard for btn in row}
    assert callback_data == {f"audiofmt:{fmt}" for fmt in AUDIO_FORMATS}


def test_needs_bitrate_choice_true_for_lossy_false_for_lossless() -> None:
    assert needs_bitrate_choice("mp3") is True
    assert needs_bitrate_choice("wav") is False
    assert needs_bitrate_choice("flac") is False


def test_build_bitrate_keyboard_empty_for_lossless_format() -> None:
    keyboard = build_bitrate_keyboard("wav")
    assert keyboard.inline_keyboard == []


def test_build_bitrate_keyboard_has_options_for_mp3() -> None:
    keyboard = build_bitrate_keyboard("mp3")
    labels = {btn.text for row in keyboard.inline_keyboard for btn in row}
    assert "320 kbps" in labels

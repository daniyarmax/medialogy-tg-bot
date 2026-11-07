from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

FORMAT_CALLBACK_PREFIX = "audiofmt"
BITRATE_CALLBACK_PREFIX = "audiobr"

AUDIO_FORMATS: tuple[str, ...] = ("mp3", "wav", "m4a", "flac", "opus")

# Bitrate only makes sense for lossy formats; wav/flac skip straight to extraction.
_LOSSY_BITRATE_OPTIONS_KBPS: dict[str, tuple[int, ...]] = {
    "mp3": (128, 192, 320),
    "m4a": (128, 192, 256),
    "opus": (64, 96, 128),
}


def build_audio_format_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=fmt.upper(), callback_data=f"{FORMAT_CALLBACK_PREFIX}:{fmt}")]
        for fmt in AUDIO_FORMATS
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def needs_bitrate_choice(target_format: str) -> bool:
    return target_format in _LOSSY_BITRATE_OPTIONS_KBPS


def build_bitrate_keyboard(target_format: str) -> InlineKeyboardMarkup:
    options = _LOSSY_BITRATE_OPTIONS_KBPS.get(target_format, ())
    rows = [
        [
            InlineKeyboardButton(
                text=f"{kbps} kbps", callback_data=f"{BITRATE_CALLBACK_PREFIX}:{kbps}"
            )
        ]
        for kbps in options
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

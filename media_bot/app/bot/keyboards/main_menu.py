from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_DOWNLOAD_VIDEO = "🎬 Download Video"
BTN_EXTRACT_AUDIO = "🎵 Extract Audio"
BTN_MY_DOWNLOADS = "📁 My Downloads"
BTN_SETTINGS = "⚙️ Settings"
BTN_HELP = "❓ Help"


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_DOWNLOAD_VIDEO), KeyboardButton(text=BTN_EXTRACT_AUDIO)],
            [KeyboardButton(text=BTN_MY_DOWNLOADS), KeyboardButton(text=BTN_SETTINGS)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )

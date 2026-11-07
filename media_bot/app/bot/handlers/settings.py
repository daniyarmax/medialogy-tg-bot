from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards.audio_format_keyboard import AUDIO_FORMATS
from app.bot.keyboards.main_menu import BTN_SETTINGS

router = Router(name="settings")

SETTINGS_FORMAT_CALLBACK_PREFIX = "setaudiofmt"


def _settings_format_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=fmt.upper(), callback_data=f"{SETTINGS_FORMAT_CALLBACK_PREFIX}:{fmt}"
            )
        ]
        for fmt in AUDIO_FORMATS
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_settings(message: Message, user_repo) -> None:
    user = await user_repo.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )
    text = (
        "<b>Your settings</b>\n\n"
        f"Default audio format: <b>{user.default_audio_format.upper()}</b>\n"
        f"Default audio bitrate: <b>{user.default_audio_bitrate}</b>\n\n"
        "Tap a format below to change your default:"
    )
    await message.answer(text, reply_markup=_settings_format_keyboard())


@router.message(Command("settings"))
async def cmd_settings(message: Message, user_repo) -> None:
    await _show_settings(message, user_repo)


@router.message(F.text == BTN_SETTINGS)
async def settings_button(message: Message, user_repo) -> None:
    await _show_settings(message, user_repo)


@router.callback_query(F.data.startswith(f"{SETTINGS_FORMAT_CALLBACK_PREFIX}:"))
async def set_default_audio_format(callback: CallbackQuery, user_repo) -> None:
    assert callback.data is not None and callback.message is not None
    fmt = callback.data.split(":", 1)[1]
    user = await user_repo.get_or_create(callback.from_user.id)
    user.default_audio_format = fmt
    await callback.answer(f"Default audio format set to {fmt.upper()}.")
    await callback.message.edit_text(f"Default audio format is now <b>{fmt.upper()}</b>.")

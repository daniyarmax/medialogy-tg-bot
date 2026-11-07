from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards.main_menu import BTN_HELP, build_main_menu_keyboard

router = Router(name="start")

WELCOME_TEXT = (
    "<b>Media Downloader Bot</b>\n\n"
    "Send me a video link (YouTube, Instagram, TikTok, Facebook, X, Reddit) to "
    "download it, or use the menu below."
)

HELP_TEXT = (
    "<b>How to use this bot</b>\n\n"
    "🎬 <b>Download Video</b> — send a link, pick a quality, get the video.\n"
    "🎵 <b>Extract Audio</b> — send a link or a video/audio file, pick a format, "
    "get the audio.\n"
    "📁 <b>My Downloads</b> — see your recent downloads.\n"
    "⚙️ <b>Settings</b> — change your default format/bitrate.\n\n"
    "Commands: /start /help /settings /status /cancel"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=build_main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(F.text == BTN_HELP)
async def help_button(message: Message) -> None:
    await message.answer(HELP_TEXT)

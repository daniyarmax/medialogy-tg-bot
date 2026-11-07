import asyncio
import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis

from app.bot.keyboards.main_menu import BTN_DOWNLOAD_VIDEO
from app.bot.keyboards.quality_keyboard import (
    CALLBACK_PREFIX,
    build_quality_keyboard,
    curate_video_formats,
    format_selector_for_id,
)
from app.bot.progress_poller import poll_task_progress
from app.bot.states.flows import DownloadFlow
from app.core.config import get_settings
from app.core.exceptions import DurationExceededError, MediaBotError
from app.database.models import TaskOperation
from app.downloader.metadata import probe_metadata
from app.services.task_service import admit_and_create_task
from app.workers.celery_app import celery_app

router = Router(name="download")

_URL_PATTERN = re.compile(r"^https?://\S+$")


@router.message(F.text == BTN_DOWNLOAD_VIDEO)
async def start_download_flow(message: Message, state: FSMContext) -> None:
    await state.set_state(DownloadFlow.waiting_for_url)
    await message.answer("Send me a video link to download.")


@router.message(DownloadFlow.waiting_for_url)
@router.message(StateFilter(None), F.text.regexp(_URL_PATTERN))
async def receive_download_url(message: Message, state: FSMContext) -> None:
    """Handles a link either after the user pressed "Download Video" (FSM
    state set) or pasted directly with no prior state — people naturally
    paste a link first and expect it to just work, so a bare URL in the
    default state is treated the same as pressing the button first.
    """
    url = (message.text or "").strip()
    status_msg = await message.answer("🔎 Looking up that link...")

    try:
        meta = await probe_metadata(url)
        settings = get_settings()
        if meta.duration_seconds and meta.duration_seconds > settings.limits.max_duration_seconds:
            raise DurationExceededError(
                f"{meta.duration_seconds}s exceeds the {settings.limits.max_duration_seconds}s limit"
            )
    except MediaBotError as exc:
        await status_msg.edit_text(exc.user_message)
        return

    curated = curate_video_formats(meta.formats)
    if not curated:
        await status_msg.edit_text("I couldn't find any downloadable video formats for that link.")
        return

    await state.update_data(
        url=url,
        title=meta.title,
        platform=meta.platform.value,
        formats={f.format_id: f.has_audio for f in curated},
    )
    await state.set_state(DownloadFlow.choosing_quality)

    duration_text = f"{meta.duration_seconds}s" if meta.duration_seconds else "unknown"
    info_text = f"<b>{meta.title}</b>\nDuration: {duration_text}\n\nChoose a quality:"
    await status_msg.edit_text(info_text, reply_markup=build_quality_keyboard(curated))


@router.callback_query(DownloadFlow.choosing_quality, F.data.startswith(f"{CALLBACK_PREFIX}:"))
async def choose_quality(
    callback: CallbackQuery, state: FSMContext, user_repo, task_repo, redis: Redis
) -> None:
    assert callback.data is not None and callback.message is not None
    format_id = callback.data.split(":", 1)[1]
    data = await state.get_data()
    has_audio = data.get("formats", {}).get(format_id)

    if has_audio is None:
        await callback.answer("That option expired — please send the link again.", show_alert=True)
        return

    format_selector = format_selector_for_id(format_id, has_audio)

    try:
        task = await admit_and_create_task(
            user_repo=user_repo,
            task_repo=task_repo,
            telegram_user_id=callback.from_user.id,
            operation=TaskOperation.download_video,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            source_url=data["url"],
            platform=data.get("platform"),
            requested_format=format_selector,
        )
    except MediaBotError as exc:
        await callback.answer()
        await callback.message.edit_text(exc.user_message)
        await state.clear()
        return

    task.celery_task_id = str(task.id)
    # Commit before dispatching: the worker picks this up on its own DB
    # connection almost immediately, and under READ COMMITTED it can't see
    # a row this session hasn't committed yet - dispatching first caused a
    # real race where the task ran and found no matching row.
    await task_repo.session.commit()
    celery_app.send_task("tasks.download_video", args=[str(task.id)], task_id=str(task.id))

    await callback.answer("Queued!")
    await callback.message.edit_text(f"🎬 Downloading <b>{data['title']}</b>...")
    asyncio.create_task(
        poll_task_progress(
            callback.bot, callback.message.chat.id, callback.message.message_id, str(task.id), redis
        )
    )
    await state.clear()

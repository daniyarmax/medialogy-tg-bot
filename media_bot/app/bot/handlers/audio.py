import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis

from app.bot.keyboards.audio_format_keyboard import (
    BITRATE_CALLBACK_PREFIX,
    FORMAT_CALLBACK_PREFIX,
    AUDIO_FORMATS,
    build_audio_format_keyboard,
    build_bitrate_keyboard,
    needs_bitrate_choice,
)
from app.bot.keyboards.main_menu import BTN_EXTRACT_AUDIO
from app.bot.progress_poller import poll_task_progress
from app.bot.states.flows import AudioFlow
from app.core.config import get_settings
from app.core.exceptions import DurationExceededError, MediaBotError
from app.core.limits import duration_exceeded_message, file_too_large_message
from app.core.security import escape_html
from app.database.models import TaskOperation
from app.downloader.metadata import probe_metadata
from app.services.task_service import admit_and_create_task
from app.workers.celery_app import celery_app

router = Router(name="audio")


@router.message(F.text == BTN_EXTRACT_AUDIO)
async def start_audio_flow(message: Message, state: FSMContext) -> None:
    await state.set_state(AudioFlow.waiting_for_source)
    await message.answer("Send me a video/audio link, or a video/audio file directly.")


@router.message(AudioFlow.waiting_for_source, F.text)
async def receive_audio_url(message: Message, state: FSMContext) -> None:
    url = (message.text or "").strip()
    status_msg = await message.answer("🔎 Looking up that link...")

    try:
        meta = await probe_metadata(url)
        settings = get_settings()
        if meta.duration_seconds and meta.duration_seconds > settings.limits.max_duration_seconds:
            raise DurationExceededError(
                user_message=duration_exceeded_message(
                    meta.duration_seconds, settings.limits.max_duration_seconds
                )
            )
    except MediaBotError as exc:
        await status_msg.edit_text(exc.user_message)
        return

    await state.update_data(title=meta.title, source_url=url, platform=meta.platform.value, source_file_id=None)
    await state.set_state(AudioFlow.choosing_format)
    await status_msg.edit_text(
        f"<b>{escape_html(meta.title)}</b>\n\nChoose an audio format:",
        reply_markup=build_audio_format_keyboard(),
    )


@router.message(AudioFlow.waiting_for_source, F.video | F.audio | F.document)
async def receive_audio_file(message: Message, state: FSMContext) -> None:
    media = message.video or message.audio or message.document
    assert media is not None
    duration = getattr(media, "duration", None)
    file_size = getattr(media, "file_size", None)

    settings = get_settings()
    if duration and duration > settings.limits.max_duration_seconds:
        await message.answer(duration_exceeded_message(duration, settings.limits.max_duration_seconds))
        return

    bot_limits = getattr(message.bot, "media_bot_limits", None)
    if bot_limits is not None and bot_limits.max_download_bytes is not None and file_size:
        if file_size > bot_limits.max_download_bytes:
            await message.answer(file_too_large_message(file_size, bot_limits.max_download_bytes))
            return

    # file_name is fully user-controlled (whatever they named the file on
    # their own device) - truncate it and escape it for display like any
    # other untrusted text going into an HTML-parse-mode message.
    title = (getattr(media, "file_name", None) or "Uploaded file")[:200]
    await state.update_data(title=title, source_url=None, source_file_id=media.file_id, platform=None)
    await state.set_state(AudioFlow.choosing_format)
    await message.answer(
        f"<b>{escape_html(title)}</b>\n\nChoose an audio format:",
        reply_markup=build_audio_format_keyboard(),
    )


@router.callback_query(AudioFlow.choosing_format, F.data.startswith(f"{FORMAT_CALLBACK_PREFIX}:"))
async def choose_audio_format(
    callback: CallbackQuery, state: FSMContext, user_repo, task_repo, redis: Redis
) -> None:
    assert callback.data is not None and callback.message is not None
    target_format = callback.data.split(":", 1)[1]
    if target_format not in AUDIO_FORMATS:
        await callback.answer("Unknown format.", show_alert=True)
        return

    if needs_bitrate_choice(target_format):
        await state.update_data(target_format=target_format)
        await state.set_state(AudioFlow.choosing_bitrate)
        await callback.answer()
        await callback.message.edit_text(
            "Choose a bitrate:", reply_markup=build_bitrate_keyboard(target_format)
        )
        return

    await _finalize_audio_task(callback, state, user_repo, task_repo, redis, target_format, None)


@router.callback_query(AudioFlow.choosing_bitrate, F.data.startswith(f"{BITRATE_CALLBACK_PREFIX}:"))
async def choose_audio_bitrate(
    callback: CallbackQuery, state: FSMContext, user_repo, task_repo, redis: Redis
) -> None:
    assert callback.data is not None
    kbps = callback.data.split(":", 1)[1]
    data = await state.get_data()
    target_format = data.get("target_format")
    await _finalize_audio_task(
        callback, state, user_repo, task_repo, redis, target_format, f"{kbps}k"
    )


async def _finalize_audio_task(
    callback: CallbackQuery,
    state: FSMContext,
    user_repo,
    task_repo,
    redis: Redis,
    target_format: str | None,
    requested_bitrate: str | None,
) -> None:
    assert callback.message is not None
    data = await state.get_data()

    try:
        task = await admit_and_create_task(
            user_repo=user_repo,
            task_repo=task_repo,
            telegram_user_id=callback.from_user.id,
            operation=TaskOperation.extract_audio,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            source_url=data.get("source_url"),
            source_file_id=data.get("source_file_id"),
            platform=data.get("platform"),
            requested_format=target_format,
            requested_bitrate=requested_bitrate,
        )
    except MediaBotError as exc:
        await callback.answer()
        await callback.message.edit_text(exc.user_message)
        await state.clear()
        return

    task.celery_task_id = str(task.id)
    # Commit before dispatching - see the matching comment in
    # handlers/download.py for why (a real race was found here live).
    await task_repo.session.commit()
    celery_app.send_task("tasks.extract_audio", args=[str(task.id)], task_id=str(task.id))

    await callback.answer("Queued!")
    await callback.message.edit_text(
        f"🎵 Extracting audio from <b>{escape_html(data.get('title') or '')}</b>..."
    )
    asyncio.create_task(
        poll_task_progress(
            callback.bot, callback.message.chat.id, callback.message.message_id, str(task.id), redis
        )
    )
    await state.clear()

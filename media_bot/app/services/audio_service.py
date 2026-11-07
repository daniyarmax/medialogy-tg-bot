"""Orchestrates an extract_audio Task end to end: fetch the source (either
a yt-dlp download from a URL, or a direct download of a Telegram-sent
file), extract/convert the audio via ffmpeg, upload the result, record
history, and mark the Task Completed/Failed.
"""

import uuid
from datetime import UTC, datetime

from aiogram.types import FSInputFile

from app.bot.telegram_client import build_bot
from app.core.config import get_settings
from app.core.exceptions import FileTooLargeError, MediaBotError
from app.core.limits import file_too_large_message
from app.core.logging import get_logger
from app.database.models import DownloadHistory, TaskStatus
from app.database.repository import DownloadHistoryRepository, TaskRepository, UserRepository
from app.database.session import get_sessionmaker
from app.downloader.ytdlp_client import download as ytdlp_download
from app.processor.audio_extractor import extract_audio
from app.processor.ffmpeg import FFmpegProgress
from app.services.cleanup import remove_directory_tree
from app.services.disk_guard import check_disk_space
from app.services.progress_publisher import publish_progress, publish_terminal

logger = get_logger(__name__)


async def run_extract_audio_task(task_id: str) -> None:
    settings = get_settings()
    sessionmaker = get_sessionmaker()
    task_uuid = uuid.UUID(task_id)

    async with sessionmaker() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get(task_uuid)
        if task is None:
            logger.warning("audio_task_missing", task_id=task_id)
            return
        if task.status == TaskStatus.completed:
            logger.info("audio_task_already_completed", task_id=task_id)
            return

        user = await UserRepository(session).get(task.user_id)
        source_url = task.source_url
        source_file_id = task.source_file_id
        target_format = task.requested_format or "mp3"
        requested_bitrate = task.requested_bitrate
        await task_repo.set_status(task_uuid, TaskStatus.downloading, started_at=datetime.now(UTC))
        await session.commit()

    assert user is not None

    work_dir = settings.storage.temp_dir / task_id
    work_dir.mkdir(parents=True, exist_ok=True)
    bot, limits = build_bot(settings)

    try:
        check_disk_space(work_dir)

        if source_url:
            def on_download_progress(update) -> None:
                publish_progress(
                    task_id,
                    stage="Downloading",
                    percent=update.percent,
                    speed_bytes_per_sec=update.speed_bytes_per_sec,
                    eta_seconds=update.eta_seconds,
                )

            source_path = await ytdlp_download(
                source_url,
                format_selector="bestaudio/best",
                dest_dir=work_dir,
                video_id=f"{task_id}-src",
                max_filesize_mb=settings.limits.max_file_size_mb,
                progress_cb=on_download_progress,
            )
        else:
            assert source_file_id is not None
            publish_progress(task_id, stage="Downloading", percent=0)
            source_path = work_dir / f"{task_id}-src"
            await bot.download(source_file_id, destination=source_path)

        async with sessionmaker() as session:
            await TaskRepository(session).set_status(task_uuid, TaskStatus.processing)
            await session.commit()

        # Now the actual source size is known - check again with real
        # headroom (source + output could briefly coexist on disk).
        check_disk_space(work_dir, source_path.stat().st_size * 2)

        bitrate_kbps = int(requested_bitrate.rstrip("k")) if requested_bitrate else None
        dest_path = work_dir / f"{task_id}.{target_format}"

        def on_ffmpeg_progress(update: FFmpegProgress) -> None:
            publish_progress(task_id, stage="Processing", percent=update.percent)

        result_path = await extract_audio(
            source_path,
            target_format=target_format,
            dest=dest_path,
            bitrate_kbps=bitrate_kbps,
            timeout_seconds=settings.limits.max_processing_time_seconds,
            progress_cb=on_ffmpeg_progress,
        )

        file_size = result_path.stat().st_size
        if file_size > limits.max_upload_bytes:
            raise FileTooLargeError(
                user_message=file_too_large_message(file_size, limits.max_upload_bytes)
            )

        async with sessionmaker() as session:
            await TaskRepository(session).set_status(task_uuid, TaskStatus.uploading)
            await session.commit()
        publish_progress(task_id, stage="Uploading", percent=0)

        chat_id = user.telegram_user_id
        sent = await bot.send_audio(chat_id=chat_id, audio=FSInputFile(result_path))

        async with sessionmaker() as session:
            task_repo = TaskRepository(session)
            await task_repo.set_status(
                task_uuid,
                TaskStatus.completed,
                completed_at=datetime.now(UTC),
                result_file_path=str(result_path),
                result_file_size_bytes=file_size,
            )
            await DownloadHistoryRepository(session).create(
                DownloadHistory(
                    user_id=task.user_id,
                    task_id=task_uuid,
                    title=f"Audio ({target_format})",
                    platform=task.platform,
                    operation=task.operation,
                    output_format=target_format,
                    file_size_bytes=file_size,
                    storage_path=str(result_path),
                    telegram_file_id=sent.audio.file_id if sent.audio else None,
                )
            )
            await session.commit()

        publish_terminal(task_id, "Completed")

    except MediaBotError as exc:
        async with sessionmaker() as session:
            await TaskRepository(session).set_status(
                task_uuid, TaskStatus.failed, error_message=exc.user_message
            )
            await session.commit()
        publish_terminal(task_id, "Failed", error_message=exc.user_message)
        try:
            await bot.send_message(chat_id=user.telegram_user_id, text=f"❌ {exc.user_message}")
        except Exception:
            logger.exception("failed_to_notify_user_of_failure", task_id=task_id)
        raise

    finally:
        remove_directory_tree(work_dir)
        await bot.session.close()

"""Orchestrates a download_video Task end to end: download via yt-dlp,
upload the result to Telegram, record history, and mark the Task
Completed/Failed. This is what actually executes a Task that
`task_service.admit_and_create_task` created and a Celery task dispatched
— it runs inside the Celery worker process (bridged via `run_async`), not
the bot's long-polling process.
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
from app.downloader.ytdlp_client import ProgressUpdate, download as ytdlp_download
from app.processor import media_info
from app.services.cleanup import remove_directory_tree
from app.services.disk_guard import check_disk_space
from app.services.progress_publisher import publish_progress, publish_terminal

logger = get_logger(__name__)


async def run_download_video_task(task_id: str) -> None:
    settings = get_settings()
    sessionmaker = get_sessionmaker()
    task_uuid = uuid.UUID(task_id)

    async with sessionmaker() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get(task_uuid)
        if task is None:
            logger.warning("download_task_missing", task_id=task_id)
            return
        if task.status in (TaskStatus.completed, TaskStatus.cancelled):
            # Idempotency: either a previous attempt already finished but
            # its ack was lost (worker crash) and the broker redelivered
            # the task, or the user cancelled it after it was re-queued by
            # reconciliation but before a worker picked the message back
            # up - either way, don't resurrect it. (Deliberately excludes
            # Failed: Celery's own autoretry re-runs this exact function
            # after setting status to Failed, so skipping on Failed would
            # break legitimate retries.)
            logger.info("download_task_already_terminal", task_id=task_id, status=task.status.value)
            return

        user = await UserRepository(session).get(task.user_id)
        source_url = task.source_url
        format_selector = task.requested_format or "best"
        await task_repo.set_status(task_uuid, TaskStatus.downloading, started_at=datetime.now(UTC))
        await session.commit()

    assert user is not None and source_url is not None

    work_dir = settings.storage.downloads_dir / task_id
    bot, limits = build_bot(settings)

    try:
        # Loose pre-flight check: we don't know the exact output size yet
        # (that's the whole point of downloading), so this just guards
        # against starting work with almost no free space at all.
        check_disk_space(work_dir)

        def on_progress(update: ProgressUpdate) -> None:
            publish_progress(
                task_id,
                stage="Downloading",
                percent=update.percent,
                speed_bytes_per_sec=update.speed_bytes_per_sec,
                eta_seconds=update.eta_seconds,
            )

        result_path = await ytdlp_download(
            source_url,
            format_selector=format_selector,
            dest_dir=work_dir,
            video_id=task_id,
            max_filesize_mb=settings.limits.max_file_size_mb,
            progress_cb=on_progress,
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

        # Telegram's player renders the preview as a square unless told the
        # actual dimensions up front - probe the real merged file rather
        # than trust the originally-selected format's reported size, since
        # the merge/remux is the actual thing being uploaded.
        probed = await media_info.probe(result_path)
        video_width = probed.video.width if probed.video else None
        video_height = probed.video.height if probed.video else None
        video_duration = int(probed.duration_seconds) if probed.duration_seconds else None
        logger.info(
            "sending_video_to_telegram",
            task_id=task_id,
            width=video_width,
            height=video_height,
            duration=video_duration,
            file_size_bytes=file_size,
        )

        chat_id = user.telegram_user_id
        sent = await bot.send_video(
            chat_id=chat_id,
            video=FSInputFile(result_path),
            width=video_width,
            height=video_height,
            duration=video_duration,
            supports_streaming=True,
        )

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
                    title=task.platform,
                    platform=task.platform,
                    operation=task.operation,
                    output_format=result_path.suffix.lstrip("."),
                    file_size_bytes=file_size,
                    storage_path=str(result_path),
                    telegram_file_id=sent.video.file_id if sent.video else None,
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

"""Celery task bodies. Each task is a thin sync wrapper (Celery's own
entry-point requirement) around the real `async def` orchestration in
`app.services.*`, bridged via `run_async` — this keeps the actual
download/processing logic independently testable without Celery running
at all (see `tests/integration/test_celery_tasks.py`).
"""

import time
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.exceptions import DownloadFailedError, FFmpegError, NetworkTimeoutError
from app.core.logging import get_logger
from app.database.models import TaskOperation, TaskStatus
from app.database.repository import TaskRepository
from app.database.session import get_sessionmaker, run_async
from app.services import audio_service, download_service
from app.services.cleanup import remove_directory_tree
from app.workers.celery_app import celery_app

logger = get_logger(__name__)
settings = get_settings()


@celery_app.task(name="tasks.probe_metadata", queue="downloads", time_limit=30)
def probe_metadata_task(url: str) -> dict:
    from app.downloader.metadata import probe_metadata as _probe

    async def _run() -> dict:
        meta = await _probe(url)
        return {
            "video_id": meta.video_id,
            "title": meta.title,
            "platform": meta.platform.value,
            "duration_seconds": meta.duration_seconds,
        }

    return run_async(_run)


@celery_app.task(
    name="tasks.download_video",
    bind=True,
    queue="downloads",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(DownloadFailedError, NetworkTimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=4,
    soft_time_limit=settings.limits.max_processing_time_seconds,
    time_limit=settings.limits.max_processing_time_seconds + 30,
)
def download_video_task(self, task_id: str) -> None:
    run_async(download_service.run_download_video_task, task_id)


@celery_app.task(
    name="tasks.extract_audio",
    bind=True,
    queue="processing",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(FFmpegError, DownloadFailedError, NetworkTimeoutError),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=2,
    soft_time_limit=settings.limits.max_processing_time_seconds,
    time_limit=settings.limits.max_processing_time_seconds + 30,
)
def extract_audio_task(self, task_id: str) -> None:
    run_async(audio_service.run_extract_audio_task, task_id)


@celery_app.task(name="tasks.cleanup_temp", queue="maintenance")
def cleanup_temp_task() -> dict:
    """Backstop sweep for anything a crashed task's own `finally` never
    got to run — each task already cleans up its own directory on
    success/failure; this just catches what's left behind.
    """
    cutoff = time.time() - settings.storage.temp_file_ttl_hours * 3600
    removed = 0
    for base in (settings.storage.temp_dir, settings.storage.downloads_dir):
        if not base.exists():
            continue
        for entry in base.iterdir():
            try:
                if entry.stat().st_mtime < cutoff:
                    if entry.is_dir():
                        remove_directory_tree(entry)
                    else:
                        entry.unlink()
                    removed += 1
            except OSError:
                continue
    return {"removed": removed}


async def reconcile_stale_tasks_async() -> dict:
    """Scans Postgres directly (independent of Celery/broker state) for
    tasks stuck mid-stage whose `updated_at` hasn't moved — catches both a
    worker that died without triggering acks_late redelivery, and a task
    that got created in Postgres but never actually made it to Celery
    (e.g. a transient Redis outage at enqueue time).
    """
    sessionmaker = get_sessionmaker()
    threshold = datetime.now(UTC) - timedelta(
        seconds=settings.limits.max_processing_time_seconds
    )
    reenqueued, failed = 0, 0
    to_dispatch: list[tuple[str, str]] = []

    async with sessionmaker() as session:
        repo = TaskRepository(session)
        stale = await repo.find_stale(threshold)
        for task in stale:
            if task.retry_count >= task.max_retries:
                await repo.set_status(
                    task.id,
                    TaskStatus.failed,
                    error_message="Worker restart or timeout - task lost, retries exhausted.",
                )
                failed += 1
            else:
                task.retry_count += 1
                task.celery_task_id = str(task.id)
                await repo.set_status(
                    task.id, TaskStatus.pending, stage_detail="Re-queued after reconciliation"
                )
                reenqueued += 1
                task_name = (
                    "tasks.download_video"
                    if task.operation == TaskOperation.download_video
                    else "tasks.extract_audio"
                )
                to_dispatch.append((task_name, str(task.id)))
        await session.commit()

    for task_name, task_id in to_dispatch:
        celery_app.send_task(task_name, args=[task_id], task_id=task_id)

    return {"reenqueued": reenqueued, "failed": failed}


@celery_app.task(name="tasks.reconcile_stale_tasks", queue="maintenance")
def reconcile_stale_tasks() -> dict:
    return run_async(reconcile_stale_tasks_async)

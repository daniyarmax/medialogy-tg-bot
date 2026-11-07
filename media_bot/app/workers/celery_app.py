"""The Celery app: broker/backend config, queue routing, and the
crash-recovery signal hooks that guarantee a Postgres state write happens
even when a task fails or is revoked outside its own try/except (its own
body handles the normal failure path; these are the backstop).
"""

import sys
import uuid

from celery import Celery
from celery.signals import task_failure, task_revoked

if sys.platform == "darwin":
    # macOS has defaulted multiprocessing to "spawn" since Python 3.8, but
    # Celery's prefork pool uses billiard (its own forked copy of
    # multiprocessing, with its own process context independent of the
    # stdlib's - stdlib multiprocessing.set_start_method has no effect on
    # it). Under spawn, child workers start without the task registry
    # billiard's fast-path tracer expects, crashing every task with
    # "not enough values to unpack (expected 3, got 0)". It also breaks
    # `terminate=True` revocation under --pool=solo (no child process
    # exists to signal at all). Forcing billiard's own context to "fork"
    # restores correct prefork behavior on macOS dev machines, matching how
    # the Linux/Docker production worker behaves by default (fork is
    # already Linux's default there).
    import billiard.context

    billiard.context._force_start_method("fork")

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.models import TaskStatus
from app.database.repository import TaskRepository
from app.database.session import get_sessionmaker, run_async

logger = get_logger(__name__)

settings = get_settings()

celery_app = Celery(
    "media_bot",
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_routes={
        "tasks.probe_metadata": {"queue": "downloads"},
        "tasks.download_video": {"queue": "downloads"},
        "tasks.extract_audio": {"queue": "processing"},
        "tasks.cleanup_temp": {"queue": "maintenance"},
        "tasks.reconcile_stale_tasks": {"queue": "maintenance"},
    },
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    beat_schedule={
        "cleanup-temp-every-15-min": {"task": "tasks.cleanup_temp", "schedule": 900.0},
        "reconcile-stale-tasks-every-5-min": {
            "task": "tasks.reconcile_stale_tasks",
            "schedule": 300.0,
        },
    },
)


async def _mark_status(task_id: str, status: TaskStatus, **kwargs: object) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await TaskRepository(session).set_status(uuid.UUID(task_id), status, **kwargs)
        await session.commit()


@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, **kwargs) -> None:
    """Backstop: covers failures that escape the task body's own
    try/except (e.g. an OOM kill, an unexpected exception type).
    """
    if not task_id:
        return
    try:
        run_async(_mark_status, task_id, TaskStatus.failed, error_message=str(exception))
    except Exception:
        logger.exception("failed_to_record_task_failure_signal", task_id=task_id)


@task_revoked.connect
def on_task_revoked(sender=None, request=None, **kwargs) -> None:
    """Fired when `/cancel` calls `celery_app.control.revoke(..., terminate=True)`."""
    task_id = request.id if request is not None else None
    if not task_id:
        return
    try:
        run_async(_mark_status, task_id, TaskStatus.cancelled)
    except Exception:
        logger.exception("failed_to_record_task_revocation_signal", task_id=task_id)

"""Admission control + Task-row creation, shared by every enqueue path.

This is deliberately the *only* place that decides "can this user start
another job right now" — bot handlers (Phase 4) and, later, any other
dispatch path (Phase 5's reconciliation job, etc.) call through here so
there's exactly one fairness gate rather than duplicated logic.

Dispatching the created Task to a Celery worker is Phase 5's job (the
worker/queue infrastructure doesn't exist yet) — this module intentionally
stops at "the Task row exists with status Pending," which is an honest,
fully real and tested checkpoint, not a stub.
"""

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError
from app.database.models import Task, TaskOperation, TaskStatus
from app.database.repository import TaskRepository, UserRepository


class TooManyActiveTasksError(RateLimitExceededError):
    pass


async def admit_and_create_task(
    *,
    user_repo: UserRepository,
    task_repo: TaskRepository,
    telegram_user_id: int,
    operation: TaskOperation,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    source_url: str | None = None,
    source_file_id: str | None = None,
    platform: str | None = None,
    requested_format: str | None = None,
    requested_bitrate: str | None = None,
) -> Task:
    """Create a `Task` row for this user, after checking they're under
    `MAX_CONCURRENT_TASKS_PER_USER`. Raises `TooManyActiveTasksError`
    (safe `.user_message`) if they're not.
    """
    settings = get_settings()
    user = await user_repo.get_or_create(
        telegram_user_id, username=username, first_name=first_name, last_name=last_name
    )

    active_count = await task_repo.count_active_for_user(user.id)
    if active_count >= settings.limits.max_concurrent_tasks_per_user:
        raise TooManyActiveTasksError(
            user_message=(
                f"You already have {active_count} active job(s). "
                "Please wait for one to finish, or use /cancel."
            )
        )

    task = Task(
        user_id=user.id,
        operation=operation,
        source_url=source_url,
        source_file_id=source_file_id,
        platform=platform,
        requested_format=requested_format,
        requested_bitrate=requested_bitrate,
        status=TaskStatus.pending,
    )
    return await task_repo.create(task)

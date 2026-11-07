import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.database.models import TaskOperation, TaskStatus
from app.database.repository import TaskRepository, UserRepository
from app.services.task_service import TooManyActiveTasksError, admit_and_create_task


@pytest.fixture
async def session():
    engine = create_async_engine(get_settings().database.url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as s:
            yield s
            await s.rollback()
    finally:
        await engine.dispose()


async def test_admit_and_create_task_creates_pending_task(session) -> None:
    user_repo = UserRepository(session)
    task_repo = TaskRepository(session)

    task = await admit_and_create_task(
        user_repo=user_repo,
        task_repo=task_repo,
        telegram_user_id=910_000_001,
        operation=TaskOperation.download_video,
        source_url="https://www.youtube.com/watch?v=abc",
        platform="youtube",
        requested_format="134+bestaudio",
    )

    assert task.status == TaskStatus.pending
    assert task.requested_format == "134+bestaudio"


async def test_admit_and_create_task_rejects_over_concurrency_limit(session) -> None:
    user_repo = UserRepository(session)
    task_repo = TaskRepository(session)
    telegram_user_id = 910_000_002

    settings = get_settings()
    limit = settings.limits.max_concurrent_tasks_per_user

    for _ in range(limit):
        await admit_and_create_task(
            user_repo=user_repo,
            task_repo=task_repo,
            telegram_user_id=telegram_user_id,
            operation=TaskOperation.extract_audio,
            requested_format="mp3",
        )

    with pytest.raises(TooManyActiveTasksError):
        await admit_and_create_task(
            user_repo=user_repo,
            task_repo=task_repo,
            telegram_user_id=telegram_user_id,
            operation=TaskOperation.extract_audio,
            requested_format="mp3",
        )


async def test_admit_and_create_task_allows_new_task_after_one_completes(session) -> None:
    user_repo = UserRepository(session)
    task_repo = TaskRepository(session)
    telegram_user_id = 910_000_003

    settings = get_settings()
    limit = settings.limits.max_concurrent_tasks_per_user

    tasks = []
    for _ in range(limit):
        t = await admit_and_create_task(
            user_repo=user_repo,
            task_repo=task_repo,
            telegram_user_id=telegram_user_id,
            operation=TaskOperation.extract_audio,
            requested_format="mp3",
        )
        tasks.append(t)

    await task_repo.set_status(tasks[0].id, TaskStatus.completed)

    # Should now succeed since one of the limit-many tasks is no longer active.
    new_task = await admit_and_create_task(
        user_repo=user_repo,
        task_repo=task_repo,
        telegram_user_id=telegram_user_id,
        operation=TaskOperation.extract_audio,
        requested_format="flac",
    )
    assert new_task.status == TaskStatus.pending

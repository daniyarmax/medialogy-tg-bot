"""Integration tests against a real local Postgres (not mocked) — run via
`pytest tests/integration` with DATABASE_URL pointed at a real dev database.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.database.models import DownloadHistory, Task, TaskOperation, TaskStatus
from app.database.repository import DownloadHistoryRepository, TaskRepository, UserRepository


@pytest.fixture
async def session():
    # A dedicated engine per test (rather than the process-lifetime cached
    # singleton in app.database.session) because pytest-asyncio gives each
    # test function its own event loop by default, and asyncpg connections
    # are bound to the loop that opened them — reusing the global cached
    # engine across tests would reuse connections across loop boundaries.
    engine = create_async_engine(get_settings().database.url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as s:
            yield s
            await s.rollback()
    finally:
        await engine.dispose()


async def test_user_get_or_create_is_idempotent(session) -> None:
    repo = UserRepository(session)
    telegram_id = 900_000_001

    user1 = await repo.get_or_create(telegram_id, username="alice")
    user2 = await repo.get_or_create(telegram_id, username="alice-again")

    assert user1.id == user2.id
    assert user2.username == "alice"  # second call returns the existing row, doesn't overwrite


async def test_task_admission_control_counts_only_active_statuses(session) -> None:
    users = UserRepository(session)
    tasks = TaskRepository(session)
    user = await users.get_or_create(900_000_002, username="bob")

    active = Task(user_id=user.id, operation=TaskOperation.download_video, status=TaskStatus.downloading)
    done = Task(user_id=user.id, operation=TaskOperation.download_video, status=TaskStatus.completed)
    await tasks.create(active)
    await tasks.create(done)

    count = await tasks.count_active_for_user(user.id)
    assert count == 1


async def test_set_status_updates_fields(session) -> None:
    users = UserRepository(session)
    tasks = TaskRepository(session)
    user = await users.get_or_create(900_000_003, username="carol")

    task = await tasks.create(
        Task(user_id=user.id, operation=TaskOperation.extract_audio, status=TaskStatus.pending)
    )

    await tasks.set_status(
        task.id, TaskStatus.failed, error_message="boom", error_code="FFMPEG_ERROR"
    )

    refreshed = await tasks.get(task.id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.failed
    assert refreshed.error_message == "boom"


async def test_download_history_links_to_task(session) -> None:
    users = UserRepository(session)
    tasks = TaskRepository(session)
    history = DownloadHistoryRepository(session)
    user = await users.get_or_create(900_000_004, username="dave")

    task = await tasks.create(
        Task(user_id=user.id, operation=TaskOperation.extract_audio, status=TaskStatus.completed)
    )
    entry = await history.create(
        DownloadHistory(
            user_id=user.id,
            task_id=task.id,
            title="Some Podcast Episode",
            operation=TaskOperation.extract_audio,
            output_format="mp3",
        )
    )

    rows = await history.list_for_user(user.id)
    assert any(r.id == entry.id for r in rows)

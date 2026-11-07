"""Exercises the real orchestration logic behind the Celery tasks —
real yt-dlp, real ffmpeg, real Postgres state transitions — against the
actual service functions (`run_download_video_task` /
`run_extract_audio_task`), bypassing the Celery sync-wrapper layer itself
(calling it via `run_async` from inside an already-running pytest-asyncio
event loop isn't possible — nested `run_until_complete` on one thread's
loop isn't supported — and the wrapper is trivial boilerplate anyway).

Telegram delivery is the one thing mocked out: these tests must not spam
a real chat on every run. Everything upstream of that (download,
extraction, DB writes) is real.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.database.models import Task, TaskOperation, TaskStatus
from app.database.repository import DownloadHistoryRepository, TaskRepository, UserRepository
from app.database.session import get_engine, get_sessionmaker
from app.services import audio_service, download_service

# A real, short, public, legally-accessible video ("Me at the zoo") — the
# same fixture URL used for live Phase 2/3 verification.
_REAL_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


@pytest.fixture(autouse=True)
async def _isolate_global_db_singleton():
    """The service functions under test call `app.database.session.get_sessionmaker()`
    — a process-wide cached singleton whose pooled asyncpg connections are
    bound to whichever event loop was running when they were first opened.
    That's correct for production (one worker process = one persistent
    loop), but pytest-asyncio gives each test function its own loop, so the
    cache must be reset around each test or a later test reuses a prior
    test's now-invalid connections ("Future attached to a different loop").
    """
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    yield
    try:
        await get_engine().dispose()
    except Exception:
        pass
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


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


def _stub_bot():
    bot = AsyncMock()
    sent_video = AsyncMock()
    sent_video.video = AsyncMock(file_id="stub-video-file-id")
    bot.send_video.return_value = sent_video
    sent_audio = AsyncMock()
    sent_audio.audio = AsyncMock(file_id="stub-audio-file-id")
    bot.send_audio.return_value = sent_audio
    bot.session.close = AsyncMock()
    return bot


async def test_run_download_video_task_end_to_end(session, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_bot = _stub_bot()
    monkeypatch.setattr(
        download_service, "build_bot", lambda settings: (stub_bot, _fake_limits())
    )

    user_repo = UserRepository(session)
    task_repo = TaskRepository(session)
    user = await user_repo.get_or_create(920_000_001, username="celery_test_user")
    task = await task_repo.create(
        Task(
            user_id=user.id,
            operation=TaskOperation.download_video,
            source_url=_REAL_URL,
            platform="youtube",
            requested_format="160",  # tiny 192x144 mp4, no merge needed - fast
            status=TaskStatus.pending,
        )
    )
    await session.commit()
    task_id = str(task.id)

    await download_service.run_download_video_task(task_id)

    await session.refresh(task)
    refreshed = task
    assert refreshed is not None
    assert refreshed.status == TaskStatus.completed
    assert refreshed.result_file_path is not None

    stub_bot.send_video.assert_awaited_once()

    history = await DownloadHistoryRepository(session).list_for_user(user.id)
    assert any(h.task_id == task.id for h in history)


async def test_run_download_video_task_marks_failed_on_bad_format(
    session, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_bot = _stub_bot()
    monkeypatch.setattr(
        download_service, "build_bot", lambda settings: (stub_bot, _fake_limits())
    )

    user_repo = UserRepository(session)
    task_repo = TaskRepository(session)
    user = await user_repo.get_or_create(920_000_002, username="celery_test_user2")
    task = await task_repo.create(
        Task(
            user_id=user.id,
            operation=TaskOperation.download_video,
            source_url=_REAL_URL,
            platform="youtube",
            requested_format="nonexistent-format-id",
            status=TaskStatus.pending,
        )
    )
    await session.commit()
    task_id = str(task.id)

    with pytest.raises(Exception):
        await download_service.run_download_video_task(task_id)

    await session.refresh(task)
    refreshed = task
    assert refreshed is not None
    assert refreshed.status == TaskStatus.failed
    assert refreshed.error_message is not None
    stub_bot.send_video.assert_not_awaited()


async def test_run_extract_audio_task_end_to_end(session, monkeypatch: pytest.MonkeyPatch) -> None:
    stub_bot = _stub_bot()
    monkeypatch.setattr(audio_service, "build_bot", lambda settings: (stub_bot, _fake_limits()))

    user_repo = UserRepository(session)
    task_repo = TaskRepository(session)
    user = await user_repo.get_or_create(920_000_003, username="celery_test_user3")
    task = await task_repo.create(
        Task(
            user_id=user.id,
            operation=TaskOperation.extract_audio,
            source_url=_REAL_URL,
            platform="youtube",
            requested_format="mp3",
            requested_bitrate="128k",
            status=TaskStatus.pending,
        )
    )
    await session.commit()
    task_id = str(task.id)

    await audio_service.run_extract_audio_task(task_id)

    await session.refresh(task)
    refreshed = task
    assert refreshed is not None
    assert refreshed.status == TaskStatus.completed
    assert refreshed.result_file_path is not None
    assert refreshed.result_file_path.endswith(".mp3")

    stub_bot.send_audio.assert_awaited_once()


def _fake_limits():
    from app.bot.telegram_client import TelegramLimits

    return TelegramLimits(
        max_upload_bytes=50 * 1024 * 1024, max_download_bytes=20 * 1024 * 1024,
        supports_local_paths=False,
    )

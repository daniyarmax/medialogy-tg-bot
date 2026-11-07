from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import status as status_handlers
from app.database.models import DownloadHistory, Task, TaskOperation, TaskStatus


def _fake_message(user_id: int = 1):
    answered = []

    async def _answer(text: str, **kwargs) -> None:
        answered.append(text)

    return SimpleNamespace(answer=_answer, _answered=answered, from_user=SimpleNamespace(id=user_id))


async def test_cmd_status_with_no_user_reports_no_tasks() -> None:
    user_repo = AsyncMock()
    user_repo.get_by_telegram_id.return_value = None
    task_repo = AsyncMock()
    message = _fake_message()

    await status_handlers.cmd_status(message, task_repo, user_repo)

    assert "don't have any tasks" in message._answered[0]
    task_repo.list_active_for_user.assert_not_called()


async def test_cmd_status_lists_active_tasks() -> None:
    user_repo = AsyncMock()
    user_repo.get_by_telegram_id.return_value = SimpleNamespace(id=42)
    task_repo = AsyncMock()
    task_repo.list_active_for_user.return_value = [
        Task(
            id="11111111-1111-1111-1111-111111111111",
            user_id=42,
            operation=TaskOperation.download_video,
            requested_format="134+bestaudio",
            status=TaskStatus.downloading,
        )
    ]
    message = _fake_message()

    await status_handlers.cmd_status(message, task_repo, user_repo)

    assert "download_video" in message._answered[0]
    assert "Downloading" in message._answered[0]


async def test_cmd_cancel_with_no_active_tasks() -> None:
    user_repo = AsyncMock()
    user_repo.get_by_telegram_id.return_value = SimpleNamespace(id=42)
    task_repo = AsyncMock()
    task_repo.list_active_for_user.return_value = []
    message = _fake_message()

    await status_handlers.cmd_cancel(message, task_repo, user_repo)

    assert "don't have any active tasks" in message._answered[0]
    task_repo.set_status.assert_not_called()


async def test_cmd_cancel_cancels_most_recent_active_task() -> None:
    user_repo = AsyncMock()
    user_repo.get_by_telegram_id.return_value = SimpleNamespace(id=42)
    task_repo = AsyncMock()
    task_id = "22222222-2222-2222-2222-222222222222"
    task_repo.list_active_for_user.return_value = [
        Task(id=task_id, user_id=42, operation=TaskOperation.extract_audio, status=TaskStatus.pending)
    ]
    message = _fake_message()

    await status_handlers.cmd_cancel(message, task_repo, user_repo)

    task_repo.set_status.assert_awaited_once_with(task_id, TaskStatus.cancelled)
    assert task_id in message._answered[0]


async def test_my_downloads_lists_recent_history() -> None:
    user_repo = AsyncMock()
    user_repo.get_by_telegram_id.return_value = SimpleNamespace(id=42)
    history_repo = AsyncMock()
    history_repo.list_for_user.return_value = [
        DownloadHistory(
            user_id=42,
            task_id="33333333-3333-3333-3333-333333333333",
            title="My Podcast Episode",
            operation=TaskOperation.extract_audio,
            output_format="mp3",
        )
    ]
    message = _fake_message()

    await status_handlers.my_downloads(message, history_repo, user_repo)

    assert "My Podcast Episode" in message._answered[0]


async def test_my_downloads_with_no_history() -> None:
    user_repo = AsyncMock()
    user_repo.get_by_telegram_id.return_value = None
    history_repo = AsyncMock()
    message = _fake_message()

    await status_handlers.my_downloads(message, history_repo, user_repo)

    assert "haven't downloaded anything" in message._answered[0]

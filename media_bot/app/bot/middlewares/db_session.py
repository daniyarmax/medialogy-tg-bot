from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.repository import DownloadHistoryRepository, TaskRepository, UserRepository
from app.database.session import get_sessionmaker


class DbSessionMiddleware(BaseMiddleware):
    """Opens one DB session per update and injects it (plus ready-made
    repositories) into handler `data`, committing on success.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            data["db_session"] = session
            data["user_repo"] = UserRepository(session)
            data["task_repo"] = TaskRepository(session)
            data["history_repo"] = DownloadHistoryRepository(session)
            result = await handler(event, data)
            await session.commit()
            return result

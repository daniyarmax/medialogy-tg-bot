from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.logging import bind_task_context, clear_log_context


class LoggingContextMiddleware(BaseMiddleware):
    """Binds the Telegram user ID to structlog's contextvars for the
    duration of handling one update, so every log line emitted anywhere
    during that update is automatically tagged with it.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        bind_task_context(user_id=user.id if user else None)
        try:
            return await handler(event, data)
        finally:
            clear_log_context()

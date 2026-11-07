from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from redis.asyncio import Redis


class RateLimitMiddleware(BaseMiddleware):
    """Throttles raw message submissions per user via a Redis SETNX+TTL
    token — independent of (and a layer in front of) the per-user
    *task-concurrency* admission gate in `task_service.py`. This stops
    someone from pasting dozens of links in a few seconds before any of
    them even reach task admission.
    """

    def __init__(self, redis: Redis, *, min_interval_seconds: float = 2.0) -> None:
        self._redis = redis
        self._ttl_seconds = max(1, round(min_interval_seconds))

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        key = f"ratelimit:msg:{user.id}"
        allowed = await self._redis.set(key, "1", nx=True, ex=self._ttl_seconds)
        if not allowed:
            # Registered only via `dp.message.middleware(...)`, so `event`
            # is always a real `Message` in production — a plain duck-typed
            # `.answer()` call keeps this middleware testable with a
            # lightweight stand-in instead of a full aiogram Message mock.
            await event.answer("You're sending requests too fast. Please slow down a bit.")
            return None

        return await handler(event, data)

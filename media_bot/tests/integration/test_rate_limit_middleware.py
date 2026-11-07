"""Against a real local Redis (not a mock) — the whole point of this
middleware is a real SETNX+TTL race, which a mock would just assert away.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from redis.asyncio import Redis

from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.core.config import get_settings


@pytest.fixture
async def redis():
    settings = get_settings()
    client = Redis(host=settings.redis.host, port=settings.redis.port, db=15, decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()


def _fake_message(user_id: int):
    answered = []

    async def _answer(text: str) -> None:
        answered.append(text)

    message = SimpleNamespace(answer=_answer, _answered=answered)
    return message


async def test_first_message_is_allowed(redis: Redis) -> None:
    middleware = RateLimitMiddleware(redis, min_interval_seconds=2.0)
    user_id = uuid.uuid4().int % 10_000_000
    message = _fake_message(user_id)
    handler_calls = []

    async def handler(event, data):
        handler_calls.append(event)
        return "ok"

    result = await middleware(handler, message, {"event_from_user": SimpleNamespace(id=user_id)})

    assert result == "ok"
    assert len(handler_calls) == 1
    assert message._answered == []


async def test_second_message_within_interval_is_blocked(redis: Redis) -> None:
    middleware = RateLimitMiddleware(redis, min_interval_seconds=2.0)
    user_id = uuid.uuid4().int % 10_000_000
    handler_calls = []

    async def handler(event, data):
        handler_calls.append(event)
        return "ok"

    data = {"event_from_user": SimpleNamespace(id=user_id)}
    await middleware(handler, _fake_message(user_id), data)

    message2 = _fake_message(user_id)
    result2 = await middleware(handler, message2, data)

    assert result2 is None
    assert len(handler_calls) == 1  # handler was NOT called the second time
    assert len(message2._answered) == 1
    assert "too fast" in message2._answered[0]


async def test_message_allowed_again_after_interval_elapses(redis: Redis) -> None:
    middleware = RateLimitMiddleware(redis, min_interval_seconds=1.0)
    user_id = uuid.uuid4().int % 10_000_000
    handler_calls = []

    async def handler(event, data):
        handler_calls.append(event)
        return "ok"

    data = {"event_from_user": SimpleNamespace(id=user_id)}
    await middleware(handler, _fake_message(user_id), data)
    await asyncio.sleep(1.1)
    await middleware(handler, _fake_message(user_id), data)

    assert len(handler_calls) == 2


async def test_different_users_are_not_cross_throttled(redis: Redis) -> None:
    middleware = RateLimitMiddleware(redis, min_interval_seconds=5.0)
    handler_calls = []

    async def handler(event, data):
        handler_calls.append(event)
        return "ok"

    user_a = uuid.uuid4().int % 10_000_000
    user_b = uuid.uuid4().int % 10_000_000
    await middleware(handler, _fake_message(user_a), {"event_from_user": SimpleNamespace(id=user_a)})
    await middleware(handler, _fake_message(user_b), {"event_from_user": SimpleNamespace(id=user_b)})

    assert len(handler_calls) == 2

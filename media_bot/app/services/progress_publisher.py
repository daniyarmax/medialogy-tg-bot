"""Publishes task progress to a short-TTL Redis hash that the bot process
polls independently — cheaper than round-tripping Celery's own result
backend on every tick, and it's how the bot learns about progress without
depending on whether anything ever calls `AsyncResult.get()`.

Uses a plain sync Redis client (not `redis.asyncio`) because this is called
from inside Celery task bodies, which bridge into the async orchestration
code via `app.database.session.run_async` — a sync client here avoids
needing yet another event-loop bridge just for a handful of fast local
Redis round-trips.
"""

import time
from functools import lru_cache

import redis

from app.core.config import get_settings

_PROGRESS_TTL_SECONDS = 3600
_KEY_PREFIX = "task:progress:"


@lru_cache
def _client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis(
        host=settings.redis.host, port=settings.redis.port, db=settings.redis.db_cache,
        decode_responses=True,
    )


def _key(task_id: str) -> str:
    return f"{_KEY_PREFIX}{task_id}"


def publish_progress(
    task_id: str,
    *,
    stage: str,
    percent: float | None = None,
    speed_bytes_per_sec: float | None = None,
    eta_seconds: int | None = None,
) -> None:
    mapping: dict[str, str] = {"stage": stage, "updated_at": str(time.time())}
    if percent is not None:
        mapping["percent"] = str(round(percent, 1))
    if speed_bytes_per_sec is not None:
        mapping["speed_bytes_per_sec"] = str(round(speed_bytes_per_sec, 1))
    if eta_seconds is not None:
        mapping["eta_seconds"] = str(eta_seconds)

    client = _client()
    key = _key(task_id)
    client.hset(key, mapping=mapping)
    client.expire(key, _PROGRESS_TTL_SECONDS)


def publish_terminal(task_id: str, stage: str, *, error_message: str | None = None) -> None:
    mapping: dict[str, str] = {"stage": stage, "updated_at": str(time.time()), "terminal": "1"}
    if error_message:
        mapping["error_message"] = error_message

    client = _client()
    key = _key(task_id)
    client.hset(key, mapping=mapping)
    client.expire(key, _PROGRESS_TTL_SECONDS)

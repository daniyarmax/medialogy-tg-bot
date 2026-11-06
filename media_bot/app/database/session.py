import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

T = TypeVar("T")


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.database.url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session


_worker_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    """One event loop, reused for the lifetime of this process.

    `asyncio.run()` creates a brand-new loop every call, but the cached
    engine's connection pool (`get_engine`) binds its asyncpg connections to
    whichever loop was running when they were opened — reusing the engine
    across a fresh loop per call raises "Future attached to a different
    loop". A single persistent loop per worker process keeps the engine's
    assumption (one engine lives on one loop for its whole lifetime) true.
    """
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    return _worker_loop


def run_async(coro_fn: Callable[..., Awaitable[T]], /, *args: object, **kwargs: object) -> T:
    """Run an async DB/IO coroutine from a sync Celery task body.

    Celery task entry points are synchronous; the actual work (repository
    calls, etc.) is written as `async def` for consistency with the bot
    process, and bridged here via this worker process's single persistent
    event loop rather than a fresh one per call.
    """
    loop = _get_worker_loop()
    return loop.run_until_complete(coro_fn(*args, **kwargs))

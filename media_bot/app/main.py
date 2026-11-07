import asyncio

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from redis.asyncio import Redis

from app.bot.handlers import audio, download, start, status
from app.bot.handlers import settings as settings_handlers
from app.bot.middlewares.db_session import DbSessionMiddleware
from app.bot.middlewares.logging import LoggingContextMiddleware
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.bot.telegram_client import build_bot
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    bot, limits = build_bot(settings)
    bot.media_bot_limits = limits  # read by handlers/audio.py for download-size checks

    redis = Redis(
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.db_cache,
        decode_responses=True,
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(LoggingContextMiddleware())
    dp.update.middleware(DbSessionMiddleware())
    dp.message.middleware(RateLimitMiddleware(redis, min_interval_seconds=2.0))

    dp.include_router(start.router)
    dp.include_router(download.router)
    dp.include_router(audio.router)
    dp.include_router(status.router)
    dp.include_router(settings_handlers.router)

    logger.info("bot_starting", api_mode=settings.telegram.api_mode)
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await redis.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

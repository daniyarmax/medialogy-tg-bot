"""Polls the Redis progress key a worker writes (see
`app.services.progress_publisher`) and edits a tracking message in place,
using `ProgressMessageThrottler` to stay well under Telegram's edit rate
limit. Runs as a fire-and-forget `asyncio.create_task` in the bot process,
started right after a task is dispatched to Celery.
"""

import asyncio

from aiogram import Bot
from redis.asyncio import Redis

from app.bot.progress_tracker import ProgressMessageThrottler, ProgressSnapshot, render_progress_text
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_STAGE_EMOJI = {"Downloading": "🎬", "Processing": "🎵", "Uploading": "📤"}


def _render_snapshot(stage: str, data: dict[str, str]) -> ProgressSnapshot:
    percent = float(data["percent"]) if "percent" in data else None
    speed_text = None
    if "speed_bytes_per_sec" in data:
        speed_mb_s = float(data["speed_bytes_per_sec"]) / 1024 / 1024
        speed_text = f"{speed_mb_s:.1f} MB/s"
    eta_text = f"{int(data['eta_seconds'])}s" if "eta_seconds" in data else None

    label = f"{_STAGE_EMOJI.get(stage, '⏳')} {stage}..."
    return ProgressSnapshot(stage=label, percent=percent, speed_text=speed_text, eta_text=eta_text)


async def poll_task_progress(bot: Bot, chat_id: int, message_id: int, task_id: str, redis: Redis) -> None:
    settings = get_settings()
    throttler = ProgressMessageThrottler(min_interval_seconds=settings.limits.min_edit_interval_seconds)
    key = f"task:progress:{task_id}"
    loop = asyncio.get_event_loop()
    # Generous overall ceiling so a poller never outlives the task it's
    # tracking even if something upstream never publishes a terminal marker.
    deadline = loop.time() + settings.limits.max_processing_time_seconds + 120

    try:
        while loop.time() < deadline:
            data = await redis.hgetall(key)
            if not data:
                await asyncio.sleep(settings.limits.progress_poll_interval_seconds)
                continue

            stage = data.get("stage", "Working")

            if data.get("terminal") == "1":
                if stage == "Completed":
                    final_text = "✅ Processing completed!"
                elif stage == "Failed":
                    final_text = f"❌ {data.get('error_message', 'Something went wrong.')}"
                else:
                    final_text = stage
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id, text=final_text
                    )
                except Exception:
                    logger.debug("progress_final_edit_skipped", task_id=task_id)
                return

            snapshot = _render_snapshot(stage, data)
            text = render_progress_text(snapshot)
            now = loop.time()
            if throttler.should_send(text, now=now):
                try:
                    await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
                    throttler.record_sent(text, now=now)
                except Exception:
                    # MessageNotModified / transient rate limit - not fatal, just skip this tick.
                    pass

            await asyncio.sleep(settings.limits.progress_poll_interval_seconds)
    except Exception:
        logger.exception("progress_poller_crashed", task_id=task_id)

"""The single place that knows about the Standard vs. Local Bot API Server
split. Every other module asks a `TelegramLimits` instance for ceilings —
nothing else checks `settings.telegram.api_mode` directly.

Researched limits (see IMPLEMENTATION_STATUS.md / the plan for sources):
  - Standard Bot API:   50MB upload, 20MB download
  - Local Bot API Server: 2000MB upload, effectively unlimited download,
    with an absolute 4000MB per-request ceiling regardless of mode.
"""

from dataclasses import dataclass

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.core.config import Settings

_STANDARD_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_STANDARD_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
_LOCAL_MAX_UPLOAD_BYTES = 2000 * 1024 * 1024
_LOCAL_ABSOLUTE_CEILING_BYTES = 4000 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class TelegramLimits:
    max_upload_bytes: int
    max_download_bytes: int | None  # None means "effectively unlimited"
    supports_local_paths: bool


def _limits_for(settings: Settings) -> TelegramLimits:
    business_ceiling = settings.limits.max_file_size_mb * 1024 * 1024
    if settings.telegram.api_mode == "local":
        return TelegramLimits(
            max_upload_bytes=min(
                _LOCAL_MAX_UPLOAD_BYTES, _LOCAL_ABSOLUTE_CEILING_BYTES, business_ceiling
            ),
            max_download_bytes=None,
            supports_local_paths=True,
        )
    return TelegramLimits(
        max_upload_bytes=min(_STANDARD_MAX_UPLOAD_BYTES, business_ceiling),
        max_download_bytes=_STANDARD_MAX_DOWNLOAD_BYTES,
        supports_local_paths=False,
    )


def build_bot(settings: Settings) -> tuple[Bot, TelegramLimits]:
    limits = _limits_for(settings)

    if settings.telegram.api_mode == "local":
        session = AiohttpSession(
            api=TelegramAPIServer.from_base(settings.telegram.local_api_base_url, is_local=True)
        )
    else:
        session = AiohttpSession()

    bot = Bot(
        token=settings.telegram.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    return bot, limits

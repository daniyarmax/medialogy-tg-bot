from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.handlers import settings as settings_handlers
from app.database.models import User


def _fake_message(user_id: int = 1):
    answered = []

    async def _answer(text: str, **kwargs) -> None:
        answered.append(text)

    return SimpleNamespace(
        answer=_answer,
        _answered=answered,
        from_user=SimpleNamespace(id=user_id, username="alice", first_name="Alice", last_name=None),
    )


def _fake_callback(data: str, user_id: int = 1):
    edited = []

    async def _edit_text(text: str, **kwargs) -> None:
        edited.append(text)

    answers = []

    async def _answer(text: str = "", **kwargs) -> None:
        answers.append(text)

    return SimpleNamespace(
        data=data,
        message=SimpleNamespace(edit_text=_edit_text, _edited=edited),
        answer=_answer,
        _answers=answers,
        from_user=SimpleNamespace(id=user_id),
    )


async def test_cmd_settings_shows_current_defaults() -> None:
    user_repo = AsyncMock()
    user_repo.get_or_create.return_value = User(
        telegram_user_id=1, default_audio_format="mp3", default_audio_bitrate="192k"
    )
    message = _fake_message()

    await settings_handlers.cmd_settings(message, user_repo)

    assert "MP3" in message._answered[0]
    assert "192k" in message._answered[0]


async def test_set_default_audio_format_updates_user_and_confirms() -> None:
    user_repo = AsyncMock()
    user = User(telegram_user_id=1, default_audio_format="mp3", default_audio_bitrate="192k")
    user_repo.get_or_create.return_value = user
    callback = _fake_callback("setaudiofmt:flac")

    await settings_handlers.set_default_audio_format(callback, user_repo)

    assert user.default_audio_format == "flac"
    assert "FLAC" in callback.message._edited[0]

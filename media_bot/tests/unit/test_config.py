from app.core.config import get_settings


def test_settings_load_from_env() -> None:
    settings = get_settings()

    assert settings.telegram.bot_token
    assert settings.telegram.api_mode in ("cloud", "local")
    assert settings.database.url.startswith("postgresql+asyncpg://")
    assert settings.limits.max_file_size_mb > 0
    assert settings.limits.max_duration_seconds > 0


def test_settings_is_cached_singleton() -> None:
    assert get_settings() is get_settings()

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Populates os.environ from a local .env file (if present) so every nested
# BaseSettings below sees the same values whether running locally or via
# `docker compose` (which injects env vars directly, without a .env file
# inside the container).
load_dotenv()


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    api_mode: Literal["cloud", "local"] = Field("cloud", alias="TELEGRAM_API_MODE")
    local_api_base_url: str = Field(
        "http://telegram-bot-api:8081", alias="LOCAL_BOT_API_BASE_URL"
    )
    local_api_id: str | None = Field(None, alias="LOCAL_BOT_API_ID")
    local_api_hash: str | None = Field(None, alias="LOCAL_BOT_API_HASH")


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    url: str = Field(alias="DATABASE_URL")


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    host: str = Field("redis", alias="REDIS_HOST")
    port: int = Field(6379, alias="REDIS_PORT")
    db_cache: int = Field(2, alias="REDIS_DB_CACHE")


class CelerySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    broker_url: str = Field(alias="CELERY_BROKER_URL")
    result_backend: str = Field(alias="CELERY_RESULT_BACKEND")


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    root: Path = Field(Path("/storage"), alias="STORAGE_ROOT")
    downloads_dir: Path = Field(Path("/storage/downloads"), alias="DOWNLOADS_DIR")
    processed_dir: Path = Field(Path("/storage/processed"), alias="PROCESSED_DIR")
    temp_dir: Path = Field(Path("/storage/temp"), alias="TEMP_DIR")
    temp_file_ttl_hours: int = Field(24, alias="TEMP_FILE_TTL_HOURS")


class LimitsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    max_file_size_mb: int = Field(1900, alias="MAX_FILE_SIZE_MB")
    max_duration_seconds: int = Field(18000, alias="MAX_DURATION_SECONDS")
    max_processing_time_seconds: int = Field(3600, alias="MAX_PROCESSING_TIME_SECONDS")
    max_concurrent_tasks_per_user: int = Field(2, alias="MAX_CONCURRENT_TASKS_PER_USER")
    min_free_disk_mb: int = Field(2048, alias="MIN_FREE_DISK_MB")
    progress_poll_interval_seconds: float = Field(
        2.5, alias="PROGRESS_POLL_INTERVAL_SECONDS"
    )
    min_edit_interval_seconds: float = Field(3.0, alias="MIN_EDIT_INTERVAL_SECONDS")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    env: Literal["local", "docker", "production"] = Field("local", alias="ENV")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_format: Literal["console", "json"] = Field("console", alias="LOG_FORMAT")

    telegram: TelegramSettings = Field(default_factory=lambda: TelegramSettings())  # type: ignore[call-arg]
    database: DatabaseSettings = Field(default_factory=lambda: DatabaseSettings())  # type: ignore[call-arg]
    redis: RedisSettings = Field(default_factory=lambda: RedisSettings())  # type: ignore[call-arg]
    celery: CelerySettings = Field(default_factory=lambda: CelerySettings())  # type: ignore[call-arg]
    storage: StorageSettings = Field(default_factory=lambda: StorageSettings())  # type: ignore[call-arg]
    limits: LimitsSettings = Field(default_factory=lambda: LimitsSettings())  # type: ignore[call-arg]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

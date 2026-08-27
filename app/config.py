"""Central configuration loaded from environment / .env file.

A single `Settings` instance is exposed via `get_settings()`. Modules that
need config should call `get_settings()` rather than instantiating `Settings`
directly so tests can override it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration. Values come from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Required ---
    database_url: str = "sqlite:///./storage/app.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: Path = Path("./storage")
    gemini_api_key: str = ""

    # --- TTS ---
    kokoro_model_dir: Path = Path("./storage/models/kokoro")
    kokoro_voice_host_a: str = "af_bella"
    kokoro_voice_host_b: str = "am_adam"
    kokoro_voice_narrator: str = "af_nicole"

    # --- App ---
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"

    # --- Operations ---
    retention_days: int = 30
    celery_task_time_limit: int = 1800

    # --- Optional Ollama fallback (off by default) ---
    ollama_host: str | None = None
    ollama_model: str | None = None

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings instance."""
    return Settings()
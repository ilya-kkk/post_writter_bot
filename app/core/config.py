from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    bot_token: str = ""
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/post_writer_bot"
    redis_url: str = "redis://localhost:6379/0"
    auto_init_db: bool = True
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 60.0
    telegram_timeout_seconds: float = 30.0
    analyze_job_timeout_seconds: int = 360
    generate_ideas_job_timeout_seconds: int = 240
    generate_post_job_timeout_seconds: int = 360
    followup_fast_mode: bool = True
    mock_payments: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

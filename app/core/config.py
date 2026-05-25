from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    bot_token: str = ""
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/post_writer_bot"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    followup_fast_mode: bool = True
    mock_payments: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

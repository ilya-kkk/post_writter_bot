from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "production"
    bot_token: str = ""
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    auto_init_db: bool = False
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 60.0
    telegram_timeout_seconds: float = 30.0
    telegram_client_api_id: str = ""
    telegram_client_api_hash: str = ""
    telegram_client_data_dir: str = "telegram_client_data"
    telegram_client_session_name: str = "post_writer_client"
    telegram_client_admin_token: str = ""
    telegram_client_timeout_seconds: float = 10.0
    analyze_job_timeout_seconds: int = 360
    generate_ideas_job_timeout_seconds: int = 240
    generate_post_job_timeout_seconds: int = 360
    followup_fast_mode: bool = False
    mock_payments: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

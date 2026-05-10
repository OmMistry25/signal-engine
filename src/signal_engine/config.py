from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    slack_bot_token: str | None = Field(default=None, alias="SLACK_BOT_TOKEN")
    slack_channel_id: str | None = Field(default=None, alias="SLACK_CHANNEL_ID")
    hubspot_api_key: str | None = Field(default=None, alias="HUBSPOT_API_KEY")

    score_publish_threshold: float = Field(default=60.0, alias="SCORE_PUBLISH_THRESHOLD")
    greenhouse_poll_minutes: int = Field(default=15, alias="GREENHOUSE_POLL_MINUTES")
    lever_poll_minutes: int = Field(default=15, alias="LEVER_POLL_MINUTES")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

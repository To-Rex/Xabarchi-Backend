"""Application settings loaded from the environment (and .env)."""

from __future__ import annotations

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Values come from environment variables (case-insensitive), with `.env`
    as a fallback for local development. The `.env` file is the source of
    truth in deployed containers as well, mounted by the orchestrator.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30
    # NoDecode: keep pydantic-settings from JSON-parsing the raw env string;
    # the before-validator below handles the comma-separated form instead.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    # Gateway devices claim message batches under a short lease; if a device
    # dies mid-send the lease expiry returns messages to the queue.
    gateway_lease_seconds: int = 120
    gateway_claim_max: int = 100

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string (as stored in .env) or a list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def sqlalchemy_url(self) -> str:
        """DATABASE_URL rewritten for the asyncpg driver.

        The .env keeps the plain `postgresql://` form so the same value works
        with psql/other tooling; SQLAlchemy needs the explicit async dialect.
        """
        if self.database_url.startswith("postgresql+asyncpg://"):
            return self.database_url
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


settings = Settings()

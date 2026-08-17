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
    # Port the server binds to (used by ``python -m app`` and deploys).
    port: int = 8000
    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30
    # NoDecode: keep pydantic-settings from JSON-parsing the raw env string;
    # the before-validator below handles the comma-separated form instead.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    # E-mails granted admin-panel access (comma-separated). A user is also an
    # admin if their DB role is "admin" (set from the panel itself).
    admin_emails: Annotated[list[str], NoDecode] = []
    # Gateway devices claim message batches under a short lease; if a device
    # dies mid-send the lease expiry returns messages to the queue.
    gateway_lease_seconds: int = 120
    gateway_claim_max: int = 100

    # Public URLs used when building links (OAuth callbacks, e-mail links,
    # Polar checkout redirects).
    frontend_url: str = "http://localhost:5173"
    public_api_url: str = "http://localhost:8000"

    # Social auth. A provider is enabled only when its client id is set.
    google_client_id: str = ""
    google_client_secret: str = ""
    apple_client_id: str = ""
    # Apple's "client secret" is a developer-generated signed JWT.
    apple_client_secret: str = ""

    # SMTP for password-reset / e-mail-verification mail. When smtp_host is
    # empty the mail is logged instead of sent (development mode).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Xabarchi <no-reply@xabarchi.uz>"

    # Polar (polar.sh) billing. Empty token disables the integration.
    polar_access_token: str = ""
    polar_webhook_secret: str = ""
    polar_server: str = "sandbox"  # "sandbox" | "production"
    # Polar product IDs mapped to paid plan ids.
    polar_product_biznes: str = ""
    polar_product_korxona: str = ""
    # Optional org id — some Polar endpoints (discounts) want it explicitly.
    polar_organization_id: str = ""
    # Currency used when pushing prices/discounts to Polar. Must be one Polar
    # actually supports (UZS is often NOT supported — then keep it "usd").
    polar_currency: str = "uzs"

    @field_validator("cors_origins", "admin_emails", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept a comma-separated string (as stored in .env) or a list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
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

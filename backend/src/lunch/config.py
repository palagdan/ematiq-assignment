from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LUNCH_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://lunch:lunch@localhost:5433/lunch"
    database_null_pool: bool = False
    rates_url: str = "http://localhost:8001"
    secret_key: str = "dev-secret-change-me"
    session_ttl_days: int = 30
    rate_limits_enabled: bool = True
    # Lobbies with no change for this long are deleted, freeing their players.
    lobby_idle_minutes: int = 30
    cookie_secure: bool = False
    public_url: str = ""
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_security: Literal["none", "starttls", "ssl"] = "none"
    mail_from: str = "Lunch Roulette <no-reply@lunch-roulette.local>"
    reset_token_ttl_minutes: int = 30
    google_client_id: str = ""
    google_client_secret: str = ""

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()

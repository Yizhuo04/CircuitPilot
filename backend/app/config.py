"""Environment configuration; no hardcoded production credentials."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CIRCUITPILOT_", env_file=".env", extra="ignore")
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/circuitpilot.db"
    storage_dir: Path = Path("data/uploads")
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]
    cookie_secure: bool = False
    session_hours: int = Field(default=24, ge=1, le=168)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    photo_retention_days: int = Field(default=30, ge=1, le=365)
    auto_create_schema: bool = True
    detector_model_dir: Path | None = None
    require_worker_health: bool = False

    @field_validator("database_url")
    @classmethod
    def postgres_driver(cls, value: str) -> str:
        # Managed hosts supply the standard URL; this project installs psycopg 3.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value

    @model_validator(mode="after")
    def production_requirements(self) -> "Settings":
        if self.environment == "production":
            if not self.cookie_secure or self.auto_create_schema:
                raise ValueError(
                    "Production requires secure cookies and migrations (auto_create_schema=false)."
                )
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL.")
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise ValueError("Production origins must use HTTPS.")
        return self

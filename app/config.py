from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SQLITE_URL_PREFIX = "sqlite+aiosqlite:"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_host: str = "127.0.0.1"
    app_port: int = Field(8000, ge=1, le=65535)
    database_url: str = "sqlite+aiosqlite:///./cache.db"
    max_list_items: int | None = Field(None, ge=1)
    max_body_size: int | None = Field(None, ge=1)
    max_transformer_calls: int = Field(50, ge=1)

    @field_validator("database_url")
    @classmethod
    def database_must_be_sqlite(cls, database_url: str) -> str:
        # The repositories use SQLite's INSERT ... ON CONFLICT syntax and the app
        # needs an async driver, so any other URL would fail later and less clearly.
        if not database_url.startswith(SQLITE_URL_PREFIX):
            raise ValueError(f"DATABASE_URL must start with {SQLITE_URL_PREFIX}")
        return database_url

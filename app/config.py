from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_host: str = "127.0.0.1"
    app_port: int = Field(8000, ge=1, le=65535)
    database_url: str = "sqlite+aiosqlite:///./cache.db"
    max_list_items: int | None = Field(None, ge=1)
    max_body_size: int | None = Field(None, ge=1)
    max_transformer_calls: int = Field(50, ge=1)

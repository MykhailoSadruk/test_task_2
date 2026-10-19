from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "APP_HOST",
        "APP_PORT",
        "DATABASE_URL",
        "MAX_LIST_ITEMS",
        "MAX_BODY_SIZE",
        "MAX_TRANSFORMER_CALLS",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)


def write_env_file(tmp_path: Path, content: str) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    return env_file


def test_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8000
    assert settings.database_url == "sqlite+aiosqlite:///./cache.db"


def test_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    monkeypatch.setenv("APP_PORT", "9000")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///env.db")

    settings = Settings(_env_file=None)

    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 9000
    assert settings.database_url == "sqlite+aiosqlite:///env.db"


def test_values_from_env_file(tmp_path: Path) -> None:
    env_file = write_env_file(
        tmp_path,
        "APP_HOST=0.0.0.0\nAPP_PORT=9100\nDATABASE_URL=sqlite+aiosqlite:///file.db\n",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_host == "0.0.0.0"
    assert settings.app_port == 9100
    assert settings.database_url == "sqlite+aiosqlite:///file.db"


def test_env_file_is_read_from_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_env_file(tmp_path, "APP_PORT=9200\n")
    monkeypatch.chdir(tmp_path)

    assert Settings().app_port == 9200


def test_environment_overrides_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = write_env_file(tmp_path, "APP_PORT=9100\n")
    monkeypatch.setenv("APP_PORT", "9300")

    assert Settings(_env_file=env_file).app_port == 9300


def test_unknown_env_file_keys_are_ignored(tmp_path: Path) -> None:
    env_file = write_env_file(tmp_path, "UNKNOWN_KEY=1\nAPP_PORT=9400\n")

    assert Settings(_env_file=env_file).app_port == 9400


@pytest.mark.parametrize("port", ["0", "65536", "-1", "abc"])
def test_invalid_port_is_rejected(port: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PORT", port)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_limits_are_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.max_list_items is None
    assert settings.max_body_size is None


def test_limits_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_LIST_ITEMS", "500")
    monkeypatch.setenv("MAX_BODY_SIZE", "2048")

    settings = Settings(_env_file=None)

    assert settings.max_list_items == 500
    assert settings.max_body_size == 2048


def test_limits_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_LIST_ITEMS", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_transformer_call_limit_default_and_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings(_env_file=None).max_transformer_calls == 50

    monkeypatch.setenv("MAX_TRANSFORMER_CALLS", "7")

    assert Settings(_env_file=None).max_transformer_calls == 7


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+asyncpg://user:secret@localhost/cache",
        "sqlite:///cache.db",
        "mysql+aiomysql://localhost/cache",
    ],
)
def test_only_async_sqlite_urls_are_accepted(database_url: str) -> None:
    with pytest.raises(ValidationError, match=r"must start with sqlite\+aiosqlite:"):
        Settings(_env_file=None, database_url=database_url)


@pytest.mark.parametrize(
    "database_url", ["sqlite+aiosqlite://", "sqlite+aiosqlite:///./cache.db"]
)
def test_async_sqlite_urls_are_accepted(database_url: str) -> None:
    assert Settings(_env_file=None, database_url=database_url).database_url == (
        database_url
    )


def test_log_level_default_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).log_level == "INFO"

    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    assert Settings(_env_file=None).log_level == "DEBUG"


def test_unknown_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

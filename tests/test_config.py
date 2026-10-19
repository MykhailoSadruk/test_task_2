from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_HOST", "APP_PORT", "DATABASE_URL"):
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

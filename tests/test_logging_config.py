import pytest

from app.config import Settings
from app.logging_config import LOG_FORMAT
from app.main import get_app


def test_app_configures_logging_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("logging.basicConfig", lambda **options: calls.append(options))

    get_app(Settings(_env_file=None, log_level="DEBUG"))

    assert calls == [{"level": "DEBUG", "format": LOG_FORMAT}]

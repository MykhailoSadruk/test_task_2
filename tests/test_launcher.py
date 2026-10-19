import pytest

from app.__main__ import main


def test_main_runs_uvicorn_with_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    monkeypatch.setenv("APP_PORT", "9500")
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_run(app: str, **options: object) -> None:
        calls.append((app, options))

    monkeypatch.setattr("uvicorn.run", fake_run)

    main()

    assert calls == [
        ("app.main:get_app", {"factory": True, "host": "0.0.0.0", "port": 9500})
    ]

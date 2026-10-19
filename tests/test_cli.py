import io
import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn

from app.config import Settings
from app.main import get_app
from cli.client import PayloadClient, PayloadClientError
from cli.main import main
from cli.settings import CliSettings

PAYLOAD = {
    "list_1": ["first string", "second string", "third string"],
    "list_2": ["other string", "another string", "last string"],
}
PAYLOAD_JSON = json.dumps(PAYLOAD)
EXPECTED_LINE = json.dumps(
    {
        "output": "FIRST STRING, OTHER STRING, SECOND STRING, "
        "ANOTHER STRING, THIRD STRING, LAST STRING"
    },
    separators=(",", ":"),
)


def find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def server_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    port = find_free_port()
    database = tmp_path_factory.mktemp("cli") / "cli.db"
    settings = Settings(database_url=f"sqlite+aiosqlite:///{database}")
    server = uvicorn.Server(
        uvicorn.Config(
            get_app(settings), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()


def test_json_argument_prints_output(
    server_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["-H", server_url, "-j", PAYLOAD_JSON]) == 0
    assert capsys.readouterr().out == EXPECTED_LINE + "\n"


def test_input_file(
    server_url: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text(PAYLOAD_JSON)
    assert main(["-H", server_url, "-i", str(input_file)]) == 0
    assert capsys.readouterr().out == EXPECTED_LINE + "\n"


def test_stdin_input(
    server_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(PAYLOAD_JSON))
    assert main(["-H", server_url, "-i", "-"]) == 0
    assert capsys.readouterr().out == EXPECTED_LINE + "\n"


def test_repeat_prints_one_line_per_iteration(
    server_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["-H", server_url, "-r", "3", "-j", PAYLOAD_JSON]) == 0
    assert capsys.readouterr().out.splitlines() == [EXPECTED_LINE] * 3


def test_output_to_file(
    server_url: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_file = tmp_path / "out.txt"
    assert main(["-H", server_url, "-j", PAYLOAD_JSON, "-o", str(output_file)]) == 0
    assert output_file.read_text() == EXPECTED_LINE + "\n"
    assert capsys.readouterr().out == ""


def test_server_error_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    unused_url = f"http://127.0.0.1:{find_free_port()}"
    assert main(["-H", unused_url, "-j", PAYLOAD_JSON]) == 2
    assert "cannot reach server" in capsys.readouterr().err


def test_rejected_payload_is_reported(
    server_url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    unequal = json.dumps({"list_1": ["a"], "list_2": []})
    assert main(["-H", server_url, "-j", unequal]) == 2
    error = capsys.readouterr().err
    assert "failed with status 422: " in error
    assert "must have the same length" in error


def test_not_found_reason_is_reported(server_url: str) -> None:
    client = PayloadClient(httpx.Client(base_url=server_url))
    missing_id = "0" * 64

    with pytest.raises(
        PayloadClientError, match=f"status 404: Payload {missing_id} not found"
    ):
        client.get_output(missing_id)


def test_timeout_defaults_to_ten_minutes() -> None:
    assert CliSettings(_cli_parse_args=["-j", PAYLOAD_JSON]).timeout == 600


def test_timeout_option_is_parsed() -> None:
    settings = CliSettings(_cli_parse_args=["-j", PAYLOAD_JSON, "-t", "2.5"])

    assert settings.timeout == 2.5


def test_timeout_must_be_positive(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["-j", PAYLOAD_JSON, "--timeout", "0"]) == 2
    assert "greater than 0" in capsys.readouterr().err


def test_request_timeout_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen()
        url = f"http://127.0.0.1:{silent.getsockname()[1]}"
        assert main(["-H", url, "-j", PAYLOAD_JSON, "-t", "0.2"]) == 2
    assert "cannot reach server" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv, message",
    [
        ([], "exactly one of --input and --json"),
        (["-j", PAYLOAD_JSON, "-i", "-"], "exactly one of --input and --json"),
        (["-j", PAYLOAD_JSON, "-r", "0"], "greater than or equal to 1"),
        (["-j", PAYLOAD_JSON, "-r", "many"], "valid integer"),
        (["-j", PAYLOAD_JSON, "-H", "not a url"], "valid URL"),
        (["-j", "{broken"], "Invalid JSON"),
        (["-j", '{"list_1": ["a"]}'], "list_2"),
        (["-j", '{"list_1": [1], "list_2": ["a"]}'], "list_1"),
        (["-i", "missing-file.json"], "cannot read input"),
    ],
)
def test_invalid_arguments_exit_with_message(
    argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 2
    assert message in capsys.readouterr().err


def test_help_exits_successfully(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["-h"])
    assert exit_info.value.code == 0
    assert "--host" in capsys.readouterr().out


def set_conflicting_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST", "http://bad")
    monkeypatch.setenv("OUTPUT", "x.txt")
    monkeypatch.setenv("R", "5")


def test_environment_does_not_change_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_conflicting_environment(monkeypatch)

    settings = CliSettings(_cli_parse_args=["-j", PAYLOAD_JSON])

    assert str(settings.host) == "http://localhost:8000/"
    assert settings.output == "-"
    assert settings.repeat == 1


def test_environment_is_ignored_by_main(
    server_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_conflicting_environment(monkeypatch)
    monkeypatch.chdir(tmp_path)

    assert main(["-H", server_url, "-j", PAYLOAD_JSON]) == 0

    assert capsys.readouterr().out == EXPECTED_LINE + "\n"
    assert not (tmp_path / "x.txt").exists()

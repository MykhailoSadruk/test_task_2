import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO

import httpx
from pydantic import ValidationError
from pydantic_core import ErrorDetails

from cli.client import PayloadClient, PayloadClientError
from cli.settings import CliSettings, PayloadInput


def describe_issue(issue: ErrorDetails) -> str:
    location = ".".join(map(str, issue["loc"]))
    return f"{location}: {issue['msg']}" if location else issue["msg"]


def format_validation_error(error: ValidationError) -> str:
    return "; ".join(describe_issue(issue) for issue in error.errors())


@contextmanager
def open_output(path: str) -> Iterator[TextIO]:
    if path == "-":
        yield sys.stdout
        return
    with open(path, "w", encoding="utf-8") as file:
        yield file


def run(settings: CliSettings, payload: PayloadInput) -> None:
    http = httpx.Client(base_url=str(settings.host), timeout=settings.timeout)
    with http, open_output(settings.output) as output:
        client = PayloadClient(http)
        for _ in range(settings.repeat):
            payload_id = client.create(payload)
            output.write(client.get_output(payload_id).model_dump_json() + "\n")
            output.flush()


def fail(message: str) -> int:
    print(f"cache-cli: error: {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    try:
        settings = CliSettings(_cli_parse_args=sys.argv[1:] if argv is None else argv)
        payload = settings.load_payload()
    except ValidationError as error:
        return fail(format_validation_error(error))
    except OSError as error:
        return fail(f"cannot read input: {error}")
    try:
        run(settings, payload)
    except PayloadClientError as error:
        return fail(str(error))
    except OSError as error:
        return fail(f"cannot write output: {error}")
    return 0

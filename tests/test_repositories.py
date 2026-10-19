from sqlalchemy.orm import Session

from app.infrastructure.dtos import PayloadDto
from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
)


def test_get_many_returns_only_hits(session: Session) -> None:
    repository = TransformedStringRepository(session)
    repository.add_many({"a": "A", "b": "B"})

    assert repository.get_many(["a", "b"]) == {"a": "A", "b": "B"}


def test_get_many_returns_partial_hits(session: Session) -> None:
    repository = TransformedStringRepository(session)
    repository.add_many({"a": "A"})

    assert repository.get_many(["a", "missing"]) == {"a": "A"}


def test_get_many_with_empty_input(session: Session) -> None:
    repository = TransformedStringRepository(session)

    assert repository.get_many([]) == {}


def test_add_many_persists_entries(session: Session) -> None:
    repository = TransformedStringRepository(session)
    repository.add_many({"x": "X", "y": "Y"})

    assert repository.get_many(["x", "y"]) == {"x": "X", "y": "Y"}


def test_payload_add_and_get(session: Session) -> None:
    repository = PayloadRepository(session)
    repository.add(PayloadDto(id="abc", output="A, B"))

    assert repository.get("abc") == PayloadDto(id="abc", output="A, B")


def test_payload_get_missing_returns_none(session: Session) -> None:
    assert PayloadRepository(session).get("nope") is None

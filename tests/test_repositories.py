from sqlalchemy.dialects import registry
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.dtos import PayloadDto, TransformedStringDto
from app.infrastructure.models import Payload
from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
    insert_ignoring_duplicates,
)


async def stored(session: AsyncSession, **entries: str) -> TransformedStringRepository:
    repository = TransformedStringRepository(session)
    await repository.add_many(
        TransformedStringDto(original=key, transformed=value)
        for key, value in entries.items()
    )
    return repository


def as_dict(entries: list[TransformedStringDto]) -> dict[str, str]:
    return {entry.original: entry.transformed for entry in entries}


async def test_get_many_returns_only_hits(session: AsyncSession) -> None:
    repository = await stored(session, a="A", b="B")

    assert as_dict(await repository.get_many(["a", "b"])) == {"a": "A", "b": "B"}


async def test_get_many_returns_partial_hits(session: AsyncSession) -> None:
    repository = await stored(session, a="A")

    assert await repository.get_many(["a", "missing"]) == [
        TransformedStringDto(original="a", transformed="A")
    ]


async def test_get_many_with_empty_input(session: AsyncSession) -> None:
    assert await TransformedStringRepository(session).get_many([]) == []


async def test_add_many_persists_entries(session: AsyncSession) -> None:
    repository = await stored(session, x="X", y="Y")

    assert as_dict(await repository.get_many(["x", "y"])) == {"x": "X", "y": "Y"}


async def test_payload_add_and_get(session: AsyncSession) -> None:
    repository = PayloadRepository(session)
    await repository.add(PayloadDto(id="abc", output="A, B"))

    assert await repository.get("abc") == PayloadDto(id="abc", output="A, B")


async def test_payload_get_missing_returns_none(session: AsyncSession) -> None:
    assert await PayloadRepository(session).get("nope") is None


async def test_add_many_ignores_existing_entry(session: AsyncSession) -> None:
    repository = await stored(session, a="A")

    await stored(session, a="changed", b="B")

    assert as_dict(await repository.get_many(["a", "b"])) == {"a": "A", "b": "B"}


async def test_payload_add_ignores_existing_id(session: AsyncSession) -> None:
    repository = PayloadRepository(session)
    await repository.add(PayloadDto(id="abc", output="A, B"))

    await repository.add(PayloadDto(id="abc", output="changed"))

    assert await repository.get("abc") == PayloadDto(id="abc", output="A, B")


def test_postgresql_insert_uses_on_conflict_do_nothing() -> None:
    statement = insert_ignoring_duplicates("postgresql", Payload)

    compiled = str(statement.compile(dialect=registry.load("postgresql")()))

    assert "ON CONFLICT DO NOTHING" in compiled

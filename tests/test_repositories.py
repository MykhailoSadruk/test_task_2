from sqlalchemy.ext.asyncio import AsyncSession

from app.dtos import PayloadDto, TransformedStringDto
from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
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


async def test_get_many_with_more_strings_than_one_chunk(
    session: AsyncSession,
) -> None:
    entries = {f"s{index}": f"S{index}" for index in range(10_500)}
    repository = await stored(session, **entries)

    assert as_dict(await repository.get_many(list(entries))) == entries


async def test_add_and_get_many_beyond_sqlite_variable_limit(
    session: AsyncSession,
) -> None:
    entries = {f"s{index}": f"S{index}" for index in range(40_000)}
    repository = await stored(session, **entries)

    assert as_dict(await repository.get_many(list(entries))) == entries

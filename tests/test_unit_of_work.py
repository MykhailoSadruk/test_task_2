import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dtos import PayloadDto, TransformedStringDto
from app.infrastructure.unit_of_work import UnitOfWork


async def test_changes_are_lost_without_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with UnitOfWork(session_factory) as unit_of_work:
        await unit_of_work.payloads.add(PayloadDto(id="abc", output="A"))
        await unit_of_work.transformed_strings.add_many(
            [TransformedStringDto(original="a", transformed="A")]
        )

    async with UnitOfWork(session_factory) as unit_of_work:
        assert await unit_of_work.payloads.get("abc") is None
        assert await unit_of_work.transformed_strings.get_many(["a"]) == []


async def test_commit_keeps_changes_of_both_repositories(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with UnitOfWork(session_factory) as unit_of_work:
        await unit_of_work.payloads.add(PayloadDto(id="abc", output="A"))
        await unit_of_work.transformed_strings.add_many(
            [TransformedStringDto(original="a", transformed="A")]
        )
        await unit_of_work.commit()

    async with UnitOfWork(session_factory) as unit_of_work:
        assert await unit_of_work.payloads.get("abc") == PayloadDto(
            id="abc", output="A"
        )
        assert await unit_of_work.transformed_strings.get_many(["a"]) == [
            TransformedStringDto(original="a", transformed="A")
        ]


async def test_exception_rolls_back_uncommitted_changes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(RuntimeError):
        async with UnitOfWork(session_factory) as unit_of_work:
            await unit_of_work.payloads.add(PayloadDto(id="kept", output="K"))
            await unit_of_work.commit()
            await unit_of_work.payloads.add(PayloadDto(id="lost", output="L"))
            raise RuntimeError

    async with UnitOfWork(session_factory) as unit_of_work:
        assert await unit_of_work.payloads.get("kept") is not None
        assert await unit_of_work.payloads.get("lost") is None

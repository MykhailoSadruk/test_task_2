from sqlalchemy.ext.asyncio import AsyncSession

from app.dtos import PayloadDto, TransformedStringDto
from app.infrastructure.unit_of_work import UnitOfWork


async def test_commit_keeps_changes_of_both_repositories(
    session: AsyncSession,
) -> None:
    unit_of_work = UnitOfWork(session)
    await unit_of_work.payloads.add(PayloadDto(id="abc", output="A"))
    await unit_of_work.transformed_strings.add_many(
        [TransformedStringDto(original="a", transformed="A")]
    )

    await unit_of_work.commit()
    await session.rollback()

    assert await unit_of_work.payloads.get("abc") == PayloadDto(id="abc", output="A")
    assert await unit_of_work.transformed_strings.get_many(["a"]) == [
        TransformedStringDto(original="a", transformed="A")
    ]

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.dtos import PayloadDto, TransformedStringDto
from app.infrastructure.models import Payload, TransformedString


class TransformedStringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_many(self, strings: Iterable[str]) -> list[TransformedStringDto]:
        statement = select(TransformedString).where(
            TransformedString.original.in_(list(strings))
        )
        entries = await self._session.scalars(statement)
        return [
            TransformedStringDto(original=row.original, transformed=row.transformed)
            for row in entries
        ]

    async def add_many(self, entries: Iterable[TransformedStringDto]) -> None:
        self._session.add_all(
            TransformedString(original=entry.original, transformed=entry.transformed)
            for entry in entries
        )
        await self._session.commit()


class PayloadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, payload_id: str) -> PayloadDto | None:
        payload = await self._session.get(Payload, payload_id)
        if payload is None:
            return None
        return PayloadDto(id=payload.id, output=payload.output)

    async def add(self, payload: PayloadDto) -> None:
        self._session.add(Payload(id=payload.id, output=payload.output))
        await self._session.commit()

from collections.abc import Iterable
from itertools import batched

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.dtos import PayloadDto, TransformedStringDto
from app.infrastructure.models import Payload, TransformedString

LOOKUP_CHUNK_SIZE = 500


class TransformedStringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_many(self, strings: Iterable[str]) -> list[TransformedStringDto]:
        found: list[TransformedStringDto] = []
        for chunk in batched(dict.fromkeys(strings), LOOKUP_CHUNK_SIZE):
            found.extend(await self._find(chunk))
        return found

    async def _find(self, originals: tuple[str, ...]) -> list[TransformedStringDto]:
        statement = select(TransformedString).where(
            TransformedString.original.in_(originals)
        )
        rows = await self._session.scalars(statement)
        return [TransformedStringDto(row.original, row.transformed) for row in rows]

    async def add_many(self, entries: Iterable[TransformedStringDto]) -> None:
        rows = [
            {"original": entry.original, "transformed": entry.transformed}
            for entry in entries
        ]
        if rows:
            await self._session.execute(
                insert(TransformedString).on_conflict_do_nothing(), rows
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
        await self._session.execute(
            insert(Payload).on_conflict_do_nothing(),
            {"id": payload.id, "output": payload.output},
        )
        await self._session.commit()

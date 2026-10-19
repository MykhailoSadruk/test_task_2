from collections.abc import Iterable
from itertools import batched

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.dtos import PayloadDto, TransformedStringDto
from app.infrastructure.models import Payload, TransformedString

# SQLite caps bound parameters per statement (32766 since 3.32), so large
# batches are split into chunks that stay well below that limit.
LOOKUP_CHUNK_SIZE = 10_000
INSERT_CHUNK_SIZE = 10_000


class TransformedStringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_many(self, strings: Iterable[str]) -> list[TransformedStringDto]:
        found: list[TransformedStringDto] = []
        for chunk in batched(dict.fromkeys(strings), LOOKUP_CHUNK_SIZE):
            found.extend(await self._find(chunk))
        return found

    async def _find(self, originals: tuple[str, ...]) -> list[TransformedStringDto]:
        statement = select(
            TransformedString.original, TransformedString.transformed
        ).where(TransformedString.original.in_(originals))
        rows = await self._session.execute(statement)
        return [
            TransformedStringDto(original, transformed)
            for original, transformed in rows
        ]

    async def add_many(self, entries: Iterable[TransformedStringDto]) -> None:
        # A concurrent request may have just stored the same string. Its value is
        # identical, so skipping the duplicate is safe and avoids a failed insert.
        connection = await self._session.connection()
        for chunk in batched(entries, INSERT_CHUNK_SIZE):
            rows = [
                {"original": entry.original, "transformed": entry.transformed}
                for entry in chunk
            ]
            await connection.execute(
                insert(TransformedString).on_conflict_do_nothing(), rows
            )


class PayloadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, payload_id: str) -> PayloadDto | None:
        payload = await self._session.get(Payload, payload_id)
        if payload is None:
            return None
        return PayloadDto(id=payload.id, output=payload.output)

    async def add(self, payload: PayloadDto) -> None:
        # The id is derived from the content, so an existing row already holds
        # the same output; ignoring the conflict keeps simultaneous identical
        # requests from failing.
        await self._session.execute(
            insert(Payload).on_conflict_do_nothing(),
            {"id": payload.id, "output": payload.output},
        )

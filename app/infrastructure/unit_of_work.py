from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
)


class UnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.payloads = PayloadRepository(session)
        self.transformed_strings = TransformedStringRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

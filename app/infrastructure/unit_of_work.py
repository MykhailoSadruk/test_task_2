from typing import Self

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.exceptions import DatabaseUnavailableError
from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
)


class UnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.payloads = PayloadRepository(self._session)
        self.transformed_strings = TransformedStringRepository(self._session)
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, *args: object
    ) -> None:
        if exc_type:
            await self.rollback()
        await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def ping(self) -> None:
        try:
            await self._session.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError from error

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.infrastructure.database import create_tables
from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
)
from app.services.interfaces import Transformer
from app.services.payloads import PayloadService

LIST_1 = [f"first {index}" for index in range(20)]
LIST_2 = [f"second {index}" for index in range(20)]


class SlowTransformer(Transformer):
    async def transform(self, text: str) -> str:
        await asyncio.sleep(0.05)
        return text.upper()


async def test_identical_payloads_created_concurrently(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'race.db'}")
    await create_tables(engine)

    async def create_payload() -> str:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            service = PayloadService(
                PayloadRepository(session),
                TransformedStringRepository(session),
                SlowTransformer(),
            )
            return await service.create(LIST_1, LIST_2)

    ids = await asyncio.gather(*(create_payload() for _ in range(5)))
    await engine.dispose()

    assert len(set(ids)) == 1

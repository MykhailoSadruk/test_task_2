import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.infrastructure.database import create_database_engine, create_tables
from app.infrastructure.unit_of_work import UnitOfWork
from app.services.interfaces import Transformer
from app.services.payloads import PayloadService

LIST_1 = [f"first {index}" for index in range(20)]
LIST_2 = [f"second {index}" for index in range(20)]


class SlowTransformer(Transformer):
    async def transform(self, text: str) -> str:
        await asyncio.sleep(0.05)
        return text.upper()


class QuickTransformer(Transformer):
    async def transform(self, text: str) -> str:
        await asyncio.sleep(0.001)
        return text.upper()


async def test_identical_payloads_created_concurrently(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+aiosqlite:///{tmp_path / 'race.db'}")
    await create_tables(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_payload() -> str:
        service = PayloadService(UnitOfWork(session_factory), SlowTransformer())
        return await service.create(LIST_1, LIST_2)

    ids = await asyncio.gather(*(create_payload() for _ in range(5)))
    await engine.dispose()

    assert len(set(ids)) == 1


async def test_many_writers_with_different_payloads(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+aiosqlite:///{tmp_path / 'writers.db'}")
    await create_tables(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_payload(worker: int) -> tuple[int, str, str]:
        list_1 = [f"w{worker} a{index}" for index in range(300)]
        list_2 = [f"w{worker} b{index}" for index in range(300)]
        service = PayloadService(UnitOfWork(session_factory), QuickTransformer())
        payload_id = await service.create(list_1, list_2)
        return worker, payload_id, await service.get_output(payload_id)

    results = await asyncio.gather(*(create_payload(worker) for worker in range(20)))
    await engine.dispose()

    assert len({payload_id for _, payload_id, _ in results}) == 20
    for worker, _, output in results:
        words = output.split(", ")
        assert len(words) == 600
        assert words[0] == f"W{worker} A0"

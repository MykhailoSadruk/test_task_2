import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.infrastructure.database import create_database_engine, create_tables
from app.infrastructure.unit_of_work import UnitOfWork
from app.services.interfaces import Transformer
from app.services.payloads import PayloadService
from app.services.single_flight import SingleFlightTransformer

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


class InFlightTransformer(Transformer):
    def __init__(self) -> None:
        self.in_flight = 0
        self.max_in_flight = 0

    async def transform(self, text: str) -> str:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.001)
        self.in_flight -= 1
        return text.upper()


async def test_transformer_limit_is_shared_between_requests(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+aiosqlite:///{tmp_path / 'limit.db'}")
    await create_tables(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    transformer = InFlightTransformer()
    limiter = asyncio.Semaphore(3)

    async def create_payload(request: int) -> str:
        service = PayloadService(
            UnitOfWork(session_factory),
            transformer,
            max_concurrency=10,
            transformer_limiter=limiter,
        )
        list_1 = [f"r{request} a{index}" for index in range(40)]
        list_2 = [f"r{request} b{index}" for index in range(40)]
        return await service.create(list_1, list_2)

    await asyncio.gather(*(create_payload(request) for request in range(5)))
    await engine.dispose()

    assert transformer.max_in_flight == 3


class CallRecordingTransformer(Transformer):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def transform(self, text: str) -> str:
        self.calls.append(text)
        await asyncio.sleep(0.02)
        return text.upper()


async def test_requests_share_calls_for_the_same_new_strings(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+aiosqlite:///{tmp_path / 'flight.db'}")
    await create_tables(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    recorder = CallRecordingTransformer()
    shared_transformer = SingleFlightTransformer(recorder)

    async def create_payload(list_1: list[str], list_2: list[str]) -> str:
        service = PayloadService(UnitOfWork(session_factory), shared_transformer)
        return await service.create(list_1, list_2)

    await asyncio.gather(
        create_payload(["a", "b", "c"], ["d", "e", "f"]),
        create_payload(["c", "d", "e"], ["f", "g", "h"]),
        create_payload(["a", "g", "h"], ["x", "y", "z"]),
    )
    await engine.dispose()

    assert len(recorder.calls) == len(set(recorder.calls))
    assert set(recorder.calls) == set("abcdefghxyz")

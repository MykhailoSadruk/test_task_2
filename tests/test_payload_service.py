import asyncio
import logging

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.exceptions import PayloadNotFoundError, TransformerError
from app.infrastructure.transformer import UppercaseTransformer
from app.infrastructure.unit_of_work import UnitOfWork
from app.services.interfaces import Transformer
from app.services.payloads import (
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_TRANSFORM_ATTEMPTS,
    DEFAULT_TRANSFORM_TIMEOUT_SECONDS,
    PayloadService,
)


class CountingTransformer(Transformer):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def transform(self, text: str) -> str:
        self.calls.append(text)
        return text.upper()


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()


@pytest.fixture
def service(
    session_factory: async_sessionmaker[AsyncSession], transformer: CountingTransformer
) -> PayloadService:
    return PayloadService(
        UnitOfWork(session_factory),
        transformer,
    )


async def test_transform_uppercases_text() -> None:
    assert await UppercaseTransformer().transform("abc") == "ABC"


async def test_output_is_interleaved(service: PayloadService) -> None:
    payload_id = (await service.create(["a", "b"], ["x", "y"])).id

    assert await service.get_output(payload_id) == "A, X, B, Y"


async def test_cache_is_reused_across_payloads(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    await service.create(["a", "b"], ["x", "y"])
    transformer.calls.clear()

    await service.create(["a", "c"], ["x", "z"])

    assert sorted(transformer.calls) == ["c", "z"]


async def test_repeated_payload_does_not_call_transformer(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    first_id = (await service.create(["a"], ["b"])).id
    transformer.calls.clear()

    second_id = (await service.create(["a"], ["b"])).id

    assert second_id == first_id
    assert transformer.calls == []


async def test_duplicate_strings_are_transformed_once(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    payload_id = (await service.create(["a", "a"], ["a", "b"])).id

    assert sorted(transformer.calls) == ["a", "b"]
    assert await service.get_output(payload_id) == "A, A, A, B"


async def test_unknown_id_raises(service: PayloadService) -> None:
    with pytest.raises(PayloadNotFoundError) as raised:
        await service.get_output("missing")

    assert raised.value.payload_id == "missing"


class BarrierTransformer(Transformer):
    def __init__(self, expected_calls: int) -> None:
        self._expected_calls = expected_calls
        self._started = 0
        self._all_started = asyncio.Event()

    async def transform(self, text: str) -> str:
        self._started += 1
        if self._started == self._expected_calls:
            self._all_started.set()
        await self._all_started.wait()
        return text.upper()


async def test_unique_strings_are_transformed_concurrently(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = PayloadService(
        UnitOfWork(session_factory),
        BarrierTransformer(expected_calls=4),
    )

    async with asyncio.timeout(2):
        payload_id = (await service.create(["a", "b"], ["c", "d"])).id

    assert await service.get_output(payload_id) == "A, C, B, D"


class InFlightTransformer(Transformer):
    def __init__(self) -> None:
        self.in_flight = 0
        self.max_in_flight = 0

    async def transform(self, text: str) -> str:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)
        self.in_flight -= 1
        return text.upper()


async def test_concurrency_is_limited(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    transformer = InFlightTransformer()
    service = PayloadService(
        UnitOfWork(session_factory),
        transformer,
        max_concurrency=2,
    )

    await service.create(["a", "b", "c"], ["d", "e", "f"])

    assert transformer.max_in_flight == 2


async def test_many_strings_stay_within_concurrency_limit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    transformer = InFlightTransformer()
    service = PayloadService(
        UnitOfWork(session_factory),
        transformer,
        max_concurrency=5,
    )
    list_1 = [f"a{index}" for index in range(500)]
    list_2 = [f"b{index}" for index in range(500)]

    await service.create(list_1, list_2)

    assert transformer.max_in_flight == 5


async def test_many_repeated_strings_are_transformed_once(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    list_1 = [f"s{index % 50}" for index in range(500)]
    list_2 = [f"s{index % 70}" for index in range(500)]

    await service.create(list_1, list_2)

    assert len(transformer.calls) == len(set(transformer.calls)) == 70


class FailingTransformer(Transformer):
    def __init__(self, failing_texts: set[str], delay: float = 0.0) -> None:
        self.calls: list[str] = []
        self._failing_texts = failing_texts
        self._delay = delay

    async def transform(self, text: str) -> str:
        self.calls.append(text)
        await asyncio.sleep(self._delay)
        if text in self._failing_texts:
            raise RuntimeError(text)
        return text.upper()


class FlakyTransformer(Transformer):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def transform(self, text: str) -> str:
        self.calls.append(text)
        if self.calls.count(text) == 1:
            raise RuntimeError(text)
        return text.upper()


class SlowTransformer(Transformer):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def transform(self, text: str) -> str:
        self.calls.append(text)
        await asyncio.sleep(5)
        return text.upper()


def build_service(
    session_factory: async_sessionmaker[AsyncSession],
    transformer: Transformer,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    transform_timeout: float = DEFAULT_TRANSFORM_TIMEOUT_SECONDS,
    transform_attempts: int = DEFAULT_TRANSFORM_ATTEMPTS,
) -> PayloadService:
    return PayloadService(
        UnitOfWork(session_factory),
        transformer,
        max_concurrency,
        transform_timeout,
        transform_attempts,
    )


async def test_transformer_failure_raises_and_keeps_finished_work(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    failing = build_service(
        session_factory,
        FailingTransformer({"bad"}),
        max_concurrency=1,
        transform_attempts=1,
    )

    with pytest.raises(TransformerError):
        await failing.create(["a", "bad"], ["b", "c"])

    healthy = CountingTransformer()
    await build_service(session_factory, healthy).create(["a", "bad"], ["b", "c"])
    assert healthy.calls == ["bad", "c"]


async def test_failure_stops_remaining_workers(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    transformer = FailingTransformer({"bad"}, delay=0.01)
    service = build_service(
        session_factory, transformer, max_concurrency=3, transform_attempts=1
    )
    texts = [f"t{index}" for index in range(50)]

    with pytest.raises(TransformerError):
        await service.create(["bad", *texts], [*texts, "last"])

    assert len(transformer.calls) < 50


async def test_transient_failure_is_retried(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    transformer = FlakyTransformer()
    service = build_service(session_factory, transformer, transform_attempts=2)

    payload_id = (await service.create(["a"], ["b"])).id

    assert await service.get_output(payload_id) == "A, B"
    assert sorted(transformer.calls) == ["a", "a", "b", "b"]


async def test_timeout_raises_transformer_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    transformer = SlowTransformer()
    service = build_service(
        session_factory,
        transformer,
        max_concurrency=1,
        transform_timeout=0.05,
        transform_attempts=2,
    )

    with pytest.raises(TransformerError):
        await service.create(["a"], ["b"])

    assert transformer.calls == ["a", "a"]


async def test_results_are_saved_in_batches(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_sizes: list[int] = []
    original_save = PayloadService._save_transformed

    async def spy_save(
        self: PayloadService, transformed_by_text: dict[str, str]
    ) -> None:
        saved_sizes.append(len(transformed_by_text))
        await original_save(self, transformed_by_text)

    monkeypatch.setattr("app.services.payloads.SAVE_BATCH_SIZE", 2)
    monkeypatch.setattr(PayloadService, "_save_transformed", spy_save)
    service = build_service(session_factory, CountingTransformer())

    await service.create(["a", "b", "c"], ["f", "g", "h"])

    assert saved_sizes == [2, 2, 2]


async def test_failure_keeps_batches_saved_before_it(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.payloads.SAVE_BATCH_SIZE", 2)
    failing = build_service(
        session_factory,
        FailingTransformer({"e"}),
        max_concurrency=1,
        transform_attempts=1,
    )

    with pytest.raises(TransformerError):
        await failing.create(["a", "b", "c"], ["d", "e", "f"])

    healthy = CountingTransformer()
    await build_service(session_factory, healthy).create(
        ["a", "b", "c"], ["d", "e", "f"]
    )
    assert healthy.calls == ["e", "c", "f"]


async def test_cache_hits_and_misses_are_logged(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.services.payloads")
    service = build_service(session_factory, CountingTransformer())
    await service.create(["a", "b"], ["c", "d"])

    await service.create(["a", "e"], ["c", "f"])

    messages = [record.getMessage() for record in caplog.records]
    assert "Cache: 0 hits, 4 to transform" in messages
    assert "Cache: 2 hits, 2 to transform" in messages


async def test_repeated_payload_is_logged_as_reused(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.services.payloads")
    service = build_service(session_factory, CountingTransformer())
    payload_id = (await service.create(["a"], ["b"])).id

    await service.create(["a"], ["b"])

    messages = [record.getMessage() for record in caplog.records]
    assert f"Payload {payload_id} already exists, reusing it" in messages


async def test_transformer_failures_are_logged(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="app.services.payloads")
    service = build_service(
        session_factory,
        FailingTransformer({"bad"}),
        max_concurrency=1,
        transform_attempts=2,
    )

    with pytest.raises(TransformerError):
        await service.create(["bad"], ["ok"])

    levels = [record.levelname for record in caplog.records]
    assert levels == ["WARNING", "WARNING", "ERROR"]

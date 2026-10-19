import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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
def service(session: AsyncSession, transformer: CountingTransformer) -> PayloadService:
    return PayloadService(
        UnitOfWork(session),
        transformer,
    )


async def test_transform_uppercases_text() -> None:
    assert await UppercaseTransformer().transform("abc") == "ABC"


async def test_output_is_interleaved(service: PayloadService) -> None:
    payload_id = await service.create(["a", "b"], ["x", "y"])

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
    first_id = await service.create(["a"], ["b"])
    transformer.calls.clear()

    second_id = await service.create(["a"], ["b"])

    assert second_id == first_id
    assert transformer.calls == []


async def test_duplicate_strings_are_transformed_once(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    payload_id = await service.create(["a", "a"], ["a", "b"])

    assert sorted(transformer.calls) == ["a", "b"]
    assert await service.get_output(payload_id) == "A, A, A, B"


async def test_unknown_id_raises(service: PayloadService) -> None:
    with pytest.raises(PayloadNotFoundError):
        await service.get_output("missing")


async def test_unequal_lengths_raise(service: PayloadService) -> None:
    with pytest.raises(ValueError):
        await service.create(["a"], ["b", "c"])


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
    session: AsyncSession,
) -> None:
    service = PayloadService(
        UnitOfWork(session),
        BarrierTransformer(expected_calls=4),
    )

    async with asyncio.timeout(2):
        payload_id = await service.create(["a", "b"], ["c", "d"])

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


async def test_concurrency_is_limited(session: AsyncSession) -> None:
    transformer = InFlightTransformer()
    service = PayloadService(
        UnitOfWork(session),
        transformer,
        max_concurrency=2,
    )

    await service.create(["a", "b", "c"], ["d", "e", "f"])

    assert transformer.max_in_flight == 2


async def test_many_strings_stay_within_concurrency_limit(
    session: AsyncSession,
) -> None:
    transformer = InFlightTransformer()
    service = PayloadService(
        UnitOfWork(session),
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
    session: AsyncSession,
    transformer: Transformer,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    transform_timeout: float = DEFAULT_TRANSFORM_TIMEOUT_SECONDS,
    transform_attempts: int = DEFAULT_TRANSFORM_ATTEMPTS,
) -> PayloadService:
    return PayloadService(
        UnitOfWork(session),
        transformer,
        max_concurrency,
        transform_timeout,
        transform_attempts,
    )


async def test_transformer_failure_raises_and_keeps_finished_work(
    session: AsyncSession,
) -> None:
    failing = build_service(
        session,
        FailingTransformer({"bad"}),
        max_concurrency=1,
        transform_attempts=1,
    )

    with pytest.raises(TransformerError):
        await failing.create(["a", "bad"], ["b", "c"])

    healthy = CountingTransformer()
    await build_service(session, healthy).create(["a", "bad"], ["b", "c"])
    assert healthy.calls == ["bad", "c"]


async def test_failure_stops_remaining_workers(session: AsyncSession) -> None:
    transformer = FailingTransformer({"bad"}, delay=0.01)
    service = build_service(
        session, transformer, max_concurrency=3, transform_attempts=1
    )
    texts = [f"t{index}" for index in range(50)]

    with pytest.raises(TransformerError):
        await service.create(["bad", *texts], [*texts, "last"])

    assert len(transformer.calls) < 50


async def test_transient_failure_is_retried(session: AsyncSession) -> None:
    transformer = FlakyTransformer()
    service = build_service(session, transformer, transform_attempts=2)

    payload_id = await service.create(["a"], ["b"])

    assert await service.get_output(payload_id) == "A, B"
    assert sorted(transformer.calls) == ["a", "a", "b", "b"]


async def test_timeout_raises_transformer_error(session: AsyncSession) -> None:
    transformer = SlowTransformer()
    service = build_service(
        session,
        transformer,
        max_concurrency=1,
        transform_timeout=0.05,
        transform_attempts=2,
    )

    with pytest.raises(TransformerError):
        await service.create(["a"], ["b"])

    assert transformer.calls == ["a", "a"]

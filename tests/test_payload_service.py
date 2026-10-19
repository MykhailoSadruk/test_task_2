import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import PayloadNotFoundError
from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
)
from app.infrastructure.transformer import UppercaseTransformer
from app.services.interfaces import Transformer
from app.services.payloads import PayloadService


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
        PayloadRepository(session),
        TransformedStringRepository(session),
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
        PayloadRepository(session),
        TransformedStringRepository(session),
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
        PayloadRepository(session),
        TransformedStringRepository(session),
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
        PayloadRepository(session),
        TransformedStringRepository(session),
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

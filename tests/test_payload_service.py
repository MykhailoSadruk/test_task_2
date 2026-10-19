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

    def transform(self, text: str) -> str:
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
    assert UppercaseTransformer().transform("abc") == "ABC"


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

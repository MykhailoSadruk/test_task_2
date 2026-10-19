from collections.abc import Iterable
from typing import Self

import pytest

from app.dtos import PayloadDto, TransformedStringDto
from app.exceptions import PayloadNotFoundError
from app.services.interfaces import Transformer
from app.services.payloads import PayloadService


class InMemoryPayloadStore:
    def __init__(self) -> None:
        self.rows: dict[str, PayloadDto] = {}

    async def get(self, payload_id: str) -> PayloadDto | None:
        return self.rows.get(payload_id)

    async def add(self, payload: PayloadDto) -> None:
        self.rows.setdefault(payload.id, payload)


class InMemoryTransformedStringStore:
    def __init__(self) -> None:
        self.rows: dict[str, str] = {}

    async def get_many(self, strings: Iterable[str]) -> list[TransformedStringDto]:
        return [
            TransformedStringDto(text, self.rows[text])
            for text in strings
            if text in self.rows
        ]

    async def add_many(self, entries: Iterable[TransformedStringDto]) -> None:
        for entry in entries:
            self.rows.setdefault(entry.original, entry.transformed)


class InMemoryUnitOfWork:
    def __init__(self) -> None:
        self.payloads = InMemoryPayloadStore()
        self.transformed_strings = InMemoryTransformedStringStore()
        self.commits = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, *args: object
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class CountingTransformer(Transformer):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def transform(self, text: str) -> str:
        self.calls.append(text)
        return text.upper()


async def test_service_works_with_in_memory_storage() -> None:
    unit_of_work = InMemoryUnitOfWork()
    transformer = CountingTransformer()
    service = PayloadService(unit_of_work, transformer)

    first = await service.create(["a", "b"], ["c", "d"])
    second = await service.create(["a", "b"], ["c", "d"])

    payload_id = first.id
    assert (first.created, second.created) == (True, False)
    assert second.id == payload_id
    assert await service.get_output(payload_id) == "A, C, B, D"
    assert sorted(transformer.calls) == ["a", "b", "c", "d"]
    assert unit_of_work.commits == 2


async def test_unknown_payload_raises_with_in_memory_storage() -> None:
    service = PayloadService(InMemoryUnitOfWork(), CountingTransformer())

    with pytest.raises(PayloadNotFoundError):
        await service.get_output("missing")

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Protocol, Self

from app.dtos import PayloadDto, TransformedStringDto


class Transformer(ABC):
    @abstractmethod
    async def transform(self, text: str) -> str:
        """Return the transformed form of a single string."""


class PayloadStore(Protocol):
    async def get(self, payload_id: str) -> PayloadDto | None: ...

    async def add(self, payload: PayloadDto) -> None: ...


class TransformedStringStore(Protocol):
    async def get_many(self, strings: Iterable[str]) -> list[TransformedStringDto]: ...

    async def add_many(self, entries: Iterable[TransformedStringDto]) -> None: ...


class StorageUnitOfWork(Protocol):
    @property
    def payloads(self) -> PayloadStore: ...

    @property
    def transformed_strings(self) -> TransformedStringStore: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self, exc_type: type[BaseException] | None, *args: object
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

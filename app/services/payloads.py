import asyncio
import hashlib
import json

from app.dtos import PayloadDto, TransformedStringDto
from app.exceptions import PayloadNotFoundError
from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
)
from app.services.interfaces import Transformer

DEFAULT_MAX_CONCURRENCY = 10


class PayloadService:
    def __init__(
        self,
        payloads: PayloadRepository,
        transformed_strings: TransformedStringRepository,
        transformer: Transformer,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self._payloads = payloads
        self._transformed_strings = transformed_strings
        self._transformer = transformer
        self._max_concurrency = max_concurrency

    async def create(self, list_1: list[str], list_2: list[str]) -> str:
        if len(list_1) != len(list_2):
            raise ValueError("Lists must have the same length")
        payload_id = self._compute_payload_id(list_1, list_2)
        if await self._payloads.get(payload_id) is not None:
            return payload_id
        strings = self._interleave(list_1, list_2)
        mapping = await self._transform_all(strings)
        output = ", ".join(mapping[text] for text in strings)
        await self._payloads.add(PayloadDto(id=payload_id, output=output))
        return payload_id

    async def get_output(self, payload_id: str) -> str:
        payload = await self._payloads.get(payload_id)
        if payload is None:
            raise PayloadNotFoundError(payload_id)
        return payload.output

    async def _transform_all(self, strings: list[str]) -> dict[str, str]:
        cached = await self._load_cached(strings)
        missing = [text for text in dict.fromkeys(strings) if text not in cached]
        return cached | await self._transform_missing(missing)

    async def _load_cached(self, strings: list[str]) -> dict[str, str]:
        entries = await self._transformed_strings.get_many(strings)
        return {entry.original: entry.transformed for entry in entries}

    async def _transform_missing(self, texts: list[str]) -> dict[str, str]:
        semaphore = asyncio.Semaphore(self._max_concurrency)
        results = await asyncio.gather(
            *(self._transform_limited(semaphore, text) for text in texts)
        )
        created = dict(zip(texts, results))
        await self._transformed_strings.add_many(
            TransformedStringDto(original, transformed)
            for original, transformed in created.items()
        )
        return created

    async def _transform_limited(self, semaphore: asyncio.Semaphore, text: str) -> str:
        async with semaphore:
            return await self._transformer.transform(text)

    @staticmethod
    def _compute_payload_id(list_1: list[str], list_2: list[str]) -> str:
        canonical = json.dumps(
            [list_1, list_2], ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _interleave(list_1: list[str], list_2: list[str]) -> list[str]:
        return [text for pair in zip(list_1, list_2) for text in pair]

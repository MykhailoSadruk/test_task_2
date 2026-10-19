import asyncio
import hashlib
import json
from collections.abc import Iterator

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
        # Workers share one iterator, so every text is transformed exactly once
        # and at most max_concurrency calls run at the same time, without
        # creating one task per text.
        texts_to_transform = iter(texts)
        transformed_by_text: dict[str, str] = {}
        workers = [
            self._transform_until_empty(texts_to_transform, transformed_by_text)
            for _ in range(self._max_concurrency)
        ]
        await asyncio.gather(*workers)
        await self._save_transformed(transformed_by_text)
        return transformed_by_text

    async def _transform_until_empty(
        self, texts_to_transform: Iterator[str], transformed_by_text: dict[str, str]
    ) -> None:
        for text in texts_to_transform:
            transformed_by_text[text] = await self._transformer.transform(text)

    async def _save_transformed(self, transformed_by_text: dict[str, str]) -> None:
        await self._transformed_strings.add_many(
            TransformedStringDto(original, transformed)
            for original, transformed in transformed_by_text.items()
        )

    @staticmethod
    def _compute_payload_id(list_1: list[str], list_2: list[str]) -> str:
        # Canonical JSON (no whitespace, raw unicode) depends only on the content,
        # so identical input always yields the same id and a repeated request can
        # reuse the stored payload. Hashing keeps the id short for any input size.
        canonical = json.dumps(
            [list_1, list_2], ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _interleave(list_1: list[str], list_2: list[str]) -> list[str]:
        return [text for pair in zip(list_1, list_2) for text in pair]

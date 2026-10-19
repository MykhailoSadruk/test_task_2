import asyncio
import hashlib
import json

from app.exceptions import PayloadNotFoundError
from app.infrastructure.dtos import PayloadDto, TransformedStringDto
from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
)
from app.services.interfaces import Transformer


class PayloadService:
    def __init__(
        self,
        payloads: PayloadRepository,
        transformed_strings: TransformedStringRepository,
        transformer: Transformer,
    ) -> None:
        self._payloads = payloads
        self._transformed_strings = transformed_strings
        self._transformer = transformer

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
        unique = list(dict.fromkeys(strings))
        mapping = {
            entry.original: entry.transformed
            for entry in await self._transformed_strings.get_many(unique)
        }
        pending = [text for text in unique if text not in mapping]
        transformed = await asyncio.gather(
            *(self._transformer.transform(text) for text in pending)
        )
        new_entries = [
            TransformedStringDto(text, result)
            for text, result in zip(pending, transformed)
        ]
        await self._transformed_strings.add_many(new_entries)
        mapping.update({entry.original: entry.transformed for entry in new_entries})
        return mapping

    @staticmethod
    def _compute_payload_id(list_1: list[str], list_2: list[str]) -> str:
        canonical = json.dumps(
            [list_1, list_2], ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _interleave(list_1: list[str], list_2: list[str]) -> list[str]:
        return [text for pair in zip(list_1, list_2) for text in pair]

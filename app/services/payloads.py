import hashlib
import json
from collections.abc import Callable

from app.infrastructure.dtos import PayloadDto, TransformedStringDto
from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
)


class PayloadNotFoundError(Exception):
    pass


def compute_payload_id(list_1: list[str], list_2: list[str]) -> str:
    canonical = json.dumps([list_1, list_2], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def interleave(list_1: list[str], list_2: list[str]) -> list[str]:
    return [text for pair in zip(list_1, list_2) for text in pair]


class PayloadService:
    def __init__(
        self,
        payloads: PayloadRepository,
        transformed_strings: TransformedStringRepository,
        transformer: Callable[[str], str],
    ) -> None:
        self._payloads = payloads
        self._transformed_strings = transformed_strings
        self._transformer = transformer

    def create(self, list_1: list[str], list_2: list[str]) -> str:
        if len(list_1) != len(list_2):
            raise ValueError("Lists must have the same length")
        payload_id = compute_payload_id(list_1, list_2)
        if self._payloads.get(payload_id) is not None:
            return payload_id
        mapping = self._transform_all(interleave(list_1, list_2))
        output = ", ".join(mapping[text] for text in interleave(list_1, list_2))
        self._payloads.add(PayloadDto(id=payload_id, output=output))
        return payload_id

    def get_output(self, payload_id: str) -> str:
        payload = self._payloads.get(payload_id)
        if payload is None:
            raise PayloadNotFoundError(payload_id)
        return payload.output

    def _transform_all(self, strings: list[str]) -> dict[str, str]:
        unique = list(dict.fromkeys(strings))
        mapping = {
            entry.original: entry.transformed
            for entry in self._transformed_strings.get_many(unique)
        }
        new_entries = [
            TransformedStringDto(text, self._transformer(text))
            for text in unique
            if text not in mapping
        ]
        self._transformed_strings.add_many(new_entries)
        mapping.update({entry.original: entry.transformed for entry in new_entries})
        return mapping

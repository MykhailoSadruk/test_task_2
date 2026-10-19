import asyncio
import hashlib
import json
import logging
from collections.abc import Iterator
from itertools import batched

from app.dtos import PayloadCreationDto, PayloadDto, TransformedStringDto
from app.exceptions import PayloadNotFoundError, TransformerError
from app.services.interfaces import StorageUnitOfWork, Transformer

logger = logging.getLogger(__name__)

SAVE_BATCH_SIZE = 10_000
DEFAULT_MAX_CONCURRENCY = 10
DEFAULT_TRANSFORM_TIMEOUT_SECONDS = 30.0
DEFAULT_TRANSFORM_ATTEMPTS = 2


class PayloadService:
    def __init__(
        self,
        unit_of_work: StorageUnitOfWork,
        transformer: Transformer,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        transform_timeout: float = DEFAULT_TRANSFORM_TIMEOUT_SECONDS,
        transform_attempts: int = DEFAULT_TRANSFORM_ATTEMPTS,
        transformer_limiter: asyncio.Semaphore | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._transformer = transformer
        self._max_concurrency = max_concurrency
        self._transform_timeout = transform_timeout
        self._transform_attempts = transform_attempts
        self._transformer_limiter = transformer_limiter or asyncio.Semaphore(
            max_concurrency
        )

    async def create(self, list_1: list[str], list_2: list[str]) -> PayloadCreationDto:
        if len(list_1) != len(list_2):
            raise ValueError("Lists must have the same length")
        payload_id = self._compute_payload_id(list_1, list_2)
        if await self._payload_exists(payload_id):
            logger.info("Payload %s already exists, reusing it", payload_id)
            return PayloadCreationDto(payload_id, created=False)
        strings = self._interleave(list_1, list_2)
        mapping = await self._transform_all(strings)
        output = ", ".join(mapping[text] for text in strings)
        await self._save_payload(PayloadDto(id=payload_id, output=output))
        return PayloadCreationDto(payload_id, created=True)

    async def get_output(self, payload_id: str) -> str:
        async with self._unit_of_work as uow:
            payload = await uow.payloads.get(payload_id)
        if payload is None:
            raise PayloadNotFoundError(payload_id)
        return payload.output

    async def _payload_exists(self, payload_id: str) -> bool:
        async with self._unit_of_work as uow:
            return await uow.payloads.get(payload_id) is not None

    async def _transform_all(self, strings: list[str]) -> dict[str, str]:
        cached = await self._load_cached(strings)
        missing = [text for text in dict.fromkeys(strings) if text not in cached]
        logger.info("Cache: %d hits, %d to transform", len(cached), len(missing))
        return cached | await self._transform_missing(missing)

    async def _load_cached(self, strings: list[str]) -> dict[str, str]:
        async with self._unit_of_work as uow:
            entries = await uow.transformed_strings.get_many(strings)
        return {entry.original: entry.transformed for entry in entries}

    async def _transform_missing(self, texts: list[str]) -> dict[str, str]:
        transformed_by_text: dict[str, str] = {}
        for batch in batched(texts, SAVE_BATCH_SIZE):
            transformed_by_text |= await self._transform_batch(batch)
        return transformed_by_text

    async def _transform_batch(self, texts: tuple[str, ...]) -> dict[str, str]:
        texts_to_transform = iter(texts)
        transformed_by_text: dict[str, str] = {}
        try:
            await self._run_workers(texts_to_transform, transformed_by_text)
        finally:
            # Each batch is saved as soon as it is done, and also when one of its
            # calls fails. The cache is valid on its own, so finished work is never
            # lost to a later error and a retry transforms only what is missing.
            await self._save_transformed(transformed_by_text)
        return transformed_by_text

    async def _run_workers(
        self, texts_to_transform: Iterator[str], transformed_by_text: dict[str, str]
    ) -> None:
        # Workers share one iterator, so every text is transformed exactly once
        # and at most max_concurrency calls run at the same time, without
        # creating one task per text. TaskGroup cancels the other workers as soon
        # as one fails, so a broken transformer is not called for the rest.
        try:
            async with asyncio.TaskGroup() as group:
                for _ in range(self._max_concurrency):
                    group.create_task(
                        self._transform_until_empty(
                            texts_to_transform, transformed_by_text
                        )
                    )
        except ExceptionGroup as failures:
            raise failures.exceptions[0] from None

    async def _transform_until_empty(
        self, texts_to_transform: Iterator[str], transformed_by_text: dict[str, str]
    ) -> None:
        for text in texts_to_transform:
            transformed_by_text[text] = await self._transform_with_retries(text)

    async def _transform_with_retries(self, text: str) -> str:
        attempts_left = self._transform_attempts
        while True:
            logger.debug("Transforming %r", text)
            try:
                # The limiter is shared by all requests, so the number of calls to
                # the transformer stays bounded however many requests are running.
                # Waiting for it is not counted against the call timeout.
                async with self._transformer_limiter:
                    async with asyncio.timeout(self._transform_timeout):
                        return await self._transformer.transform(text)
            except Exception as error:
                attempts_left -= 1
                logger.warning(
                    "Transformer failed for %r (%d attempts left): %r",
                    text[:50],
                    attempts_left,
                    error,
                )
                if attempts_left == 0:
                    logger.error("Giving up on %r", text[:50])
                    raise TransformerError(text) from error

    async def _save_transformed(self, transformed_by_text: dict[str, str]) -> None:
        logger.debug("Saving %d transformed strings", len(transformed_by_text))
        async with self._unit_of_work as uow:
            await uow.transformed_strings.add_many(
                TransformedStringDto(original, transformed)
                for original, transformed in transformed_by_text.items()
            )
            await uow.commit()

    async def _save_payload(self, payload: PayloadDto) -> None:
        # Separate transaction after the cache is committed: if saving the payload
        # fails, the transformed strings are already stored.
        async with self._unit_of_work as uow:
            await uow.payloads.add(payload)
            await uow.commit()

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

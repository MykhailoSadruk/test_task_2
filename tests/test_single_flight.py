import asyncio

import pytest

from app.services.interfaces import Transformer
from app.services.single_flight import SingleFlightTransformer


class SlowCountingTransformer(Transformer):
    def __init__(self, delay: float = 0.05, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.delay = delay
        self._fail = fail

    async def transform(self, text: str) -> str:
        self.calls.append(text)
        await asyncio.sleep(self.delay)
        if self._fail:
            raise RuntimeError(text)
        return text.upper()


async def test_concurrent_requests_for_one_text_call_transformer_once() -> None:
    inner = SlowCountingTransformer()
    transformer = SingleFlightTransformer(inner)

    results = await asyncio.gather(*(transformer.transform("a") for _ in range(5)))

    assert results == ["A"] * 5
    assert inner.calls == ["a"]


async def test_different_texts_are_transformed_separately() -> None:
    inner = SlowCountingTransformer()
    transformer = SingleFlightTransformer(inner)

    results = await asyncio.gather(
        transformer.transform("a"), transformer.transform("b")
    )

    assert list(results) == ["A", "B"]
    assert sorted(inner.calls) == ["a", "b"]


async def test_failure_reaches_every_waiter_and_is_not_remembered() -> None:
    failing = SlowCountingTransformer(fail=True)
    transformer = SingleFlightTransformer(failing)

    results = await asyncio.gather(
        *(transformer.transform("a") for _ in range(3)), return_exceptions=True
    )

    assert all(isinstance(result, RuntimeError) for result in results)
    assert failing.calls == ["a"]
    healthy = SingleFlightTransformer(SlowCountingTransformer())
    assert await healthy.transform("a") == "A"


async def test_cancelled_waiter_does_not_cancel_the_shared_call() -> None:
    inner = SlowCountingTransformer()
    transformer = SingleFlightTransformer(inner)
    leader = asyncio.create_task(transformer.transform("a"))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(transformer.transform("a"))
    await asyncio.sleep(0)

    waiter.cancel()

    assert await leader == "A"
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert inner.calls == ["a"]


async def test_cancelled_leader_fails_waiters_and_clears_the_entry() -> None:
    inner = SlowCountingTransformer(delay=1)
    transformer = SingleFlightTransformer(inner)
    leader = asyncio.create_task(transformer.transform("a"))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(transformer.transform("a"))
    await asyncio.sleep(0)

    leader.cancel()

    with pytest.raises(RuntimeError):
        await waiter
    with pytest.raises(asyncio.CancelledError):
        await leader
    inner.delay = 0
    assert await transformer.transform("a") == "A"

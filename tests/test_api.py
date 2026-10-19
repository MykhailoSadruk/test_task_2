from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.dependencies import get_transformer, get_unit_of_work
from app.infrastructure.unit_of_work import UnitOfWork
from app.main import get_app
from app.services.interfaces import Transformer

SAMPLE = {
    "list_1": ["first string", "second string", "third string"],
    "list_2": ["other string", "another string", "last string"],
}
SAMPLE_OUTPUT = (
    "FIRST STRING, OTHER STRING, SECOND STRING, "
    "ANOTHER STRING, THIRD STRING, LAST STRING"
)


class CountingTransformer(Transformer):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def transform(self, text: str) -> str:
        self.calls.append(text)
        return text.upper()


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession], transformer: CountingTransformer
) -> AsyncIterator[AsyncClient]:
    app = get_app()
    app.dependency_overrides[get_unit_of_work] = lambda: UnitOfWork(session_factory)
    app.dependency_overrides[get_transformer] = lambda: transformer
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client


async def test_sample_payload_round_trip(client: AsyncClient) -> None:
    created = await client.post("/payload", json=SAMPLE)

    assert created.status_code == 201
    payload_id = created.json()["id"]
    assert payload_id in created.json()["message"]
    fetched = await client.get(f"/payload/{payload_id}")
    assert fetched.status_code == 200
    assert fetched.json() == {"output": SAMPLE_OUTPUT}


async def test_same_input_returns_same_id_without_new_transforms(
    client: AsyncClient, transformer: CountingTransformer
) -> None:
    first = (await client.post("/payload", json=SAMPLE)).json()["id"]
    calls_after_first = len(transformer.calls)

    second = (await client.post("/payload", json=SAMPLE)).json()["id"]

    assert first == second
    assert len(transformer.calls) == calls_after_first


async def test_shared_strings_are_not_transformed_again(
    client: AsyncClient, transformer: CountingTransformer
) -> None:
    await client.post("/payload", json=SAMPLE)
    transformer.calls.clear()

    await client.post(
        "/payload",
        json={"list_1": ["first string", "new"], "list_2": ["last string", "x"]},
    )

    assert sorted(transformer.calls) == ["new", "x"]


async def test_unequal_lengths_return_422(client: AsyncClient) -> None:
    response = await client.post(
        "/payload", json={"list_1": ["a", "b"], "list_2": ["c"]}
    )

    assert response.status_code == 422


async def test_unknown_id_returns_404(client: AsyncClient) -> None:
    response = await client.get("/payload/unknown")

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_large_input_is_accepted(client: AsyncClient) -> None:
    list_1 = [f"a{index}" for index in range(10_000)]
    list_2 = [f"b{index}" for index in range(10_000)]

    created = await client.post("/payload", json={"list_1": list_1, "list_2": list_2})

    assert created.status_code == 201
    fetched = await client.get(f"/payload/{created.json()['id']}")
    expected = ", ".join(f"A{index}, B{index}" for index in range(10_000))
    assert fetched.json() == {"output": expected}


async def test_very_long_string_is_accepted(client: AsyncClient) -> None:
    response = await client.post(
        "/payload", json={"list_1": ["a" * 100_000], "list_2": ["b"]}
    )

    assert response.status_code == 201


class BrokenTransformer(Transformer):
    async def transform(self, text: str) -> str:
        raise RuntimeError(text)


async def test_transformer_failure_returns_502(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = get_app()
    app.dependency_overrides[get_unit_of_work] = lambda: UnitOfWork(session_factory)
    app.dependency_overrides[get_transformer] = BrokenTransformer
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as broken_client:
        response = await broken_client.post("/payload", json=SAMPLE)

    assert response.status_code == 502
    assert response.json() == {"detail": "Transformer service failed"}

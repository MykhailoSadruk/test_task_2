from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_transformer
from app.infrastructure.database import get_session
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
    session: AsyncSession, transformer: CountingTransformer
) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app = get_app()
    app.dependency_overrides[get_session] = override_session
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

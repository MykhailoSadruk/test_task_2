from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import get_transformer, get_unit_of_work
from app.infrastructure.unit_of_work import UnitOfWork
from app.config import Settings
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


UNKNOWN_ID = "0" * 64
SAMPLE_SMALL = {"list_1": ["a"], "list_2": ["b"]}


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
    app = get_app(Settings(_env_file=None))
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
    response = await client.get(f"/payload/{UNKNOWN_ID}")

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
    app = get_app(Settings(_env_file=None))
    app.dependency_overrides[get_unit_of_work] = lambda: UnitOfWork(session_factory)
    app.dependency_overrides[get_transformer] = BrokenTransformer
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as broken_client:
        response = await broken_client.post("/payload", json=SAMPLE)

    assert response.status_code == 502
    assert response.json() == {"detail": "Transformer service failed"}


async def test_health_reports_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_reports_unavailable_database() -> None:
    engine = create_async_engine("sqlite+aiosqlite:////missing-directory/db.sqlite")
    broken_factory = async_sessionmaker(engine, expire_on_commit=False)
    app = get_app(Settings(_env_file=None))
    app.dependency_overrides[get_unit_of_work] = lambda: UnitOfWork(broken_factory)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as broken_client:
        response = await broken_client.get("/health")
    await engine.dispose()

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


async def test_list_limit_from_settings_returns_413(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = get_app(Settings(_env_file=None, max_list_items=2))
    app.dependency_overrides[get_unit_of_work] = lambda: UnitOfWork(session_factory)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as limited_client:
        within = await limited_client.post(
            "/payload", json={"list_1": ["a", "b"], "list_2": ["c", "d"]}
        )
        over = await limited_client.post(
            "/payload", json={"list_1": ["a", "b", "c"], "list_2": ["d", "e", "f"]}
        )

    assert within.status_code == 201
    assert over.status_code == 413
    assert over.json() == {"detail": "Lists may have at most 2 items"}


async def test_body_size_limit_rejects_large_body(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = get_app(Settings(_env_file=None, max_body_size=100))
    app.dependency_overrides[get_unit_of_work] = lambda: UnitOfWork(session_factory)
    big = {"list_1": ["a" * 200], "list_2": ["b"]}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as limited_client:
        small = await limited_client.post("/payload", json=SAMPLE_SMALL)
        large = await limited_client.post("/payload", json=big)

    assert small.status_code == 201
    assert large.status_code == 413
    assert large.json() == {"detail": "Request body may be at most 100 bytes"}


async def test_body_size_limit_counts_streamed_bytes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = get_app(Settings(_env_file=None, max_body_size=100))
    app.dependency_overrides[get_unit_of_work] = lambda: UnitOfWork(session_factory)

    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"list_1": ["' + b"a" * 80
        yield b"a" * 80 + b'"], "list_2": ["b"]}'

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as limited_client:
        response = await limited_client.post(
            "/payload",
            content=chunks(),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413


async def test_new_payload_returns_201_and_existing_returns_200(
    client: AsyncClient,
) -> None:
    first = await client.post("/payload", json=SAMPLE)
    second = await client.post("/payload", json=SAMPLE)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


@pytest.mark.parametrize("payload_id", ["unknown", "A" * 64, "0" * 63, "0" * 65])
async def test_malformed_id_returns_422(client: AsyncClient, payload_id: str) -> None:
    response = await client.get(f"/payload/{payload_id}")

    assert response.status_code == 422

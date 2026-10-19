from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_transformer
from app.infrastructure.database import get_session
from app.main import app
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

    def transform(self, text: str) -> str:
        self.calls.append(text)
        return text.upper()


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()


@pytest.fixture
def client(session: Session, transformer: CountingTransformer) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_transformer] = lambda: transformer
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_sample_payload_round_trip(client: TestClient) -> None:
    created = client.post("/payload", json=SAMPLE)

    assert created.status_code == 201
    payload_id = created.json()["id"]
    assert payload_id in created.json()["message"]
    fetched = client.get(f"/payload/{payload_id}")
    assert fetched.status_code == 200
    assert fetched.json() == {"output": SAMPLE_OUTPUT}


def test_same_input_returns_same_id_without_new_transforms(
    client: TestClient, transformer: CountingTransformer
) -> None:
    first = client.post("/payload", json=SAMPLE).json()["id"]
    calls_after_first = len(transformer.calls)

    second = client.post("/payload", json=SAMPLE).json()["id"]

    assert first == second
    assert len(transformer.calls) == calls_after_first


def test_shared_strings_are_not_transformed_again(
    client: TestClient, transformer: CountingTransformer
) -> None:
    client.post("/payload", json=SAMPLE)
    transformer.calls.clear()

    client.post(
        "/payload",
        json={"list_1": ["first string", "new"], "list_2": ["last string", "x"]},
    )

    assert sorted(transformer.calls) == ["new", "x"]


def test_unequal_lengths_return_422(client: TestClient) -> None:
    response = client.post("/payload", json={"list_1": ["a", "b"], "list_2": ["c"]})

    assert response.status_code == 422


def test_unknown_id_returns_404(client: TestClient) -> None:
    response = client.get("/payload/unknown")

    assert response.status_code == 404
    assert "detail" in response.json()

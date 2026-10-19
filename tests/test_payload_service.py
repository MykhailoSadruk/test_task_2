import pytest
from sqlalchemy.orm import Session

from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
)
from app.infrastructure.transformer import UppercaseTransformer
from app.services.interfaces import Transformer
from app.services.payloads import PayloadNotFoundError, PayloadService


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
def service(session: Session, transformer: CountingTransformer) -> PayloadService:
    return PayloadService(
        PayloadRepository(session),
        TransformedStringRepository(session),
        transformer,
    )


def test_transform_uppercases_text() -> None:
    assert UppercaseTransformer().transform("abc") == "ABC"


def test_output_is_interleaved(service: PayloadService) -> None:
    payload_id = service.create(["a", "b"], ["x", "y"])

    assert service.get_output(payload_id) == "A, X, B, Y"


def test_cache_is_reused_across_payloads(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    service.create(["a", "b"], ["x", "y"])
    transformer.calls.clear()

    service.create(["a", "c"], ["x", "z"])

    assert sorted(transformer.calls) == ["c", "z"]


def test_repeated_payload_does_not_call_transformer(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    first_id = service.create(["a"], ["b"])
    transformer.calls.clear()

    second_id = service.create(["a"], ["b"])

    assert second_id == first_id
    assert transformer.calls == []


def test_duplicate_strings_are_transformed_once(
    service: PayloadService, transformer: CountingTransformer
) -> None:
    payload_id = service.create(["a", "a"], ["a", "b"])

    assert sorted(transformer.calls) == ["a", "b"]
    assert service.get_output(payload_id) == "A, A, A, B"


def test_unknown_id_raises(service: PayloadService) -> None:
    with pytest.raises(PayloadNotFoundError):
        service.get_output("missing")


def test_unequal_lengths_raise(service: PayloadService) -> None:
    with pytest.raises(ValueError):
        service.create(["a"], ["b", "c"])

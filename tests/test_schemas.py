import pytest
from pydantic import ValidationError

from app.schemas.payloads import PayloadCreateRequest


def test_million_items_are_accepted() -> None:
    items = ["a"] * 1_000_000

    request = PayloadCreateRequest(list_1=items, list_2=items)

    assert len(request.list_1) == 1_000_000


def test_unequal_lengths_are_rejected() -> None:
    with pytest.raises(ValidationError):
        PayloadCreateRequest(list_1=["a"], list_2=[])

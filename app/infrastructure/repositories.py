from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.dtos import PayloadDto
from app.infrastructure.models import Payload, TransformedString


class TransformedStringRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_many(self, strings: Iterable[str]) -> dict[str, str]:
        statement = select(TransformedString).where(
            TransformedString.original.in_(list(strings))
        )
        entries = self._session.scalars(statement)
        return {row.original: row.transformed for row in entries}

    def add_many(self, transformed: dict[str, str]) -> None:
        self._session.add_all(
            TransformedString(original=original, transformed=value)
            for original, value in transformed.items()
        )
        self._session.commit()


class PayloadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, payload_id: str) -> PayloadDto | None:
        payload = self._session.get(Payload, payload_id)
        if payload is None:
            return None
        return PayloadDto(id=payload.id, output=payload.output)

    def add(self, payload: PayloadDto) -> None:
        self._session.add(Payload(id=payload.id, output=payload.output))
        self._session.commit()

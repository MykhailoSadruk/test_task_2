from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Payload, TransformedString


class TransformedStringRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_many(self, strings: Iterable[str]) -> dict[str, str]:
        statement = select(TransformedString).where(
            TransformedString.original.in_(list(strings))
        )
        rows = self._session.scalars(statement)
        return {row.original: row.transformed for row in rows}

    def add_many(self, transformed: dict[str, str]) -> None:
        self._session.add_all(
            TransformedString(original=original, transformed=value)
            for original, value in transformed.items()
        )
        self._session.commit()


class PayloadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, payload_id: str) -> Payload | None:
        return self._session.get(Payload, payload_id)

    def add(self, payload: Payload) -> None:
        self._session.add(payload)
        self._session.commit()

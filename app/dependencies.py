from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database import get_session
from app.infrastructure.repositories import (
    PayloadRepository,
    TransformedStringRepository,
)
from app.infrastructure.transformer import UppercaseTransformer
from app.services.interfaces import Transformer
from app.services.payloads import PayloadService


def get_payload_repository(
    session: Session = Depends(get_session),
) -> PayloadRepository:
    return PayloadRepository(session)


def get_transformed_string_repository(
    session: Session = Depends(get_session),
) -> TransformedStringRepository:
    return TransformedStringRepository(session)


def get_transformer() -> Transformer:
    return UppercaseTransformer()


def get_payload_service(
    payloads: PayloadRepository = Depends(get_payload_repository),
    transformed_strings: TransformedStringRepository = Depends(
        get_transformed_string_repository
    ),
    transformer: Transformer = Depends(get_transformer),
) -> PayloadService:
    return PayloadService(payloads, transformed_strings, transformer)


PayloadServiceDep = Annotated[PayloadService, Depends(get_payload_service)]

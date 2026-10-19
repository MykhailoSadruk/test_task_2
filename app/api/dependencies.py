from typing import Annotated

from fastapi import Depends

from app.infrastructure.database import session_factory
from app.infrastructure.transformer import UppercaseTransformer
from app.infrastructure.unit_of_work import UnitOfWork
from app.services.interfaces import Transformer
from app.services.payloads import PayloadService


def get_unit_of_work() -> UnitOfWork:
    return UnitOfWork(session_factory)


def get_transformer() -> Transformer:
    return UppercaseTransformer()


def get_payload_service(
    unit_of_work: UnitOfWork = Depends(get_unit_of_work),
    transformer: Transformer = Depends(get_transformer),
) -> PayloadService:
    return PayloadService(unit_of_work, transformer)


UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_unit_of_work)]
PayloadServiceDep = Annotated[PayloadService, Depends(get_payload_service)]

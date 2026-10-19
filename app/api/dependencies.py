import asyncio
from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.exceptions import PayloadTooLargeError
from app.infrastructure.unit_of_work import UnitOfWork
from app.services.interfaces import Transformer
from app.schemas.payloads import PayloadCreateRequest
from app.services.payloads import PayloadService


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_transformer_limiter(request: Request) -> asyncio.Semaphore:
    limiter: asyncio.Semaphore = request.app.state.transformer_limiter
    return limiter


def get_unit_of_work(request: Request) -> UnitOfWork:
    return UnitOfWork(request.app.state.session_factory)


def get_transformer(request: Request) -> Transformer:
    transformer: Transformer = request.app.state.transformer
    return transformer


def get_payload_service(
    unit_of_work: UnitOfWork = Depends(get_unit_of_work),
    transformer: Transformer = Depends(get_transformer),
    transformer_limiter: asyncio.Semaphore = Depends(get_transformer_limiter),
) -> PayloadService:
    return PayloadService(
        unit_of_work, transformer, transformer_limiter=transformer_limiter
    )


def get_checked_payload(
    body: PayloadCreateRequest, settings: Settings = Depends(get_settings)
) -> PayloadCreateRequest:
    limit = settings.max_list_items
    if limit is not None and len(body.list_1) > limit:
        raise PayloadTooLargeError(f"Lists may have at most {limit} items")
    return body


UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_unit_of_work)]
PayloadServiceDep = Annotated[PayloadService, Depends(get_payload_service)]
CheckedPayloadDep = Annotated[PayloadCreateRequest, Depends(get_checked_payload)]

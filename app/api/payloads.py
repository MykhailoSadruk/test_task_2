from fastapi import APIRouter, status

from app.dependencies import PayloadServiceDep
from app.schemas.payloads import (
    PayloadCreateRequest,
    PayloadCreateResponse,
    PayloadResponse,
)

router = APIRouter(prefix="/payload", tags=["payload"])


@router.post(
    "",
    response_model=PayloadCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payload(
    request: PayloadCreateRequest, service: PayloadServiceDep
) -> PayloadCreateResponse:
    payload_id = await service.create(request.list_1, request.list_2)
    return PayloadCreateResponse(
        id=payload_id, message=f"Payload {payload_id} is ready"
    )


@router.get("/{payload_id}", response_model=PayloadResponse)
async def get_payload(payload_id: str, service: PayloadServiceDep) -> PayloadResponse:
    return PayloadResponse(output=await service.get_output(payload_id))

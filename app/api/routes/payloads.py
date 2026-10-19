from fastapi import APIRouter, Response, status

from app.api.dependencies import CheckedPayloadDep, PayloadServiceDep
from app.schemas.payloads import PayloadCreateResponse, PayloadResponse

router = APIRouter()


@router.post(
    "",
    response_model=PayloadCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payload(
    request: CheckedPayloadDep, service: PayloadServiceDep, response: Response
) -> PayloadCreateResponse:
    creation = await service.create(request.list_1, request.list_2)
    if not creation.created:
        response.status_code = status.HTTP_200_OK
    return PayloadCreateResponse(
        id=creation.id, message=f"Payload {creation.id} is ready"
    )


@router.get("/{payload_id}", response_model=PayloadResponse)
async def get_payload(payload_id: str, service: PayloadServiceDep) -> PayloadResponse:
    return PayloadResponse(output=await service.get_output(payload_id))

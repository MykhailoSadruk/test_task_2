from fastapi import APIRouter

from app.api.dependencies import UnitOfWorkDep
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("", response_model=HealthResponse)
async def check_health(unit_of_work: UnitOfWorkDep) -> HealthResponse:
    async with unit_of_work as uow:
        await uow.ping()
    return HealthResponse(status="ok")

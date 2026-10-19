from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.payloads import router as payloads_router
from app.exceptions import PayloadNotFoundError
from app.infrastructure.database import create_tables


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await create_tables()
    yield


def payload_not_found_handler(_: Request, error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": f"Payload {error} not found"},
    )


def get_app() -> FastAPI:
    app = FastAPI(title="Payload service", lifespan=lifespan)
    app.include_router(payloads_router)
    app.add_exception_handler(PayloadNotFoundError, payload_not_found_handler)
    return app

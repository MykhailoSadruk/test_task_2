from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.payloads import router as payloads_router
from app.exceptions.handlers import register_exception_handlers
from app.infrastructure.database import create_tables


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await create_tables()
    yield


def get_app() -> FastAPI:
    app = FastAPI(title="Payload service", lifespan=lifespan)
    app.include_router(payloads_router)
    register_exception_handlers(app)
    return app

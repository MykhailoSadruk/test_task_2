from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import get_router
from app.api.middleware import BodySizeLimitMiddleware
from app.config import Settings
from app.exceptions.handlers import register_exception_handlers
from app.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    create_tables,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_database_engine(app.state.settings.database_url)
    app.state.session_factory = create_session_factory(engine)
    await create_tables(engine)
    yield
    await engine.dispose()


def get_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Payload service", lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.add_middleware(
        BodySizeLimitMiddleware, max_body_size=app.state.settings.max_body_size
    )
    app.include_router(get_router())
    register_exception_handlers(app)
    return app

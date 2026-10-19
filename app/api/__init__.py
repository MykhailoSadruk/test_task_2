from fastapi import APIRouter

from app.api.routes import health, payloads


def get_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health.router, prefix="/health", tags=["Health"])
    router.include_router(payloads.router, prefix="/payload", tags=["Payload"])
    return router

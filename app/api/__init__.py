from fastapi import APIRouter

from app.api.routes import payloads


def get_router() -> APIRouter:
    router = APIRouter()
    router.include_router(payloads.router, prefix="/payload", tags=["Payload"])
    return router

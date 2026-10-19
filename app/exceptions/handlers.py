from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.exceptions.errors import PayloadNotFoundError


def payload_not_found_handler(_: Request, error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": f"Payload {error} not found"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PayloadNotFoundError, payload_not_found_handler)

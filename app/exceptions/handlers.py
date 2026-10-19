from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.exceptions.errors import (
    DatabaseUnavailableError,
    PayloadNotFoundError,
    TransformerError,
)


def payload_not_found_handler(_: Request, error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": f"Payload {error} not found"},
    )


def transformer_error_handler(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "Transformer service failed"},
    )


def database_unavailable_handler(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database unavailable"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PayloadNotFoundError, payload_not_found_handler)
    app.add_exception_handler(TransformerError, transformer_error_handler)
    app.add_exception_handler(DatabaseUnavailableError, database_unavailable_handler)

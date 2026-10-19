from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.status import HTTP_413_CONTENT_TOO_LARGE
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int | None) -> None:
        self._app = app
        self._max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._max_body_size is None:
            await self._app(scope, receive, send)
            return
        limit: int = self._max_body_size
        detail = f"Request body may be at most {limit} bytes"
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and int(declared) > limit:
            response = JSONResponse(
                {"detail": detail}, status_code=HTTP_413_CONTENT_TOO_LARGE
            )
            await response(scope, receive, send)
            return
        # A client can omit Content-Length (chunked upload), so the bytes that
        # actually arrive are counted too and the read is aborted at the limit.
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(HTTP_413_CONTENT_TOO_LARGE, detail)
            return message

        await self._app(scope, limited_receive, send)

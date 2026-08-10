"""ASGI-level guard against oversized request bodies.

Runs before FastAPI parses the request body, so a declared-oversized upload
is refused without ever being buffered into memory or spooled to disk just to
be rejected by the endpoint's own validation.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

# The multipart body carries the file plus its boundaries and part headers,
# so it is always a little larger than the file itself; this is slack over
# the declared upload limit to avoid rejecting a file exactly at the limit.
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject a request whose declared ``Content-Length`` exceeds a limit.

    This catches every request that declares its size honestly — which is
    every real file upload from a browser or ``curl -F``, since the size is
    known before the request is sent. A request that omits ``Content-Length``
    (chunked transfer encoding) is not covered here; the endpoint's own
    post-read size check remains as a second line of defence for that case.

    The limit is read from settings on every request rather than captured
    once at startup, so it stays in step with ``Settings.max_upload_mb``.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = None
            limit = get_settings().max_upload_mb * 1024 * 1024 + _MULTIPART_OVERHEAD_BYTES
            if declared is not None and declared > limit:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"The request body is {declared} bytes, larger than the "
                            f"{limit} byte limit."
                        )
                    },
                )
        return await call_next(request)

"""Core application bootstrap, middleware, logging, and error handling."""

import uuid
from contextvars import ContextVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-Id"
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return request id."""
    return request_id_ctx.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware for RequestContext."""
    async def dispatch(self, request: Request, call_next):
        """Handle dispatch."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = request_id_ctx.set(request_id)
        try:
            response: Response = await call_next(request)
        finally:
            request_id_ctx.reset(token)

        response.headers[REQUEST_ID_HEADER] = request_id
        return response

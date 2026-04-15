"""Core application bootstrap, middleware, logging, and error handling."""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.request_context import get_request_id


def configure_logging(level: str) -> None:
    """Configure logging."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for RequestLogging."""
    async def dispatch(self, request: Request, call_next):
        """Handle dispatch."""
        logger = logging.getLogger("ldt.request")
        started_at = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - started_at) * 1000)

        logger.info(
            "%s %s status=%s duration_ms=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            get_request_id(),
        )
        return response

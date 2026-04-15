"""Core application bootstrap, middleware, logging, and error handling."""

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.core.request_context import get_request_id
from src.schemas.common import ErrorDetail, ErrorResponse


class AppError(Exception):
    """Application-level exception with structured error metadata."""
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        target: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the instance and its dependencies."""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.target = target
        self.metadata = metadata or {}


def _render_error(status_code: int, detail: ErrorDetail) -> JSONResponse:
    """Internal helper to render error."""
    payload = ErrorResponse(request_id=get_request_id(), error=detail)
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    """Handle app error handler."""
    return _render_error(
        exc.status_code,
        ErrorDetail(
            code=exc.code,
            message=exc.message,
            target=exc.target,
            metadata=exc.metadata,
        ),
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation error handler."""
    return _render_error(
        422,
        ErrorDetail(
            code="validation_error",
            message="Request validation failed.",
            metadata={"errors": exc.errors()},
        ),
    )


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled error handler."""
    return _render_error(
        500,
        ErrorDetail(
            code="internal_error",
            message="An unexpected error occurred.",
            metadata={"error_type": exc.__class__.__name__},
        ),
    )

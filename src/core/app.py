"""Core application bootstrap, middleware, logging, and error handling."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from src.api.routers.admin import router as admin_router
from src.api.routers.runs import router as runs_router
from src.api.routers.system import router as system_router
from src.config.settings import Settings, get_settings
from src.core.container import ServiceContainer
from src.core.errors import (
    AppError,
    app_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from src.core.logging import RequestLoggingMiddleware, configure_logging
from src.core.request_context import RequestContextMiddleware


def create_app(settings: Settings | None = None, container: ServiceContainer | None = None) -> FastAPI:
    """Create app."""
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    app = FastAPI(title=app_settings.app_name, version=app_settings.app_version)
    app.state.settings = app_settings
    app.state.container = container or ServiceContainer(settings=app_settings)

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    app.include_router(system_router, tags=["system"])
    app.include_router(runs_router, prefix="/v1", tags=["runs"])
    app.include_router(admin_router, prefix="/v1/admin", tags=["admin"])
    return app

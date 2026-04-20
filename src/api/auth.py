"""Authentication dependencies for API route protection."""

from __future__ import annotations

import secrets

from fastapi import Request

from src.core.errors import AppError


def require_admin_auth(request: Request) -> None:
    """Enforce admin authentication for `/v1/admin/*` endpoints."""

    settings = request.app.state.settings
    configured_key = settings.admin_api_key.strip()

    if not configured_key:
        if settings.environment.lower() == "prod":
            raise AppError(
                status_code=503,
                code="admin_auth_not_configured",
                message="Admin API authentication is required in prod but LDT_ADMIN_API_KEY is not configured.",
            )
        return

    presented_key = _extract_presented_key(request)
    if not presented_key:
        raise AppError(
            status_code=401,
            code="admin_auth_missing",
            message="Admin API authentication is required.",
        )
    if not secrets.compare_digest(presented_key, configured_key):
        raise AppError(
            status_code=403,
            code="admin_auth_invalid",
            message="Admin API authentication failed.",
        )


def _extract_presented_key(request: Request) -> str:
    """Extract an API key from standard admin-auth headers."""

    authorization = request.headers.get("Authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    return request.headers.get("X-Admin-Api-Key", "").strip()

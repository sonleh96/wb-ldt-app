from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.core.app import create_app
from src.core.container import ServiceContainer


def test_admin_routes_require_configured_auth_in_prod() -> None:
    app = create_app(container=ServiceContainer(settings=Settings(environment="prod", auto_seed_sources=False)))
    with TestClient(app) as client:
        response = client.get("/v1/admin/sources")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "admin_auth_not_configured"


def test_admin_routes_reject_missing_and_invalid_tokens_when_key_configured() -> None:
    app = create_app(
        container=ServiceContainer(
            settings=Settings(environment="dev", admin_api_key="top-secret", auto_seed_sources=False),
        )
    )
    with TestClient(app) as client:
        missing = client.get("/v1/admin/sources")
        wrong = client.get("/v1/admin/sources", headers={"Authorization": "Bearer wrong"})

    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "admin_auth_missing"
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "admin_auth_invalid"


def test_admin_routes_accept_authorized_tokens() -> None:
    app = create_app(
        container=ServiceContainer(
            settings=Settings(environment="dev", admin_api_key="top-secret", auto_seed_sources=False),
        )
    )
    with TestClient(app) as client:
        bearer = client.get("/v1/admin/sources", headers={"Authorization": "Bearer top-secret"})
        header = client.get("/v1/admin/sources", headers={"X-Admin-Api-Key": "top-secret"})

    assert bearer.status_code == 200
    assert bearer.json() == []
    assert header.status_code == 200
    assert header.json() == []

"""Basic HTTP checks. Supabase HTTP calls are mocked; no real keys or database needed."""

import importlib
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from supabase import AsyncClientOptions, acreate_client

from app.core.config import Settings, get_settings

LEAD_ID = "11111111-1111-4111-8111-111111111111"
TAG_ID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def client():
    settings = Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="sb_secret_test-only-key",
        telegram_bot_token="123:test-bot-token",
        jwt_secret="test-only-jwt-secret-at-least-32-bytes",
        browser_pin="2026",
        pin_login_enabled=True,
        webhook_secret="test123",
    )
    calls = []

    def database(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET" and request.url.path == "/rest/v1/users":
            return httpx.Response(200, json=[{
                "id": str(settings.demo_manager_id), "telegram_id": None,
                "role": "manager", "created_at": "2026-01-01T00:00:00Z",
            }])
        if request.method == "GET" and request.url.path == "/rest/v1/leads":
            return httpx.Response(200, json=[])
        raise AssertionError(f"Unexpected database request: {request.method} {request.url}")

    async def create_database(config: Settings):
        return await acreate_client(
            str(config.supabase_url), config.supabase_service_role_key.get_secret_value(),
            options=AsyncClientOptions(
                httpx_client=httpx.AsyncClient(transport=httpx.MockTransport(database)),
                auto_refresh_token=False, persist_session=False,
            ),
        )

    # Keep the normal Depends function, but prevent loading a local .env on initial import.
    get_settings.cache_clear()
    with patch("app.core.config.Settings", return_value=settings):
        get_settings()
    main = importlib.import_module("app.main")
    main.app.dependency_overrides[get_settings] = lambda: settings
    main.app.state.login_limiter = main.auth.LoginLimiter()
    try:
        with patch.object(main, "create_supabase", create_database):
            with TestClient(main.app) as test_client:
                yield test_client, calls
    finally:
        main.app.dependency_overrides.pop(get_settings, None)
        get_settings.cache_clear()


def test_health(client):
    api, calls = client
    response = api.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls == []


def test_pin_issues_working_token(client):
    api, _ = client
    response = api.post("/auth/pin", json={"pin": "2026"})
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]
    response = api.get("/leads", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == []


def test_wrong_pin_is_rejected(client):
    api, calls = client
    assert api.post("/auth/pin", json={"pin": "0000"}).status_code == 401
    assert calls == []


@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token"])
@pytest.mark.parametrize("method,path,body", [
    ("GET", "/leads", None),
    ("POST", "/leads", {"name": "Иван", "contact": "ivan@example.com"}),
    ("PATCH", f"/leads/{LEAD_ID}", {"status": "done"}),
    ("DELETE", f"/leads/{LEAD_ID}", None),
    ("GET", "/tags", None),
    ("POST", "/tags", {"name": "Веб-форма"}),
    ("POST", f"/leads/{LEAD_ID}/tags/{TAG_ID}", None),
])
def test_protected_routes_require_valid_jwt(client, method, path, body, authorization):
    api, calls = client
    headers = {"Authorization": authorization} if authorization else {}
    response = api.request(method, path, json=body, headers=headers)
    assert response.status_code == 401
    assert calls == []

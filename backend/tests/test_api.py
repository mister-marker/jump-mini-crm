"""Basic HTTP checks. Supabase HTTP calls are mocked; no real keys or database needed."""

import importlib
import json
from unittest.mock import patch

from aiogram.methods import SendMessage
from aiogram.types import Message
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
        telegram_webhook_secret="telegram-test-secret-at-least-32-chars",
    )
    calls = []
    saved_leads = {}
    replies = []
    failures = {"reply": False, "database": False}

    def database(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET" and request.url.path == "/rest/v1/users":
            return httpx.Response(200, json=[{
                "id": str(settings.demo_manager_id), "telegram_id": None,
                "role": "manager", "created_at": "2026-01-01T00:00:00Z",
            }])
        if request.method == "GET" and request.url.path == "/rest/v1/leads":
            return httpx.Response(200, json=list(saved_leads.values()))
        if request.method == "POST" and request.url.path == "/rest/v1/rpc/create_bot_lead":
            body = json.loads(request.content)
            if failures["database"]:
                failures["database"] = False
                raise httpx.ReadTimeout("Simulated DB timeout")
            saved_leads.setdefault(body["p_id"], {
                "id": body["p_id"], "name": body["p_name"], "contact": body["p_contact"],
                "request": body["p_request"], "source": "bot", "status": "new",
                "next_contact_date": None, "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "tags": [{"id": TAG_ID, "name": "Telegram-бот", "color": "#6B7280"}],
            })
            return httpx.Response(200, json=body["p_id"])
        raise AssertionError(f"Unexpected database request: {request.method} {request.url}")

    async def telegram_request(session, bot, method, timeout=None):
        assert isinstance(method, SendMessage)
        if failures["reply"]:
            failures["reply"] = False
            raise TimeoutError("Simulated Telegram timeout")
        replies.append(method)
        return Message(message_id=len(replies), date=1,
                       chat={"id": method.chat_id, "type": "private"}, text=method.text)

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
        with patch.object(main, "create_supabase", create_database), patch(
            "aiogram.client.session.aiohttp.AiohttpSession.make_request", telegram_request
        ):
            with TestClient(main.app) as test_client:
                test_client.saved_leads = saved_leads
                test_client.replies = replies
                test_client.failures = failures
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


TELEGRAM_HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "telegram-test-secret-at-least-32-chars"}


def send_update(api, number, text=None, **message_fields):
    message = {"message_id": number, "date": 1, "chat": {"id": 101, "type": "private"},
               "from": {"id": 101, "is_bot": False, "first_name": "Иван"}}
    if text is not None:
        message["text"] = text
    message.update(message_fields)
    return api.post("/api/webhooks/telegram", headers=TELEGRAM_HEADERS,
                    json={"update_id": number, "message": message})


def fill_application(api, start=1):
    for number, text in enumerate(
        ["/start", "Иван", "Email", "ivan@example.com", "Нужен лендинг для стартапа"], start
    ):
        assert send_update(api, number, text).status_code == 200


@pytest.mark.parametrize("secret", [None, "wrong", "test123"])
def test_telegram_rejects_bad_secret_before_processing(client, secret):
    api, calls = client
    headers = {"X-Telegram-Bot-Api-Secret-Token": secret} if secret else {}
    response = api.post("/api/webhooks/telegram", content="not-json", headers=headers)
    assert response.status_code == 401
    assert not calls and not api.replies


@pytest.mark.parametrize("body", [None, {}, {"update_id": 1, "message": {}}])
def test_telegram_rejects_malformed_update(client, body):
    api, _ = client
    response = api.post("/api/webhooks/telegram", json=body, headers=TELEGRAM_HEADERS)
    assert response.status_code == 400


def test_bot_full_flow_confirmation_and_duplicates(client):
    api, calls = client
    fill_application(api)
    assert not api.saved_leads  # A preview is not a submitted application.
    assert send_update(api, 6, "Отправить заявку").status_code == 200
    reply_count = len(api.replies)
    assert send_update(api, 6, "Отправить заявку").status_code == 200
    assert len(api.replies) == reply_count
    assert len(api.saved_leads) == 1
    lead = next(iter(api.saved_leads.values()))
    assert (lead["name"], lead["contact"], lead["source"]) == ("Иван", "ivan@example.com", "bot")
    assert lead["tags"][0]["name"] == "Telegram-бот"
    assert len(calls) == 1
    fill_application(api, start=10)
    assert send_update(api, 15, "Отправить заявку").status_code == 200
    assert len(api.saved_leads) == 2  # Same person may submit a new application.


@pytest.mark.parametrize("cancel", ["/cancel", "Отмена"])
def test_bot_cancel_does_not_create_lead(client, cancel):
    api, calls = client
    fill_application(api)
    assert send_update(api, 6, cancel).status_code == 200
    assert send_update(api, 7, "Отправить заявку").status_code == 200
    assert not calls
    assert " /start" in api.replies[-1].text


def test_bot_duplicate_field_does_not_advance_state(client):
    api, _ = client
    send_update(api, 1, "/start")
    send_update(api, 2, "Иван")
    send_update(api, 2, "Иван")
    send_update(api, 3, "Email")
    send_update(api, 4, "ivan@example.com")
    send_update(api, 5, "Нужен сайт")
    assert "Связь (Email): ivan@example.com" in api.replies[-1].text


def test_bot_retries_database_failure(client):
    api, _ = client
    fill_application(api)
    api.failures["database"] = True
    assert send_update(api, 6, "Отправить заявку").status_code == 503
    assert not api.saved_leads
    assert send_update(api, 6, "Отправить заявку").status_code == 200
    assert len(api.saved_leads) == 1


def test_bot_reply_failure_after_commit_does_not_duplicate_lead(client):
    api, calls = client
    fill_application(api)
    api.failures["reply"] = True
    assert send_update(api, 6, "Отправить заявку").status_code == 503
    assert len(api.saved_leads) == 1
    assert send_update(api, 6, "Отправить заявку").status_code == 200
    assert len(api.saved_leads) == 1
    assert len(calls) == 2
    assert json.loads(calls[0].content)["p_id"] == json.loads(calls[1].content)["p_id"]


def test_bot_validation_and_phone_without_username(client):
    api, _ = client
    send_update(api, 1, "/start")
    send_update(api, 2, "   ")
    assert "Введите имя" in api.replies[-1].text
    send_update(api, 3, "Иван")
    assert all(not button.request_contact for row in api.replies[-1].reply_markup.keyboard for button in row)
    send_update(api, 4, "Телефон")
    assert api.replies[-1].reply_markup.keyboard[0][0].request_contact is True
    send_update(api, 5, contact={"phone_number": "+79990000000", "first_name": "Друг", "user_id": 102})
    assert "своим контактом" in api.replies[-1].text
    send_update(api, 6, contact={"phone_number": "+79990000000", "first_name": "Иван", "user_id": 101})
    send_update(api, 7, "   ")
    assert "Опишите задачу" in api.replies[-1].text
    send_update(api, 8, "Нужен сайт")
    send_update(api, 9, "Отправить заявку")
    assert next(iter(api.saved_leads.values()))["contact"] == "+79990000000"


def test_bot_ignores_groups_and_unsupported_updates(client):
    api, calls = client
    assert send_update(api, 1, "/start", chat={"id": -100, "type": "group"}).status_code == 200
    response = api.post("/api/webhooks/telegram", headers=TELEGRAM_HEADERS, json={"update_id": 2})
    assert response.status_code == 200
    assert not api.replies and not calls


def test_bot_contact_choice_and_email_do_not_request_phone(client):
    api, _ = client
    send_update(api, 1, "/start")
    send_update(api, 2, "Иван")
    labels = [button.text for row in api.replies[-1].reply_markup.keyboard for button in row]
    assert "Telegram" not in labels  # This user has no username.
    send_update(api, 3, "ivan@example.com")
    assert "Выберите один способ" in api.replies[-1].text
    send_update(api, 4, "Email")
    assert all(not button.request_contact for row in api.replies[-1].reply_markup.keyboard for button in row)
    send_update(api, 5, "+79991234567")
    assert "Введите email" in api.replies[-1].text
    send_update(api, 6, "ivan@example.com")
    send_update(api, 7, "Нужен сайт")
    send_update(api, 8, "Отправить заявку")
    assert next(iter(api.saved_leads.values()))["contact"] == "ivan@example.com"


def test_bot_telegram_contact_uses_senders_username(client):
    api, _ = client
    sender = {"id": 101, "is_bot": False, "first_name": "Иван", "username": "ivan_crm"}
    for number, text in enumerate(["/start", "Иван", "Telegram", "Нужен сайт", "Отправить заявку"], 1):
        assert send_update(api, number, text, **{"from": sender}).status_code == 200
    assert next(iter(api.saved_leads.values()))["contact"] == "@ivan_crm"
    assert not any(button.request_contact for reply in api.replies
                   if hasattr(reply.reply_markup, "keyboard")
                   for row in reply.reply_markup.keyboard for button in row)


def test_bot_can_change_contact_method_and_normalizes_phone(client):
    api, _ = client
    for number, text in enumerate([
        "/start", "Иван", "Email", "Другой способ связи", "Телефон", "ivan@example.com",
    ], 1):
        send_update(api, number, text)
    assert "Введите номер" in api.replies[-1].text
    send_update(api, 7, "+7 (999) 123-45-67")
    send_update(api, 8, "Нужен сайт")
    assert "Связь (Телефон): +79991234567" in api.replies[-1].text
    send_update(api, 9, "Отправить заявку")
    assert next(iter(api.saved_leads.values()))["contact"] == "+79991234567"


def test_bot_registration_preserves_pending_updates(client):
    import asyncio
    api, _ = client
    runtime = api.app.state.telegram
    runtime.settings.telegram_webhook_url = "https://example.com/api/webhooks/telegram"
    from unittest.mock import AsyncMock
    with patch.object(runtime.bot, "set_webhook", new_callable=AsyncMock) as register:
        asyncio.run(runtime.start())
        assert register.call_args.kwargs["max_connections"] == 1
        assert register.call_args.kwargs["drop_pending_updates"] is False
        assert register.call_args.kwargs["allowed_updates"] == ["message"]


def test_bot_concurrent_delivery_creates_one_lead(client):
    from concurrent.futures import ThreadPoolExecutor
    api, calls = client
    fill_application(api)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: send_update(api, 6, "Отправить заявку"), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert len(api.saved_leads) == 1
    assert len(calls) == 1


def test_disabled_bot_leaves_other_api_available(client):
    api, _ = client
    settings = api.app.state.telegram.settings.model_copy(update={"telegram_webhook_secret": None})
    api.app.dependency_overrides[get_settings] = lambda: settings
    assert api.post("/api/webhooks/telegram", json={}).status_code == 503
    assert api.get("/health").status_code == 200


@pytest.mark.parametrize("changes", [
    {"telegram_webhook_secret": "short"},
    {"telegram_webhook_secret": "a" * 32 + "!"},
    {"telegram_webhook_secret": None, "telegram_webhook_url": "https://example.com/api/webhooks/telegram"},
    {"telegram_webhook_url": "http://example.com/api/webhooks/telegram"},
    {"telegram_webhook_url": "https://example.com/wrong-path"},
])
def test_invalid_bot_configuration_is_rejected(client, changes):
    from pydantic import ValidationError
    api, _ = client
    values = api.app.state.telegram.settings.model_dump()
    values.update(changes)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)

"""Basic HTTP checks. Supabase HTTP calls are mocked; no real keys or database needed."""

import importlib
import json
from unittest.mock import patch

from aiogram.methods import SendMessage, SetChatMenuButton
from aiogram.types import MenuButtonCommands, MenuButtonWebApp, Message
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
    menus = []
    staff_chat_ids = set()
    saved_sources = [{"id": "bot", "name": "Telegram-бот"},
                     {"id": "manual", "name": "Не уточнён (ручной ввод)"}]
    failures = {"reply": False, "database": False}
    database_user = {
        "id": str(settings.demo_manager_id), "telegram_id": None,
        "role": "manager", "created_at": "2026-01-01T00:00:00Z",
    }

    def database(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET" and request.url.path == "/rest/v1/users":
            if "telegram_id" in request.url.params:
                chat_id = int(request.url.params["telegram_id"].removeprefix("eq."))
                return httpx.Response(200, json=[{"role": "manager"}] if chat_id in staff_chat_ids else [])
            return httpx.Response(200, json=[database_user])
        if request.method == "GET" and request.url.path == "/rest/v1/sources":
            return httpx.Response(200, json=saved_sources)
        if request.method == "POST" and request.url.path == "/rest/v1/sources":
            item = {"id": "33333333-3333-4333-8333-333333333333", **json.loads(request.content)}
            saved_sources.append(item)
            return httpx.Response(201, json=[item])
        if request.method == "GET" and request.url.path == "/rest/v1/leads":
            return httpx.Response(200, json=list(saved_leads.values()))
        if request.method == "POST" and request.url.path == "/rest/v1/leads":
            body = json.loads(request.content)
            item = {"id": LEAD_ID, **body, "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z", "tags": []}
            saved_leads[LEAD_ID] = item
            return httpx.Response(201, json=[item])
        if request.method == "DELETE" and request.url.path == "/rest/v1/lead_tags":
            lead_id = request.url.params['lead_id'].removeprefix('eq.')
            tag_id = request.url.params['tag_id'].removeprefix('eq.')
            saved_leads[lead_id]['tags'] = [tag for tag in saved_leads[lead_id]['tags'] if tag['id'] != tag_id]
            return httpx.Response(200, json=[])
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
                "tags": [],
            })
            return httpx.Response(200, json=body["p_id"])
        raise AssertionError(f"Unexpected database request: {request.method} {request.url}")

    async def telegram_request(session, bot, method, timeout=None):
        if isinstance(method, SetChatMenuButton):
            menus.append(method)
            return True
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
                test_client.menus = menus
                test_client.staff_chat_ids = staff_chat_ids
                test_client.saved_sources = saved_sources
                test_client.failures = failures
                test_client.database_user = database_user
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
    ("GET", "/auth/me", None),
    ("GET", "/leads", None),
    ("POST", "/leads", {"name": "Иван", "contact": "ivan@example.com"}),
    ("PATCH", f"/leads/{LEAD_ID}", {"status": "done"}),
    ("DELETE", f"/leads/{LEAD_ID}", None),
    ("GET", "/tags", None),
    ("GET", "/sources", None),
    ("POST", "/sources", {"name": "Рекомендация"}),
    ("POST", "/tags", {"name": "Веб-форма"}),
    ("POST", f"/leads/{LEAD_ID}/tags/{TAG_ID}", None),
    ("DELETE", f"/leads/{LEAD_ID}/tags/{TAG_ID}", None),
])
def test_protected_routes_require_valid_jwt(client, method, path, body, authorization):
    api, calls = client
    headers = {"Authorization": authorization} if authorization else {}
    response = api.request(method, path, json=body, headers=headers)
    assert response.status_code == 401
    assert calls == []


def test_me_preserves_manager_role_for_pin_session(client):
    api, _ = client
    token = api.post('/auth/pin', json={'pin': '2026'}).json()['access_token']
    api.database_user['role'] = 'admin'
    response = api.get('/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    assert response.json()['role'] == 'manager'
    assert response.headers['Cache-Control'] == 'no-store'


def test_source_directory_and_admin_only_creation(client):
    api, _ = client
    token = api.post('/auth/pin', json={'pin': '2026'}).json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    response = api.get('/sources', headers=headers)
    assert response.status_code == 200
    assert response.json()[0]['id'] == 'bot'
    assert api.post('/sources', json={'name': 'Рекомендация'}, headers=headers).status_code == 403


def test_admin_can_add_source(client):
    from app.core.security import create_access_token
    from app.models.schemas import User

    api, _ = client
    api.database_user['role'] = 'admin'
    settings = api.app.state.telegram.settings
    token = create_access_token(User.model_validate(api.database_user), settings, method='telegram')
    response = api.post('/sources', json={'name': 'Рекомендация'},
                        headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 201
    assert response.json()['name'] == 'Рекомендация'
    assert api.saved_sources[-1]['name'] == 'Рекомендация'


def test_manual_lead_requires_selected_source(client):
    api, calls = client
    token = api.post('/auth/pin', json={'pin': '2026'}).json()['access_token']
    response = api.post('/leads', headers={'Authorization': f'Bearer {token}'},
                        json={'name': 'Иван', 'contact': '@ivan'})
    assert response.status_code == 422
    assert not any(call.method == 'POST' and call.url.path == '/rest/v1/leads' for call in calls)


def test_manual_lead_uses_selected_source_without_automatic_tags(client):
    api, calls = client
    token = api.post('/auth/pin', json={'pin': '2026'}).json()['access_token']
    response = api.post('/leads', headers={'Authorization': f'Bearer {token}'},
                        json={'name': 'Иван', 'contact': '@ivan',
                              'source': '33333333-3333-4333-8333-333333333333'})
    assert response.status_code == 201
    assert response.json()['source'] == '33333333-3333-4333-8333-333333333333'
    assert response.json()['tags'] == []
    insertion = next(call for call in calls if call.method == 'POST' and call.url.path == '/rest/v1/leads')
    assert json.loads(insertion.content)['source'] == response.json()['source']


def test_manager_can_remove_tag_without_deleting_lead(client):
    api, _ = client
    api.saved_leads[LEAD_ID] = {
        'id': LEAD_ID, 'name': 'Иван', 'contact': 'ivan@example.com', 'request': 'Нужен сайт',
        'source': 'manual', 'status': 'new', 'created_at': '2026-01-01T00:00:00Z',
        'updated_at': '2026-01-01T00:00:00Z',
        'tags': [{'id': TAG_ID, 'name': 'Приоритетный', 'color': '#A3E635'}],
    }
    token = api.post('/auth/pin', json={'pin': '2026'}).json()['access_token']
    response = api.delete(f'/leads/{LEAD_ID}/tags/{TAG_ID}', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    assert response.json()['tags'] == []
    assert LEAD_ID in api.saved_leads


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
    assert lead["tags"] == []
    assert sum(call.url.path == '/rest/v1/rpc/create_bot_lead' for call in calls) == 1
    fill_application(api, start=10)
    assert send_update(api, 15, "Отправить заявку").status_code == 200
    assert len(api.saved_leads) == 2  # Same person may submit a new application.


@pytest.mark.parametrize("cancel", ["/cancel", "Отмена"])
def test_bot_cancel_does_not_create_lead(client, cancel):
    api, calls = client
    fill_application(api)
    assert send_update(api, 6, cancel).status_code == 200
    assert send_update(api, 7, "Отправить заявку").status_code == 200
    assert not any(call.url.path == '/rest/v1/rpc/create_bot_lead' for call in calls)
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
    submissions = [call for call in calls if call.url.path == '/rest/v1/rpc/create_bot_lead']
    assert len(submissions) == 2
    assert json.loads(submissions[0].content)["p_id"] == json.loads(submissions[1].content)["p_id"]


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
    assert sum(call.url.path == '/rest/v1/rpc/create_bot_lead' for call in calls) == 1


def test_bot_menu_is_private_to_registered_staff(client):
    api, _ = client
    assert isinstance(api.menus[0].menu_button, MenuButtonCommands)
    assert api.menus[0].chat_id is None
    assert send_update(api, 1, '/start').status_code == 200
    assert api.menus[-1].chat_id == 101
    assert isinstance(api.menus[-1].menu_button, MenuButtonCommands)
    api.staff_chat_ids.add(101)
    assert send_update(api, 2, '/start').status_code == 200
    assert isinstance(api.menus[-1].menu_button, MenuButtonWebApp)
    assert api.menus[-1].menu_button.web_app.url.rstrip('/') == 'https://jump-mini-crm.vercel.app'
    api.staff_chat_ids.clear()
    assert send_update(api, 3, '/start').status_code == 200
    assert isinstance(api.menus[-1].menu_button, MenuButtonCommands)


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

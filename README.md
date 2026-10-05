# Jump Ads CRM — MVP

FastAPI + асинхронный Supabase Client, без ORM.

## Структура

- `backend/requirements.txt` — все зависимости.
- `backend/app/` — конфигурация, схемы, авторизация, лиды, теги и вебхуки.
- `backend/bot/` — перенесённые заготовки Telegram-бота; FSM пока не реализован.
- `backend/.env.example` — пример общей конфигурации.
- `backend/Dockerfile` — простой образ для запуска API.
- `backend/tests/test_api.py` — базовые HTTP-тесты без подключения к реальной БД.
- `migrations/001_initial_schema.sql` — SQL из предыдущего шага.

## Запуск из корня проекта

```bash
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Заполнить `backend/.env`: Supabase URL, серверный ключ, Telegram bot token и сгенерированный `JWT_SECRET`. Для демо: `PIN_LOGIN_ENABLED=true`, `BROWSER_PIN=2026`, `WEBHOOK_SECRET=test123`.

Один раз выполнить `migrations/001_initial_schema.sql` в SQL Editor нового проекта Supabase. Миграция создаёт таблицы, тестового менеджера и функцию создания вебхук-лида с тегами.

```bash
python -m uvicorn app.main:app --app-dir backend --reload
```

Открыть http://127.0.0.1:8000/docs. Выполнить `POST /auth/pin` с `{"pin":"2026"}`, скопировать `access_token` в **Authorize**.

## Проверка и Docker

Из корня проекта, с активированным `.venv`:

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_api.py -q
docker build -t jump-crm-api backend
docker run --rm --env-file backend/.env -e PORT=8000 -p 8000:8000 jump-crm-api
```

Тесты проверяют `/health`, получение и использование JWT через PIN, неверный PIN и все CRUD-маршруты без токена или с невалидным токеном. Supabase HTTP подменяется через `httpx.MockTransport`, реальные секреты не нужны. Docker копирует только `requirements.txt` и `app/`; `.env` передаётся при запуске.

## API

- `POST /auth/telegram` — подписанный `initData`, проверка HMAC и `auth_date`, JWT. Telegram ID сотрудника должен быть заранее добавлен в `users`.
- `POST /auth/pin` — JWT тестового менеджера.
- `GET /leads`, `POST /leads`, `PATCH /leads/{id}`, `DELETE /leads/{id}`.
- `GET /tags`, `POST /tags`, `POST /leads/{id}/tags/{tag_id}`.
- Все CRUD-маршруты требуют JWT; удаление — только admin. Роль читается из БД.
- `GET /leads` поддерживает `status`, `tag_id`, `next_contact_date`, `limit`, `offset`.

## Вебхук

`POST /api/webhooks/external`:

```json
{
  "source_name": "website_form",
  "name": "Иван Петров",
  "contact": "ivan@example.com",
  "request": "Нужен лендинг для стартапа, срочно!",
  "secret": "test123"
}
```

Неверный или отсутствующий секрет → 401. Пустой текст или подстрока `spam`, `test`, `игнор`, `ignore`, `null`, `undefined` без учёта регистра → 400 с `{"error":"Request filtered as spam"}`. Email и тип события не блокируются.

Валидный лид получает `source='webhook'` и тег «Веб-форма»; текст короче 10 символов — дополнительно `short_request`. Лид и теги создаются одной транзакцией через Supabase RPC. Следующая итерация: настраиваемые правила через админ-панель.

PIN 2026 и секрет test123 предназначены для демо. Серверный ключ Supabase хранится только в backend/.env. Публичный деплой и проверка с реальным Supabase ещё не выполнены.

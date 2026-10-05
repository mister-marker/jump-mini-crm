# Jump Ads CRM — MVP

FastAPI + асинхронный Supabase Client, без ORM.

## Структура

- `backend/requirements.txt` — все зависимости.
- `backend/app/` — конфигурация, схемы, авторизация, лиды, теги и вебхуки.
- `backend/bot/` — aiogram FSM и webhook-runtime в процессе FastAPI.
- `backend/.env.example` — пример общей конфигурации.
- `backend/Dockerfile` — простой образ для запуска API.
- `backend/tests/test_api.py` — базовые HTTP-тесты без подключения к реальной БД.
- `migrations/001_initial_schema.sql` — SQL из предыдущего шага.
- `migrations/20261005083640_bot_lead_creation.sql` — атомарное создание заявки бота с тегом.

## Запуск из корня проекта

```bash
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
# Только при первой настройке: не перезаписывать заполненный .env.
cp -n backend/.env.example backend/.env
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Заполнить `backend/.env`: Supabase URL, серверный ключ, Telegram bot token и сгенерированный `JWT_SECRET`. Для демо: `PIN_LOGIN_ENABLED=true`, `BROWSER_PIN=2026`, `WEBHOOK_SECRET=test123`.

В новом проекте Supabase выполнить SQL-файлы из `migrations/` по порядку. Первая миграция создаёт таблицы, тестового менеджера и функцию внешнего вебхука. Вторая добавляет функцию бота. В существующем проекте повторять первую миграцию нельзя.

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

Тесты проверяют `/health`, JWT/PIN, защиту CRUD, секрет Telegram webhook, FSM, подтверждение, отмену, повторную доставку и восстановление после ошибок БД/Telegram. Supabase HTTP и Telegram API подменяются, реальные секреты не нужны. Docker копирует `requirements.txt`, `app/` и `bot/`; `.env` передаётся при запуске.

## Telegram-бот на Render

Бот: https://t.me/jump_crm_lead_bot. API: https://jump-mini-crm.onrender.com/docs.

Бот и FastAPI работают в одном Web Service, без polling и отдельного worker. Сценарий:
`/start → имя → контакт → запрос → Отправить заявку`. `/cancel` или «Отмена» сбрасывает анкету.
Контакт можно ввести текстом или отправить кнопкой; username не обязателен. Лид создаётся
только после подтверждения, с `source='bot'` и тегом «Telegram-бот». Заявитель не получает доступ к CRM.

После применения второй SQL-миграции добавить в Render **Environment**:

```dotenv
TELEGRAM_WEBHOOK_URL=https://jump-mini-crm.onrender.com/api/webhooks/telegram
TELEGRAM_WEBHOOK_SECRET=<отдельный случайный секрет из backend/.env>
```

Секрет генерируется через `secrets.token_urlsafe(48)` (команда выше), хранится только в `.env`
и Render. Это отдельный секрет: `WEBHOOK_SECRET` обслуживает `/api/webhooks/external`.
При старте сервис сам вызывает `setWebhook`, разрешает только `message`, `max_connections=1`,
сохраняет ожидающие обновления. Ошибка регистрации останавливает запуск с безопасным сообщением.
Не задавать `TELEGRAM_WEBHOOK_URL` локально, чтобы локальный запуск не менял webhook рабочего бота.
Без `TELEGRAM_WEBHOOK_SECRET` бот отключён, остальные API продолжают работать.

Маршрут `POST /api/webhooks/telegram` проверяет заголовок `X-Telegram-Bot-Api-Secret-Token`.
Ответ `200` выдаётся после обработки; при сбое возвращается `503` для повторной доставки Telegram.
Повтор обработанного update не сдвигает FSM. UUID заявки зависит от ID бота, чата и сообщения `/start`:
SQL-функция не создаёт второй лид и не перезаписывает изменения менеджера при повторе.
Новая заявка того же человека начинается новым `/start` и получает другой UUID.

Ограничения MVP: **один процесс Uvicorn**, FSM в памяти. После сна/перезапуска Render
незавершённую анкету нужно начать заново через `/start`; сохранённые лиды остаются в Supabase.
На бесплатном Render первый ответ после сна может задержаться. Медиа, группы и личный MTProto
не поддерживаются; спам-фильтр внешнего вебхука к явной анкете бота не применяется.

Проверка после деплоя: открыть `/ready`, пройти `/start` и подтвердить заявку, затем проверить
её и тег через JWT-защищённый `GET /leads` в `/docs`. GitHub push обновляет сервис, если включён
Auto-Deploy; иначе выбрать Manual Deploy → Deploy latest commit.

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

PIN 2026 и секрет test123 предназначены для демо. Серверный ключ Supabase хранится только
в backend/.env и окружении Render. Базовый API проверен на Render с настоящим Supabase;
приём заявки живым ботом проверяется после деплоя версии с webhook и добавления его переменных.

# AGENTS.md — Правила и контекст проекта

## О проекте
Мини-CRM для агентства Jump Ads. Задача: Собирает лиды из Telegram-бота, вручную и через внешние вебхуки.
Стек: **FastAPI + Supabase (PostgreSQL) + React/Vite (Telegram Mini App)**.
Цель: работающий MVP. Приоритет — функциональность, Скорость, стабильность, чистый код и премиальный UX. Никакого overengineering. Мы решаем бизнес-задачу минимальными средствами.

## Обязательные пункты MVP:
- **«Заявки из Telegram-бота. Человек пишет боту... она сама появляется в CRM.» — Реализовано и проверено пользователем на Render. backend/bot/: FSM имя → способ связи → контакт → запрос → подтверждение. Telegram webhook принимает FastAPI, общий сервис сохраняет лид и тег в Supabase.**
- **«Ручное добавление.» — Кнопка React-интерфейса и MainButton Telegram открывают панель Vaul. Полноценная браузерная версия работает без Telegram SDK.**
- **«Теги. Лидам можно присваивать теги и видеть лидов по тегу.» На главной вкладке у нас горизонтальный скролл с чипсами-тегами для фильтрации, а в карточках лидов теги подсвечиваются цветом.**

## Архитектура
- **Frontend:** Telegram Mini App (React/Vite или Retool) + адаптив под iOS/Android/Desktop.
- **Backend:** FastAPI (async) — единый шлюз для API, вебхуков и валидации Telegram initData.
- **Database:** Supabase (PostgreSQL) — хранение лидов, тегов, пользователей, ролей.
- **Bot:** Python + aiogram 3.x — сбор заявок и взаимодействие с Mini App.
- **Deploy:** Render Free Web Service (бот + FastAPI, один процесс) + Vercel (Mini App) + Supabase (БД).
- **Webhook бота:** `/api/webhooks/telegram`, отдельный `TELEGRAM_WEBHOOK_SECRET`. `TELEGRAM_WEBHOOK_URL` задаётся только на Render; регистрация при старте. Незавершённый FSM в памяти теряется после перезапуска.

## Роли
- **admin** — полный доступ (удаление, аналитика). Ваш Telegram ID прописан в БД.
- **manager** — создание/редактирование лидов, смена статусов, работа с тегами.

## Функциональные требования (обязательные)
1. Telegram-бот собирает заявку (имя, контакт, запрос) → лид в CRM.
2. Ручное добавление лида через Mini App.
3. Присвоение тегов и фильтрация по ним.
4. (Опционально) Подключение обычного Telegram через вебхук.

## Дополнительно (лайт-версии для MVP)
- **Авторизация в браузере:** если initData пуст, показываем окно «Введите ПИН-код (2026)» → выдаём JWT тестового менеджера. 
- **RBAC:** колонка `role` в таблице `users`. Кнопка удаления и аналитика — только для admin.
- **Внешние вебхуки:** `POST /api/webhooks/external` принимает JSON. **Критическое правило:** скрипт должен фильтровать входящий поток и полностью исключать определенные входящие email-запросы с сайта, чтобы они не попадали в CRM как лиды.
- **После обязательного MVP:** канбан, календарь, аналитика и личный Telegram API. Сначала браузерный список, ручное создание, теги/фильтры и работающий бот; тот же фронтенд открывается в Telegram.
- **UI/UX Директивы:** Темная тема по умолчанию. Используй CSS-переменные Telegram (например, `bg-[var(--tg-theme-bg-color)]`). Карточки: `bg-[#1e293b] rounded-2xl border-slate-700`.


## Модель данных (SQL)
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE,
    role TEXT CHECK (role IN ('admin', 'manager')) DEFAULT 'manager',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    contact TEXT NOT NULL,
    request TEXT,
    source TEXT CHECK (source IN ('bot', 'manual', 'telegram', 'webhook')) DEFAULT 'manual',
    status TEXT CHECK (status IN ('new', 'in_progress', 'done', 'rejected')) DEFAULT 'new',
    next_contact_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    color TEXT DEFAULT '#6B7280'
);

CREATE TABLE lead_tags (
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (lead_id, tag_id)
);

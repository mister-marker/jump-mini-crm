"""Webhook-only aiogram runtime, owned by FastAPI's lifespan (one worker)."""

import asyncio
from collections import OrderedDict

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import MenuButtonCommands, Update
from supabase import AsyncClient

from app.core.config import Settings
from bot.handlers.leads import create_router


class BotRuntime:
    def __init__(self, settings: Settings, db: AsyncClient) -> None:
        self.settings = settings
        self.db = db
        self.bot = Bot(settings.telegram_bot_token.get_secret_value(),
                       session=AiohttpSession(timeout=10))
        self.dispatcher = Dispatcher(storage=MemoryStorage())
        self.dispatcher.include_router(create_router())
        self.lock = asyncio.Lock()
        self.processed: OrderedDict[int, None] = OrderedDict()

    async def start(self) -> None:
        # A global Web App menu would expose the CRM entry point to applicants.
        await self.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        if self.settings.telegram_webhook_url is not None:
            await self.bot.set_webhook(
                url=str(self.settings.telegram_webhook_url),
                secret_token=self.settings.telegram_webhook_secret.get_secret_value(),
                allowed_updates=["message"], max_connections=1, drop_pending_updates=False,
            )

    async def close(self) -> None:
        # Do not delete the remote webhook on shutdown: Render sleeps/restarts.
        await self.dispatcher.storage.close()
        await self.bot.session.close()

    async def process(self, update: Update) -> None:
        message = update.message
        if (message is None or message.chat.type != "private"
                or message.from_user is None or message.from_user.is_bot):
            return
        # Serialize FSM transitions and duplicate checks; this MVP runs one worker.
        async with self.lock:
            if update.update_id in self.processed:
                return
            context = self.dispatcher.fsm.get_context(
                bot=self.bot, chat_id=message.chat.id, user_id=message.from_user.id,
            )
            previous_state = await context.get_state()
            previous_data = await context.get_data()
            if message.message_id <= previous_data.get("last_message_id", -1):
                return
            try:
                await self.dispatcher.feed_update(
                    self.bot, update, db=self.db,
                    crm_web_app_url=str(self.settings.crm_web_app_url),
                )
                await context.update_data(last_message_id=message.message_id)
            except Exception:
                # A failed DB call or Telegram reply must leave the update retryable.
                # If the DB committed before a timeout, the RPC's stable ID prevents a duplicate.
                await context.set_state(previous_state)
                await context.set_data(previous_data)
                raise
            self.processed[update.update_id] = None
            if len(self.processed) > 10000:
                self.processed.popitem(last=False)

"""One explicit application: name → contact → request → confirmation."""

import re
from uuid import NAMESPACE_URL, UUID, uuid5

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove
from supabase import AsyncClient

from app.models.schemas import LeadCreate
from app.services.leads import create_bot_lead
from bot.keyboards import (
    CANCEL, CHANGE_CONTACT, EMAIL, PHONE, SUBMIT, TELEGRAM,
    cancel_keyboard, confirm_keyboard, contact_keyboard, contact_method_keyboard,
)


class Application(StatesGroup):
    name = State()
    contact_method = State()
    contact = State()
    request = State()
    confirm = State()


async def start(message: Message, state: FSMContext) -> None:
    # Stable across retries; a new /start message begins a different application.
    submission_id = uuid5(
        NAMESPACE_URL, f"telegram:{message.bot.id}:{message.chat.id}:{message.message_id}"
    )
    await state.set_data({"submission_id": str(submission_id)})
    await state.set_state(Application.name)
    await message.answer(
        "Здравствуйте! Это бот для заявок в агентство Jump Ads.\n\n"
        "Хотите обсудить проект? Я уточню ваше имя, удобный способ связи и задачу. "
        "Затем вы проверите заявку и решите, отправлять ли её менеджеру.\n"
        "До подтверждения заявка не отправляется. Отменить заполнение можно командой /cancel.\n\n"
        "Шаг 1 из 3. Как к вам обращаться?", reply_markup=cancel_keyboard(),
    )


async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Заявка отменена. Чтобы начать заново, отправьте /start.",
                         reply_markup=ReplyKeyboardRemove())


async def unknown_command(message: Message) -> None:
    await message.answer("Используйте /start для новой заявки или /cancel для отмены.")


async def name(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 1 <= len(value) <= 200:
        await message.answer("Введите имя текстом: от 1 до 200 символов.")
        return
    await state.update_data(name=value)
    await ask_contact_method(message, state)


async def ask_contact_method(message: Message, state: FSMContext) -> None:
    await state.set_state(Application.contact_method)
    username = message.from_user.username if message.from_user else None
    telegram_hint = f"\nTelegram — используем ваш @{username}." if username else ""
    await message.answer(
        "Шаг 2 из 3. Где вам удобнее получить ответ менеджера?\n"
        f"Выберите один способ кнопкой ниже.{telegram_hint}",
        reply_markup=contact_method_keyboard(has_username=bool(username)),
    )


async def choose_contact_method(message: Message, state: FSMContext) -> None:
    method = message.text
    if method == TELEGRAM and message.from_user and message.from_user.username:
        await save_contact(message, state, f"@{message.from_user.username}", TELEGRAM)
        return
    if method not in (PHONE, EMAIL):
        await ask_contact_method(message, state)
        return
    await state.update_data(contact_method=method)
    await state.set_state(Application.contact)
    prompt = (
        "Вы выбрали телефон. Нажмите «Поделиться моим номером» и подтвердите передачу "
        "номера в Telegram или введите номер с кодом страны, например +79991234567."
        if method == PHONE else
        "Вы выбрали email. Введите адрес, на который менеджер сможет ответить, "
        "например name@example.com."
    )
    await message.answer(prompt, reply_markup=contact_keyboard(share_phone=method == PHONE))


async def contact(message: Message, state: FSMContext) -> None:
    if message.text == CHANGE_CONTACT:
        await ask_contact_method(message, state)
        return
    data = await state.get_data()
    method = data["contact_method"]
    value = (message.text or "").strip()
    if method == PHONE:
        if message.contact:
            if message.from_user is None or message.contact.user_id != message.from_user.id:
                await message.answer("Поделитесь своим контактом или введите свой номер текстом.")
                return
            value = "+" + message.contact.phone_number.strip().lstrip("+")
        value = re.sub(r"[ ()-]", "", value)
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
            await message.answer("Введите номер с кодом страны, например +79991234567, "
                                 "или нажмите «Поделиться моим номером».")
            return
    elif not 1 <= len(value) <= 320 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        await message.answer("Введите email в формате name@example.com. "
                             "Чтобы оставить телефон, нажмите «Другой способ связи».")
        return
    await save_contact(message, state, value, method)


async def save_contact(message: Message, state: FSMContext, value: str, method: str) -> None:
    await state.update_data(contact=value, contact_method=method)
    await state.set_state(Application.request)
    await message.answer(f"Способ связи: {method} — {value}.\n\n"
                         "Шаг 3 из 3. Расскажите, с какой задачей нужна помощь.\n"
                         "Например: «Нужен лендинг для нового проекта». До 3000 символов.",
                         reply_markup=cancel_keyboard())


async def request_text(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 1 <= len(value) <= 3000:
        await message.answer("Опишите задачу текстом: от 1 до 3000 символов.")
        return
    data = await state.update_data(request=value)
    await state.set_state(Application.confirm)
    # No HTML/Markdown parsing: client text must remain literal text.
    await message.answer(
        f"Проверьте заявку для Jump Ads:\n\nИмя: {data['name']}\n"
        f"Связь ({data['contact_method']}): {data['contact']}\n"
        f"Задача: {value}\n\nПосле нажатия «{SUBMIT}» заявка появится у менеджера. "
        "Чтобы заполнить заново, отправьте /start. Для отмены — /cancel.",
        reply_markup=confirm_keyboard(),
    )


async def submit(message: Message, state: FSMContext, db: AsyncClient) -> None:
    data = await state.get_data()
    lead = LeadCreate(name=data["name"], contact=data["contact"],
                      request=data["request"], source="bot")
    await create_bot_lead(db, UUID(data["submission_id"]), lead)
    await message.answer("Спасибо! Заявка передана команде Jump Ads. "
                         "Менеджер свяжется с вами по указанному контакту.\n"
                         "Для новой заявки отправьте /start.", reply_markup=ReplyKeyboardRemove())
    await state.clear()


async def confirm_help(message: Message) -> None:
    await message.answer(f"Нажмите «{SUBMIT}», чтобы сохранить заявку, или /cancel для отмены.",
                         reply_markup=confirm_keyboard())


async def idle(message: Message) -> None:
    await message.answer("Чтобы оставить заявку, отправьте /start.",
                         reply_markup=ReplyKeyboardRemove())


def create_router() -> Router:
    router = Router(name="lead_application")
    router.message.filter(F.chat.type == "private", F.from_user.is_bot == False)
    router.message.register(start, CommandStart())
    router.message.register(cancel, Command("cancel"))
    router.message.register(cancel, F.text == CANCEL)
    router.message.register(unknown_command, F.text.startswith("/"))
    router.message.register(name, Application.name)
    router.message.register(choose_contact_method, Application.contact_method)
    router.message.register(contact, Application.contact)
    router.message.register(request_text, Application.request)
    router.message.register(submit, Application.confirm, F.text == SUBMIT)
    router.message.register(confirm_help, Application.confirm)
    router.message.register(idle)
    return router

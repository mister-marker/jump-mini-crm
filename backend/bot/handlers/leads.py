"""One explicit application: name → contact → request → confirmation."""

from uuid import NAMESPACE_URL, UUID, uuid5

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove
from supabase import AsyncClient

from app.models.schemas import LeadCreate
from app.services.leads import create_bot_lead
from bot.keyboards import CANCEL, SUBMIT, cancel_keyboard, confirm_keyboard, contact_keyboard


class Application(StatesGroup):
    name = State()
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
        "Здравствуйте! Оставьте заявку для Jump Ads. Как к вам обращаться?\n"
        "Отменить заполнение можно командой /cancel.", reply_markup=cancel_keyboard(),
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
    await state.set_state(Application.contact)
    await message.answer("Как с вами связаться? Введите телефон, email или @username. "
                         "Можно поделиться своим телефоном кнопкой ниже.",
                         reply_markup=contact_keyboard())


async def contact(message: Message, state: FSMContext) -> None:
    if message.contact:
        if message.from_user is None or message.contact.user_id != message.from_user.id:
            await message.answer("Поделитесь своим контактом или введите контакт текстом.")
            return
        value = message.contact.phone_number.strip()
    else:
        value = (message.text or "").strip()
    if not 1 <= len(value) <= 320:
        await message.answer("Введите контакт текстом: от 1 до 320 символов.")
        return
    await state.update_data(contact=value)
    await state.set_state(Application.request)
    await message.answer("Расскажите, с какой задачей нужна помощь (до 3000 символов).",
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
        f"Проверьте заявку:\n\nИмя: {data['name']}\nКонтакт: {data['contact']}\n"
        f"Запрос: {value}\n\nНажмите «{SUBMIT}» или отмените заполнение.",
        reply_markup=confirm_keyboard(),
    )


async def submit(message: Message, state: FSMContext, db: AsyncClient) -> None:
    data = await state.get_data()
    lead = LeadCreate(name=data["name"], contact=data["contact"],
                      request=data["request"], source="bot")
    await create_bot_lead(db, UUID(data["submission_id"]), lead)
    await message.answer("Спасибо! Заявка сохранена. Мы свяжемся с вами.\n"
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
    router.message.register(contact, Application.contact)
    router.message.register(request_text, Application.request)
    router.message.register(submit, Application.confirm, F.text == SUBMIT)
    router.message.register(confirm_help, Application.confirm)
    router.message.register(idle)
    return router

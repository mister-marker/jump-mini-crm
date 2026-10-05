"""Small reply keyboards; the bot also works without a Telegram username."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

CANCEL = "Отмена"
SUBMIT = "Отправить заявку"
TELEGRAM = "Telegram"
PHONE = "Телефон"
EMAIL = "Email"
CHANGE_CONTACT = "Другой способ связи"


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=CANCEL)]], resize_keyboard=True)


def contact_method_keyboard(has_username: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=TELEGRAM)]] if has_username else []
    rows.extend([[KeyboardButton(text=PHONE), KeyboardButton(text=EMAIL)],
                 [KeyboardButton(text=CANCEL)]])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def contact_keyboard(share_phone: bool = False) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="Поделиться моим номером", request_contact=True)]] if share_phone else []
    rows.extend([[KeyboardButton(text=CHANGE_CONTACT)], [KeyboardButton(text=CANCEL)]])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def confirm_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=SUBMIT)], [KeyboardButton(text=CANCEL)],
    ], resize_keyboard=True)

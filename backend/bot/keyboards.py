"""Small reply keyboards; the bot also works without a Telegram username."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

CANCEL = "Отмена"
SUBMIT = "Отправить заявку"


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=CANCEL)]], resize_keyboard=True)


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Поделиться телефоном", request_contact=True)],
        [KeyboardButton(text=CANCEL)],
    ], resize_keyboard=True)


def confirm_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=SUBMIT)], [KeyboardButton(text=CANCEL)],
    ], resize_keyboard=True)

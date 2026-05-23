from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

MIN_PIN = 4
MAX_PIN = 8


def pin_dots(count: int) -> str:
    """Return dot progress line, e.g. ● ● ○ ○"""
    total = max(count, MIN_PIN)
    parts = ["●" if i < count else "○" for i in range(total)]
    return "  ".join(parts)


def pin_webapp_kb(base_url: str, mode: str) -> ReplyKeyboardMarkup:
    """
    Reply keyboard that opens the HTML PIN Mini App.
    sendData() ONLY works from a reply keyboard button — not inline keyboard.
    """
    url = f"{base_url}?mode={mode}"
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🔐 Enter PIN", web_app=WebAppInfo(url=url)))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def pin_remove_kb() -> ReplyKeyboardRemove:
    """Remove the reply keyboard after PIN is received."""
    return ReplyKeyboardRemove()


def pin_pad_kb(
    digits: int,
    cancel_data: str = "pin:cancel",
    show_forgot: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row_nums in [(1, 2, 3), (4, 5, 6), (7, 8, 9)]:
        builder.row(*[
            InlineKeyboardButton(text=str(n), callback_data=f"pin:d:{n}")
            for n in row_nums
        ])
    right = (
        InlineKeyboardButton(text="✅", callback_data="pin:submit")
        if digits >= MIN_PIN
        else InlineKeyboardButton(text="✕", callback_data=cancel_data)
    )
    builder.row(
        InlineKeyboardButton(text="⌫", callback_data="pin:back"),
        InlineKeyboardButton(text="0", callback_data="pin:d:0"),
        right,
    )
    if show_forgot:
        builder.row(
            InlineKeyboardButton(text="🔑 Forgot PIN?", callback_data="pin:forgot")
        )
    return builder.as_markup()

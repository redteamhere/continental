from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.i18n.translations import STRINGS


def language_select_kb() -> InlineKeyboardMarkup:
    """5-language selection keyboard shown on first /start."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=STRINGS["en"]["flag"], callback_data="lang:en"),
        InlineKeyboardButton(text=STRINGS["zh"]["flag"], callback_data="lang:zh"),
    )
    builder.row(
        InlineKeyboardButton(text=STRINGS["ru"]["flag"], callback_data="lang:ru"),
        InlineKeyboardButton(text=STRINGS["pt"]["flag"], callback_data="lang:pt"),
    )
    builder.row(
        InlineKeyboardButton(text=STRINGS["tr"]["flag"], callback_data="lang:tr"),
    )
    return builder.as_markup()

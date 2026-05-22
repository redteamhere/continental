from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

MIN_PIN = 4
MAX_PIN = 8


def pin_dots(count: int) -> str:
    """Return dot progress line, e.g. ● ● ○ ○"""
    total = max(count, MIN_PIN)
    parts = ["●" if i < count else "○" for i in range(total)]
    return "  ".join(parts)


def pin_pad_kb(digits: int, cancel_data: str = "pin:cancel") -> InlineKeyboardMarkup:
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
    return builder.as_markup()

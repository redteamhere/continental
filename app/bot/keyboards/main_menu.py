from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.i18n.translations import t


def main_menu_kb(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("btn_new_deal", lang), callback_data="menu:new_deal"),
        InlineKeyboardButton(text=t("btn_my_deals", lang), callback_data="menu:my_deals"),
    )
    builder.row(
        InlineKeyboardButton(text=t("btn_profile",  lang), callback_data="menu:profile"),
        InlineKeyboardButton(text=t("btn_wallet",   lang), callback_data="menu:wallet"),
    )
    builder.row(
        InlineKeyboardButton(text=t("btn_stats",    lang), callback_data="menu:stats"),
        InlineKeyboardButton(text=t("btn_referral", lang), callback_data="menu:referral"),
    )
    builder.row(
        InlineKeyboardButton(text=t("btn_help",     lang), callback_data="menu:help"),
    )
    return builder.as_markup()


def back_kb(callback: str = "menu:main", lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=t("btn_back", lang), callback_data=callback)
        ]]
    )


def deals_list_kb(deals: list, page: int = 0, total: int = 0, lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for deal in deals:
        status_icon = {
            "pending":          "🟡",
            "awaiting_payment": "💳",
            "funded":           "💰",
            "in_progress":      "⚙️",
            "completed":        "✅",
            "cancelled":        "❌",
            "disputed":         "⚖️",
            "refunded":         "↩️",
        }.get(deal.status.value, "❓")
        builder.row(
            InlineKeyboardButton(
                text=f"{status_icon} {deal.deal_number} — {deal.amount} {deal.currency.symbol}",
                callback_data=f"deal:view:{deal.id}",
            )
        )

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"deals:page:{page-1}"))
    if (page + 1) * 10 < total:
        nav_row.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"deals:page:{page+1}"))
    if nav_row:
        builder.row(*nav_row)

    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="menu:main"))
    return builder.as_markup()

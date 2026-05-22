from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_panel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⚖️ Open Disputes", callback_data="admin:disputes"),
        InlineKeyboardButton(text="👥 Users", callback_data="admin:users"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats"),
        InlineKeyboardButton(text="💰 Transactions", callback_data="admin:transactions"),
    )
    builder.row(
        InlineKeyboardButton(text="🔍 Lookup User", callback_data="admin:lookup_user"),
        InlineKeyboardButton(text="🔍 Lookup Deal", callback_data="admin:lookup_deal"),
    )
    builder.row(InlineKeyboardButton(text="⬅️ Main Menu", callback_data="menu:main"))
    return builder.as_markup()


def dispute_resolve_kb(dispute_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Full Refund to Buyer", callback_data=f"admin:resolve:{dispute_id}:buyer_refund")],
        [InlineKeyboardButton(text="💵 Release to Seller", callback_data=f"admin:resolve:{dispute_id}:seller_release")],
        [InlineKeyboardButton(text="⚖️ Partial Split", callback_data=f"admin:resolve:{dispute_id}:partial_split")],
        [InlineKeyboardButton(text="📁 No Action", callback_data=f"admin:resolve:{dispute_id}:no_action")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="admin:disputes")],
    ])


def user_action_kb(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    ban_btn = (
        InlineKeyboardButton(text="✅ Unban", callback_data=f"admin:unban:{user_id}")
        if is_banned
        else InlineKeyboardButton(text="🚫 Ban", callback_data=f"admin:ban:{user_id}")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [ban_btn],
        [InlineKeyboardButton(text="🔑 Set Moderator", callback_data=f"admin:set_mod:{user_id}")],
        [InlineKeyboardButton(text="📋 View Deals", callback_data=f"admin:user_deals:{user_id}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="admin:users")],
    ])

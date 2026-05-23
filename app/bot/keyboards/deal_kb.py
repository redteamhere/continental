from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models.deal import Deal, DealStatus


def currency_select_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💵 USDT (TRC20)", callback_data="currency:USDT_TRC20"))
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="deal:cancel_creation"))
    return builder.as_markup()


def deadline_select_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 day", callback_data="deadline:1"),
        InlineKeyboardButton(text="3 days", callback_data="deadline:3"),
        InlineKeyboardButton(text="7 days", callback_data="deadline:7"),
    )
    builder.row(
        InlineKeyboardButton(text="14 days", callback_data="deadline:14"),
        InlineKeyboardButton(text="30 days", callback_data="deadline:30"),
    )
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="deal:cancel_creation"))
    return builder.as_markup()


def confirm_cancel_kb(confirm_data: str, cancel_data: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Confirm", callback_data=confirm_data),
        InlineKeyboardButton(text="❌ Cancel", callback_data=cancel_data),
    ]])


def deal_action_kb(deal: Deal, viewer_id: int) -> InlineKeyboardMarkup:
    """Build action keyboard based on deal status and viewer role."""
    builder = InlineKeyboardBuilder()
    is_buyer = deal.buyer_id == viewer_id
    is_seller = deal.seller_id == viewer_id

    if deal.status == DealStatus.PENDING and is_seller:
        builder.row(
            InlineKeyboardButton(text="✅ Accept Deal", callback_data=f"deal:accept:{deal.id}"),
            InlineKeyboardButton(text="❌ Decline", callback_data=f"deal:decline:{deal.id}"),
        )

    elif deal.status == DealStatus.AWAITING_PAYMENT and is_buyer:
        builder.row(
            InlineKeyboardButton(text="💳 Pay Now", callback_data=f"deal:pay:{deal.id}"),
        )
        builder.row(
            InlineKeyboardButton(text="❌ Cancel Deal", callback_data=f"deal:cancel:{deal.id}"),
        )

    elif deal.status == DealStatus.FUNDED:
        if is_buyer:
            builder.row(
                InlineKeyboardButton(text="✅ Release Funds", callback_data=f"deal:release:{deal.id}"),
                InlineKeyboardButton(text="⚖️ Open Dispute", callback_data=f"deal:dispute:{deal.id}"),
            )
        if is_seller:
            builder.row(
                InlineKeyboardButton(text="📦 Mark as Delivered", callback_data=f"deal:delivered:{deal.id}"),
            )
            builder.row(
                InlineKeyboardButton(text="⚖️ Open Dispute", callback_data=f"deal:dispute:{deal.id}"),
            )
        if is_buyer or is_seller:
            builder.row(
                InlineKeyboardButton(text="💬 Deal Chat", callback_data=f"deal:chat:{deal.id}"),
            )

    elif deal.status == DealStatus.IN_PROGRESS:
        if is_buyer:
            builder.row(
                InlineKeyboardButton(text="✅ Release Funds", callback_data=f"deal:release:{deal.id}"),
                InlineKeyboardButton(text="⚖️ Open Dispute", callback_data=f"deal:dispute:{deal.id}"),
            )
        if is_buyer or is_seller:
            builder.row(
                InlineKeyboardButton(text="💬 Deal Chat", callback_data=f"deal:chat:{deal.id}"),
            )

    elif deal.status == DealStatus.COMPLETED and (is_buyer or is_seller):
        if not deal.review:
            builder.row(
                InlineKeyboardButton(text="⭐ Leave Review", callback_data=f"deal:review:{deal.id}"),
            )

    builder.row(InlineKeyboardButton(text="⬅️ Back to Deals", callback_data="menu:my_deals"))
    return builder.as_markup()


def seller_deal_kb(deal: Deal) -> InlineKeyboardMarkup:
    """Seller view — accept/decline."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Accept", callback_data=f"deal:accept:{deal.id}"),
            InlineKeyboardButton(text="❌ Decline", callback_data=f"deal:decline:{deal.id}"),
        ]
    ])


def buyer_deal_funded_kb(deal: Deal) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Release Funds to Seller", callback_data=f"deal:release:{deal.id}")],
        [InlineKeyboardButton(text="⚖️ Open Dispute", callback_data=f"deal:dispute:{deal.id}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu:my_deals")],
    ])


def payment_detail_kb(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Check Payment Status", callback_data=f"deal:check_payment:{deal_id}")],
        [InlineKeyboardButton(text="❌ Cancel Deal", callback_data=f"deal:cancel:{deal_id}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data=f"deal:view:{deal_id}")],
    ])


def review_stars_kb(deal_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(*[
        InlineKeyboardButton(text=f"{'⭐' * i}", callback_data=f"review:{deal_id}:{i}")
        for i in range(1, 6)
    ])
    builder.row(InlineKeyboardButton(text="Skip", callback_data=f"review:{deal_id}:skip"))
    return builder.as_markup()

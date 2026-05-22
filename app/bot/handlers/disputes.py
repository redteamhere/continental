"""Dispute opening and evidence submission."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Document, Message, PhotoSize

from app.bot.keyboards.main_menu import back_kb, main_menu_kb
from app.bot.states.dispute import DisputeStates
from app.database import AsyncSessionFactory
from app.models.dispute import Dispute, DisputeStatus
from app.services.audit_service import AuditService
from app.services.deal_service import DealService
from app.services.notification_service import NotificationService
from app.services.user_service import UserService

router = Router()


@router.callback_query(F.data.startswith("deal:dispute:"))
async def open_dispute_start(callback: CallbackQuery, state: FSMContext, db_user) -> None:
    deal_id = int(callback.data.split(":")[2])
    await state.update_data(dispute_deal_id=deal_id)
    await state.set_state(DisputeStates.enter_reason)
    await callback.message.answer(
        "⚖️ <b>Open Dispute</b>\n\n"
        "Describe the issue clearly (max 1000 chars). "
        "Include what was agreed, what happened, and what resolution you want:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(DisputeStates.enter_reason)
async def dispute_enter_reason(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    reason = message.text.strip()
    if len(reason) < 20:
        await message.answer("❌ Please provide more detail (min 20 chars).")
        return
    if len(reason) > 1000:
        await message.answer("❌ Too long (max 1000 chars).")
        return

    await state.update_data(dispute_reason=reason)
    await state.set_state(DisputeStates.upload_evidence)
    await message.answer(
        "📎 Upload evidence (photos or documents). "
        "Send up to 5 files, then type /done when finished.\n"
        "Type /skip to skip evidence."
    )


@router.message(DisputeStates.upload_evidence, F.photo)
async def dispute_upload_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    evidence = data.get("evidence_file_ids", [])
    if len(evidence) >= 5:
        await message.answer("Maximum 5 files reached. Type /done to continue.")
        return
    # Use the largest available photo size
    file_id = message.photo[-1].file_id
    evidence.append({"type": "photo", "file_id": file_id})
    await state.update_data(evidence_file_ids=evidence)
    await message.answer(f"✅ Photo {len(evidence)}/5 received. Send more or type /done.")


@router.message(DisputeStates.upload_evidence, F.document)
async def dispute_upload_doc(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    evidence = data.get("evidence_file_ids", [])
    if len(evidence) >= 5:
        await message.answer("Maximum 5 files reached. Type /done to continue.")
        return
    evidence.append({"type": "document", "file_id": message.document.file_id})
    await state.update_data(evidence_file_ids=evidence)
    await message.answer(f"✅ Document {len(evidence)}/5 received.")


@router.message(DisputeStates.upload_evidence, F.text.in_({"/done", "/skip"}))
async def dispute_evidence_done(message: Message, state: FSMContext, db_user) -> None:
    data = await state.get_data()
    await state.set_state(DisputeStates.confirm_pin)
    evidence_count = len(data.get("evidence_file_ids", []))
    await message.answer(
        f"Evidence: {evidence_count} file(s) collected.\n\n"
        f"Enter your PIN to confirm and open the dispute:"
    )


@router.message(DisputeStates.confirm_pin)
async def dispute_confirm_pin(message: Message, state: FSMContext) -> None:
    pin = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass

    from app.security.pin_manager import PinManager

    async with AsyncSessionFactory() as session:
        svc = UserService(session)
        user = await svc.get_by_telegram_id(message.from_user.id)

        ok = await svc.verify_pin(user, pin)
        if not ok:
            await AuditService(session).pin_failed(user.id)
            await session.commit()
            await message.answer("❌ Wrong PIN. Dispute cancelled.")
            await state.clear()
            return
        await session.commit()

    await _create_dispute(message, state)


async def _create_dispute(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    deal_id = data["dispute_deal_id"]

    async with AsyncSessionFactory() as session:
        deal_svc = DealService(session)
        user_svc = UserService(session)
        notif_svc = NotificationService(session, message.bot)
        audit = AuditService(session)

        deal = await deal_svc.get_by_id(deal_id)
        opener = await user_svc.get_by_telegram_id(message.from_user.id)

        if not deal or opener.id not in (deal.buyer_id, deal.seller_id):
            await message.answer("Deal not found.", reply_markup=main_menu_kb())
            await state.clear()
            return

        # Open dispute
        await deal_svc.open_dispute(deal, opener, data["dispute_reason"])

        dispute = Dispute(
            deal_id=deal.id,
            opened_by_id=opener.id,
            status=DisputeStatus.OPEN,
            reason=data["dispute_reason"],
            evidence_file_ids=data.get("evidence_file_ids", []),
        )
        session.add(dispute)

        opener.total_disputes_opened += 1

        other_id = deal.seller_id if opener.id == deal.buyer_id else deal.buyer_id
        other_user = await user_svc.get_by_id(other_id)
        buyer = await user_svc.get_by_id(deal.buyer_id)
        seller = await user_svc.get_by_id(deal.seller_id)

        await notif_svc.dispute_opened(deal, opener, other_user)
        await audit.dispute_opened(opener.id, deal.id, data["dispute_reason"])

        # Notify admins
        from app.config import settings
        for admin_tg_id in settings.ADMIN_IDS:
            try:
                await message.bot.send_message(
                    admin_tg_id,
                    f"⚖️ <b>New Dispute</b>\n\n"
                    f"Deal: <code>{deal.deal_number}</code>\n"
                    f"Opened by: {opener.display_name}\n"
                    f"Reason: {data['dispute_reason'][:200]}\n"
                    f"Evidence: {len(data.get('evidence_file_ids', []))} file(s)\n\n"
                    f"Use /admin to review.",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        await session.commit()

    await state.clear()
    await message.answer(
        f"⚖️ <b>Dispute Opened</b>\n\n"
        f"Deal <code>{deal.deal_number}</code> is now under review.\n"
        f"A moderator will contact you within 24–48 hours.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )

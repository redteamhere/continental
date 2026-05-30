"""APScheduler setup with all background jobs."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger


def create_scheduler(bot=None) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Blockchain monitoring — every 60 seconds
    scheduler.add_job(
        _run_blockchain_monitor,
        trigger=IntervalTrigger(seconds=60),
        id="blockchain_monitor",
        replace_existing=True,
        max_instances=1,
    )

    # Deal expiry check — every 30 minutes
    scheduler.add_job(
        _run_deal_expiry,
        trigger=IntervalTrigger(minutes=30),
        id="deal_expiry",
        replace_existing=True,
        max_instances=1,
    )

    # Expiry warnings — every hour
    scheduler.add_job(
        _run_expiry_warnings,
        kwargs={"bot": bot},
        trigger=IntervalTrigger(hours=1),
        id="expiry_warnings",
        replace_existing=True,
        max_instances=1,
    )

    # Notify deal parties when payment confirmed — every 30 seconds
    scheduler.add_job(
        _run_payment_notifications,
        kwargs={"bot": bot},
        trigger=IntervalTrigger(seconds=30),
        id="payment_notifications",
        replace_existing=True,
        max_instances=1,
    )

    # Update bot short description with live user count — every hour
    scheduler.add_job(
        _run_update_bot_description,
        kwargs={"bot": bot},
        trigger=IntervalTrigger(hours=1),
        id="update_bot_description",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler


async def _run_blockchain_monitor() -> None:
    try:
        from app.crypto.monitor import BlockchainMonitor
        monitor = BlockchainMonitor()
        await monitor.run_cycle()
    except Exception as e:
        logger.error(f"[Scheduler] Blockchain monitor error: {e}")


async def _run_deal_expiry() -> None:
    try:
        from app.workers.deal_expiry import expire_overdue_deals
        await expire_overdue_deals()
    except Exception as e:
        logger.error(f"[Scheduler] Deal expiry error: {e}")


async def _run_expiry_warnings(bot=None) -> None:
    try:
        from app.workers.deal_expiry import send_expiry_warnings
        await send_expiry_warnings(bot)
    except Exception as e:
        logger.error(f"[Scheduler] Expiry warning error: {e}")


async def _run_payment_notifications(bot=None) -> None:
    try:
        from app.workers.blockchain_monitor import notify_funded_deals
        await notify_funded_deals(bot)
    except Exception as e:
        logger.error(f"[Scheduler] Payment notification error: {e}")


async def _run_update_bot_description(bot=None) -> None:
    """Push live monthly-active-user count to the bot's short description."""
    if not bot:
        return
    try:
        from app.database import AsyncSessionFactory
        from app.services.user_service import UserService
        from app.config import settings

        async with AsyncSessionFactory() as session:
            svc = UserService(session)
            monthly = await svc.count_monthly_active()

        count = monthly + settings.USER_COUNT_OFFSET
        short_desc = f"👥 {count:,} monthly active users"
        await bot.set_my_short_description(short_description=short_desc)
        logger.info(f"[Scheduler] Bot short description updated: {short_desc}")
    except Exception as e:
        logger.error(f"[Scheduler] Bot description update error: {e}")

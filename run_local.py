"""
Local development runner — polling mode (no webhook, no domain needed).
Usage: python run_local.py
"""
import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from loguru import logger

from app.config import settings
from app.database import create_tables
from app.bot.handlers import get_main_router
from app.bot.middleware.auth import AuthMiddleware
from app.bot.middleware.rate_limit import RateLimitMiddleware
from app.workers.scheduler import create_scheduler


async def main():
    logger.remove()
    logger.add(sys.stdout, level="DEBUG",
               format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")

    logger.info("Creating database tables...")
    await create_tables()
    logger.info("Tables ready.")

    # Use MemoryStorage if Redis is not configured (simpler local dev)
    try:
        storage = RedisStorage.from_url(settings.REDIS_URL)
        # Test the connection
        await storage.redis.ping()
        logger.info("Redis connected.")
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}), falling back to MemoryStorage (FSM resets on restart)")
        storage = MemoryStorage()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.message.middleware(RateLimitMiddleware(settings.REDIS_URL))
    dp.callback_query.middleware(RateLimitMiddleware(settings.REDIS_URL))

    dp.include_router(get_main_router())

    # Start background scheduler
    scheduler = create_scheduler(bot)
    scheduler.start()
    logger.info("Background scheduler started.")

    # Register bot commands in Telegram menu
    user_commands = [
        BotCommand(command="start", description="Start / open main menu"),
        BotCommand(command="help",  description="How to use this bot"),
    ]
    admin_commands = user_commands + [
        BotCommand(command="admin",   description="Open admin panel"),
        BotCommand(command="sim_pay", description="[DEV] Simulate payment for a deal"),
    ]

    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            logger.warning(f"Could not set admin commands for {admin_id}: {e}")

    me = await bot.get_me()
    logger.info(f"Bot started: @{me.username} — polling mode")
    logger.info("Press Ctrl+C to stop.")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())

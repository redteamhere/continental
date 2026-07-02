"""
Application entrypoint.
Supports both webhook mode (production) and polling mode (development).
"""
from __future__ import annotations

import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from fastapi import FastAPI
from loguru import logger

from app.config import settings
from app.database import create_tables, engine
from app.bot.handlers import get_main_router
from app.bot.middleware.auth import AuthMiddleware
from app.bot.middleware.rate_limit import RateLimitMiddleware
from app.workers.scheduler import create_scheduler

# ── Logging ──────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stdout,
    level=settings.LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
)
logger.add(
    "logs/escrow_bot.log",
    rotation="100 MB",
    retention="30 days",
    compression="gz",
    level="INFO",
)

# ── Storage (Redis with MemoryStorage fallback) ───────────────
try:
    import redis as _sync_redis
    _r = _sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    _r.ping()
    _r.close()
    storage = RedisStorage.from_url(settings.REDIS_URL)
    logger.info("Redis storage configured.")
except Exception as _e:
    from aiogram.fsm.storage.memory import MemoryStorage as _MemoryStorage
    storage = _MemoryStorage()
    logger.warning(f"Redis unavailable ({_e}), using MemoryStorage (FSM resets on restart)")

# ── Bot & Dispatcher ─────────────────────────────────────────
bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=storage)

# Register middleware
dp.message.middleware(AuthMiddleware())
dp.callback_query.middleware(AuthMiddleware())
dp.message.middleware(RateLimitMiddleware(settings.REDIS_URL))
dp.callback_query.middleware(RateLimitMiddleware(settings.REDIS_URL))

# Register routers
dp.include_router(get_main_router())

# ── FastAPI app ──────────────────────────────────────────────
app = FastAPI(
    title="EscrowBot",
    version="1.0.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
)

scheduler = create_scheduler(bot)


async def _migrate_columns() -> None:
    """Safely add new columns/enum values that may not exist in older deployments."""
    from sqlalchemy import text
    stmts = [
        "ALTER TABLE deals ADD COLUMN IF NOT EXISTS chat_group_id BIGINT",
        "ALTER TABLE deals ADD COLUMN IF NOT EXISTS chat_invite_link VARCHAR(256)",
        "ALTER TABLE wallets ALTER COLUMN private_key_encrypted DROP NOT NULL",
        "ALTER TYPE chain ADD VALUE IF NOT EXISTS 'BSC'",
        "ALTER TYPE chain ADD VALUE IF NOT EXISTS 'DOGECOIN'",
        "ALTER TYPE chain ADD VALUE IF NOT EXISTS 'FANTOM'",
        "ALTER TYPE chain ADD VALUE IF NOT EXISTS 'TON'",
        "ALTER TYPE currency ADD VALUE IF NOT EXISTS 'USDT_BEP20'",
        "ALTER TYPE currency ADD VALUE IF NOT EXISTS 'USDT_ERC20'",
        "ALTER TYPE currency ADD VALUE IF NOT EXISTS 'USDT_TON'",
        "ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ETH'",
        "ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BNB'",
        "ALTER TYPE currency ADD VALUE IF NOT EXISTS 'LTC'",
        "ALTER TYPE currency ADD VALUE IF NOT EXISTS 'DOGE'",
        "ALTER TYPE currency ADD VALUE IF NOT EXISTS 'TRX'",
        "ALTER TYPE currency ADD VALUE IF NOT EXISTS 'TON'",
        "ALTER TYPE currency ADD VALUE IF NOT EXISTS 'FTM'",
    ]
    async with engine.begin() as conn:
        for stmt in stmts:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                logger.warning(f"Migration skipped ({stmt[:50]}...): {e}")


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting EscrowBot...")

    # Create DB tables then apply incremental schema changes
    await create_tables()
    await _migrate_columns()
    logger.info("Database tables ready.")

    # Start background scheduler
    scheduler.start()
    logger.info("Background scheduler started.")

    # Clear any previously set short description
    try:
        await bot.set_my_short_description(short_description="")
    except Exception:
        pass

    if settings.BOT_WEBHOOK_URL:
        # Webhook mode
        webhook_url = f"{settings.BOT_WEBHOOK_URL}{settings.BOT_WEBHOOK_PATH}"
        await bot.set_webhook(
            webhook_url,
            secret_token=settings.BOT_WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
        logger.info(f"Webhook set to {webhook_url}")
    else:
        # Polling mode (dev)
        import asyncio
        asyncio.create_task(dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()))
        logger.info("Polling mode started.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("Shutting down...")
    scheduler.shutdown(wait=False)
    await bot.delete_webhook(drop_pending_updates=False)
    await bot.session.close()
    logger.info("Shutdown complete.")


# ── Register routes ──────────────────────────────────────────
from app.api.routes.health import router as health_router
from app.api.routes.webhook import get_webhook_router

app.include_router(health_router)


@app.on_event("startup")
async def register_webhook_route() -> None:
    webhook_router = await get_webhook_router(bot, dp)
    app.include_router(webhook_router)


# ── Dev entrypoint ───────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=not settings.is_production)

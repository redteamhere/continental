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
from app.database import create_tables
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

# ── Bot & Dispatcher ─────────────────────────────────────────
storage = RedisStorage.from_url(settings.REDIS_URL)
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


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Starting EscrowBot...")

    # Create DB tables (use Alembic in production)
    await create_tables()
    logger.info("Database tables ready.")

    # Start background scheduler
    scheduler.start()
    logger.info("Background scheduler started.")

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

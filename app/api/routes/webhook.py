"""Telegram webhook endpoint."""
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings

router = APIRouter()


async def get_webhook_router(bot: Bot, dp: Dispatcher) -> APIRouter:
    @router.post(settings.BOT_WEBHOOK_PATH)
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str = Header(default=""),
    ) -> dict:
        if settings.BOT_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != settings.BOT_WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid secret token")

        body = await request.json()
        update = Update.model_validate(body)
        await dp.feed_update(bot=bot, update=update)
        return {"ok": True}

    return router

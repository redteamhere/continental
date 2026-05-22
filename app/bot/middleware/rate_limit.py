"""Per-user rate limiting via Redis sliding window."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
import redis.asyncio as aioredis

from app.config import settings

_WINDOW_SECONDS = 60
_MAX_REQUESTS = settings.MAX_REQUESTS_PER_MINUTE


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        key = f"rl:{tg_user.id}"
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, _WINDOW_SECONDS)
        results = await pipe.execute()
        count = results[0]

        if count > _MAX_REQUESTS:
            if isinstance(event, Message):
                await event.answer("⚠️ Too many requests. Please slow down.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⚠️ Too many requests.", show_alert=True)
            return

        return await handler(event, data)

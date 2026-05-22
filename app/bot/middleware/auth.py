"""
Middleware that injects the current User (or None) into handler data.
Blocks banned users from all interactions except /start.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from app.database import AsyncSessionFactory
from app.services.user_service import UserService


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        async with AsyncSessionFactory() as session:
            svc = UserService(session)
            user = await svc.get_by_telegram_id(tg_user.id)

            if user:
                await svc.update_last_active(user)
                await session.commit()

                if user.is_banned:
                    if isinstance(event, Message):
                        await event.answer(
                            "🚫 Your account has been suspended.\n"
                            f"Reason: {user.ban_reason or 'Policy violation'}"
                        )
                    elif isinstance(event, CallbackQuery):
                        await event.answer("🚫 Account suspended.", show_alert=True)
                    return

            data["db_user"] = user
            data["db_session"] = session
            return await handler(event, data)

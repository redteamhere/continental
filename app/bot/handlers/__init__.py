from aiogram import Router
from app.bot.handlers import start, profile, deals, payments, disputes, admin, pin_input

def get_main_router() -> Router:
    router = Router()
    router.include_router(pin_input.router)   # must be first — shared digit/backspace handlers
    router.include_router(start.router)
    router.include_router(profile.router)
    router.include_router(deals.router)
    router.include_router(payments.router)
    router.include_router(disputes.router)
    router.include_router(admin.router)
    return router

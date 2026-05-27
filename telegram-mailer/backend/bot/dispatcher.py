from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from backend.config import settings
from backend.bot.middleware import AccessMiddleware
from backend.bot.handlers import (
    start, accounts, templates, groups, campaigns, reports, settings as settings_handler, admin_management
)

bot = Bot(token=settings.bot_token)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Регистрируем middleware
dp.message.middleware(AccessMiddleware())
dp.callback_query.middleware(AccessMiddleware())

def register_handlers():
    dp.include_router(start.router)
    dp.include_router(accounts.router)
    dp.include_router(templates.router)
    dp.include_router(groups.router)
    dp.include_router(campaigns.router)
    dp.include_router(reports.router)
    dp.include_router(settings_handler.router)
    dp.include_router(admin_management.router)

register_handlers()
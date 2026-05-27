from aiogram import Bot
from backend.config import settings

# Создаём единственный экземпляр бота
bot = Bot(token=settings.bot_token)

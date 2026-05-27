import asyncio
import logging
from backend.bot.dispatcher import dp
from backend.bot.bot_instance import bot
from backend.database import init_db
from backend.config import settings

logging.basicConfig(level=settings.log_level)

async def main():
    await init_db()
    logging.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

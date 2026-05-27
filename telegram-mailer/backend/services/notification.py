from backend.bot.bot_instance import bot
from backend.config import settings
from backend.database import get_all_admins

async def notify_admin(message: str):
    admins = await get_all_admins()
    for admin in admins:
        try:
            await bot.send_message(admin.telegram_id, f"📢 {message}")
        except:
            pass
    try:
        await bot.send_message(settings.superadmin_id, f"📢 {message}")
    except:
        pass

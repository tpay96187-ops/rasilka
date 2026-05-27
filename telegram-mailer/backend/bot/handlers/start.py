from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from backend.database import get_user_role, is_user_active, log_admin_action
from backend.bot.keyboards import main_menu_kb
from backend.config import settings

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    telegram_id = message.from_user.id
    role = await get_user_role(telegram_id)
    if not role or not await is_user_active(telegram_id):
        await message.answer("❌ Доступ запрещён. Обратитесь к администратору.")
        return
    await log_admin_action(telegram_id, "start_bot")
    await message.answer(
        f"👋 Добро пожаловать, {message.from_user.full_name}!\n"
        f"Ваша роль: {role}\n\n"
        f"Управление системой рассылок Telegram.",
        reply_markup=main_menu_kb(role)
    )

@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    role = await get_user_role(telegram_id)
    await callback.message.edit_text(
        "🏠 Главное меню",
        reply_markup=main_menu_kb(role)
    )
    await callback.answer()
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from backend.config import settings
from backend.database import get_user_role, log_admin_action
from backend.bot.keyboards import back_to_main_kb
from backend.services.notification import notify_admin

router = Router()

class SettingsStates(StatesGroup):
    waiting_new_max_accounts = State()
    waiting_new_message_interval = State()
    waiting_new_cycle_interval = State()

@router.callback_query(F.data == "menu_settings")
async def settings_menu(callback: CallbackQuery):
    role = await get_user_role(callback.from_user.id)
    if role != "superadmin":
        await callback.answer("⛔ Только Super Admin может изменять настройки", show_alert=True)
        return
    
    text = (
        f"⚙️ **Настройки системы**\n\n"
        f"📱 Максимум аккаунтов: `{settings.max_accounts}`\n"
        f"⏱️ Интервал между сообщениями (по умолчанию): `{settings.default_message_interval}` сек\n"
        f"🔄 Интервал между циклами (по умолчанию): `{settings.default_cycle_interval}` сек\n"
        f"👑 Super Admin ID: `{settings.superadmin_id}`\n"
        f"🔐 Шифрование: включено\n"
        f"🗄️ База данных: PostgreSQL\n\n"
        f"Для изменения параметров нажмите на соответствующую кнопку."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Изменить макс. аккаунтов", callback_data="set_max_accounts")],
        [InlineKeyboardButton(text="⏱️ Изменить интервал сообщений", callback_data="set_msg_interval")],
        [InlineKeyboardButton(text="🔄 Изменить интервал циклов", callback_data="set_cycle_interval")],
        [InlineKeyboardButton(text="🔄 Проверить переменные окружения", callback_data="check_env")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "set_max_accounts")
async def set_max_accounts(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новое максимальное количество аккаунтов (число):")
    await state.set_state(SettingsStates.waiting_new_max_accounts)
    await callback.answer()

@router.message(SettingsStates.waiting_new_max_accounts)
async def process_max_accounts(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите целое число.")
        return
    new_value = int(message.text)
    if new_value < 1 or new_value > 500:
        await message.answer("❌ Значение должно быть от 1 до 500.")
        return
    settings.max_accounts = new_value
    await log_admin_action(message.from_user.id, "change_max_accounts", "system", new_value)
    await message.answer(f"✅ Максимум аккаунтов изменён на {new_value} (до перезапуска бота).\n"
                         f"⚠️ Для постоянного изменения пропишите в .env переменную MAX_ACCOUNTS и перезапустите.")
    await state.clear()
    await settings_menu(message)

@router.callback_query(F.data == "set_msg_interval")
async def set_msg_interval(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новый интервал между сообщениями (в секундах, от 1 до 300):")
    await state.set_state(SettingsStates.waiting_new_message_interval)
    await callback.answer()

@router.message(SettingsStates.waiting_new_message_interval)
async def process_msg_interval(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите целое число.")
        return
    new_val = int(message.text)
    if new_val < 1 or new_val > 300:
        await message.answer("❌ Интервал должен быть от 1 до 300 секунд.")
        return
    settings.default_message_interval = new_val
    await log_admin_action(message.from_user.id, "change_msg_interval", "system", new_val)
    await message.answer(f"✅ Интервал сообщений изменён на {new_val} сек (только для новых рассылок).")
    await state.clear()
    await settings_menu(message)

@router.callback_query(F.data == "set_cycle_interval")
async def set_cycle_interval(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новый интервал между циклами (в секундах, от 10 до 3600):")
    await state.set_state(SettingsStates.waiting_new_cycle_interval)
    await callback.answer()

@router.message(SettingsStates.waiting_new_cycle_interval)
async def process_cycle_interval(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите целое число.")
        return
    new_val = int(message.text)
    if new_val < 10 or new_val > 3600:
        await message.answer("❌ Интервал должен быть от 10 до 3600 секунд.")
        return
    settings.default_cycle_interval = new_val
    await log_admin_action(message.from_user.id, "change_cycle_interval", "system", new_val)
    await message.answer(f"✅ Интервал циклов изменён на {new_val} сек.")
    await state.clear()
    await settings_menu(message)

@router.callback_query(F.data == "check_env")
async def check_env(callback: CallbackQuery):
    required_vars = ["BOT_TOKEN", "SUPERADMIN_ID", "ENCRYPTION_KEY", "DATABASE_URL", "REDIS_URL"]
    status = []
    for var in required_vars:
        val = getattr(settings, var.lower(), None)
        if val:
            # Маскируем чувствительные данные
            if var in ["BOT_TOKEN", "ENCRYPTION_KEY", "DATABASE_URL", "REDIS_URL"]:
                val = str(val)[:10] + "..."
            status.append(f"✅ {var} = {val}")
        else:
            status.append(f"❌ {var} не задан")
    text = "🔍 **Переменные окружения:**\n" + "\n".join(status)
    await callback.message.edit_text(text, reply_markup=back_to_main_kb(), parse_mode="Markdown")
    await callback.answer()

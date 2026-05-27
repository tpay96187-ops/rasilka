from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from backend.database import (
    get_all_admins, add_admin, remove_admin, block_admin, get_user_role, 
    log_admin_action, is_user_active
)
from backend.bot.keyboards import back_to_main_kb, confirm_kb
from backend.config import settings
from backend.services.notification import notify_admin

router = Router()

# FSM для добавления администратора
class AddAdminStates(StatesGroup):
    waiting_telegram_id = State()
    waiting_username = State()
    waiting_role = State()

@router.callback_query(F.data == "menu_admin_manage")
async def admin_manage_menu(callback: CallbackQuery):
    """Главное меню управления администраторами (только для superadmin)"""
    role = await get_user_role(callback.from_user.id)
    if role != "superadmin":
        await callback.answer("⛔ Только Super Admin может управлять администраторами", show_alert=True)
        return
    
    admins = await get_all_admins()
    text = "👑 **Управление администраторами**\n\n"
    if admins:
        text += "Список:\n"
        for a in admins:
            status = "✅ Активен" if a.is_active else "❌ Заблокирован"
            text += f"• `{a.username or a.telegram_id}` (ID: `{a.telegram_id}`) – {a.role} – {status}\n"
    else:
        text += "Нет администраторов (кроме Super Admin).\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить администратора", callback_data="add_admin_start")],
        [InlineKeyboardButton(text="🗑 Удалить администратора", callback_data="remove_admin_start")],
        [InlineKeyboardButton(text="🔒 Заблокировать администратора", callback_data="block_admin_start")],
        [InlineKeyboardButton(text="🔓 Разблокировать администратора", callback_data="unblock_admin_start")],
        [InlineKeyboardButton(text="📋 Просмотр действий администраторов", callback_data="admin_actions_log")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# ---------- Добавление администратора ----------
@router.callback_query(F.data == "add_admin_start")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите Telegram ID пользователя (число):")
    await state.set_state(AddAdminStates.waiting_telegram_id)
    await callback.answer()

@router.message(AddAdminStates.waiting_telegram_id)
async def add_admin_telegram_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Telegram ID должен быть числом. Попробуйте ещё раз.")
        return
    tg_id = int(message.text)
    # Проверяем, не суперадмин ли это
    if tg_id == settings.superadmin_id:
        await message.answer("❌ Этот пользователь уже является Super Admin.")
        await state.clear()
        return
    # Проверяем, не существует ли уже
    existing = await get_all_admins()
    if any(a.telegram_id == tg_id for a in existing):
        await message.answer("❌ Пользователь уже в списке администраторов.")
        await state.clear()
        return
    await state.update_data(telegram_id=tg_id)
    await message.answer("Введите username (можно без @, или '-' чтобы пропустить):")
    await state.set_state(AddAdminStates.waiting_username)

@router.message(AddAdminStates.waiting_username)
async def add_admin_username(message: Message, state: FSMContext):
    username = message.text.strip()
    if username == "-":
        username = None
    else:
        username = username.lstrip('@')
    await state.update_data(username=username)
    # Роль: либо admin (пока только одна роль, можно расширить)
    await state.update_data(role="admin")
    data = await state.get_data()
    success = await add_admin(data['telegram_id'], data['username'], data['role'])
    if success:
        await log_admin_action(message.from_user.id, "add_admin", "user", data['telegram_id'])
        await notify_admin(f"👑 Добавлен новый администратор: {data['username'] or data['telegram_id']}")
        await message.answer(f"✅ Администратор {data['telegram_id']} успешно добавлен.")
    else:
        await message.answer("❌ Не удалось добавить администратора (возможно, уже существует).")
    await state.clear()
    await admin_manage_menu(message)

# ---------- Удаление администратора ----------
@router.callback_query(F.data == "remove_admin_start")
async def remove_admin_list(callback: CallbackQuery):
    admins = await get_all_admins()
    non_super = [a for a in admins if a.telegram_id != settings.superadmin_id]
    if not non_super:
        await callback.answer("Нет обычных администраторов для удаления", show_alert=True)
        return
    buttons = []
    for a in non_super:
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {a.username or a.telegram_id}",
            callback_data=f"remove_admin_{a.telegram_id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="menu_admin_manage")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выберите администратора для удаления:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("remove_admin_"))
async def confirm_remove_admin(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(
        f"⚠️ Вы уверены, что хотите удалить администратора с ID {tg_id}?",
        reply_markup=confirm_kb(f"remove_admin_final_{tg_id}", tg_id)
    )

@router.callback_query(F.data.startswith("confirm_remove_admin_final_"))
async def remove_admin_final(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[4])
    success = await remove_admin(tg_id)
    if success:
        await log_admin_action(callback.from_user.id, "remove_admin", "user", tg_id)
        await notify_admin(f"🗑 Администратор {tg_id} удалён.")
        await callback.message.edit_text("✅ Администратор удалён.")
    else:
        await callback.message.edit_text("❌ Не удалось удалить (возможно, это Super Admin).")
    await admin_manage_menu(callback)

# ---------- Блокировка администратора ----------
@router.callback_query(F.data == "block_admin_start")
async def block_admin_list(callback: CallbackQuery):
    admins = await get_all_admins()
    active_admins = [a for a in admins if a.is_active and a.telegram_id != settings.superadmin_id]
    if not active_admins:
        await callback.answer("Нет активных администраторов для блокировки", show_alert=True)
        return
    buttons = []
    for a in active_admins:
        buttons.append([InlineKeyboardButton(
            text=f"🔒 {a.username or a.telegram_id}",
            callback_data=f"block_admin_{a.telegram_id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="menu_admin_manage")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выберите администратора для блокировки:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("block_admin_"))
async def confirm_block_admin(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(
        f"⚠️ Заблокировать администратора {tg_id}? Он потеряет доступ к боту.",
        reply_markup=confirm_kb(f"block_admin_final_{tg_id}", tg_id)
    )

@router.callback_query(F.data.startswith("confirm_block_admin_final_"))
async def block_admin_final(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[4])
    success = await block_admin(tg_id)
    if success:
        await log_admin_action(callback.from_user.id, "block_admin", "user", tg_id)
        await notify_admin(f"🔒 Администратор {tg_id} заблокирован.")
        await callback.message.edit_text("✅ Администратор заблокирован.")
    else:
        await callback.message.edit_text("❌ Не удалось заблокировать.")
    await admin_manage_menu(callback)

# ---------- Разблокировка администратора ----------
@router.callback_query(F.data == "unblock_admin_start")
async def unblock_admin_list(callback: CallbackQuery):
    admins = await get_all_admins()
    inactive_admins = [a for a in admins if not a.is_active and a.telegram_id != settings.superadmin_id]
    if not inactive_admins:
        await callback.answer("Нет заблокированных администраторов", show_alert=True)
        return
    buttons = []
    for a in inactive_admins:
        buttons.append([InlineKeyboardButton(
            text=f"🔓 {a.username or a.telegram_id}",
            callback_data=f"unblock_admin_{a.telegram_id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="menu_admin_manage")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выберите администратора для разблокировки:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("unblock_admin_"))
async def confirm_unblock_admin(callback: CallbackQuery):
    tg_id = int(callback.data.split("_")[2])
    # Просто разблокируем без подтверждения
    from backend.database import update
    from backend.models import User
    from backend.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        from sqlalchemy import update
        await session.execute(update(User).where(User.telegram_id == tg_id).values(is_active=True))
        await session.commit()
    await log_admin_action(callback.from_user.id, "unblock_admin", "user", tg_id)
    await notify_admin(f"🔓 Администратор {tg_id} разблокирован.")
    await callback.message.edit_text("✅ Администратор разблокирован.")
    await admin_manage_menu(callback)

# ---------- Лог действий администраторов ----------
@router.callback_query(F.data == "admin_actions_log")
async def admin_actions_log(callback: CallbackQuery):
    from backend.database import AsyncSessionLocal
    from backend.models import AdminActionLog, User
    from sqlalchemy import select, desc
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AdminActionLog)
            .order_by(desc(AdminActionLog.timestamp))
            .limit(20)
        )
        logs = result.scalars().all()
    
    if not logs:
        text = "📋 Журнал действий администраторов пуст."
    else:
        text = "📋 **Последние 20 действий:**\n\n"
        for log in logs:
            text += f"• `{log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}` – Admin {log.user_telegram_id} – {log.action}"
            if log.target_type:
                text += f" ({log.target_type} #{log.target_id})"
            text += "\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_actions_log")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_admin_manage")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()
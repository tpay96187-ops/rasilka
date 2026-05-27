from aiogram import Router, F
from aiogram.types import CallbackQuery
from backend.database import get_groups, clear_account_groups, get_accounts
from backend.mtproto.group_fetcher import fetch_all_groups_for_account
from backend.bot.keyboards import group_list_kb, back_to_main_kb
from backend.services.notification import notify_admin

router = Router()

@router.callback_query(F.data == "menu_groups")
async def list_groups_menu(callback: CallbackQuery):
    # Сначала показываем список аккаунтов для выбора
    accounts = await get_accounts()
    if not accounts:
        await callback.message.edit_text("Нет аккаунтов. Сначала добавьте аккаунт.", reply_markup=back_to_main_kb())
        return
    # Создаём inline-кнопки для выбора аккаунта
    buttons = []
    for acc in accounts:
        buttons.append([InlineKeyboardButton(text=f"{acc.name}", callback_data=f"show_groups_{acc.id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выберите аккаунт для просмотра групп:", reply_markup=kb)

@router.callback_query(F.data.startswith("show_groups_"))
async def show_groups(callback: CallbackQuery):
    account_id = int(callback.data.split("_")[2])
    groups = await get_groups(account_id)
    if not groups:
        # Предлагаем обновить
        await callback.message.edit_text("Группы не загружены. Обновить?", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_groups_{account_id}")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_groups")]
            ]))
    else:
        await callback.message.edit_text(f"👥 Группы аккаунта (всего {len(groups)}):", reply_markup=group_list_kb(groups))

@router.callback_query(F.data.startswith("refresh_groups_"))
async def refresh_groups(callback: CallbackQuery):
    account_id = int(callback.data.split("_")[2])
    await callback.answer("🔄 Загрузка групп...")
    await clear_account_groups(account_id)
    groups = await fetch_all_groups_for_account(account_id)
    await notify_admin(f"Аккаунт {account_id}: загружено {len(groups)} групп")
    await callback.message.edit_text(f"✅ Загружено {len(groups)} групп.", reply_markup=back_to_main_kb())
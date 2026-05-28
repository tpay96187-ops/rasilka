from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from backend.database import get_groups, clear_account_groups, get_accounts
from backend.mtproto.group_fetcher import fetch_all_groups_for_account
from backend.bot.keyboards import back_to_main_kb
from backend.services.notification import notify_admin

router = Router()

# === Меню выбора аккаунта для просмотра групп ===
@router.callback_query(F.data == "menu_groups")
async def list_groups_menu(callback: CallbackQuery):
    accounts = await get_accounts()
    if not accounts:
        await callback.message.edit_text("Нет аккаунтов. Сначала добавьте аккаунт.", reply_markup=back_to_main_kb())
        return
    buttons = []
    for acc in accounts:
        buttons.append([InlineKeyboardButton(text=f"{acc.name}", callback_data=f"show_groups_{acc.id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выберите аккаунт для просмотра групп:", reply_markup=kb)
    await callback.answer()

# === Обработчик выбора аккаунта – показывает группы с пагинацией ===
@router.callback_query(F.data.startswith("show_groups_"))
async def show_groups(callback: CallbackQuery, page: int = 0):
    # Извлекаем ID аккаунта из callback_data
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Ошибка: неверный формат")
        return
    account_id = int(parts[2])
    
    # Получаем все группы аккаунта
    all_groups = await get_groups(account_id)
    # Фильтруем только настоящие группы (исключаем каналы, если вдруг попали)
    groups = [g for g in all_groups if g.group_type != "channel"]
    
    per_page = 10
    total_pages = max(1, (len(groups) + per_page - 1) // per_page)
    # Если переданная страница выходит за пределы, корректируем
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    
    start = page * per_page
    end = start + per_page
    page_groups = groups[start:end]
    
    # Формируем текст
    text = f"👥 Группы аккаунта (страница {page+1} из {total_pages}):\n"
    for grp in page_groups:
        participants = grp.participants_count or 0
        if participants >= 1_000_000:
            participants_str = f"{participants // 1_000_000}M"
        elif participants >= 1_000:
            participants_str = f"{participants // 1_000}k"
        else:
            participants_str = str(participants)
        text += f"• {grp.title} – 👥 {participants_str}\n"
    
    # Клавиатура
    buttons = []
    # Кнопки для каждой группы (можно сделать детали, но для простоты просто названия)
    for grp in page_groups:
        buttons.append([InlineKeyboardButton(text=f"👥 {grp.title[:30]}", callback_data=f"group_detail_{grp.id}")])
    # Навигация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"groups_page_{account_id}_{page-1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"groups_page_{account_id}_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_groups_{account_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_groups")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

# === Обработчик пагинации ===
@router.callback_query(F.data.startswith("groups_page_"))
async def groups_page_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("Ошибка пагинации")
        return
    account_id = int(parts[2])
    page = int(parts[3])
    # Эмулируем вызов show_groups с нужной страницей
    # Временно подменяем callback.data, чтобы show_groups мог извлечь account_id
    # Но проще создать новый callback с нужными атрибутами? Не будем усложнять.
    # Передадим параметры через атрибуты, но в aiogram так нельзя.
    # Поэтому просто вызовем ту же логику напрямую:
    await show_groups_with_page(callback, account_id, page)

async def show_groups_with_page(callback: CallbackQuery, account_id: int, page: int):
    """Вспомогательная функция для отображения страницы групп"""
    all_groups = await get_groups(account_id)
    groups = [g for g in all_groups if g.group_type != "channel"]
    per_page = 10
    total_pages = max(1, (len(groups) + per_page - 1) // per_page)
    if page < 0:
        page = 0
    if page >= total_pages:
        page = total_pages - 1
    start = page * per_page
    end = start + per_page
    page_groups = groups[start:end]
    text = f"👥 Группы аккаунта (страница {page+1} из {total_pages}):\n"
    for grp in page_groups:
        participants = grp.participants_count or 0
        if participants >= 1_000_000:
            participants_str = f"{participants // 1_000_000}M"
        elif participants >= 1_000:
            participants_str = f"{participants // 1_000}k"
        else:
            participants_str = str(participants)
        text += f"• {grp.title} – 👥 {participants_str}\n"
    buttons = []
    for grp in page_groups:
        buttons.append([InlineKeyboardButton(text=f"👥 {grp.title[:30]}", callback_data=f"group_detail_{grp.id}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"groups_page_{account_id}_{page-1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"groups_page_{account_id}_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_groups_{account_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_groups")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

# === Обновление списка групп (принудительная загрузка через Telegram) ===
@router.callback_query(F.data.startswith("refresh_groups_"))
async def refresh_groups(callback: CallbackQuery):
    account_id = int(callback.data.split("_")[2])
    await callback.answer("🔄 Загрузка групп...")
    await clear_account_groups(account_id)
    groups = await fetch_all_groups_for_account(account_id)
    await notify_admin(f"Аккаунт {account_id}: загружено {len(groups)} групп")
    await callback.message.edit_text(f"✅ Загружено {len(groups)} групп.", reply_markup=back_to_main_kb())

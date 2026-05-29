from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

def main_menu_kb(role: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📱 Аккаунты", callback_data="menu_accounts")],
        [InlineKeyboardButton(text="✉️ Рассылки", callback_data="menu_campaigns")],
        [InlineKeyboardButton(text="📝 Шаблоны", callback_data="menu_templates")],
        [InlineKeyboardButton(text="👥 Группы", callback_data="menu_groups")],
        [InlineKeyboardButton(text="📊 Отчёты", callback_data="menu_reports")],
    ]
    if role == "superadmin":
        buttons.append([InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")])
        buttons.append([InlineKeyboardButton(text="👑 Управление админами", callback_data="menu_admin_manage")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])

def account_list_kb(accounts: List) -> InlineKeyboardMarkup:
    buttons = []
    for acc in accounts:
        status = "✅" if acc.is_valid else "❌"
        buttons.append([InlineKeyboardButton(text=f"{status} {acc.name}", callback_data=f"acc_{acc.id}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add_account_start")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def account_actions_kb(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_acc_{account_id}")],
        [InlineKeyboardButton(text="🔍 Проверить SpamBot", callback_data=f"spambot_acc_{account_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_acc_{account_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_accounts")]
    ])

def templates_list_kb(templates: List) -> InlineKeyboardMarkup:
    buttons = []
    for tpl in templates:
        active = "✅" if tpl.is_active else "❌"
        buttons.append([InlineKeyboardButton(text=f"{active} {tpl.name}", callback_data=f"template_{tpl.id}")])
    buttons.append([InlineKeyboardButton(text="➕ Создать шаблон", callback_data="new_template")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def template_actions_kb(template_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Отключить" if is_active else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_template_{template_id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"toggle_template_{template_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_template_{template_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_templates")]
    ])

def campaigns_list_kb(campaigns: List) -> InlineKeyboardMarkup:
    buttons = []
    for camp in campaigns:
        status_emoji = {"running": "▶️", "paused": "⏸️", "stopped": "⏹️", "completed": "✅", "draft": "📝"}.get(camp.status, "❓")
        buttons.append([InlineKeyboardButton(text=f"{status_emoji} {camp.name}", callback_data=f"campaign_{camp.id}")])
    buttons.append([InlineKeyboardButton(text="➕ Создать рассылку", callback_data="new_campaign")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def campaign_actions_kb(campaign_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "draft" or status == "stopped":
        buttons.append([InlineKeyboardButton(text="▶️ Запустить", callback_data=f"camp_start_{campaign_id}")])
    if status == "running":
        buttons.append([InlineKeyboardButton(text="⏸️ Пауза", callback_data=f"camp_pause_{campaign_id}")])
    if status == "running" or status == "paused":
        buttons.append([InlineKeyboardButton(text="⏹️ Остановить", callback_data=f"camp_stop_{campaign_id}")])
        if status == "paused":
    buttons.append([InlineKeyboardButton(text="▶️ Возобновить", callback_data=f"camp_start_{campaign_id}")])
    buttons.append([InlineKeyboardButton(text="📈 Статистика", callback_data=f"camp_stats_{campaign_id}")])
    buttons.append([InlineKeyboardButton(text="📊 Excel-отчёт", callback_data=f"camp_report_{campaign_id}")])
    buttons.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"camp_delete_{campaign_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_campaigns")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def group_list_kb(groups: List) -> InlineKeyboardMarkup:
    buttons = []
    for grp in groups[:50]:  # ограничим вывод
        buttons.append([InlineKeyboardButton(text=f"👥 {grp.title}", callback_data=f"group_{grp.id}")])
    buttons.append([InlineKeyboardButton(text="🔄 Обновить группы", callback_data="refresh_groups")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def select_items_kb(items: List, item_type: str, action: str, page: int = 0, per_page: int = 5, show_select_all: bool = False) -> InlineKeyboardMarkup:
    start = page * per_page
    end = start + per_page
    page_items = items[start:end]
    buttons = []
    for item in page_items:
        name = getattr(item, "name", None) or getattr(item, "title", "Unknown")
        buttons.append([InlineKeyboardButton(text=f"☑️ {name}", callback_data=f"{item_type}_select_{action}_{item.id}")])
    
    # Кнопка "Выбрать ВСЕ"
    if show_select_all and items:
        buttons.append([InlineKeyboardButton(text="✅ Выбрать ВСЕ", callback_data=f"{item_type}_select_all_{action}")])
    
    # Пагинация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{item_type}_page_{action}_{page-1}"))
    if end < len(items):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{item_type}_page_{action}_{page+1}"))
    if nav:
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data=f"{item_type}_done_{action}")])
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data=f"cancel_{action}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_kb(action: str, target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}_{target_id}"),
         InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_{action}_{target_id}")]
    ])

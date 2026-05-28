from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from backend.bot.states import CampaignStates
from backend.bot.keyboards import campaigns_list_kb, campaign_actions_kb, select_items_kb, confirm_kb, back_to_main_kb
from backend.database import (
    get_campaigns, get_campaign, create_campaign, update_campaign, delete_campaign,
    get_templates, get_accounts, get_groups, add_account_to_campaign, add_group_to_campaign,
    get_campaign_accounts, get_campaign_groups, log_admin_action, get_template
)
from backend.tasks.send_tasks import start_campaign_task
from datetime import datetime

router = Router()

# === Список рассылок ===
@router.callback_query(F.data == "menu_campaigns")
async def list_campaigns(callback: CallbackQuery):
    campaigns = await get_campaigns()
    if not campaigns:
        await callback.message.edit_text("✉️ Рассылки отсутствуют.", reply_markup=campaigns_list_kb(campaigns))
    else:
        await callback.message.edit_text("✉️ Список рассылок:", reply_markup=campaigns_list_kb(campaigns))
    await callback.answer()

# === Обработчик инлайн-кнопки "Создать рассылку" ===
@router.callback_query(F.data == "new_campaign")
async def new_campaign_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название рассылки:")
    await state.set_state(CampaignStates.waiting_name)
    await callback.answer()

# === Обработчик команды /new_campaign (альтернативный способ) ===
@router.message(Command("new_campaign"))
async def new_campaign_cmd(message: Message, state: FSMContext):
    await message.answer("Введите название рассылки:")
    await state.set_state(CampaignStates.waiting_name)

# === FSM: название ===
@router.message(CampaignStates.waiting_name)
async def campaign_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    templates = await get_templates(active_only=True)
    if not templates:
        await message.answer("❌ Нет активных шаблонов. Сначала создайте шаблон через /new_template")
        await state.clear()
        return
    buttons = [[InlineKeyboardButton(text=t.name, callback_data=f"camp_tpl_{t.id}")] for t in templates]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Выберите шаблон:", reply_markup=kb)
    await state.set_state(CampaignStates.waiting_template)

@router.callback_query(F.data.startswith("camp_tpl_"), CampaignStates.waiting_template)
async def campaign_template(callback: CallbackQuery, state: FSMContext):
    template_id = int(callback.data.split("_")[2])
    await state.update_data(template_id=template_id)
    accounts = await get_accounts()
    valid_accounts = [a for a in accounts if a.is_valid and not a.spam_blocked and (not a.flood_wait_until or a.flood_wait_until < datetime.utcnow())]
    if not valid_accounts:
        await callback.answer("Нет доступных аккаунтов", show_alert=True)
        return
    await state.update_data(selected_accounts=[])
    await callback.message.edit_text("Выберите аккаунты для рассылки (можно несколько):", 
                                     reply_markup=select_items_kb(valid_accounts, "account", "campaign", 0))
    await state.set_state(CampaignStates.waiting_accounts)

# === Остальной код (выбор аккаунтов, групп, интервалов, создание) ===
# ... (все остальные функции, которые были ранее, включая select_account, accounts_done, select_group, groups_done, campaign_interval, campaign_cycle, campaign_limit)

# === Просмотр и управление рассылкой ===
@router.callback_query(F.data.startswith("campaign_"))
async def show_campaign(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[1])
    camp = await get_campaign(campaign_id)
    if not camp:
        await callback.answer("Рассылка не найдена")
        return
    template = await get_template(camp.template_id)
    accounts = await get_campaign_accounts(campaign_id)
    groups = await get_campaign_groups(campaign_id)
    text = (f"📢 {camp.name}\n"
            f"Статус: {camp.status}\n"
            f"Шаблон: {template.name if template else 'Не указан'}\n"
            f"Аккаунтов: {len(accounts)}\n"
            f"Групп: {len(groups)}\n"
            f"Интервал между сообщениями: {camp.message_interval} сек\n"
            f"Интервал между циклами: {camp.cycle_interval} сек\n"
            f"Отправлено: {camp.total_sent} (✅ {camp.total_success}, ❌ {camp.total_failed})")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Старт", callback_data=f"camp_start_{campaign_id}")],
        [InlineKeyboardButton(text="ℹ️ Информация о шаблоне", callback_data=f"camp_info_{campaign_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_campaigns")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("camp_info_"))
async def campaign_info(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    camp = await get_campaign(campaign_id)
    if not camp:
        await callback.answer("Рассылка не найдена")
        return
    template = await get_template(camp.template_id)
    text = f"📝 Шаблон рассылки «{camp.name}»:\n{template.content if template else 'Нет шаблона'}"
    await callback.message.answer(text)
    await callback.answer()

@router.callback_query(F.data.startswith("camp_start_"))
async def campaign_start(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    await update_campaign(campaign_id, status="running", started_at=datetime.utcnow())
    start_campaign_task(campaign_id)
    await log_admin_action(callback.from_user.id, "start_campaign", "campaign", campaign_id)
    await callback.answer("Рассылка запущена")
    await show_campaign(callback)

# ... (остальные обработчики: пауза, стоп, статистика, удаление)

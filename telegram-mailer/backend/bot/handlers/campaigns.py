from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from backend.bot.states import CampaignStates
from backend.bot.keyboards import campaigns_list_kb, campaign_actions_kb, select_items_kb, confirm_kb, back_to_main_kb
from backend.database import (
    get_campaigns, get_campaign, create_campaign, update_campaign, delete_campaign,
    get_templates, get_accounts, get_groups, add_account_to_campaign, add_group_to_campaign,
    get_campaign_accounts, get_campaign_groups, log_admin_action
)
from backend.tasks.send_tasks import start_campaign_task
from datetime import datetime

router = Router()

@router.callback_query(F.data == "menu_campaigns")
async def list_campaigns(callback: CallbackQuery):
    campaigns = await get_campaigns()
    if not campaigns:
        await callback.message.edit_text("✉️ Рассылки отсутствуют. Создайте новую /new_campaign", reply_markup=back_to_main_kb())
    else:
        await callback.message.edit_text("✉️ Список рассылок:", reply_markup=campaigns_list_kb(campaigns))
    await callback.answer()

@router.message(Command("new_campaign"))
async def new_campaign_cmd(message: Message, state: FSMContext):
    await message.answer("Введите название рассылки:")
    await state.set_state(CampaignStates.waiting_name)

@router.message(CampaignStates.waiting_name)
async def campaign_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    # Выбор шаблона
    templates = await get_templates(active_only=True)
    if not templates:
        await message.answer("❌ Нет активных шаблонов. Сначала создайте шаблон через /new_template")
        await state.clear()
        return
    # Показываем список шаблонов для выбора
    buttons = []
    for t in templates:
        buttons.append([InlineKeyboardButton(text=t.name, callback_data=f"camp_tpl_{t.id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Выберите шаблон:", reply_markup=kb)
    await state.set_state(CampaignStates.waiting_template)

@router.callback_query(F.data.startswith("camp_tpl_"))
async def campaign_template(callback: CallbackQuery, state: FSMContext):
    template_id = int(callback.data.split("_")[2])
    await state.update_data(template_id=template_id)
    # Выбор аккаунтов
    accounts = await get_accounts()
    valid_accounts = [a for a in accounts if a.is_valid and not a.spam_blocked and (not a.flood_wait_until or a.flood_wait_until < datetime.utcnow())]
    if not valid_accounts:
        await callback.answer("Нет доступных аккаунтов", show_alert=True)
        return
    await state.update_data(selected_accounts=[])
    await callback.message.edit_text("Выберите аккаунты для рассылки (можно несколько):", 
                                     reply_markup=select_items_kb(valid_accounts, "account", "campaign", 0))
    await state.set_state(CampaignStates.waiting_accounts)

@router.callback_query(F.data.startswith("account_select_campaign_"))
async def select_account(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    selected = data.get("selected_accounts", [])
    if account_id not in selected:
        selected.append(account_id)
    await state.update_data(selected_accounts=selected)
    await callback.answer("Аккаунт добавлен", show_alert=False)

@router.callback_query(F.data.startswith("account_done_campaign"))
async def accounts_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_accounts", [])
    if not selected:
        await callback.answer("Выберите хотя бы один аккаунт", show_alert=True)
        return
    await state.update_data(campaign_accounts=selected)
    # Выбор групп
    # Для простоты возьмём все группы из всех выбранных аккаунтов
    groups = []
    for acc_id in selected:
        acc_groups = await get_groups(acc_id)
        groups.extend(acc_groups)
    if not groups:
        await callback.message.edit_text("Нет групп для выбранных аккаунтов. Загрузите группы через меню 'Группы'.")
        return
    await state.update_data(selected_groups=[])
    await callback.message.edit_text("Выберите группы для рассылки:", 
                                     reply_markup=select_items_kb(groups, "group", "campaign", 0))
    await state.set_state(CampaignStates.waiting_groups)

@router.callback_query(F.data.startswith("group_select_campaign_"))
async def select_group(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    selected = data.get("selected_groups", [])
    if group_id not in selected:
        selected.append(group_id)
    await state.update_data(selected_groups=selected)
    await callback.answer("Группа добавлена")

@router.callback_query(F.data.startswith("group_done_campaign"))
async def groups_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_groups", [])
    if not selected:
        await callback.answer("Выберите хотя бы одну группу", show_alert=True)
        return
    await state.update_data(campaign_groups=selected)
    await callback.message.edit_text("Введите интервал между сообщениями (в секундах, по умолчанию 30):")
    await state.set_state(CampaignStates.waiting_message_interval)

@router.message(CampaignStates.waiting_message_interval)
async def campaign_interval(message: Message, state: FSMContext):
    interval = int(message.text) if message.text.isdigit() else 30
    await state.update_data(message_interval=interval)
    await message.answer("Введите интервал между циклами (в секундах, по умолчанию 300):")
    await state.set_state(CampaignStates.waiting_cycle_interval)

@router.message(CampaignStates.waiting_cycle_interval)
async def campaign_cycle(message: Message, state: FSMContext):
    cycle = int(message.text) if message.text.isdigit() else 300
    await state.update_data(cycle_interval=cycle)
    await message.answer("Введите дневной лимит сообщений (0 = без лимита):")
    await state.set_state(CampaignStates.waiting_daily_limit)

@router.message(CampaignStates.waiting_daily_limit)
async def campaign_limit(message: Message, state: FSMContext):
    limit = int(message.text) if message.text.isdigit() else 0
    data = await state.get_data()
    # Создаём кампанию
    campaign = await create_campaign(
        name=data['name'],
        template_id=data['template_id'],
        message_interval=data['message_interval'],
        cycle_interval=data['cycle_interval'],
        daily_limit=limit
    )
    for acc_id in data['campaign_accounts']:
        await add_account_to_campaign(campaign.id, acc_id)
    for grp_id in data['campaign_groups']:
        await add_group_to_campaign(campaign.id, grp_id)
    await log_admin_action(message.from_user.id, "create_campaign", "campaign", campaign.id)
    await message.answer(f"✅ Рассылка «{campaign.name}» создана. Используйте меню для запуска.")
    await state.clear()
    await list_campaigns(message)

# Управление кампанией: запуск, пауза, стоп
@router.callback_query(F.data.startswith("camp_start_"))
async def campaign_start(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    await update_campaign(campaign_id, status="running", started_at=datetime.utcnow())
    # Запускаем Celery задачу
    from backend.tasks.send_tasks import process_campaign
    process_campaign.delay(campaign_id)
    await log_admin_action(callback.from_user.id, "start_campaign", "campaign", campaign_id)
    await callback.answer("Рассылка запущена")
    await show_campaign(callback)

@router.callback_query(F.data.startswith("camp_pause_"))
async def campaign_pause(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    await update_campaign(campaign_id, status="paused")
    await log_admin_action(callback.from_user.id, "pause_campaign", "campaign", campaign_id)
    await callback.answer("Рассылка приостановлена")
    await show_campaign(callback)

@router.callback_query(F.data.startswith("camp_stop_"))
async def campaign_stop(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    await update_campaign(campaign_id, status="stopped", stopped_at=datetime.utcnow())
    await log_admin_action(callback.from_user.id, "stop_campaign", "campaign", campaign_id)
    await callback.answer("Рассылка остановлена")
    await show_campaign(callback)

@router.callback_query(F.data.startswith("camp_stats_"))
async def campaign_stats(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    camp = await get_campaign(campaign_id)
    if not camp:
        await callback.answer("Кампания не найдена")
        return
    text = (f"📊 Статистика рассылки «{camp.name}»\n"
            f"Статус: {camp.status}\n"
            f"Отправлено всего: {camp.total_sent}\n"
            f"Успешно: {camp.total_success}\n"
            f"Неудачно: {camp.total_failed}\n"
            f"Процент успеха: {round(camp.total_success/(camp.total_sent or 1)*100, 2)}%")
    await callback.message.edit_text(text, reply_markup=campaign_actions_kb(campaign_id, camp.status))

@router.callback_query(F.data.startswith("camp_delete_"))
async def confirm_delete_campaign(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("Удалить рассылку?", reply_markup=confirm_kb("del_campaign", campaign_id))

@router.callback_query(F.data.startswith("confirm_del_campaign_"))
async def delete_campaign_final(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[3])
    await delete_campaign(campaign_id)
    await log_admin_action(callback.from_user.id, "delete_campaign", "campaign", campaign_id)
    await callback.message.edit_text("✅ Рассылка удалена")
    await list_campaigns(callback)

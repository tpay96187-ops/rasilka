from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from backend.bot.states import CampaignStates
from backend.bot.keyboards import campaigns_list_kb, select_items_kb, confirm_kb, back_to_main_kb
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

# === Команда /new_campaign ===
@router.message(Command("new_campaign"))
async def new_campaign_cmd(message: Message, state: FSMContext):
    await message.answer("Введите название рассылки:")
    await state.set_state(CampaignStates.waiting_name)

# === Шаг: название ===
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

# === Шаг: выбор шаблона ===
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

# === Выбор аккаунтов (по одному) ===
@router.callback_query(F.data.startswith("account_select_campaign_"))
async def select_account(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    selected = data.get("selected_accounts", [])
    if account_id not in selected:
        selected.append(account_id)
    await state.update_data(selected_accounts=selected)
    await callback.answer("Аккаунт добавлен", show_alert=False)

# === Завершение выбора аккаунтов ===
@router.callback_query(F.data.startswith("account_done_campaign"), CampaignStates.waiting_accounts)
async def accounts_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_accounts", [])
    if not selected:
        await callback.answer("Выберите хотя бы один аккаунт", show_alert=True)
        return
    await state.update_data(campaign_accounts=selected)
    
    # Собираем группы из выбранных аккаунтов
    all_groups = []
    for acc_id in selected:
        acc_groups = await get_groups(acc_id)
        all_groups.extend(acc_groups)
    # Фильтруем каналы
    groups = [g for g in all_groups if g.group_type != "channel"]
    if not groups:
        await callback.message.edit_text("Нет групп для выбранных аккаунтов. Загрузите группы через меню 'Группы'.")
        return
    
    await state.update_data(selected_groups=[])
    await callback.message.edit_text(
        "Выберите группы для рассылки:",
        reply_markup=select_items_kb(groups, "group", "campaign", 0, per_page=5, show_select_all=True)
    )
    await state.set_state(CampaignStates.waiting_groups)

# === Выбор групп (по одной) ===
@router.callback_query(F.data.startswith("group_select_campaign_"))
async def select_group(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    selected = data.get("selected_groups", [])
    if group_id not in selected:
        selected.append(group_id)
    await state.update_data(selected_groups=selected)
    await callback.answer("Группа добавлена")

# === Кнопка "Выбрать ВСЕ" ===
@router.callback_query(F.data == "group_select_all_campaign")
async def select_all_groups(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    accounts_ids = data.get("campaign_accounts", [])
    all_groups = []
    for acc_id in accounts_ids:
        groups = await get_groups(acc_id)
        all_groups.extend(groups)
    all_groups = [g for g in all_groups if g.group_type != "channel"]
    selected_ids = [g.id for g in all_groups]
    # Сохраняем сразу как campaign_groups
    await state.update_data(campaign_groups=selected_ids, selected_groups=selected_ids)
    await callback.answer(f"✅ Выбрано {len(selected_ids)} групп")
    await callback.message.edit_text("Введите интервал между сообщениями (в секундах, по умолчанию 30):")
    await state.set_state(CampaignStates.waiting_message_interval)

# === Завершение выбора групп ===
@router.callback_query(F.data.startswith("group_done_campaign"), CampaignStates.waiting_groups)
async def groups_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_groups", [])
    if not selected:
        await callback.answer("Выберите хотя бы одну группу", show_alert=True)
        return
    # Сохраняем под ключом 'campaign_groups'
    await state.update_data(campaign_groups=selected)
    await callback.message.edit_text("Введите интервал между сообщениями (в секундах, по умолчанию 30):")
    await state.set_state(CampaignStates.waiting_message_interval)

# === Интервал между сообщениями ===
@router.message(CampaignStates.waiting_message_interval)
async def campaign_interval(message: Message, state: FSMContext):
    interval = int(message.text) if message.text.isdigit() else 30
    await state.update_data(message_interval=interval)
    await message.answer("Введите интервал между циклами (в секундах, по умолчанию 300):")
    await state.set_state(CampaignStates.waiting_cycle_interval)

# === Интервал между циклами ===
@router.message(CampaignStates.waiting_cycle_interval)
async def campaign_cycle(message: Message, state: FSMContext):
    cycle = int(message.text) if message.text.isdigit() else 300
    await state.update_data(cycle_interval=cycle)
    await message.answer("Введите дневной лимит сообщений (0 = без лимита):")
    await state.set_state(CampaignStates.waiting_daily_limit)

# === Финальное создание рассылки ===
@router.message(CampaignStates.waiting_daily_limit)
async def campaign_limit(message: Message, state: FSMContext):
    limit_text = message.text.strip()
    daily_limit = int(limit_text) if limit_text.isdigit() else 0
    data = await state.get_data()
    
    # Проверка наличия ключей
    required_keys = ['name', 'template_id', 'message_interval', 'cycle_interval', 'campaign_accounts', 'campaign_groups']
    for key in required_keys:
        if key not in data:
            await message.answer(f"❌ Ошибка: не найден ключ {key}. Попробуйте создать рассылку заново.")
            await state.clear()
            return
    
    try:
        campaign = await create_campaign(
            name=data['name'],
            template_id=data['template_id'],
            message_interval=data['message_interval'],
            cycle_interval=data['cycle_interval'],
            daily_limit=daily_limit
        )
        for acc_id in data['campaign_accounts']:
            await add_account_to_campaign(campaign.id, acc_id)
        for grp_id in data['campaign_groups']:
            await add_group_to_campaign(campaign.id, grp_id)
        await log_admin_action(message.from_user.id, "create_campaign", "campaign", campaign.id)
        await message.answer(f"✅ Рассылка «{campaign.name}» создана! Перейдите в раздел «Рассылки» для запуска.")
        await state.clear()
        await list_campaigns(message)
    except Exception as e:
        await message.answer(f"❌ Ошибка при создании рассылки: {str(e)}")
        await state.clear()

# === Просмотр деталей рассылки ===
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

# === Информация о шаблоне ===
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

# === Запуск рассылки ===
@router.callback_query(F.data.startswith("camp_start_"))
async def campaign_start(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    await update_campaign(campaign_id, status="running", started_at=datetime.utcnow())
    
    # Вместо Celery запускаем задачу напрямую
    import asyncio
    from backend.tasks.send_tasks import process_campaign
    asyncio.create_task(process_campaign(campaign_id))
    
    await log_admin_action(callback.from_user.id, "start_campaign", "campaign", campaign_id)
    await callback.answer("✅ Рассылка запущена в фоновом режиме")
    await show_campaign(callback)

# === Пауза ===
@router.callback_query(F.data.startswith("camp_pause_"))
async def campaign_pause(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    await update_campaign(campaign_id, status="paused")
    await log_admin_action(callback.from_user.id, "pause_campaign", "campaign", campaign_id)
    await callback.answer("Рассылка приостановлена")
    await show_campaign(callback)

# === Остановка ===
@router.callback_query(F.data.startswith("camp_stop_"))
async def campaign_stop(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    await update_campaign(campaign_id, status="stopped", stopped_at=datetime.utcnow())
    await log_admin_action(callback.from_user.id, "stop_campaign", "campaign", campaign_id)
    await callback.answer("Рассылка остановлена")
    await show_campaign(callback)

# === Статистика ===
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

# === Удаление ===
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

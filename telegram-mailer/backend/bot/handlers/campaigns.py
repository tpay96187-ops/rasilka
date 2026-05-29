from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from backend.bot.states import CampaignStates
from backend.bot.keyboards import campaigns_list_kb, campaign_actions_kb, groups_selection_kb, back_to_main_kb, confirm_kb
from backend.database import (
    get_campaigns, get_campaign, create_campaign, update_campaign, delete_campaign,
    get_templates, get_accounts, get_groups, add_account_to_campaign, add_group_to_campaign,
    get_campaign_accounts, get_campaign_groups, log_admin_action, get_template
)
from backend.tasks.send_tasks import run_campaign
import asyncio
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

# === Начало создания рассылки (инлайн или команда) ===
@router.callback_query(F.data == "new_campaign")
async def new_campaign_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название рассылки:")
    await state.set_state(CampaignStates.waiting_name)
    await callback.answer()

@router.message(Command("new_campaign"))
async def new_campaign_cmd(message: Message, state: FSMContext):
    await message.answer("Введите название рассылки:")
    await state.set_state(CampaignStates.waiting_name)

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
    # Показываем список аккаунтов для выбора
    buttons = []
    for acc in valid_accounts:
        buttons.append([InlineKeyboardButton(text=f"{acc.name} ({acc.phone})", callback_data=f"acc_sel_{acc.id}")])
    buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data="acc_selection_done")])
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_campaign_creation")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выберите аккаунты для рассылки (можно несколько). После выбора нажмите «Готово»:", reply_markup=kb)
    await state.set_state(CampaignStates.waiting_accounts)

@router.callback_query(F.data.startswith("acc_sel_"), CampaignStates.waiting_accounts)
async def select_account(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected = data.get("selected_accounts", [])
    if account_id in selected:
        selected.remove(account_id)
        await callback.answer("Аккаунт удалён из выбранных")
    else:
        selected.append(account_id)
        await callback.answer("Аккаунт добавлен")
    await state.update_data(selected_accounts=selected)
    # обновляем клавиатуру (можно не обновлять, просто меняем состояние)
    # но для наглядности можно показать сообщение с выбранными
    await callback.message.answer(f"Выбрано аккаунтов: {len(selected)}. Продолжайте выбор или нажмите «Готово».")

@router.callback_query(F.data.startswith("account_done_campaign"), CampaignStates.waiting_accounts)
async def accounts_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_accounts", [])
    if not selected:
        await callback.answer("Выберите хотя бы один аккаунт", show_alert=True)
        return
    await state.update_data(campaign_accounts=selected)
    # Переходим к выбору групп
    await callback.message.edit_text("Теперь выберите способ указания групп:", reply_markup=groups_selection_kb())
    await state.set_state(CampaignStates.waiting_groups_selection_method)

# === Обработка отмены создания рассылки ===
@router.callback_query(F.data == "cancel_campaign_creation")
async def cancel_campaign_creation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Создание рассылки отменено.", reply_markup=back_to_main_kb())
    await callback.answer()

# === Выбор метода выбора групп ===
@router.callback_query(F.data == "groups_select_all", CampaignStates.waiting_groups_selection_method)
async def groups_select_all(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_ids = data.get("campaign_accounts", [])
    all_groups = []
    for acc_id in account_ids:
        groups = await get_groups(acc_id)
        # фильтруем каналы
        groups = [g for g in groups if g.group_type != "channel"]
        all_groups.extend(groups)
    group_ids = [g.id for g in all_groups]
    if not group_ids:
        await callback.message.edit_text("Нет групп для выбранных аккаунтов. Загрузите группы через меню «Группы».")
        return
    await state.update_data(campaign_groups=group_ids)
    await callback.message.edit_text("Введите интервал между сообщениями (в секундах, по умолчанию 30):")
    await state.set_state(CampaignStates.waiting_message_interval)

@router.callback_query(F.data == "groups_select_manual", CampaignStates.waiting_groups_selection_method)
async def groups_select_manual(callback: CallbackQuery, state: FSMContext):
    # Показываем список групп с их ID в текстовом виде
    data = await state.get_data()
    account_ids = data.get("campaign_accounts", [])
    all_groups = []
    for acc_id in account_ids:
        groups = await get_groups(acc_id)
        groups = [g for g in groups if g.group_type != "channel"]
        all_groups.extend(groups)
    if not all_groups:
        await callback.message.edit_text("Нет групп для выбранных аккаунтов. Загрузите группы через меню «Группы».")
        return
    # Формируем текстовое сообщение с перечнем групп
    text = "📋 Список доступных групп (укажите ID через пробел или запятую):\n\n"
    for grp in all_groups:
        text += f"ID: {grp.id} — {grp.title}\n"
    await callback.message.edit_text(text)
    await callback.message.answer("Введите ID групп, которые нужно добавить, через пробел или запятую. Например: 15 22 37")
    await state.update_data(available_groups=all_groups)
    await state.set_state(CampaignStates.waiting_manual_groups_ids)

@router.message(CampaignStates.waiting_manual_groups_ids)
async def process_manual_groups(message: Message, state: FSMContext):
    data = await state.get_data()
    available_groups = data.get("available_groups", [])
    try:
        # Парсим введённые ID
        parts = message.text.replace(',', ' ').split()
        selected_ids = [int(p) for p in parts]
    except ValueError:
        await message.answer("❌ Неверный формат. Введите числа через пробел или запятую.")
        return
    # Проверяем, что все введённые ID присутствуют в доступных группах
    available_ids = {g.id for g in available_groups}
    invalid_ids = [sid for sid in selected_ids if sid not in available_ids]
    if invalid_ids:
        await message.answer(f"❌ Следующие ID не найдены: {invalid_ids}. Попробуйте ещё раз.")
        return
    await state.update_data(campaign_groups=selected_ids)
    await message.answer("Введите интервал между сообщениями (в секундах, по умолчанию 30):")
    await state.set_state(CampaignStates.waiting_message_interval)

# === Остальные шаги (интервалы, лимит, создание) ===
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
    limit_text = message.text.strip()
    daily_limit = int(limit_text) if limit_text.isdigit() else 0
    data = await state.get_data()
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

# === Просмотр и управление рассылкой ===
@router.callback_query(F.data.startswith("campaign_"))
async def show_campaign(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 2 or not parts[1].isdigit():
        await callback.answer("Неверный формат")
        return
    campaign_id = int(parts[1])
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
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"camp_delete_{campaign_id}")],
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
    asyncio.create_task(run_campaign(campaign_id))
    await log_admin_action(callback.from_user.id, "start_campaign", "campaign", campaign_id)
    await callback.answer("✅ Рассылка запущена")
    await callback.message.edit_text(
        f"📢 Рассылка #{campaign_id} запущена. Отправка сообщений в фоновом режиме.\nСтатус можно проверить в списке рассылок.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К списку", callback_data="menu_campaigns")]
        ])
    )

@router.callback_query(F.data.startswith("camp_pause_"))
async def campaign_pause(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    await update_campaign(campaign_id, status="paused")
    await log_admin_action(callback.from_user.id, "pause_campaign", "campaign", campaign_id)
    await callback.answer("⏸️ Рассылка приостановлена")
    await show_campaign(callback)

@router.callback_query(F.data.startswith("camp_stop_"))
async def campaign_stop(callback: CallbackQuery):
    campaign_id = int(callback.data.split("_")[2])
    await update_campaign(campaign_id, status="stopped", stopped_at=datetime.utcnow())
    await log_admin_action(callback.from_user.id, "stop_campaign", "campaign", campaign_id)
    await callback.answer("⏹️ Рассылка остановлена")
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

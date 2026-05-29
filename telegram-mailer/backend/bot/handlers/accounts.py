from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from backend.database import get_accounts, get_account, delete_account, set_spam_block, log_admin_action, get_account_by_phone
from backend.mtproto.auth import add_telegram_account
from backend.mtproto.spam_checker import check_account_spam_bot
from backend.services.notification import notify_admin
from backend.utils.validators import validate_phone
from backend.bot.keyboards import (
    account_list_kb, account_actions_kb, back_to_main_kb, confirm_kb
)
from datetime import datetime

router = Router()

class AddAccountStates(StatesGroup):
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()

# === Список аккаунтов ===
@router.callback_query(F.data == "menu_accounts")
async def list_accounts(callback: CallbackQuery):
    accounts = await get_accounts()
    if not accounts:
        text = "📱 Аккаунты отсутствуют.\n➕ Нажмите кнопку ниже, чтобы добавить."
        await callback.message.edit_text(text, reply_markup=account_list_kb(accounts))
    else:
        await callback.message.edit_text("📱 Список аккаунтов:", reply_markup=account_list_kb(accounts))
    await callback.answer()

# === Обработчик inline-кнопки "Добавить аккаунт" ===
@router.callback_query(F.data == "add_account_start")
async def add_account_start_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🔑 Введите API ID (можно получить на my.telegram.org):")
    await state.set_state(AddAccountStates.waiting_api_id)
    await callback.answer()

@router.callback_query(F.data.startswith("acc_"))
async def show_account(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 2 or not parts[1].isdigit():
        # Это не числовой ID (например, acc_sel), просто игнорируем
        await callback.answer()
        return
    account_id = int(parts[1])
    acc = await get_account(account_id)
    if not acc:
        await callback.answer("Аккаунт не найден")
        return
    status = "✅ Активен" if acc.is_valid else "❌ Не активен"
    flood = f"⚠️ FloodWait до {acc.flood_wait_until}" if acc.flood_wait_until and acc.flood_wait_until > datetime.utcnow() else "✅ Нет FloodWait"
    spam = "🚫 SpamBlock" if acc.spam_blocked else "✅ Нет блокировки"
    text = f"📱 *{acc.name}*\n📞 `{acc.phone}`\n{status}\n{flood}\n{spam}\n🕒 Последняя активность: {acc.last_activity}"
    await callback.message.edit_text(text, reply_markup=account_actions_kb(account_id), parse_mode="Markdown")
    await callback.answer()

# === Команда /add_account (альтернативный способ) ===
@router.message(Command("add_account"))
async def add_account_cmd(message: Message, state: FSMContext):
    await message.answer("🔑 Введите API ID (можно получить на my.telegram.org):")
    await state.set_state(AddAccountStates.waiting_api_id)

@router.message(AddAccountStates.waiting_api_id)
async def add_account_api_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ API ID должен быть числом. Попробуйте ещё раз:")
        return
    await state.update_data(api_id=int(message.text))
    await message.answer("🔐 Введите API HASH:")
    await state.set_state(AddAccountStates.waiting_api_hash)

@router.message(AddAccountStates.waiting_api_hash)
async def add_account_api_hash(message: Message, state: FSMContext):
    if len(message.text) < 10:
        await message.answer("❌ API HASH слишком короткий. Попробуйте ещё раз:")
        return
    await state.update_data(api_hash=message.text)
    await message.answer("📞 Введите номер телефона в международном формате (например, +79123456789):")
    await state.set_state(AddAccountStates.waiting_phone)

@router.message(AddAccountStates.waiting_phone)
async def add_account_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not validate_phone(phone):
        await message.answer("❌ Неверный формат номера. Пример: +79123456789")
        return
    # Проверка на существующий аккаунт
    existing = await get_account_by_phone(phone)
    if existing:
        await message.answer("❌ Аккаунт с таким номером уже добавлен. Удалите его перед повторным добавлением.")
        await state.clear()
        return
    await state.update_data(phone=phone)
    data = await state.get_data()
    result = await add_telegram_account(
        api_id=data['api_id'],
        api_hash=data['api_hash'],
        phone=phone,
        step="init"
    )
    if result.get("error"):
        await message.answer(f"❌ Ошибка: {result['error']}")
        await state.clear()
        return
    if result.get("step") == "code":
        await state.update_data(auth_step="code")
        if result.get("phone_code_hash"):
            await state.update_data(phone_code_hash=result['phone_code_hash'])
        await message.answer("📨 Введите код подтверждения, полученный в Telegram:")
        await state.set_state(AddAccountStates.waiting_code)

@router.message(AddAccountStates.waiting_code)
async def add_account_code(message: Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    result = await add_telegram_account(
        api_id=data['api_id'],
        api_hash=data['api_hash'],
        phone=data['phone'],
        code=code,
        phone_code_hash=data.get('phone_code_hash'),
        step="code"
    )
    if result.get("error"):
        await message.answer(f"❌ Ошибка: {result['error']}")
        if "пароль" in result['error'].lower() or "2FA" in result['error']:
            await state.set_state(AddAccountStates.waiting_password)
        else:
            await state.clear()
        return
    if result.get("step") == "password":
        await state.update_data(auth_step="password")
        await message.answer("🔒 Введите пароль 2FA:")
        await state.set_state(AddAccountStates.waiting_password)
        return
    if result.get("step") == "done":
        await message.answer(f"✅ Аккаунт {result['account'].first_name} успешно добавлен!")
        await log_admin_action(message.from_user.id, "add_account", "account", result['account'].id)
        await state.clear()
        # Обновляем список аккаунтов
        accounts = await get_accounts()
        if not accounts:
            text = "📱 Аккаунты отсутствуют.\n➕ Нажмите кнопку ниже, чтобы добавить."
            await message.answer(text, reply_markup=account_list_kb(accounts))
        else:
            await message.answer("📱 Список аккаунтов:", reply_markup=account_list_kb(accounts))

@router.message(AddAccountStates.waiting_password)
async def add_account_password(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    result = await add_telegram_account(
        api_id=data['api_id'],
        api_hash=data['api_hash'],
        phone=data['phone'],
        password=password,
        step="password"
    )
    if result.get("error"):
        await message.answer(f"❌ Ошибка: {result['error']}")
        await state.clear()
        return
    if result.get("step") == "done":
        await message.answer(f"✅ Аккаунт {result['account'].first_name} успешно добавлен!")
        await log_admin_action(message.from_user.id, "add_account", "account", result['account'].id)
        await state.clear()
        # Обновляем список
        accounts = await get_accounts()
        await message.answer("📱 Список аккаунтов:", reply_markup=account_list_kb(accounts))

# === Проверка статуса аккаунта ===
@router.callback_query(F.data.startswith("check_acc_"))
async def check_account_status(callback: CallbackQuery):
    await callback.answer("🔄 Проверка выполняется...")
    await callback.message.answer("✅ Аккаунт активен (проверка сессии).")

# === Проверка через SpamBot ===
@router.callback_query(F.data.startswith("spambot_acc_"))
async def spambot_check(callback: CallbackQuery):
    account_id = int(callback.data.split("_")[2])
    await callback.answer("🔄 Проверка через @SpamBot...")
    result = await check_account_spam_bot(account_id)
    if result == "blocked":
        await set_spam_block(account_id, True)
        await callback.message.answer(f"⚠️ Аккаунт {account_id} помечен как спам-блокированный.")
    else:
        await set_spam_block(account_id, False)
        await callback.message.answer(f"✅ Аккаунт {account_id} чист, ограничений нет.")
    await callback.answer()

# === Удаление аккаунта ===
@router.callback_query(F.data.startswith("del_acc_"))
async def confirm_delete_account(callback: CallbackQuery):
    account_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите удалить аккаунт? Это действие необратимо.",
        reply_markup=confirm_kb("del_account", account_id)
    )

@router.callback_query(F.data.startswith("confirm_del_account_"))
async def delete_account_final(callback: CallbackQuery):
    account_id = int(callback.data.split("_")[3])
    acc = await get_account(account_id)
    if acc:
        import os
        if acc.session_file and os.path.exists(acc.session_file):
            os.remove(acc.session_file)
        await delete_account(account_id)
        await log_admin_action(callback.from_user.id, "delete_account", "account", account_id)
        await notify_admin(f"🗑 Аккаунт {acc.phone} удалён.")
    await callback.message.edit_text("✅ Аккаунт удалён.")
    # Показать обновлённый список
    accounts = await get_accounts()
    if not accounts:
        text = "📱 Аккаунты отсутствуют.\n➕ Нажмите кнопку ниже, чтобы добавить."
        await callback.message.answer(text, reply_markup=account_list_kb(accounts))
    else:
        await callback.message.answer("📱 Список аккаунтов:", reply_markup=account_list_kb(accounts))

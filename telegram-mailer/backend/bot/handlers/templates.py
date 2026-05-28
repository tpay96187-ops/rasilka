from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from backend.database import get_templates, get_template, create_template, update_template, delete_template, log_admin_action
from backend.bot.keyboards import templates_list_kb, template_actions_kb, back_to_main_kb, confirm_kb
from backend.services.notification import notify_admin

router = Router()

class TemplateStates(StatesGroup):
    waiting_name = State()
    waiting_content = State()
    waiting_edit_name = State()      # добавлено
    waiting_edit_content = State()   # добавлено

@router.callback_query(F.data == "menu_templates")
async def list_templates(callback: CallbackQuery):
    templates = await get_templates()
    if not templates:
        await callback.message.edit_text("📝 Шаблоны отсутствуют.\nСоздайте новый /new_template", reply_markup=back_to_main_kb())
    else:
        await callback.message.edit_text("📝 Ваши шаблоны:", reply_markup=templates_list_kb(templates))
    await callback.answer()

@router.callback_query(F.data.startswith("template_"))
async def show_template(callback: CallbackQuery):
    template_id = int(callback.data.split("_")[1])
    tpl = await get_template(template_id)
    if not tpl:
        await callback.answer("Шаблон не найден")
        return
    status = "✅ Активен" if tpl.is_active else "❌ Не активен"
    text = f"📝 *{tpl.name}*\n{status}\n\n📄 Содержание:\n{tpl.content[:500]}"
    await callback.message.edit_text(text, reply_markup=template_actions_kb(template_id, tpl.is_active), parse_mode="Markdown")
    await callback.answer()

@router.message(Command("new_template"))
async def new_template_cmd(message: Message, state: FSMContext):
    await message.answer("Введите название шаблона:")
    await state.set_state(TemplateStates.waiting_name)

@router.message(TemplateStates.waiting_name)
async def template_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите текст сообщения (можно с эмодзи, ссылками, переносами строк):")
    await state.set_state(TemplateStates.waiting_content)

@router.message(TemplateStates.waiting_content)
async def template_content(message: Message, state: FSMContext):
    data = await state.get_data()
    tpl = await create_template(data['name'], message.text, message.from_user.id)
    await log_admin_action(message.from_user.id, "create_template", "template", tpl.id)
    await message.answer(f"✅ Шаблон «{tpl.name}» создан!")
    await state.clear()
    await list_templates(message)

@router.callback_query(F.data.startswith("edit_template_"))
async def edit_template_start(callback: CallbackQuery, state: FSMContext):
    template_id = int(callback.data.split("_")[2])
    await state.update_data(edit_id=template_id)
    await callback.message.answer("Введите новое название (или отправьте '-' чтобы оставить без изменений):")
    await state.set_state(TemplateStates.waiting_edit_name)

@router.message(TemplateStates.waiting_edit_name)
async def edit_template_name(message: Message, state: FSMContext):
    data = await state.get_data()
    if message.text != "-":
        await update_template(data['edit_id'], name=message.text)
    await message.answer("Введите новый текст сообщения (или '-' чтобы оставить без изменений):")
    await state.set_state(TemplateStates.waiting_edit_content)

@router.message(TemplateStates.waiting_edit_content)
async def edit_template_content(message: Message, state: FSMContext):
    data = await state.get_data()
    if message.text != "-":
        await update_template(data['edit_id'], content=message.text)
    await update_template(data['edit_id'], is_active=True)
    await log_admin_action(message.from_user.id, "edit_template", "template", data['edit_id'])
    await message.answer("✅ Шаблон обновлён")
    await state.clear()
    await list_templates(message)

@router.callback_query(F.data.startswith("toggle_template_"))
async def toggle_template(callback: CallbackQuery):
    template_id = int(callback.data.split("_")[2])
    tpl = await get_template(template_id)
    if tpl:
        new_status = not tpl.is_active
        await update_template(template_id, is_active=new_status)
        await log_admin_action(callback.from_user.id, "toggle_template", "template", template_id)
        await callback.answer("Статус изменён")
        await show_template(callback)

@router.callback_query(F.data.startswith("del_template_"))
async def confirm_delete_template(callback: CallbackQuery):
    template_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("Удалить шаблон?", reply_markup=confirm_kb("del_template", template_id))

@router.callback_query(F.data.startswith("confirm_del_template_"))
async def delete_template_final(callback: CallbackQuery):
    template_id = int(callback.data.split("_")[3])
    await delete_template(template_id)
    await log_admin_action(callback.from_user.id, "delete_template", "template", template_id)
    await callback.message.edit_text("✅ Шаблон удалён")
    await list_templates(callback)

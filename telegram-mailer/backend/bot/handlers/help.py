from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

@router.message(Command("help"))
async def help_cmd(message: Message):
    text = (
        "📚 *Список команд:*\n\n"
        "/start – Главное меню\n"
        "/add_account – Добавить Telegram-аккаунт\n"
        "/new_template – Создать шаблон сообщения\n"
        "/new_campaign – Создать новую рассылку\n"
        "/help – Показать эту справку\n\n"
        "Также вы можете управлять системой через inline-кнопки в меню."
    )
    await message.answer(text, parse_mode="Markdown")

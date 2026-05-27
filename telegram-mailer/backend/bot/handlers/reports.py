from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import os

from backend.database import get_campaigns, get_campaign_stats_by_group, get_campaign_stats_by_account
from backend.services.excel_reporter import generate_group_report, generate_account_report
from backend.bot.keyboards import back_to_main_kb
from backend.services.notification import notify_admin

router = Router()

@router.callback_query(F.data == "menu_reports")
async def reports_menu(callback: CallbackQuery):
    """Показывает список рассылок для выбора отчёта"""
    campaigns = await get_campaigns()
    if not campaigns:
        await callback.message.edit_text(
            "📊 Нет завершённых или запущенных рассылок для формирования отчётов.\n"
            "Сначала создайте и запустите хотя бы одну рассылку.",
            reply_markup=back_to_main_kb()
        )
        await callback.answer()
        return
    
    buttons = []
    for camp in campaigns:
        status_emoji = {"running": "▶️", "paused": "⏸️", "completed": "✅", "stopped": "⏹️", "draft": "📝"}.get(camp.status, "❓")
        buttons.append([InlineKeyboardButton(
            text=f"{status_emoji} {camp.name} (отправлено: {camp.total_sent})",
            callback_data=f"report_camp_{camp.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "📊 Выберите рассылку для формирования Excel-отчёта:\n"
        "Будут сгенерированы два файла:\n"
        "• Отчёт по группам\n"
        "• Отчёт по аккаунтам",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("report_camp_"))
async def generate_and_send_reports(callback: CallbackQuery):
    """Генерирует оба отчёта и отправляет их пользователю"""
    campaign_id = int(callback.data.split("_")[2])
    
    # Уведомление о начале генерации
    await callback.message.edit_text("⏳ Генерация Excel-отчётов... Пожалуйста, подождите.")
    await callback.answer()
    
    try:
        # Генерируем отчёт по группам
        group_file = await generate_group_report(campaign_id)
        # Генерируем отчёт по аккаунтам
        account_file = await generate_account_report(campaign_id)
        
        # Отправляем файлы
        await callback.message.answer_document(
            FSInputFile(group_file),
            caption=f"📊 Отчёт по группам для рассылки #{campaign_id}\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await callback.message.answer_document(
            FSInputFile(account_file),
            caption=f"📊 Отчёт по аккаунтам для рассылки #{campaign_id}"
        )
        
        # Чистим временные файлы
        os.remove(group_file)
        os.remove(account_file)
        
        # Логируем действие
        await notify_admin(f"Пользователь {callback.from_user.id} сгенерировал отчёты для рассылки {campaign_id}")
        
        # Возвращаемся в меню отчётов
        await reports_menu(callback)
        
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации отчёта: {str(e)}")
        await callback.answer()
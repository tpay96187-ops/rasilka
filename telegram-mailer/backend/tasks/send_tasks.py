import asyncio
import logging
from backend.database import (
    get_campaign, get_campaign_accounts, get_campaign_groups, get_template, update_campaign,
    log_mailing, update_campaign_stats
)
from backend.mtproto.messenger import send_message_to_group
from backend.mtproto.group_fetcher import get_group_entity_by_id

logger = logging.getLogger(__name__)

async def run_campaign(campaign_id: int):
    """Фоновая задача для выполнения рассылки"""
    logger.info(f"Запущена рассылка #{campaign_id}")
    campaign = await get_campaign(campaign_id)
    if not campaign or campaign.status != "running":
        logger.warning(f"Рассылка #{campaign_id} не найдена или не в статусе running")
        return

    accounts = await get_campaign_accounts(campaign_id)
    groups = await get_campaign_groups(campaign_id)  # список объектов Group из БД
    template = await get_template(campaign.template_id)
    if not template or not template.is_active:
        logger.warning(f"Рассылка #{campaign_id}: шаблон не активен или не найден")
        await update_campaign(campaign_id, status="stopped")
        return

    logger.info(f"Рассылка #{campaign_id}: аккаунтов={len(accounts)}, групп={len(groups)}")

    for account in accounts:
        logger.info(f"Отправка с аккаунта {account.id} ({account.phone})")
        for group in groups:  # group - объект БД, имеет поля .id и .group_id
            # Получаем entity группы по Telegram ID (group.group_id)
            group_entity = await get_group_entity_by_id(account.id, group.group_id)
            if not group_entity:
                logger.error(f"Не удалось получить entity для группы {group.group_id}")
                # Логируем ошибку в БД с group.id
                await log_mailing(campaign_id, account.id, group.id, success=False,
                                  error_type="other", error_detail="Cannot get group entity")
                continue
            # Отправляем сообщение, передавая db_group_id=group.id
            result = await send_message_to_group(account.id, group_entity, template.content, campaign_id, db_group_id=group.id)
            if result.get("error") == "floodwait":
                logger.warning(f"Аккаунт {account.id} в FloodWait, пропускаем группу {group.id}")
                continue
            await asyncio.sleep(campaign.message_interval)
        await asyncio.sleep(campaign.cycle_interval)

    await update_campaign(campaign_id, status="completed")
    logger.info(f"Рассылка #{campaign_id} завершена")

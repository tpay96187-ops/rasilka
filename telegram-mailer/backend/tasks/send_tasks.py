import asyncio
import logging
from backend.database import get_campaign, get_campaign_accounts, get_campaign_groups, get_template, update_campaign, log_mailing
from backend.mtproto.messenger import send_message_to_group
from backend.mtproto.group_fetcher import get_group_entity_by_id

logger = logging.getLogger(__name__)

async def run_campaign(campaign_id: int):
    logger.info(f"Запущена рассылка #{campaign_id}")
    campaign = await get_campaign(campaign_id)
    if not campaign or campaign.status != "running":
        logger.warning(f"Рассылка #{campaign_id} не в статусе running")
        return
    
    accounts = await get_campaign_accounts(campaign_id)
    groups = await get_campaign_groups(campaign_id)
    template = await get_template(campaign.template_id)
    
    if not accounts:
        logger.error(f"Нет аккаунтов для рассылки #{campaign_id}")
        await update_campaign(campaign_id, status="stopped")
        return
    if not groups:
        logger.error(f"Нет групп для рассылки #{campaign_id}")
        await update_campaign(campaign_id, status="stopped")
        return
    if not template or not template.is_active:
        logger.error(f"Нет активного шаблона для рассылки #{campaign_id}")
        await update_campaign(campaign_id, status="stopped")
        return
    
    logger.info(f"Рассылка #{campaign_id}: аккаунтов={len(accounts)}, групп={len(groups)}")
    
    for account in accounts:
        logger.info(f"Отправка с аккаунта {account.id} ({account.phone})")
        for group in groups:
            try:
                group_entity = await get_group_entity_by_id(account.id, group.group_id)
                if not group_entity:
                    logger.error(f"Не удалось получить entity группы {group.group_id} для аккаунта {account.id}")
                    continue
                result = await send_message_to_group(account.id, group_entity, template.content, campaign_id)
                if result.get("success"):
                    logger.info(f"Успешно отправлено в группу {group.title} ({group.group_id})")
                else:
                    logger.error(f"Ошибка при отправке в группу {group.title}: {result.get('error')}")
                await asyncio.sleep(campaign.message_interval)
            except Exception as e:
                logger.exception(f"Неожиданная ошибка при отправке в группу {group.group_id}: {e}")
                await log_mailing(campaign_id, account.id, group.group_id, False, "exception", str(e))
        await asyncio.sleep(campaign.cycle_interval)
    
    await update_campaign(campaign_id, status="completed")
    logger.info(f"Рассылка #{campaign_id} завершена")

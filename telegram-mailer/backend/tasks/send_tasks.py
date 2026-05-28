from backend.database import get_campaign, get_campaign_accounts, get_campaign_groups, get_template, update_campaign
from backend.mtproto.messenger import send_message_to_group
from backend.mtproto.group_fetcher import get_group_entity_by_id
import asyncio

async def run_campaign(campaign_id: int):
    """Асинхронная фоновая задача для выполнения рассылки"""
    campaign = await get_campaign(campaign_id)
    if not campaign or campaign.status != "running":
        return {"status": "stopped"}
    
    accounts = await get_campaign_accounts(campaign_id)
    groups = await get_campaign_groups(campaign_id)
    template = await get_template(campaign.template_id)
    if not template or not template.is_active:
        await update_campaign(campaign_id, status="stopped")
        return {"status": "no_active_template"}
    
    for account in accounts:
        for group in groups:
            group_entity = await get_group_entity_by_id(account.id, group.group_id)
            if not group_entity:
                continue
            result = await send_message_to_group(account.id, group_entity, template.content, campaign_id)
            if result.get("error") == "floodwait":
                continue
            await asyncio.sleep(campaign.message_interval)
        await asyncio.sleep(campaign.cycle_interval)
    await update_campaign(campaign_id, status="completed")
    return {"status": "completed"}

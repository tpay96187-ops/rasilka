from telethon import TelegramClient, errors
from backend.database import get_account, set_flood_wait, log_mailing, increment_daily_sent
from backend.utils.crypto import decrypt_value
from datetime import datetime, timedelta
import asyncio

async def send_message_to_group(account_id: int, group_entity, message_text: str, campaign_id: int):
    acc = await get_account(account_id)
    if not acc or not acc.is_valid:
        return {"success": False, "error": "invalid_account"}
    if acc.flood_wait_until and acc.flood_wait_until > datetime.utcnow():
        return {"success": False, "error": "floodwait"}
    if acc.spam_blocked:
        return {"success": False, "error": "spamblock"}
    if acc.daily_limit and acc.daily_sent >= acc.daily_limit:
        return {"success": False, "error": "daily_limit"}
    
    api_hash = decrypt_value(acc.api_hash)
    client = TelegramClient(acc.session_file, acc.api_id, api_hash)
    await client.connect()
    
    try:
        await client.send_message(group_entity, message_text)
        await increment_daily_sent(account_id)
        await log_mailing(campaign_id, account_id, group_entity.id, success=True)
        return {"success": True}
    except errors.FloodWaitError as e:
        await set_flood_wait(account_id, e.seconds)
        await log_mailing(campaign_id, account_id, group_entity.id, success=False, error_type="floodwait", error_detail=str(e))
        return {"success": False, "error": "floodwait", "wait_seconds": e.seconds}
    except errors.FloodError:
        await set_flood_wait(account_id, 60)
        await log_mailing(campaign_id, account_id, group_entity.id, success=False, error_type="flood", error_detail="Flood error")
        return {"success": False, "error": "flood"}
    except errors.PeerFloodError:
        await log_mailing(campaign_id, account_id, group_entity.id, success=False, error_type="peerflood", error_detail="Peer flood detected")
        return {"success": False, "error": "peerflood"}
    except Exception as e:
        await log_mailing(campaign_id, account_id, group_entity.id, success=False, error_type="other", error_detail=str(e))
        return {"success": False, "error": "other"}
    finally:
        await client.disconnect()
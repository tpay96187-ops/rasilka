from telethon import TelegramClient, errors
from backend.database import get_account, set_flood_wait, log_mailing, increment_daily_sent
from backend.utils.crypto import decrypt_value
from datetime import datetime

async def send_message_to_group(account_id: int, group_entity, message_text: str, campaign_id: int, db_group_id: int):
    acc = await get_account(account_id)
    if not acc or not acc.is_valid:
        return {"success": False, "error": "invalid_account"}
    
    # FloodWait проверка
    if acc.flood_wait_until and acc.flood_wait_until > datetime.utcnow():
        return {"success": False, "error": "floodwait"}
    
    # Не блокируем отправку из-за spam_blocked без проверки
    # Но если есть явный флаг от SpamBot, то действительно блокируем:
   # if acc.spam_blocked:
   #     return {"success": False, "error": "spamblock"}
    
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
        await log_mailing(campaign_id, account_id, db_group_id, group_entity.id, success=success, error_type="floodwait", error_detail=str(e))
        return {"success": False, "error": "floodwait", "wait_seconds": e.seconds}
    
    except errors.PeerFloodError:
        # Не ставим spam_blocked, только логируем
        await log_mailing(campaign_id, account_id, group_entity.id, success=False, error_type="peerflood", error_detail="Peer flood detected")
        return {"success": False, "error": "peerflood"}
    
    except errors.RPCError as e:
        await log_mailing(campaign_id, account_id, group_entity.id, success=False, error_type="rpc_error", error_detail=str(e))
        return {"success": False, "error": "rpc_error"}
    
    except Exception as e:
        await log_mailing(campaign_id, account_id, group_entity.id, success=False, error_type="other", error_detail=str(e))
        return {"success": False, "error": "other"}
    
    finally:
        await client.disconnect()

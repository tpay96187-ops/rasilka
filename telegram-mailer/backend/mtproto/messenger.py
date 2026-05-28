import logging
from telethon import TelegramClient, errors
from backend.database import get_account, set_flood_wait, log_mailing
from backend.utils.crypto import decrypt_value

logger = logging.getLogger(__name__)

async def send_message_to_group(account_id: int, group_entity, message_text: str, campaign_id: int, db_group_id: int):
    """
    Отправляет сообщение в группу.
    - account_id: ID аккаунта в БД
    - group_entity: объект Telegram (полученный через telethon)
    - message_text: текст сообщения
    - campaign_id: ID рассылки
    - db_group_id: внутренний ID группы в таблице groups (для логирования)
    """
    acc = await get_account(account_id)
    if not acc or not acc.is_valid:
        logger.error(f"Аккаунт {account_id} не валиден")
        return {"success": False, "error": "invalid_account"}

    # Временно отключаем проверку spam_blocked для теста
    # if acc.spam_blocked:
    #     logger.warning(f"Аккаунт {account_id} помечен как спам-блокированный")
    #     return {"success": False, "error": "spamblock"}

    # Проверка floodwait
    from datetime import datetime
    if acc.flood_wait_until and acc.flood_wait_until > datetime.utcnow():
        logger.warning(f"Аккаунт {account_id} в floodwait до {acc.flood_wait_until}")
        return {"success": False, "error": "floodwait"}

    api_hash = decrypt_value(acc.api_hash)
    client = TelegramClient(acc.session_file, acc.api_id, api_hash)
    await client.connect()

    try:
        await client.send_message(group_entity, message_text)
        await log_mailing(campaign_id, account_id, db_group_id, success=True)
        logger.info(f"Успешная отправка: аккаунт {account_id}, группа {db_group_id}")
        return {"success": True}
    except errors.FloodWaitError as e:
        logger.warning(f"FloodWait на аккаунте {account_id}: {e.seconds} сек")
        await set_flood_wait(account_id, e.seconds)
        await log_mailing(campaign_id, account_id, db_group_id, success=False,
                          error_type="floodwait", error_detail=str(e))
        return {"success": False, "error": "floodwait", "wait_seconds": e.seconds}
    except errors.FloodError:
        logger.warning(f"FloodError (общий) на аккаунте {account_id}")
        await set_flood_wait(account_id, 60)
        await log_mailing(campaign_id, account_id, db_group_id, success=False,
                          error_type="flood", error_detail="General flood error")
        return {"success": False, "error": "flood"}
    except errors.PeerFloodError:
        logger.error(f"PeerFloodError на аккаунте {account_id}")
        await log_mailing(campaign_id, account_id, db_group_id, success=False,
                          error_type="peerflood", error_detail="Peer flood detected")
        return {"success": False, "error": "peerflood"}
    except Exception as e:
        logger.error(f"Неизвестная ошибка при отправке: {e}", exc_info=True)
        await log_mailing(campaign_id, account_id, db_group_id, success=False,
                          error_type="other", error_detail=str(e))
        return {"success": False, "error": "other"}
    finally:
        await client.disconnect()

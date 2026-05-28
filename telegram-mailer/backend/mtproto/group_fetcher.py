from telethon import TelegramClient
from backend.database import get_account, save_group, clear_account_groups
from backend.utils.crypto import decrypt_value

async def fetch_all_groups_for_account(account_id: int):
    acc = await get_account(account_id)
    if not acc or not acc.is_valid:
        return []
    api_hash = decrypt_value(acc.api_hash)
    client = TelegramClient(acc.session_file, acc.api_id, api_hash)
    await client.connect()
    groups = []
    async for dialog in client.iter_dialogs():
        # Только группы и супергруппы, исключаем каналы
        if dialog.is_group or (dialog.is_channel and dialog.entity.megagroup):
            participants_count = 0
            try:
                if dialog.is_group:
                    participants_count = dialog.entity.participants_count if hasattr(dialog.entity, 'participants_count') else 0
                elif dialog.is_channel and dialog.entity.megagroup:
                    participants_count = dialog.entity.participants_count
            except:
                participants_count = 0
            group_data = {
                "id": dialog.id,
                "title": dialog.name,
                "username": dialog.entity.username if hasattr(dialog.entity, 'username') else None,
                "invite_link": None,
                "type": "group" if not dialog.is_channel else "supergroup",
                "participants_count": participants_count
            }
            await save_group(group_data, account_id)
            groups.append(group_data)
    await client.disconnect()
    return groups

async def get_group_entity_by_id(account_id: int, group_id: int):
    """Получить entity группы по её ID через указанный аккаунт"""
    from backend.mtproto.client_manager import get_client
    client = await get_client(account_id)
    try:
        entity = await client.get_entity(group_id)
        return entity
    except Exception as e:
        print(f"Error getting group entity: {e}")
        return None
    finally:
        await client.disconnect()

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
        if dialog.is_group or dialog.is_channel:
            group_data = {
                "id": dialog.id,
                "title": dialog.name,
                "username": dialog.entity.username if hasattr(dialog.entity, 'username') else None,
                "invite_link": None,  # можно получить отдельным методом
                "type": "supergroup" if dialog.is_channel else "group"
            }
            await save_group(group_data, account_id)
            groups.append(group_data)
    await client.disconnect()
    return groups
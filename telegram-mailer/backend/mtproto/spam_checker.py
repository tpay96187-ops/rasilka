from telethon import TelegramClient
from backend.database import get_account
from backend.utils.crypto import decrypt_value

async def check_account_spam_bot(account_id: int) -> str:
    acc = await get_account(account_id)
    if not acc:
        return "error"
    api_hash = decrypt_value(acc.api_hash)
    client = TelegramClient(acc.session_file, acc.api_id, api_hash)
    await client.connect()
    try:
        spam_bot = await client.get_entity("@SpamBot")
        async with client.conversation(spam_bot) as conv:
            await conv.send_message("/start")
            response = await conv.get_response()
            if "не ограничен" in response.text or "not restricted" in response.text:
                return "clean"
            else:
                return "blocked"
    except Exception:
        return "error"
    finally:
        await client.disconnect()
from telethon import TelegramClient
from backend.database import get_account
from backend.utils.crypto import decrypt_value
import os

async def get_client(account_id: int):
    acc = await get_account(account_id)
    if not acc or not acc.session_file or not os.path.exists(acc.session_file):
        raise Exception("Session not found")
    api_hash = decrypt_value(acc.api_hash)
    client = TelegramClient(acc.session_file, acc.api_id, api_hash)
    await client.connect()
    return client

async def check_session_valid(account) -> bool:
    try:
        client = TelegramClient(account.session_file, account.api_id, decrypt_value(account.api_hash))
        await client.connect()
        me = await client.get_me()
        await client.disconnect()
        return me is not None
    except:
        return False
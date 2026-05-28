from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
from telethon.tl.functions.account import UpdateDeviceRequest
from backend.database import save_account
from backend.utils.crypto import encrypt_value
from backend.services.notification import notify_admin
import os

async def add_telegram_account(api_id: int, api_hash: str, phone: str, code: str = None, password: str = None, step: str = "init"):
    session_path = f"sessions/{phone}.session"
    client = TelegramClient(session_path, api_id, api_hash, lang_code='ru', system_lang_code='ru-RU')
    await client.connect()

    # Отправляем информацию об устройстве (имитируем реальное приложение)
    try:
        await client(UpdateDeviceRequest(
            device_model="Samsung SM-G998B",
            system_version="Android 13",
            app_version="10.3.0 (123456)",
            lang_code="ru",
            system_lang_code="ru-RU"
        ))
    except Exception as e:
        print(f"Device info update error: {e}")

    if step == "init":
        await client.send_code_request(phone)
        return {"step": "code", "message": "Код отправлен"}

    elif step == "code":
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            return {"step": "password", "message": "Требуется пароль 2FA"}
        except PhoneCodeInvalidError:
            return {"error": "Неверный код"}
        except PhoneCodeExpiredError:
            return {"error": "Код истёк, запросите новый"}
        else:
            me = await client.get_me()
            await save_account(
                name=me.first_name or me.username or phone,
                phone=phone,
                api_id=api_id,
                api_hash=encrypt_value(api_hash),
                session_file=session_path,
                is_valid=True
            )
            await notify_admin(f"✅ Аккаунт {me.first_name} ({phone}) добавлен")
            await client.disconnect()
            return {"step": "done", "account": me}

    elif step == "password":
        try:
            await client.sign_in(password=password)
            me = await client.get_me()
            await save_account(
                name=me.first_name or me.username or phone,
                phone=phone,
                api_id=api_id,
                api_hash=encrypt_value(api_hash),
                session_file=session_path,
                is_valid=True
            )
            await notify_admin(f"✅ Аккаунт {me.first_name} ({phone}) добавлен (2FA)")
            await client.disconnect()
            return {"step": "done", "account": me}
        except Exception as e:
            return {"error": str(e)}

    else:
        return {"error": "Неизвестный шаг"}

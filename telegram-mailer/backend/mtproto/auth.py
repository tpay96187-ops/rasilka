from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
from backend.database import save_account
from backend.utils.crypto import encrypt_value
from backend.services.notification import notify_admin
import os

async def add_telegram_account(api_id: int, api_hash: str, phone: str, code: str = None, password: str = None, step: str = "init", phone_code_hash: str = None):
    session_path = f"sessions/{phone}.session"
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    
    # Пожалуйста, добавьте этот код сразу после подключения клиента (await client.connect())
from telethon.tl.functions.account import UpdateDeviceRequest

try:
    await client(UpdateDeviceRequest(
        device_model="Samsung SM-G998B",         # Модель смартфона
        system_version="Android 13",             # Версия ОС
        app_version="10.3.0 (123456)",           # Версия приложения
        lang_code="ru",                          # Язык
        system_lang_code="ru-RU"                 # Язык системы
    ))
except Exception as e:
    print(f"Ошибка при обновлении информации об устройстве: {e}")
        if step == "init":
            # Запрашиваем код
            result = await client.send_code_request(phone)
            # result содержит phone_code_hash
            return {
                "step": "code",
                "message": "Код отправлен",
                "phone_code_hash": result.phone_code_hash
            }
        
        elif step == "code":
            # Используем полученный phone_code_hash
            if not phone_code_hash:
                return {"error": "Missing phone_code_hash"}
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
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
            await client.sign_in(password=password)
            me = await client.get_me()
            await save_account(...)
            await client.disconnect()
            return {"step": "done", "account": me}
    
    except Exception as e:
        return {"error": str(e)}
    finally:
        if client.is_connected():
            await client.disconnect()

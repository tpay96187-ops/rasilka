from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError
)
from backend.database import save_account
from backend.utils.crypto import encrypt_value
from backend.services.notification import notify_admin

async def add_telegram_account(api_id: int, api_hash: str, phone: str, code: str = None, password: str = None, phone_code_hash: str = None, step: str = "init"):
    session_path = f"sessions/{phone}.session"
    client = TelegramClient(
        session_path,
        api_id,
        api_hash,
        device_model="Samsung SM-G998B",
        system_version="Android 13",
        app_version="10.14.0 (123456)",
        lang_code="ru",
        system_lang_code="ru-RU"
    )
    await client.connect()

    if not client.is_connected():
        return {"error": "Не удалось подключиться к Telegram"}

    try:
        if step == "init":
            # Отправляем запрос кода и получаем phone_code_hash
            result = await client.send_code_request(phone)
            return {
                "step": "code",
                "message": "Код отправлен",
                "phone_code_hash": result.phone_code_hash
            }

        elif step == "code":
            # Используем полученный phone_code_hash
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                return {"step": "password", "message": "Требуется пароль 2FA"}
            except PhoneCodeInvalidError:
                return {"error": "Неверный код подтверждения"}
            except PhoneCodeExpiredError:
                return {"error": "Код истёк, запросите новый"}
            except FloodWaitError as e:
                return {"error": f"Слишком много попыток. Подождите {e.seconds} сек."}
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
                return {"error": f"Ошибка при вводе пароля: {str(e)}"}

        else:
            return {"error": "Неизвестный шаг"}

    except FloodWaitError as e:
        return {"error": f"FloodWait: подождите {e.seconds} сек."}
    except Exception as e:
        return {"error": f"Ошибка: {str(e)}"}
    finally:
        if client.is_connected():
            await client.disconnect()

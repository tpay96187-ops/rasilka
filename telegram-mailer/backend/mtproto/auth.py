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
import asyncio

async def add_telegram_account(api_id: int, api_hash: str, phone: str, code: str = None, password: str = None, step: str = "init"):
    """
    Пошаговая авторизация Telegram-аккаунта через MTProto.
    step может быть: 'init', 'code', 'password'.
    """
    session_path = f"sessions/{phone}.session"

    # Создаём клиента с реалистичными параметрами устройства (имитируем Android)
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

    # Проверка, что соединение установлено
    if not client.is_connected():
        return {"error": "Не удалось подключиться к Telegram"}

    try:
        if step == "init":
            # Отправляем запрос кода
            await client.send_code_request(phone)
            return {"step": "code", "message": "Код подтверждения отправлен"}

        elif step == "code":
            # Пытаемся войти с полученным кодом
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                # Требуется 2FA пароль
                return {"step": "password", "message": "Требуется пароль двухфакторной аутентификации"}
            except PhoneCodeInvalidError:
                return {"error": "Неверный код подтверждения"}
            except PhoneCodeExpiredError:
                return {"error": "Код истёк, запросите новый"}
            except FloodWaitError as e:
                return {"error": f"Слишком много попыток. Подождите {e.seconds} секунд."}
            else:
                # Успешная авторизация
                me = await client.get_me()
                await save_account(
                    name=me.first_name or me.username or phone,
                    phone=phone,
                    api_id=api_id,
                    api_hash=encrypt_value(api_hash),
                    session_file=session_path,
                    is_valid=True
                )
                await notify_admin(f"✅ Аккаунт {me.first_name} ({phone}) успешно добавлен")
                await client.disconnect()
                return {"step": "done", "account": me}

        elif step == "password":
            # Ввод 2FA пароля
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
            return {"error": "Неизвестный шаг авторизации"}

    except FloodWaitError as e:
        return {"error": f"FloodWait: подождите {e.seconds} секунд"}
    except Exception as e:
        return {"error": f"Ошибка: {str(e)}"}
    finally:
        if client.is_connected():
            await client.disconnect()

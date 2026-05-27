from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
from backend.database import get_user_role, is_user_active

class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        
        if user_id:
            role = await get_user_role(user_id)
            if not role or not await is_user_active(user_id):
                if isinstance(event, Message):
                    await event.answer("❌ Доступ запрещён")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ Доступ запрещён", show_alert=True)
                return
        
        return await handler(event, data)
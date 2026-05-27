from backend.database import get_account, increment_daily_sent

async def can_send(account_id: int) -> bool:
    acc = await get_account(account_id)
    if not acc:
        return False
    if acc.daily_limit and acc.daily_sent >= acc.daily_limit:
        return False
    return True

async def record_send(account_id: int):
    await increment_daily_sent(account_id)
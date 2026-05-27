from celery import shared_task
from backend.database import clear_old_logs, reset_daily_limits
import asyncio

@shared_task
def cleanup_old_logs(days=30):
    asyncio.run(clear_old_logs(days))

@shared_task
def reset_daily_counters():
    asyncio.run(reset_daily_limits())

from celery import shared_task
from backend.database import clear_old_logs, reset_daily_limits
from datetime import timedelta, datetime

@shared_task
def cleanup_old_logs(days=30):
    # Удаляем логи старше 30 дней
    pass

@shared_task
def reset_daily_counters():
    # Сбрасываем daily_sent для всех аккаунтов
    pass
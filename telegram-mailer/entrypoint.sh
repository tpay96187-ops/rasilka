#!/bin/bash
set -e

# Инициализация базы данных (создание таблиц, суперадмина)
python -c "from backend.database import init_db; import asyncio; asyncio.run(init_db())"

case "$1" in
    bot)
        echo "Starting Telegram Bot..."
        exec python -m backend.main
        ;;
    worker)
        echo "Starting Celery Worker..."
        exec celery -A backend.tasks.celery_app worker --loglevel=info --concurrency=2
        ;;
    beat)
        echo "Starting Celery Beat..."
        exec celery -A backend.tasks.celery_app beat --loglevel=info
        ;;
    *)
        echo "Usage: $0 {bot|worker|beat}"
        exit 1
        ;;
esac

#!/bin/bash
set -e

# Ожидание PostgreSQL
echo "Waiting for PostgreSQL..."
while ! nc -z db 5432; do
    sleep 0.5
done
echo "PostgreSQL started"

# Ожидание Redis
while ! nc -z redis 6379; do
    sleep 0.5
done
echo "Redis started"

# Инициализация БД (создание таблиц и суперадмина)
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

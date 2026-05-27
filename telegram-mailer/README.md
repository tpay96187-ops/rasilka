# Telegram Mailer System

## Требования
- Docker, Docker Compose
- Telegram Bot Token (от @BotFather)
- API ID и API Hash (my.telegram.org)

## Быстрый старт
1. Клонировать репозиторий
2. Скопировать `.env.example` в `.env` и заполнить (BOT_TOKEN, SUPERADMIN_ID, ENCRYPTION_KEY)
3. Запустить: `docker-compose up -d`
4. Написать `/start` вашему боту

## Команды бота
- `/start` – главное меню
- `/add_account` – добавить аккаунт
- `/new_template` – создать шаблон
- `/new_campaign` – создать рассылку
- `/report` – сформировать отчёт

## Мониторинг
- Логи: `docker-compose logs backend`
- Сессии хранятся в `./sessions/` (зашифрованы)
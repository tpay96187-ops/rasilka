import asyncio
import logging
from datetime import datetime, timedelta
from backend.database import (
    get_campaign, get_campaign_accounts, get_campaign_groups, get_template,
    update_campaign, log_mailing, get_account, increment_daily_sent, set_flood_wait, set_spam_block
)
from backend.mtproto.messenger import send_message_to_group
from backend.mtproto.group_fetcher import get_group_entity_by_id
from backend.services.notification import notify_admin

logger = logging.getLogger(__name__)

async def run_campaign(campaign_id: int):
    """Фоновая задача для выполнения рассылки с цикличностью до дневного лимита"""
    logger.info(f"Запущена рассылка #{campaign_id}")
    campaign = await get_campaign(campaign_id)
    if not campaign or campaign.status != "running":
        logger.warning(f"Рассылка #{campaign_id} не найдена или не в статусе running")
        return

    accounts = await get_campaign_accounts(campaign_id)
    groups = await get_campaign_groups(campaign_id)
    template = await get_template(campaign.template_id)

    if not template or not template.is_active:
        logger.error(f"Рассылка #{campaign_id}: шаблон не активен или не найден")
        await update_campaign(campaign_id, status="stopped")
        await notify_admin(f"❌ Рассылка #{campaign_id} остановлена: шаблон не активен")
        return

    daily_limit = campaign.daily_limit  # 0 = без лимита
    total_sent_this_run = 0

    # Основной цикл рассылки
    while True:
        # Проверяем лимит рассылки
        if daily_limit > 0 and total_sent_this_run >= daily_limit:
            logger.info(f"Рассылка #{campaign_id} достигла дневного лимита {daily_limit}, завершаем")
            await update_campaign(campaign_id, status="completed")
            await notify_admin(f"✅ Рассылка #{campaign_id} завершена: достигнут дневной лимит ({daily_limit} сообщений)")
            break

        # Проверяем, не была ли кампания остановлена или поставлена на паузу
        campaign = await get_campaign(campaign_id)
        if campaign.status != "running":
            logger.info(f"Рассылка #{campaign_id} остановлена (статус {campaign.status})")
            break

        # Перебираем аккаунты и группы
        any_message_sent = False
        for account in accounts:
            # Проверяем лимит аккаунта
            acc = await get_account(account.id)
            if acc.daily_limit and acc.daily_sent >= acc.daily_limit:
                logger.warning(f"Аккаунт {account.id} превысил дневной лимит, пропускаем")
                continue

            for group in groups:
                # Проверяем, не превышен ли лимит рассылки во время цикла
                if daily_limit > 0 and total_sent_this_run >= daily_limit:
                    break

                # Проверяем лимит аккаунта
                acc = await get_account(account.id)
                if acc.daily_limit and acc.daily_sent >= acc.daily_limit:
                    break

                group_entity = await get_group_entity_by_id(account.id, group.group_id)
                if not group_entity:
                    logger.error(f"Не удалось получить entity для группы {group.id}")
                    continue

                result = await send_message_to_group(
                    account_id=account.id,
                    group_entity=group_entity,
                    message_text=template.content,
                    campaign_id=campaign_id,
                    db_group_id=group.id
                )

                if result.get("error"):
                    if result["error"] == "floodwait":
                        wait_seconds = result.get("wait_seconds", 60)
                        # Останавливаем рассылку, уведомляем админов
                        await update_campaign(campaign_id, status="paused")
                        await notify_admin(
                            f"⚠️ Рассылка #{campaign_id} остановлена из-за FloodWait\n"
                            f"Аккаунт {account.phone}\n"
                            f"Ожидание {wait_seconds} секунд (до {datetime.now() + timedelta(seconds=wait_seconds)})\n"
                            f"Запустите рассылку вручную после снятия ограничения."
                        )
                        logger.warning(f"Рассылка #{campaign_id} остановлена FloodWait на {wait_seconds} сек")
                        return  # Выходим из задачи

                    elif result["error"] == "spamblock":
                        # Устанавливаем метку SpamBlock для аккаунта
                        await set_spam_block(account.id, True)
                        await update_campaign(campaign_id, status="stopped")
                        await notify_admin(
                            f"🚫 Рассылка #{campaign_id} остановлена из-за SpamBlock\n"
                            f"Аккаунт {account.phone} заблокирован за спам.\n"
                            f"Проверьте аккаунт через @SpamBot и снимите блокировку вручную."
                        )
                        logger.error(f"Рассылка #{campaign_id} остановлена SpamBlock для аккаунта {account.id}")
                        return

                    elif result["error"] == "peerflood":
                        await update_campaign(campaign_id, status="paused")
                        await notify_admin(
                            f"⚠️ Рассылка #{campaign_id} остановлена из-за PeerFlood\n"
                            f"Аккаунт {account.phone} помечен как рискованный.\n"
                            f"Проверьте аккаунт."
                        )
                        return

                    else:
                        # Другие ошибки (invalid_account, rate_limit, etc.)
                        logger.error(f"Ошибка отправки: {result['error']}")
                        await asyncio.sleep(campaign.message_interval)
                        continue
                else:
                    # Успешная отправка
                    any_message_sent = True
                    total_sent_this_run += 1
                    await increment_daily_sent(account.id)
                    logger.info(f"Отправлено {total_sent_this_run}/{daily_limit if daily_limit>0 else '∞'}")

                await asyncio.sleep(campaign.message_interval)

            if daily_limit > 0 and total_sent_this_run >= daily_limit:
                break

        if not any_message_sent:
            # Если за весь цикл не было отправлено ни одного сообщения (все аккаунты на лимите или ошибки)
            logger.warning(f"Рассылка #{campaign_id}: за цикл не отправлено ни одного сообщения. Завершаем.")
            await update_campaign(campaign_id, status="completed")
            await notify_admin(f"⚠️ Рассылка #{campaign_id} завершена: нет доступных аккаунтов или групп")
            break

        # Пауза между циклами
        await asyncio.sleep(campaign.cycle_interval)

    # Финальное уведомление
    if campaign.status == "running":
        await update_campaign(campaign_id, status="completed")
        await notify_admin(f"✅ Рассылка #{campaign_id} успешно завершена. Отправлено {total_sent_this_run} сообщений.")

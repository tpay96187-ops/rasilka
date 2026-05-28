from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from sqlalchemy import case, select, update, delete, func, and_, or_
from backend.models import Base, User, Account, Template, Group, Campaign, CampaignAccount, CampaignGroup, MailingLog, FloodWaitLog, AdminActionLog
from backend.config import async def get_campaign_stats_by_group
from typing import List, Optional, Dict, Any
import asyncio

# Приводим DATABASE_URL к виду, подходящему для asyncpg
database_url = settings.database_url
if database_url and database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(database_url, echo=False, pool_size=10, max_overflow=20)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_superadmin()

async def ensure_superadmin():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == settings.superadmin_id))
        user = result.scalar_one_or_none()
        if not user:
            superadmin = User(
                telegram_id=settings.superadmin_id,
                username="superadmin",
                role="superadmin",
                is_active=True
            )
            session.add(superadmin)
            await session.commit()

# --- Роли и пользователи ---
async def get_user_role(telegram_id: int) -> Optional[str]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id, User.is_active == True))
        user = result.scalar_one_or_none()
        return user.role if user else None

async def is_user_active(telegram_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        return user.is_active if user else False

async def get_all_admins() -> List[User]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.role.in_(["admin", "superadmin"])))
        return result.scalars().all()

async def add_admin(telegram_id: int, username: str, role: str = "admin") -> bool:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(User).where(User.telegram_id == telegram_id))
        if existing.scalar_one_or_none():
            return False
        user = User(telegram_id=telegram_id, username=username, role=role)
        session.add(user)
        await session.commit()
        return True

async def remove_admin(telegram_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user.scalar_one_or_none()
        if user and user.telegram_id != settings.superadmin_id:
            await session.delete(user)
            await session.commit()
            return True
        return False

async def block_admin(telegram_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = user.scalar_one_or_none()
        if user and user.telegram_id != settings.superadmin_id:
            user.is_active = False
            await session.commit()
            return True
        return False

async def log_admin_action(telegram_id: int, action: str, target_type: str = None, target_id: int = None):
    async with AsyncSessionLocal() as session:
        log = AdminActionLog(
            user_telegram_id=telegram_id,
            action=action,
            target_type=target_type,
            target_id=target_id
        )
        session.add(log)
        await session.commit()

# --- Аккаунты ---
async def get_accounts() -> List[Account]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account))
        return result.scalars().all()

async def get_account(account_id: int) -> Optional[Account]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.id == account_id))
        return result.scalar_one_or_none()

async def get_account_by_phone(phone: str) -> Optional[Account]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.phone == phone))
        return result.scalar_one_or_none()

async def save_account(name: str, phone: str, api_id: int, api_hash: str, session_file: str, is_valid: bool) -> Account:
    async with AsyncSessionLocal() as session:
        # Проверяем, существует ли уже
        existing = await session.execute(select(Account).where(Account.phone == phone))
        acc = existing.scalar_one_or_none()
        if acc:
            # Обновляем существующий
            acc.name = name
            acc.api_id = api_id
            acc.api_hash = api_hash
            acc.session_file = session_file
            acc.is_valid = is_valid
            acc.last_activity = datetime.utcnow()
        else:
            acc = Account(
                name=name,
                phone=phone,
                api_id=api_id,
                api_hash=api_hash,
                session_file=session_file,
                is_valid=is_valid,
                last_activity=datetime.utcnow()
            )
            session.add(acc)
        await session.commit()
        await session.refresh(acc)
        return acc

async def update_account_session(account_id: int, session_file: str, is_valid: bool):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Account).where(Account.id == account_id).values(
                session_file=session_file, is_valid=is_valid, last_activity=datetime.utcnow()
            )
        )
        await session.commit()

async def delete_account(account_id: int):
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Account).where(Account.id == account_id))
        await session.commit()

async def set_flood_wait(account_id: int, wait_seconds: int):
    until = datetime.utcnow() + timedelta(seconds=wait_seconds)
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Account).where(Account.id == account_id).values(flood_wait_until=until)
        )
        log = FloodWaitLog(account_id=account_id, wait_seconds=wait_seconds)
        session.add(log)
        await session.commit()

async def set_spam_block(account_id: int, blocked: bool):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Account).where(Account.id == account_id).values(spam_blocked=blocked)
        )
        await session.commit()

async def increment_daily_sent(account_id: int):
    async with AsyncSessionLocal() as session:
        acc = await session.get(Account, account_id)
        if acc.last_reset_date.date() < datetime.utcnow().date():
            acc.daily_sent = 0
            acc.last_reset_date = datetime.utcnow()
        acc.daily_sent += 1
        await session.commit()

# --- Шаблоны ---
async def get_templates(active_only: bool = False) -> List[Template]:
    async with AsyncSessionLocal() as session:
        query = select(Template)
        if active_only:
            query = query.where(Template.is_active == True)
        result = await session.execute(query)
        return result.scalars().all()

async def get_template(template_id: int) -> Optional[Template]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Template).where(Template.id == template_id))
        return result.scalar_one_or_none()

async def create_template(name: str, content: str, created_by: int) -> Template:
    async with AsyncSessionLocal() as session:
        tmpl = Template(name=name, content=content, created_by=created_by)
        session.add(tmpl)
        await session.commit()
        await session.refresh(tmpl)
        return tmpl

async def update_template(template_id: int, name: str = None, content: str = None, is_active: bool = None):
    async with AsyncSessionLocal() as session:
        data = {}
        if name is not None:
            data["name"] = name
        if content is not None:
            data["content"] = content
        if is_active is not None:
            data["is_active"] = is_active
        await session.execute(update(Template).where(Template.id == template_id).values(**data))
        await session.commit()

async def delete_template(template_id: int):
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Template).where(Template.id == template_id))
        await session.commit()

# --- Группы ---
async def get_groups(account_id: int = None) -> List[Group]:
    async with AsyncSessionLocal() as session:
        if account_id:
            result = await session.execute(select(Group).where(Group.account_id == account_id))
        else:
            result = await session.execute(select(Group))
        return result.scalars().all()

async def save_group(group_data: dict, account_id: int) -> Group:
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(Group).where(Group.group_id == group_data["id"], Group.account_id == account_id)
        )
        group = existing.scalar_one_or_none()
        if group:
            group.title = group_data.get("title", "Unknown")
            group.username = group_data.get("username")
            group.invite_link = group_data.get("invite_link")
            group.group_type = group_data.get("type", "group")
            group.participants_count = group_data.get("participants_count", 0)   # ДОБАВИТЬ
        else:
            group = Group(
                group_id=group_data["id"],
                title=group_data.get("title", "Unknown"),
                username=group_data.get("username"),
                invite_link=group_data.get("invite_link"),
                group_type=group_data.get("type", "group"),
                account_id=account_id,
                participants_count=group_data.get("participants_count", 0)   # ДОБАВИТЬ
            )
            session.add(group)
        await session.commit()
        await session.refresh(group)
        return group

async def clear_account_groups(account_id: int):
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Group).where(Group.account_id == account_id))
        await session.commit()

# --- Кампании ---
async def get_campaigns(status: str = None) -> List[Campaign]:
    async with AsyncSessionLocal() as session:
        query = select(Campaign)
        if status:
            query = query.where(Campaign.status == status)
        result = await session.execute(query)
        return result.scalars().all()

async def get_campaign(campaign_id: int) -> Optional[Campaign]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
        return result.scalar_one_or_none()

async def create_campaign(name: str, template_id: int, message_interval: int, cycle_interval: int, daily_limit: int) -> Campaign:
    async with AsyncSessionLocal() as session:
        camp = Campaign(
            name=name,
            template_id=template_id,
            message_interval=message_interval,
            cycle_interval=cycle_interval,
            daily_limit=daily_limit
        )
        session.add(camp)
        await session.commit()
        await session.refresh(camp)
        return camp

async def update_campaign(campaign_id: int, **kwargs):
    async with AsyncSessionLocal() as session:
        await session.execute(update(Campaign).where(Campaign.id == campaign_id).values(**kwargs))
        await session.commit()

async def delete_campaign(campaign_id: int):
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Campaign).where(Campaign.id == campaign_id))
        await session.commit()

async def add_account_to_campaign(campaign_id: int, account_id: int):
    async with AsyncSessionLocal() as session:
        ca = CampaignAccount(campaign_id=campaign_id, account_id=account_id)
        session.add(ca)
        await session.commit()

async def add_group_to_campaign(campaign_id: int, group_id: int):
    async with AsyncSessionLocal() as session:
        cg = CampaignGroup(campaign_id=campaign_id, group_id=group_id)
        session.add(cg)
        await session.commit()

async def get_campaign_accounts(campaign_id: int) -> List[Account]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Account).join(CampaignAccount).where(CampaignAccount.campaign_id == campaign_id)
        )
        return result.scalars().all()

async def get_campaign_groups(campaign_id: int) -> List[Group]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Group).join(CampaignGroup).where(CampaignGroup.campaign_id == campaign_id)
        )
        return result.scalars().all()

async def update_campaign_stats(campaign_id: int, success: bool):
    async with AsyncSessionLocal() as session:
        camp = await session.get(Campaign, campaign_id)
        if camp:
            camp.total_sent += 1
            if success:
                camp.total_success += 1
            else:
                camp.total_failed += 1
            await session.commit()

async def log_mailing(campaign_id: int, account_id: int, group_id: int, success: bool, error_type: str = None, error_detail: str = None):
    async with AsyncSessionLocal() as session:
        log = MailingLog(
            campaign_id=campaign_id,
            account_id=account_id,
            group_id=group_id,
            success=success,
            error_type=error_type,
            error_detail=error_detail
        )
        session.add(log)
        await session.commit()
    await update_campaign_stats(campaign_id, success)

# --- Статистика для отчётов ---
async def get_campaign_stats_by_group(campaign_id: int) -> List[dict]:
    async with AsyncSessionLocal() as session:
        query = text("""
            SELECT g.title, g.group_id, g.invite_link,
                   COUNT(ml.id) AS attempts,
                   SUM(CASE WHEN ml.success THEN 1 ELSE 0 END) AS success,
                   SUM(CASE WHEN NOT ml.success THEN 1 ELSE 0 END) AS failed
            FROM mailing_logs ml
            JOIN groups g ON g.id = ml.group_id
            WHERE ml.campaign_id = :campaign_id
            GROUP BY g.id
        """)
        result = await session.execute(query, {"campaign_id": campaign_id})
        rows = result.fetchall()
        output = []
        for row in rows:
            attempts = row[3] or 0
            success = row[4] or 0
            failed = row[5] or 0
            success_pct = (success / attempts * 100) if attempts > 0 else 0
            error_pct = (failed / attempts * 100) if attempts > 0 else 0
            output.append([
                row[0] or "", row[1] or 0, row[2] or "",
                attempts, success, failed,
                round(success_pct, 2), round(error_pct, 2),
                0
            ])
        return output

async def get_campaign_stats_by_account(campaign_id: int) -> List[dict]:
    async with AsyncSessionLocal() as session:
        query = text("""
            SELECT a.name, a.phone,
                   COUNT(DISTINCT ml.group_id) AS groups_count,
                   COUNT(ml.id) AS attempts,
                   SUM(CASE WHEN ml.success THEN 1 ELSE 0 END) AS success,
                   SUM(CASE WHEN NOT ml.success THEN 1 ELSE 0 END) AS failed
            FROM mailing_logs ml
            JOIN accounts a ON a.id = ml.account_id
            WHERE ml.campaign_id = :campaign_id
            GROUP BY a.id
        """)
        result = await session.execute(query, {"campaign_id": campaign_id})
        rows = result.fetchall()
        output = []
        for row in rows:
            attempts = row[3] or 0
            success = row[4] or 0
            failed = row[5] or 0
            groups_count = row[2] or 0
            success_pct = (success / attempts * 100) if attempts > 0 else 0
            error_pct = (failed / attempts * 100) if attempts > 0 else 0
            output.append([
                row[0] or "", row[1] or "",
                groups_count, attempts, success, failed,
                round(success_pct, 2), round(error_pct, 2)
            ])
        return output

async def get_campaign_stats_by_account(campaign_id: int) -> List[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                Account.name,
                Account.phone,
                func.count(func.distinct(MailingLog.group_id)).label("groups_count"),
                func.count(MailingLog.id).label("attempts"),
                func.sum(case((MailingLog.success == True, 1), else_=0)).label("success"),
                func.sum(case((MailingLog.success == False, 1), else_=0)).label("failed")
            )
            .join(MailingLog, MailingLog.account_id == Account.id)
            .where(MailingLog.campaign_id == campaign_id)
            .group_by(Account.id)
        )
        rows = result.all()
        output = []
        for row in rows:
            attempts = int(row.attempts) if row.attempts is not None else 0
            success = int(row.success) if row.success is not None else 0
            failed = int(row.failed) if row.failed is not None else 0
            groups_count = int(row.groups_count) if row.groups_count is not None else 0
            success_pct = (success / attempts * 100) if attempts > 0 else 0
            error_pct = (failed / attempts * 100) if attempts > 0 else 0
            output.append([
                str(row.name) if row.name else "",
                str(row.phone) if row.phone else "",
                groups_count,
                attempts,
                success,
                failed,
                round(success_pct, 2),
                round(error_pct, 2)
            ])
        return output
# --- Очистка логов и сброс лимитов ---
async def clear_old_logs(days: int = 30):
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        await session.execute(delete(MailingLog).where(MailingLog.sent_at < cutoff))
        await session.execute(delete(FloodWaitLog).where(FloodWaitLog.occurred_at < cutoff))
        await session.execute(delete(AdminActionLog).where(AdminActionLog.timestamp < cutoff))
        await session.commit()

async def reset_daily_limits():
    async with AsyncSessionLocal() as session:
        await session.execute(update(Account).values(daily_sent=0, last_reset_date=datetime.utcnow()))
        await session.commit()

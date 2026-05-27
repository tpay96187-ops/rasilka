from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, BigInteger, Float, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255))
    role = Column(String(50), default="admin")   # superadmin, admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Связи (действия логируются отдельно)
    actions = relationship("AdminActionLog", back_populates="user")

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    phone = Column(String(50), unique=True, index=True)
    api_id = Column(Integer, nullable=False)
    api_hash = Column(String(255), nullable=False)   # зашифрован
    session_file = Column(String(255))
    is_valid = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    flood_wait_until = Column(DateTime, nullable=True)
    spam_blocked = Column(Boolean, default=False)
    peer_flood_risk = Column(Boolean, default=False)
    last_activity = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    daily_sent = Column(Integer, default=0)
    last_reset_date = Column(DateTime, default=datetime.utcnow)

    groups = relationship("Group", back_populates="account", cascade="all, delete-orphan")
    campaign_accounts = relationship("CampaignAccount", back_populates="account", cascade="all, delete-orphan")
    logs = relationship("MailingLog", back_populates="account")
    flood_logs = relationship("FloodWaitLog", back_populates="account")

class Template(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    content = Column(Text)
    is_active = Column(Boolean, default=True)
    created_by = Column(BigInteger)   # telegram_id admin
    created_at = Column(DateTime, default=datetime.utcnow)

    campaigns = relationship("Campaign", back_populates="template")

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True)
    group_id = Column(BigInteger)   # Telegram chat_id
    title = Column(String(500))
    username = Column(String(255))
    invite_link = Column(String(500))
    group_type = Column(String(50))
    access_available = Column(Boolean, default=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"))
    
    account = relationship("Account", back_populates="groups")
    campaign_groups = relationship("CampaignGroup", back_populates="group", cascade="all, delete-orphan")
    logs = relationship("MailingLog", back_populates="group")

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    template_id = Column(Integer, ForeignKey("templates.id"))
    message_interval = Column(Integer, default=30)
    cycle_interval = Column(Integer, default=300)
    daily_limit = Column(Integer, default=0)
    status = Column(String(50), default="draft")   # draft, running, paused, stopped, completed
    total_sent = Column(Integer, default=0)
    total_success = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)

    template = relationship("Template", back_populates="campaigns")
    campaign_accounts = relationship("CampaignAccount", back_populates="campaign", cascade="all, delete-orphan")
    campaign_groups = relationship("CampaignGroup", back_populates="campaign", cascade="all, delete-orphan")
    logs = relationship("MailingLog", back_populates="campaign")

class CampaignAccount(Base):
    __tablename__ = "campaign_accounts"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"))
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"))

    campaign = relationship("Campaign", back_populates="campaign_accounts")
    account = relationship("Account", back_populates="campaign_accounts")

class CampaignGroup(Base):
    __tablename__ = "campaign_groups"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"))
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))

    campaign = relationship("Campaign", back_populates="campaign_groups")
    group = relationship("Group", back_populates="campaign_groups")

class MailingLog(Base):
    __tablename__ = "mailing_logs"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    account_id = Column(Integer, ForeignKey("accounts.id"))
    group_id = Column(Integer, ForeignKey("groups.id"))
    success = Column(Boolean)
    error_type = Column(String(100))
    error_detail = Column(Text)
    sent_at = Column(DateTime, default=datetime.utcnow, index=True)

    campaign = relationship("Campaign", back_populates="logs")
    account = relationship("Account", back_populates="logs")
    group = relationship("Group", back_populates="logs")

class FloodWaitLog(Base):
    __tablename__ = "floodwait_logs"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    wait_seconds = Column(Integer)
    occurred_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    account = relationship("Account", back_populates="flood_logs")

class AdminActionLog(Base):
    __tablename__ = "admin_action_logs"
    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(BigInteger, ForeignKey("users.telegram_id"))
    action = Column(String(255))
    target_type = Column(String(50))   # account, template, campaign, etc.
    target_id = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(45), nullable=True)

    user = relationship("User", back_populates="actions")

# Индексы для производительности
Index('ix_mailing_logs_campaign_id', MailingLog.campaign_id)
Index('ix_mailing_logs_account_id', MailingLog.account_id)
Index('ix_floodwait_logs_account_id', FloodWaitLog.account_id)
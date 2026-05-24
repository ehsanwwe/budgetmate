from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, JSON, String
from app.db import Base


class TokenWallet(Base):
    __tablename__ = "token_wallets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    balance_tokens = Column(Integer, default=0, nullable=False)
    total_granted_tokens = Column(Integer, default=0, nullable=False)
    total_purchased_tokens = Column(Integer, default=0, nullable=False)
    total_consumed_tokens = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TokenUsageLog(Base):
    __tablename__ = "token_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    chat_message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    provider = Column(String, nullable=True)
    model = Column(String, nullable=True)
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    balance_before = Column(Integer, default=0, nullable=False)
    balance_after = Column(Integer, default=0, nullable=False)
    reason = Column(String, default="chat", nullable=False)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TokenPurchase(Base):
    __tablename__ = "token_purchases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    plan_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    amount_toman = Column(BigInteger, nullable=False)
    tokens_added = Column(Integer, default=0, nullable=False)
    status = Column(String, default="mock_paid", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    meta = Column(JSON, nullable=True)


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    status = Column(String, default="active", nullable=False)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=True)
    monthly_token_quota = Column(Integer, default=0, nullable=False)
    tokens_granted = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

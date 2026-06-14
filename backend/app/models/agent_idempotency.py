from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text

from app.db import Base


class AgentOperationEvent(Base):
    """Idempotency log for agent write operations.

    Prevents duplicate INSERTs/UPDATEs when chat history is replayed
    or the same operation is triggered multiple times within a turn.
    """

    __tablename__ = "agent_operation_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    operation_fingerprint = Column(String(64), nullable=False, index=True)
    operation_type = Column(String(20), nullable=False)
    table_name = Column(String(80), nullable=False)
    target_record_id = Column(Integer, nullable=True)
    status = Column(String(30), nullable=False, default="executed")
    payload_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_agent_op_events_user_fp", "user_id", "operation_fingerprint"),
    )


class PendingAgentIntent(Base):
    """Stores user intents that require a follow-up answer to complete.

    Example: user says "I want to buy rings next month" → AI asks for amount →
    intent stored with status=pending → user replies "200 million" →
    intent consumed to complete the INSERT.
    """

    __tablename__ = "pending_agent_intents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    intent_type = Column(String(80), nullable=False)
    payload_json = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    source_message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    consumed_at = Column(DateTime, nullable=True)

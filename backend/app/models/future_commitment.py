from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, JSON, String, Text

from app.db import Base


class FutureCommitment(Base):
    __tablename__ = "future_commitments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    amount = Column(BigInteger, nullable=False)
    due_date = Column(Date, nullable=True, index=True)
    due_month = Column(String, nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    related_transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    related_goal_id = Column(Integer, ForeignKey("goals.id"), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending", index=True)
    source = Column(String, nullable=False, default="chat")
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

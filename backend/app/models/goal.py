from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, JSON, String
from app.db import Base


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    target_amount = Column(BigInteger, nullable=False)
    current_amount = Column(BigInteger, default=0)
    deadline = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="active", index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    notes_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

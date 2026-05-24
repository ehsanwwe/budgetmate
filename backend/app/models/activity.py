from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from app.db import Base


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

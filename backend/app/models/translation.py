from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint
from app.db import Base


class TranslationEntry(Base):
    __tablename__ = "translation_entries"

    id = Column(Integer, primary_key=True, index=True)
    namespace = Column(String, nullable=False, index=True)
    key = Column(String, nullable=False, index=True)
    locale = Column(String, nullable=False, index=True)
    value = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_user_id = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("locale", "namespace", "key", name="uq_translation_locale_ns_key"),
    )

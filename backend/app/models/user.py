from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    is_blocked = Column(Boolean, default=False)
    language = Column(String, default="fa")
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def display_name(self) -> str | None:
        full_name = " ".join(part for part in [self.first_name, self.last_name] if part)
        return full_name or self.name

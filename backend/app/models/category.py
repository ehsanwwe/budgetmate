from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from app.db import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    icon = Column(String, default="📦")
    color = Column(String, default="#B0BEC5")
    is_default = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

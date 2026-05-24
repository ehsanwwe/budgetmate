from sqlalchemy import BigInteger, Column, Date, ForeignKey, Integer, String
from app.db import Base


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    target_amount = Column(BigInteger, nullable=False)
    current_amount = Column(BigInteger, default=0)
    deadline = Column(Date, nullable=True)

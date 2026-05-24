from datetime import datetime, date
from sqlalchemy import BigInteger, Column, Date, DateTime, Enum, ForeignKey, Integer, String
import enum
from app.db import Base


class TransactionType(str, enum.Enum):
    expense = "expense"
    income = "income"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    amount = Column(BigInteger, nullable=False)
    type = Column(Enum(TransactionType), nullable=False, default=TransactionType.expense)
    description = Column(String, nullable=True)
    date = Column(Date, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)

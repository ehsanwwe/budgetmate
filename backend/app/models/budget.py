from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, UniqueConstraint
from app.db import Base


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    amount = Column(BigInteger, default=0)
    currency = Column(String, default="تومان")

    __table_args__ = (UniqueConstraint("user_id", "month", "year", name="uq_budget_user_month_year"),)

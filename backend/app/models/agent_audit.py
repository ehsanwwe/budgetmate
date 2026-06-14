from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text

from app.db import Base


class AgentSqlAuditLog(Base):
    __tablename__ = "agent_sql_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    intent = Column(String, nullable=True)
    operation_type = Column(String, nullable=False)
    table_name = Column(String, nullable=True)
    planned_sql = Column(Text, nullable=True)
    params_json = Column(JSON, nullable=True)
    validation_status = Column(String, nullable=False)
    rejected_reason = Column(Text, nullable=True)
    executed = Column(Boolean, default=False, nullable=False)
    result_summary_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

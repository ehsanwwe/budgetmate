import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.core.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.db import Base
from app.models.user import User
from app.models.admin import AdminUser
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.goal import Goal
from app.models.chat import ChatMessage
from app.models.activity import ActivityLog
from app.models.agent_audit import AgentSqlAuditLog
from app.models.personal_cfo import (
    BehaviorInsight,
    FinancialDecisionLog,
    FinancialFact,
    FinancialMemory,
    FinancialPersona,
    FinancialWarning,
    PersonaUpdateLog,
)
from app.models.billing import TokenWallet, TokenUsageLog, TokenPurchase, UserSubscription

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

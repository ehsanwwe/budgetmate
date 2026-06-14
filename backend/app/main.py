import os
import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure app package is importable when run from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.db import engine, SessionLocal, Base
from app.core.seed import seed_db
from app.routers import health, auth, users, budgets, categories, transactions, goals, chat, admin, billing, onboarding, personal_cfo, future_commitments
from app.services.ai import log_ai_provider_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Import models to ensure they are registered with Base.metadata
    from app.models import User, AdminUser, Budget, Category, Transaction, Goal, FutureCommitment, ChatMessage, ActivityLog, AgentSqlAuditLog, FinancialPersona, FinancialMemory, BehaviorInsight, PersonaUpdateLog, FinancialFact, FinancialWarning, FinancialDecisionLog, TokenWallet, TokenUsageLog, TokenPurchase, UserSubscription
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    db = SessionLocal()
    try:
        seed_db(db)
        logger.info("Database seeded")
    finally:
        db.close()

    yield


app = FastAPI(
    title="BudgetMate API",
    description="بادجت‌میت — دستیار مالی شخصی",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

logger.info("CORS origins: %s", settings.cors_origins_list)
log_ai_provider_config()

PREFIX = "/api/v1"

app.include_router(health.router, prefix=PREFIX)
app.include_router(auth.router, prefix=PREFIX)
app.include_router(users.router, prefix=PREFIX)
app.include_router(budgets.router, prefix=PREFIX)
app.include_router(categories.router, prefix=PREFIX)
app.include_router(transactions.router, prefix=PREFIX)
app.include_router(goals.router, prefix=PREFIX)
app.include_router(chat.router, prefix=PREFIX)
app.include_router(admin.router, prefix=PREFIX)
app.include_router(billing.router, prefix=PREFIX)
app.include_router(onboarding.router, prefix=PREFIX)
app.include_router(personal_cfo.router, prefix=PREFIX)
app.include_router(future_commitments.router, prefix=PREFIX)

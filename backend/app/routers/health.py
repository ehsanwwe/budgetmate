import logging
from fastapi import APIRouter
from sqlalchemy import text
from app.db import engine

router = APIRouter()
logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = {
    "users": ["current_financial_status", "monthly_income", "preferred_currency", "chat_mode"],
}


def _check_schema() -> dict:
    missing: dict[str, list[str]] = {}
    try:
        with engine.connect() as conn:
            for table, cols in _REQUIRED_COLUMNS.items():
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                existing = {r[1] for r in rows}
                absent = [c for c in cols if c not in existing]
                if absent:
                    missing[table] = absent
                    logger.error(
                        "Schema drift detected — table=%s missing_columns=%s. "
                        "Run: python -m alembic upgrade head",
                        table,
                        absent,
                    )
    except Exception as exc:
        logger.error("Schema check failed: %s", exc)
        return {"schema_ok": False, "error": str(exc)}
    return {"schema_ok": not missing, "missing": missing}


def _alembic_revision() -> str | None:
    try:
        from alembic.runtime.migration import MigrationContext
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            return ctx.get_current_revision()
    except Exception:
        return None


@router.get("/health")
def health_check():
    schema = _check_schema()
    revision = _alembic_revision()
    ok = schema["schema_ok"]
    return {
        "status": "ok" if ok else "degraded",
        "schema_ok": ok,
        "schema_missing": schema.get("missing") or {},
        "alembic_revision": revision,
        "message": (
            "OK"
            if ok
            else "Database schema is behind code. Run: python -m alembic upgrade head"
        ),
    }

# BudgetMate — Build Progress

## What's Done ✅

### Backend (100% complete, all smoke tests passing)

**Infrastructure**
- `backend/app/db.py` — Single `Base = declarative_base()`, engine, SessionLocal, get_db
- `backend/app/core/config.py` — pydantic-settings reads `.env`
- `backend/app/core/auth.py` — JWT user + admin dependencies (separate scopes)
- `backend/app/core/seed.py` — Seeds admin + 10 default Persian categories on startup
- `backend/app/core/jalali.py` — Jalali calendar helpers (current month/year)
- `backend/.env` — All constants filled (JWT_SECRET generated, all env vars set)
- `backend/alembic/` — Alembic initialized, initial migration applied
- `backend/budgetmate.db` — SQLite DB with all tables created

**Models** (all in `backend/app/models/`)
- `user.py` — User (phone, name, is_blocked, language)
- `admin.py` — AdminUser (username, hashed_password)
- `budget.py` — Budget (user, month, year, amount, currency; UNIQUE constraint)
- `category.py` — Category (name, icon, color, is_default, user_id nullable)
- `transaction.py` — Transaction (expense/income enum, category, date)
- `goal.py` — Goal (title, target, current, deadline)
- `chat.py` — ChatMessage (user/assistant enum, content)
- `activity.py` — ActivityLog (action, meta JSON)

**Routers** (all mounted at `/api/v1`)
- `health.py` — GET /health
- `auth.py` — POST /auth/request-otp, /auth/verify-otp, /auth/admin/login
- `users.py` — GET/PATCH /users/me
- `budgets.py` — GET /budgets/current, POST /budgets, PUT /budgets/{id}
- `categories.py` — GET/POST /categories
- `transactions.py` — GET/POST/DELETE /transactions, GET /transactions/summary
- `goals.py` — Full CRUD + POST /goals/{id}/contribute
- `chat.py` — POST /chat/message, GET /chat/stream (SSE), GET/DELETE /chat/history
- `admin.py` — GET /admin/stats, GET/POST /admin/users (list, get, block, unblock), GET /admin/activity

**AI Service** (`backend/app/services/ai.py`)
- OpenClaw provider with 3 URL path fallbacks
- Ollama direct fallback
- Dynamic Persian system prompt with user's budget/spending context
- Model waterfall: PRIMARY_MODEL → FALLBACK_MODELS
- Persian fallback message if all providers fail

**Smoke Tests Results** ✅
- GET /api/v1/health → `{"status":"ok"}`
- POST /auth/request-otp → Persian message + hint
- POST /auth/verify-otp → JWT token + user object
- GET /users/me → user data
- POST /budgets → budget created
- POST /transactions → transaction created
- GET /transactions/summary → spending stats
- POST /auth/admin/login → admin JWT
- GET /admin/stats → platform stats

## What's Left ❌

### Frontend (not started)
- Next.js 14 app with Persian RTL layout
- Pages: Login (OTP), Dashboard, Transactions, Goals, Chat, Admin panel
- Tailwind CSS with RTL support
- Shamsi calendar date pickers
- AI chat UI with SSE streaming

## Exact Next Steps to Resume

1. **Start backend** (if not running):
   ```powershell
   cd D:\ai_agent\budgetmate\backend
   python -m uvicorn app.main:app --reload --port 8000
   ```

2. **Build frontend** — Next instruction to Claude:
   > Build the frontend for BudgetMate in `frontend/` using Next.js 14 + Tailwind CSS. RTL Persian layout. Pages: login (OTP flow), dashboard (budget overview, spending chart), transactions list + add form, goals page, AI chat with SSE, admin panel. Connect to backend at http://localhost:8000/api/v1. Auth via JWT in localStorage.

3. **Key backend URLs**:
   - Health: `http://localhost:8000/api/v1/health`
   - API docs: `http://localhost:8000/docs`
   - Admin login: username=`admin`, password=`5tgb%TGB`
   - OTP test code: `123456`

4. **Notes**:
   - passlib is incompatible with Python 3.13; using `bcrypt` directly
   - AI service uses OpenClaw at `http://188.136.214.220:18789`
   - If OpenClaw unreachable, set `AI_PROVIDER=ollama` in `.env`

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
- OpenAI-only active provider for chat/orchestrator planning
- Dynamic Persian system prompt with user's budget/spending context
- Model selected by `OPENAI_MODEL`
- Persian fallback message if all providers fail

### Frontend (100% complete, builds clean, dev server returns 200)

**Stack**: Next.js 16.2.6 + React 19 + TypeScript + Tailwind CSS v4

**Pages**
- `/login` — OTP flow (phone → 6-digit code boxes), test hint card
- `/dashboard` — 4 stat cards, Recharts pie + line charts, recent transactions
- `/transactions` — Filterable table, add dialog with form validation
- `/budget` — Current month budget with progress bar
- `/goals` — Goal cards with progress, create/contribute dialogs
- `/chat` — SSE streaming chat with AI advisor, typing indicator
- `/profile` — Edit name, logout
- `/blocked` — Full-screen blocked message
- `/admin` — Admin login
- `/admin/dashboard` — 5 stat cards, recent activity
- `/admin/users` — Paginated searchable table, block/unblock actions
- `/admin/users/[id]` — User detail: profile + transactions + activity

**Libraries**
- Vazirmatn font, Persian digits toFa(), toman() currency format
- Jalali dates via dayjs+jalaliday
- Zustand persisted auth store
- shadcn/ui components (hand-written due to network issue in init)
- axios with request/response interceptors for auth

## Smoke Tests ✅
- GET /api/v1/health → `{"status":"ok"}`
- POST /auth/request-otp → Persian message + hint
- POST /auth/verify-otp → JWT token + user object
- GET /users/me → user data
- Frontend at http://localhost:3000 → 200 OK

## Onboarding Redesign ✅ (2026-05-25)

### Backend additions
- User model: `family_name`, `birthdate`, `province`, `city`, `income_range`, `agreement_accepted_at`, `agreement_version`, `onboarding_completed`, `onboarding_completed_at`
- Alembic migration `003_extend_user_onboarding` applied
- New router `onboarding.py`: status, profile, agreement, complete endpoints
- Iran geo data: `backend/app/data/iran_geo.py` — 31 provinces, 5-10 cities each
- STT service `backend/app/services/stt.py` — OpenAI Whisper → safe error fallback
- `POST /chat/voice` — multipart audio transcription + AI reply
- `verify-otp` now returns `onboarding_completed` flag

### Frontend additions
- Auth store: added `onboardingCompleted` + `setOnboardingCompleted`
- Framer Motion installed for page transitions
- Shared: `PageTransition.tsx`, `OnboardingLayout.tsx`, `BgImageScreen.tsx`
- **New pages**: `/login` (welcome), `/login/phone`, `/login/otp`
- **New pages**: `/onboarding/profile`, `/onboarding/agreement`, `/onboarding/welcome`
- Chat redesigned: voice mode with Web Audio waveform, example chips, new dark-brown design
- Route guards: `(app)/layout.tsx` checks `onboardingCompleted`, `onboarding/layout.tsx` prevents re-onboarding

## What's Left ❌

### Docker & Deployment
- [ ] `docker-compose.yml` — backend + frontend containers
- [ ] Nginx reverse proxy config
- [ ] Production environment setup

### Polish
- [ ] Jalali date picker component for transaction/goal forms
- [ ] Error boundaries
- [ ] PWA manifest + icons
- [ ] Better loading skeletons

### Documentation
- [ ] README.md with setup instructions
- [ ] API documentation improvements

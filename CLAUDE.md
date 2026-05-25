# BudgetMate — Project Guide

## Project Overview
Persian RTL personal finance app with AI advisor. Full-stack: FastAPI backend + Next.js frontend.

## Architecture
```
budgetmate/
├── backend/          # FastAPI + SQLite + Alembic
│   ├── app/
│   │   ├── main.py   # App entry, router mounts
│   │   ├── models/   # SQLAlchemy models
│   │   ├── routers/  # API route handlers
│   │   ├── services/ # AI service (OpenClaw/Ollama)
│   │   └── core/     # Auth, config, seed, jalali
│   └── .env          # Secrets (JWT, AI provider)
└── frontend/         # Next.js 16 + Tailwind v4 + shadcn/ui
    └── src/
        ├── app/      # App Router pages
        ├── components/ui/  # shadcn-style components (written manually)
        ├── lib/      # api.ts, fmt.ts, utils.ts
        └── store/    # Zustand auth store
```

## Running

### Backend
```powershell
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend
```powershell
cd frontend
npm run dev
```

## Test Credentials
- User OTP phone: `09120000001`, code: `123456`
- Admin: username=`admin`, password=`5tgb%TGB`

## Key URLs
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api/v1
- API Docs: http://localhost:8000/docs
- Admin panel: http://localhost:3000/admin

## Known Bugs Fixed
- **Pydantic v2 field/type name collision**: In `schemas/transaction.py`, the field `date: Optional[date]` caused Pydantic v2 to resolve the annotation as `NoneType` because the field name `date` shadowed the imported `datetime.date` type. Fixed by `from datetime import date as DateType` and using `DateType` in annotations. Any future schema field whose name matches its type import needs the same alias treatment.

## Important Notes
- Next.js 16 with React 19 and Tailwind CSS v4 (CSS-based config, not tailwind.config.ts)
- shadcn/ui init failed due to network (ECONNRESET), components written manually in src/components/ui/
- Zod v4 breaking changes: no `invalid_type_error`/`required_error`, use `z.number()` with `valueAsNumber: true` in react-hook-form register
- passlib incompatible with Python 3.13 — bcrypt used directly in backend
- AI service uses OpenClaw at http://188.136.214.220:18789 with Ollama fallback
- jalaliday plugin used for Jalali/Shamsi calendar dates

## Authentication + Onboarding Flow (implemented)
New user path: `/login` → `/login/phone` → `/login/otp` → `/onboarding/profile` → `/onboarding/agreement` → `/onboarding/welcome` → `/chat`
Returning user path: `/login` → `/login/phone` → `/login/otp` → `/chat`

Route guards:
- `/onboarding/*` — requires token, redirects to `/chat` if `onboarding_completed=true`
- `/(app)/*` — requires token AND `onboarding_completed=true`, else redirects to `/onboarding/profile`

Auth store fields: `token`, `user`, `adminToken`, `needsProfile`, `onboardingCompleted`, `setOnboardingCompleted`

## New Endpoints (since original build)
- `GET  /api/v1/onboarding/status`
- `POST /api/v1/onboarding/profile`
- `POST /api/v1/onboarding/agreement`
- `POST /api/v1/onboarding/complete`
- `GET  /api/v1/iran/provinces` — 31 provinces
- `GET  /api/v1/iran/cities?province=X` — cities per province
- `POST /api/v1/chat/voice` — multipart audio, transcribes + replies

## Design System (Cleo-inspired)
- Background: `#f5f1eb` (warm cream)
- Primary dark: `#2d1812` (warm brown)
- Accent: `#10b981` (emerald)
- Buttons: `rounded-full`, `py-4`, full-width
- Headings: Vazirmatn 800, text-4xl
- Shared components: `PageTransition.tsx`, `OnboardingLayout.tsx`, `BgImageScreen.tsx`
- Animations: Framer Motion throughout

## What's Done
- [x] Backend: all models, routers, auth, AI service, seed data
- [x] Frontend: all pages, components, auth flow, charts, admin panel
- [x] Onboarding: full redesign — new login flow, onboarding pages, voice chat, route guards
- [x] Chat empty state: hero greeting (yellow smiley + name), suggested prompt chips, budget onboarding card, minimal header

## What's Left
- [ ] Docker Compose (backend + frontend + nginx)
- [ ] README with setup instructions
- [ ] E2E testing
- [ ] PWA manifest
- [ ] Polish: loading states, error boundaries, Jalali date picker

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

## Important Notes
- Next.js 16 with React 19 and Tailwind CSS v4 (CSS-based config, not tailwind.config.ts)
- shadcn/ui init failed due to network (ECONNRESET), components written manually in src/components/ui/
- Zod v4 breaking changes: no `invalid_type_error`/`required_error`, use `z.number()` with `valueAsNumber: true` in react-hook-form register
- passlib incompatible with Python 3.13 — bcrypt used directly in backend
- AI service uses OpenClaw at http://188.136.214.220:18789 with Ollama fallback
- jalaliday plugin used for Jalali/Shamsi calendar dates

## What's Done
- [x] Backend: all models, routers, auth, AI service, seed data
- [x] Frontend: all pages, components, auth flow, charts, admin panel

## What's Left
- [ ] Docker Compose (backend + frontend + nginx)
- [ ] README with setup instructions
- [ ] E2E testing
- [ ] PWA manifest
- [ ] Polish: loading states, error boundaries, date picker for Jalali

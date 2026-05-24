# Codex Handoff

## Project

BudgetMate is a Persian-first RTL personal finance app with a FastAPI backend, SQLite database, and Next.js frontend. It supports OTP login, budgets, transactions, goals, AI chat, and an admin panel. It is privacy-focused and does not integrate with bank accounts.

## Architecture

- `backend/app/` - FastAPI application.
  - `main.py` mounts routers under `/api/v1`, configures CORS, creates tables, and seeds startup data.
  - `core/` contains config, auth, seeding, and Jalali helpers.
  - `models/`, `schemas/`, `routers/`, `services/` contain the domain layers and AI provider service.
- `frontend/src/` - Next.js app.
  - `app/` contains App Router pages.
  - `components/` contains UI components.
  - `lib/` contains API/formatting utilities.
  - `store/` contains Zustand auth state.
- Main config/dependency files: `requirements.txt`, `backend/requirements.txt`, `backend/alembic.ini`, `frontend/package.json`, `frontend/next.config.ts`, `frontend/tsconfig.json`.

## Current State

Use `PROGRESS.md` as the source of truth.

Completed:
- Backend MVP is complete: models, routers, auth, seed data, Alembic, AI service.
- Frontend MVP is complete: login, dashboard, transactions, budget, goals, chat, profile, blocked page, admin dashboard/users/user detail.
- Previous smoke tests passed for health, OTP auth, `/users/me`, and frontend dev server response.

Pending:
- Docker Compose, nginx reverse proxy, and production environment setup.
- Jalali date picker, error boundaries, PWA manifest/icons, better loading skeletons.
- README/API documentation cleanup.

## Known Risks

- Root `README.md` is partly stale: it mentions Next.js 14/Tailwind 3 and Docker Compose, but the actual frontend uses Next.js 16.2.6, React 19.2.4, Tailwind v4, and no `docker-compose.yml` exists.
- `frontend/AGENTS.md` warns that this Next.js version has breaking changes; read relevant docs before frontend code changes.
- A Pydantic v2 field/type name collision was previously fixed in transaction schemas; future schema fields named the same as imported types need type aliases.
- `backend/budgetmate.db` is the canonical development SQLite database. Relative SQLite URLs are normalized relative to `backend/`, and Alembic reads the app settings. A root `budgetmate.db` may still exist as stale/extra data and should not be deleted without explicit approval.
- README mentions `pytest`, but `pytest` is not listed in visible requirements.

## Run / Build / Test

Backend:

```powershell
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
npm run build
npm run lint
```

Useful URLs:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000/api/v1`
- API docs: `http://localhost:8000/docs`
- Admin: `http://localhost:3000/admin`

Test credentials from handoff:
- OTP phone: `09120000001`
- OTP code: `123456`
- Admin: `admin` / `5tgb%TGB`

## Future Codex Rules

- Before making changes, read `AGENTS.md`, `CLAUDE.md`, `PROGRESS.md`, `README.md`, and relevant dependency/config files.
- Treat `PROGRESS.md` as authoritative over stale README content.
- Do not inspect large/generated folders such as `node_modules`, `.next`, `dist`, `build`, `.venv`, `venv`, uploads, outputs, cache, or database/data files unless explicitly asked.
- Explain intended changes before editing.
- Prefer minimal targeted patches; do not rewrite large parts of the project unless requested.
- Preserve existing architecture and naming conventions.
- Do not remove existing behavior unless explicitly requested.
- After changes, run the smallest relevant test/build check.
- Ask before destructive commands.

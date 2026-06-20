# BudgetMate — بادجت‌میت

**Personal CFO & multilingual AI finance assistant**  
**دستیار مالی شخصی، مشاور بودجه و همراه تصمیم‌گیری اقتصادی**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-yellow.svg)
![Node](https://img.shields.io/badge/node-20+-green.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)
![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue.svg)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57.svg)
![Status](https://img.shields.io/badge/status-MVP-orange.svg)

BudgetMate is a privacy-first personal finance app inspired by Cleo AI, but designed to be **local-first, bank-free, multilingual, and controllable by the user**.  
بادجت‌میت با الهام از Cleo AI ساخته شده، اما تمرکزش روی **حریم خصوصی، ثبت دستی داده، چندزبانه بودن، کنترل کاربر و مشاوره مالی شخصی‌سازی‌شده** است.

---

## Overview

BudgetMate helps users:

- track income and expenses manually
- manage monthly budgets
- create savings goals
- manage future commitments
- chat with an AI financial assistant
- receive practical Personal CFO-style guidance
- use the app in multiple languages and directions

The app does **not** connect to bank accounts by default. Financial decisions are based on user-entered transactions, goals, budgets, commitments, memories, and preferences.

---

## Key Features

### Personal finance

- Manual income and expense tracking
- Monthly budget initialization from onboarding income range
- Savings goals with target amount, current amount, deadline, and progress
- Future commitments such as rent, checks, installments, and scheduled payments
- Goal intake flow: the assistant asks missing amount/date, then asks whether to save as a goal or give advice
- Duplicate-safe writes for goals, transactions, and future commitments
- Session cleanup when chat history is cleared

### AI assistant

- Personal CFO / financial behavior coach style chat
- AI-grounded answers based on real user data
- Safe SQL orchestration: model plans, backend validates and executes
- Current-turn write guard: old chat history cannot replay old writes
- Advisory mode for financial decisions before saving goals
- OpenAI or Ollama provider selection from `.env`
- No OpenClaw in the active runtime path

### Multilingual app

Supported languages:

| Locale | Language | Direction |
|---|---|---|
| `fa` | فارسی | RTL |
| `ar` | العربية | RTL |
| `en` | English | LTR |
| `de` | Deutsch | LTR |
| `zh` | 中文 | LTR |

- `/` redirects to `/fa`
- Locale routes: `/fa`, `/ar`, `/en`, `/de`, `/zh`
- Frontend dictionaries for all supported languages
- Backend i18n service and dictionary overrides
- User language and currency preferences
- Admin translation management panel
- AI final answer language/currency instruction based on user preference

### Admin

- User management
- Admin dashboard
- Translation dictionary management
- Backend dictionary override support
- Safer localized backend messages

---

## Cleo AI Comparison Check

BudgetMate is inspired by Cleo AI, but its design goals are different.

| Area | BudgetMate | Cleo AI |
|---|---|---|
| Bank connection | Manual-first, no required bank connection | Built around connected personal finance features |
| Privacy model | Local/self-hostable project | Hosted commercial app |
| Cost model | Open-source MIT project | Commercial freemium/premium plans |
| AI provider | Configurable: OpenAI or Ollama | Commercial app-managed AI |
| Languages | Built for fa/ar/en/de/zh with RTL/LTR support | Public app/support language coverage should be verified per store/region |
| Admin translation control | Built-in translation override panel | Not a self-hosted/admin-editable product |

### Why this matters

BudgetMate should be evaluated against Cleo AI with clear criteria:

- Is BudgetMate better for privacy-sensitive users?
- Is it better for Persian/Arabic RTL users?
- Is it better for teams that need self-hosting and admin-controlled dictionaries?
- Is it cheaper to operate when using local Ollama models?
- Does it support more relevant languages for the target users?

The goal is not to clone Cleo. The goal is to build a controllable, multilingual, privacy-first financial assistant that can be adapted for local markets.

Useful Cleo references for comparison:

- [Cleo official website](https://web.meetcleo.com/)
- [Cleo pricing](https://web.meetcleo.com/pricing)
- [Cleo 3.0 AI feature announcement](https://web.meetcleo.com/blog/Introducing-cleo-3-0)

---

## Tech Stack

### Backend

- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic v2
- SQLite
- JWT authentication
- SSE streaming
- OpenAI / Ollama provider abstraction
- Backend i18n dictionaries and admin translation overrides

### Frontend

- Next.js App Router
- TypeScript
- TailwindCSS
- shadcn/ui
- lucide-react
- recharts
- zustand
- axios
- locale-prefixed routing
- RTL/LTR aware UI

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- Git
- SQLite
- Optional: Ollama for local LLM mode

---

## Backend Setup

```bash
cd backend
pip install --user -r requirements.txt
```

Create `backend/.env`:

```env
DATABASE_URL=sqlite:///./budgetmate.db
APP_TIMEZONE=Asia/Tehran

JWT_SECRET=change_me
JWT_ALGORITHM=HS256

ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_me

OTP_MOCK_CODE=123456
CORS_ORIGINS=http://localhost:3000

# LLM provider: openai or ollama
AI_PROVIDER=openai

# OpenAI mode
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

# Ollama mode
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:20b
```

Run migrations and start backend:

```bash
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Backend:

```text
http://localhost:8000
```

API docs:

```text
http://localhost:8000/docs
```

---

## Frontend Setup

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

Run:

```bash
npm run dev
```

Frontend:

```text
http://localhost:3000
```

Default route:

```text
/  ->  /fa
```

---

## Switching AI Providers

### OpenAI

```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

### Ollama

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:20b
```

If using Ollama:

```bash
ollama pull gpt-oss:20b
ollama serve
```

---

## Testing

Backend:

```bash
cd backend
python -m alembic upgrade head
python -m pytest
python -m compileall app
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

---

## Important Behavior Rules

- Chat history is context only; old messages must not create new writes.
- Pending goal/advisory sessions are transient and should clear when chat history is cleared.
- Goal-like future purchases are not automatically commitments.
- Commitments are required future payments such as rent, checks, installments, or remaining debt.
- Goals are desired future purchases or savings targets.
- Transactions are already paid/received money movements.
- The backend validates and scopes all model-planned operations.
- The model must not control `user_id`.
- Destructive SQL is forbidden.

---

## Roadmap

- Complete remaining hardcoded UI translation cleanup
- Improve profile language/currency UX
- Add richer admin translation workflows
- Add optional FX conversion support
- Add recurring transactions
- Add export to CSV/Excel
- Add receipt OCR
- Add production PostgreSQL profile
- Add real SMS provider integration
- Add mobile app wrapper

---

## License

BudgetMate is released under the **MIT License**.

---

## Acknowledgments

- Inspired by [Cleo AI](https://web.meetcleo.com/)
- Built with FastAPI, Next.js, TailwindCSS, shadcn/ui, and SQLAlchemy
- Made for privacy-first personal finance and multilingual AI assistance

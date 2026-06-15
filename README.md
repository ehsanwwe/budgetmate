<div align="center">

# 💰 BudgetMate — بادجت‌میت

### Your Personal Persian AI Finance Assistant
### دستیار مالی شخصی هوشمند فارسی‌زبان

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-yellow.svg)
![Node](https://img.shields.io/badge/node-20+-green.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)
![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue.svg)
![TailwindCSS](https://img.shields.io/badge/Tailwind-3.4-38B2AC.svg)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57.svg)
![Status](https://img.shields.io/badge/status-MVP-orange.svg)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

<p>
  <strong>Inspired by Cleo AI — but private, local, and Persian-first.</strong>
</p>

<p>
  <a href="#english">English</a> • <a href="#-فارسی">فارسی</a>
</p>

</div>

---

<a id="english"></a>

## 🌟 Overview

**BudgetMate** is a privacy-first personal finance app inspired by Cleo AI, built specifically for Persian-speaking users. Unlike Cleo, it **never connects to any bank account** — you manually enter your budget, track expenses, set savings goals, and chat with an AI advisor that gives money advice in Persian based on your data.

### Why BudgetMate?

- 🔒 **100% Privacy** — no bank integration, your data stays on your machine
- 🇮🇷 **Persian-first** — full RTL UI, Jalali calendar, Persian numerals throughout
- 🤖 **AI-powered** — chat with a financial advisor that knows your budget and spending
- 🔌 **Pluggable AI provider** — chat planning uses OpenAI or Ollama, with backend validation and audit
- 👨‍💼 **Built-in admin panel** — manage users, view stats, block accounts
- 📱 **Mobile-first responsive design** — works beautifully on any screen size

---

## 📸 Screenshots

> _Add your screenshots here_

<div align="center">

| Login | Dashboard | Chat |
|:-:|:-:|:-:|
| ![Login](docs/screenshots/login.png) | ![Dashboard](docs/screenshots/dashboard.png) | ![Chat](docs/screenshots/chat.png) |

| Transactions | Goals | Admin Panel |
|:-:|:-:|:-:|
| ![Transactions](docs/screenshots/transactions.png) | ![Goals](docs/screenshots/goals.png) | ![Admin](docs/screenshots/admin.png) |

</div>

---

## ✨ Features

### For Users
- 🔐 **Phone + OTP login** (mock OTP for development: `123456`)
- 📊 **Dashboard** with budget summary, spending pie chart, and 7-day trend
- 💸 **Transaction tracking** with categories, filters, and search
- 🎯 **Savings goals** with progress tracking and contributions
- 💬 **AI chat** with streaming responses, grounded in your real financial data
- 📅 **Jalali calendar** support throughout
- 🌙 **Smooth animations** and modern gradient UI

### For Admins
- 📈 **Stats dashboard** — total users, active users, transaction counts
- 👥 **User management** — search, view details, block/unblock
- 📋 **Activity logs** — full audit trail of important actions
- 🔒 **Separate admin authentication** with its own JWT scope

### Technical
- 🚀 **FastAPI backend** with auto-generated OpenAPI docs
- ⚡ **Server-Sent Events (SSE)** for streaming AI responses
- 🗄️ **SQLAlchemy 2.x + Alembic** migrations
- 🎨 **Next.js 14 App Router** with React Server Components
- 💅 **shadcn/ui** components, fully customized for RTL
- ✅ **Type-safe end-to-end** (TypeScript + Pydantic v2)

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────┐
│                      Next.js 14 Frontend                   │
│  (App Router · TypeScript · Tailwind · shadcn/ui · RTL)    │
└────────────────────────┬───────────────────────────────────┘
                         │ REST + SSE
                         ↓
┌────────────────────────────────────────────────────────────┐
│                       FastAPI Backend                      │
│   (Auth · Budgets · Transactions · Goals · Chat · Admin)   │
└──┬──────────────────────┬──────────────────────────────────┘
   │                      │
   ↓                      ↓
┌─────────┐    ┌─────────────────────────────────┐
│ SQLite  │    │   AI Provider (pluggable)       │
│   DB    │    │  ┌──────────┐  ┌──────────┐    │
└─────────┘    │     OpenAI / Ollama Planner     │
               │  backend validates actions  │
               └─────────────────────────────────┘
```

---

## 🛠️ Tech Stack

### Backend
- **FastAPI** 0.115 — modern async Python web framework
- **SQLAlchemy** 2.x — ORM with full type support
- **Alembic** — database migrations
- **Pydantic** v2 — data validation
- **python-jose** — JWT authentication
- **bcrypt** — password hashing
- **httpx** — async HTTP for AI provider calls
- **sse-starlette** — Server-Sent Events for streaming

### Frontend
- **Next.js** 14 (App Router)
- **TypeScript** 5
- **TailwindCSS** 3.4 (with logical properties for RTL)
- **shadcn/ui** — accessible component primitives
- **lucide-react** — icon library
- **recharts** — charts and data visualization
- **zustand** — state management
- **axios** — HTTP client
- **react-hook-form** + **zod** — form validation
- **dayjs** + **jalaliday** — Jalali calendar
- **@fontsource/vazirmatn** — Persian web font

---

## 🚀 Getting Started

### Prerequisites

- **Python** 3.11 or higher
- **Node.js** 20 or higher
- **Git**
- **Windows PowerShell** or any Unix-like shell

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/budgetmate.git
cd budgetmate
```

### 2. Backend setup

```bash
cd backend

# Install dependencies (no venv needed)
pip install --user fastapi "uvicorn[standard]" sqlalchemy alembic pydantic "pydantic-settings" "python-jose[cryptography]" "passlib[bcrypt]" bcrypt httpx python-dotenv sse-starlette python-multipart

# Or use requirements.txt
pip install --user -r requirements.txt
```

Create `backend/.env`:

```env
# LLM provider
AI_PROVIDER=openai

# OpenAI
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:20b

APP_TIMEZONE=Asia/Tehran
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_admin_password
OTP_MOCK_CODE=123456
JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
JWT_ALGORITHM=HS256
DATABASE_URL=sqlite:///./budgetmate.db
CORS_ORIGINS=http://localhost:3000
```

Development SQLite note: `backend/budgetmate.db` is the canonical local database. Relative SQLite URLs are normalized by the backend config relative to `backend/`, so starting FastAPI or Alembic from the repo root or from `backend/` uses the same DB file. A root-level `budgetmate.db` may exist from older relative-path runs and should not be deleted unless you explicitly decide to clean it up.

Run migrations and start the server:

```bash
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Backend will be available at: **http://localhost:8000**  
API docs: **http://localhost:8000/docs**

### 3. Frontend setup

In a new terminal:

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

Run the dev server:

```bash
npm run dev
```

Frontend will be available at: **http://localhost:3000**

### 4. Login and test

1. Open **http://localhost:3000**
2. Enter any phone number (e.g., `09120000000`)
3. Use OTP code: **`123456`**
4. You're in! Set a budget, add transactions, chat with the AI.

Onboarding budget note: when a new user selects an income range, the initial current-month budget is set from the maximum value of that range. For example, `40-80 million toman` initializes the monthly budget to `80,000,000` toman. This initialization runs once when onboarding is completed and does not overwrite later customized budgets.

For the admin panel:

1. Open **http://localhost:3000/admin**
2. Username: `admin`
3. Password: (whatever you set in `.env`)

---

## 🔌 Switching AI Providers

BudgetMate's active chat/orchestrator path selects its LLM provider from environment variables. The selected LLM plans; the backend validates, scopes, executes, audits, and formats.

OpenAI mode:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
```

Ollama mode:

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:20b
```

Default mode: if `AI_PROVIDER` is missing and `OPENAI_API_KEY` exists, OpenAI is used. If both are missing, Ollama is used with `OLLAMA_BASE_URL=http://localhost:11434` and `OLLAMA_MODEL=gpt-oss:20b`.

---

## 📁 Project Structure

```
budgetmate/
├── backend/
│   ├── app/
│   │   ├── core/           # config, auth, security, seed
│   │   ├── db.py           # SQLAlchemy Base + engine
│   │   ├── models/         # User, Budget, Transaction, Goal, ...
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── routers/        # auth, budgets, transactions, chat, admin, ...
│   │   ├── services/
│   │   │   └── ai.py       # AI provider abstraction
│   │   └── main.py         # FastAPI app entry
│   ├── alembic/            # database migrations
│   ├── .env                # backend secrets (gitignored)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/            # Next.js App Router pages
│   │   ├── components/     # UI components + shadcn/ui
│   │   ├── lib/            # api client, formatters, utils
│   │   └── store/          # zustand stores
│   ├── .env.local          # frontend env (gitignored)
│   └── package.json
├── docker-compose.yml      # one-command full stack
├── CLAUDE.md               # AI agent resume guide
└── README.md
```

---

## 🐳 Docker (optional)

Run the full stack with one command:

```bash
docker compose up --build
```

Backend on `:8000`, frontend on `:3000`.

---

## 🔧 API Reference

All API endpoints are documented and testable at **http://localhost:8000/docs** (Swagger UI).

### Key endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/request-otp` | Request OTP for a phone number |
| `POST` | `/api/v1/auth/verify-otp` | Verify OTP and get JWT |
| `POST` | `/api/v1/auth/admin/login` | Admin login |
| `GET`  | `/api/v1/me` | Current user info |
| `GET`  | `/api/v1/budgets/current` | Get current month budget |
| `GET`  | `/api/v1/transactions/summary` | Spending summary for current month |
| `POST` | `/api/v1/chat/message` | Send a message to AI |
| `GET`  | `/api/v1/chat/stream` | Stream AI response (SSE) |
| `GET`  | `/api/v1/admin/stats` | Admin dashboard stats |

---

## 🧪 Testing

```bash
# Backend smoke test
cd backend
python -m pytest

# Frontend type check + build
cd frontend
npm run build
```

---

## 🗺️ Roadmap

- [ ] Real SMS OTP integration (Kavenegar, Twilio)
- [ ] Recurring transactions
- [ ] Multi-currency support
- [ ] Budget categories with custom rules
- [ ] Export to CSV / Excel
- [ ] Receipt OCR via vision models
- [ ] Mobile apps (React Native)
- [ ] PostgreSQL support for production
- [ ] Telegram bot integration

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Open a Pull Request

For major changes, please open an issue first to discuss what you'd like to change.

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Inspired by [Cleo AI](https://web.meetcleo.com/) — the original AI finance assistant
- Built with [FastAPI](https://fastapi.tiangolo.com/) and [Next.js](https://nextjs.org/)
- Persian font: [Vazirmatn](https://github.com/rastikerdar/vazirmatn) by Saber Rastikerdar
- Icons: [Lucide](https://lucide.dev/)
- UI components: [shadcn/ui](https://ui.shadcn.com/)

---

<a id="-فارسی"></a>

<div dir="rtl">

## 🌟 معرفی

**بادجت‌میت** یک اپلیکیشن مدیریت مالی شخصی است که با الهام از Cleo AI ساخته شده، اما با تمرکز کامل بر **حریم خصوصی** و **زبان فارسی**. برخلاف Cleo، **هیچ‌گاه به حساب بانکی شما متصل نمی‌شود** — شما به‌صورت دستی بودجه‌تان را وارد می‌کنید، هزینه‌ها را ثبت می‌کنید، اهداف پس‌انداز تعریف می‌کنید و با دستیار هوشمندی که از داده‌های مالی شما باخبر است، به فارسی گفت‌وگو می‌کنید.

### چرا بادجت‌میت؟

- 🔒 **حریم خصوصی کامل** — هیچ اتصال بانکی نیست، داده‌ها روی سیستم شما باقی می‌مانند
- 🇮🇷 **فارسی از پایه** — رابط راست‌چین کامل، تقویم جلالی، اعداد فارسی
- 🤖 **هوش مصنوعی مالی** — مشاوره مبتنی بر بودجه و خرج‌های واقعی شما
- 🔌 **هوش مصنوعی با OpenAI** — برنامه‌ریزی با مدل انجام می‌شود و اجرا در بک‌اند اعتبارسنجی می‌شود
- 👨‍💼 **پنل ادمین داخلی** — مدیریت کاربران، آمار، بلاک کردن
- 📱 **طراحی موبایل‌اول** — روی هر اندازه صفحه‌ای زیبا است

---

## ✨ امکانات

### برای کاربر
- 🔐 ورود با شماره موبایل و کد OTP (کد آزمایشی: `۱۲۳۴۵۶`)
- 📊 داشبورد با خلاصه بودجه، نمودار دایره‌ای و روند ۷ روز اخیر
- 💸 ثبت و مدیریت تراکنش‌ها با دسته‌بندی، فیلتر و جستجو
- 🎯 اهداف پس‌انداز با نمودار پیشرفت
- 💬 گفت‌وگو با هوش مصنوعی، پاسخ‌های جاری (streaming)
- 📅 پشتیبانی کامل از تقویم جلالی
- 🌙 انیمیشن‌های نرم و رابط مدرن

### برای ادمین
- 📈 داشبورد آمار — تعداد کاربران، کاربران فعال، تراکنش‌ها
- 👥 مدیریت کاربران — جستجو، مشاهده جزئیات، بلاک/آنبلاک
- 📋 لاگ فعالیت‌ها

---

## 🚀 راه‌اندازی

### پیش‌نیازها

- **Python** نسخه ۳.۱۱ یا بالاتر
- **Node.js** نسخه ۲۰ یا بالاتر
- **Git**

### ۱. کلون کردن مخزن

```bash
git clone https://github.com/yourusername/budgetmate.git
cd budgetmate
```

### ۲. راه‌اندازی بک‌اند

```bash
cd backend
pip install --user -r requirements.txt
```

فایل `backend/.env` را با مقادیر مناسب پر کنید (نمونه در بخش انگلیسی).

```bash
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

بک‌اند روی **http://localhost:8000** در دسترس است.  
مستندات API: **http://localhost:8000/docs**

### ۳. راه‌اندازی فرانت‌اند

در ترمینال جدید:

```bash
cd frontend
npm install
```

فایل `frontend/.env.local` بسازید:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

```bash
npm run dev
```

فرانت‌اند روی **http://localhost:3000** در دسترس است.

### ۴. ورود و تست

۱. به **http://localhost:3000** بروید  
۲. هر شماره موبایلی را وارد کنید (مثلاً `۰۹۱۲۰۰۰۰۰۰۰`)  
۳. کد OTP: **`۱۲۳۴۵۶`**  
۴. وارد داشبورد می‌شوید!

برای پنل ادمین:

۱. **http://localhost:3000/admin**  
۲. نام کاربری: `admin`  
۳. رمز عبور: (مقداری که در `.env` تنظیم کردید)

---

## 🔌 سوئیچ بین Providerهای هوش مصنوعی

مسیر فعال چت و orchestrator از `AI_PROVIDER` برای انتخاب OpenAI یا Ollama استفاده می‌کند:

- OpenAI: `AI_PROVIDER=openai`، `OPENAI_API_KEY`، `OPENAI_MODEL`
- Ollama: `AI_PROVIDER=ollama`، `OLLAMA_BASE_URL=http://localhost:11434`، `OLLAMA_MODEL=gpt-oss:20b`
- حالت پیش‌فرض: اگر `AI_PROVIDER` خالی باشد و `OPENAI_API_KEY` وجود داشته باشد OpenAI استفاده می‌شود؛ در غیر این صورت Ollama با مدل `gpt-oss:20b` استفاده می‌شود.
- مدل فقط برنامه پیشنهاد می‌دهد؛ بک‌اند SQL را اعتبارسنجی، محدود، اجرا و audit می‌کند.

---

## 🤝 مشارکت

از مشارکت شما استقبال می‌شود! مراحل:

۱. مخزن را Fork کنید  
۲. شاخه جدید بسازید (`git checkout -b feat/something`)  
۳. تغییرات را commit کنید  
۴. push کنید و Pull Request باز کنید

---

## 📜 لایسنس

این پروژه تحت لایسنس **MIT** منتشر شده است.

---

</div>

<div align="center">

### Made with ❤️ for Persian users

⭐ **Star this repo if you find it useful!**

</div>

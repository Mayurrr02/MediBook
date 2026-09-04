# MediBook: Intelligent Healthcare Appointment & Scheduling Platform

MediBook is a production-oriented intelligent healthcare appointment scheduling platform built on a modular monolith architecture with FastAPI, MongoDB, Redis, and React.

> [!NOTE]
> **Safety & Engineering Notice**: MediBook is an engineering showcase and scheduling platform. It does not provide medical diagnoses or claim HIPAA compliance.

---

## 🛠️ Tech Stack
- **Backend**: Python 3.9+, FastAPI, Motor (Async MongoDB), Redis (Distributed Locks & In-Memory Cache)
- **Frontend**: React 18, Vite, React Router, Axios
- **Payments**: Razorpay (Order creation + HMAC-SHA256 signature verification + Webhooks)
- **AI & Triage**: Google GenAI (Gemini) with clinical triage and emergency guardrails
- **Testing**: Pytest & pytest-asyncio test suite with high-concurrency race condition testing

---

## 🚀 Key Features Implemented (Phase 1)

### 1. Dynamic Scheduling Engine
- Dynamic time-slot generation computed on demand based on doctor working hours, shift start/end, break intervals (e.g. lunch breaks), and blocked vacation dates.
- Configurable doctor schedules via `GET /doctor/{id}/schedule` and `PUT /doctor/{id}/schedule`.

### 2. Redis Distributed Slot Locking
- Distributed mutex locking on slots using atomic Redis `SET ... NX EX` with configurable TTL (default 300s).
- Atomic lock release via SHA Lua script ensuring only the token holder can release the lock.
- Zero double-booking guarantee under concurrent booking attempts.
- Graceful in-memory fallback for local environments without an active Redis instance.

### 3. Formal Appointment Lifecycle State Machine
- Strict status transitions:
  - `PENDING_CONFIRMATION` ➔ `CONFIRMED`
  - `CONFIRMED` ➔ `IN_PROGRESS` | `COMPLETED` | `CANCELLED` | `RESCHEDULED` | `NO_SHOW`
  - `IN_PROGRESS` ➔ `COMPLETED` | `CANCELLED`
  - `COMPLETED`, `CANCELLED`, `RESCHEDULED`, `NO_SHOW` are immutable terminal states.
- Dedicated endpoints for cancellation (`POST /appointments/{id}/cancel`), rescheduling (`POST /appointments/{id}/reschedule`), and status updating (`PATCH /appointments/{id}/status`).

### 4. Comprehensive Automated Test Suite
- 15 automated Pytest unit and integration tests covering:
  - Scheduling slot math & break overlaps
  - Redis distributed locking, token validation, and TTL expiry
  - 20-concurrent-user race condition simulations
  - State machine transition validation
  - API endpoints and health checks

---

## 🔧 Setup & Running

### Backend Setup
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Configure MONGO_URI, REDIS_URL, JWT_SECRET, etc.
uvicorn main:app --reload
```
- API runs at `http://127.0.0.1:8000`
- Interactive Swagger docs at `http://127.0.0.1:8000/docs`
- Health check at `http://127.0.0.1:8000/health`

### Running Backend Tests
```bash
cd backend
pytest backend/tests -v
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
- Frontend runs at `http://localhost:5173`

---

## 📖 API Endpoints Overview

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/health` | Health probe (MongoDB, Redis status) | Public |
| `POST` | `/register` | Register new user account | Public |
| `POST` | `/login` | Authenticate and obtain JWT | Public |
| `GET` | `/doctors` | List all active doctors | Public |
| `GET` | `/doctor/{id}` | Get specific doctor profile | Public |
| `GET` | `/doctor/{id}/schedule` | Get doctor working hours & shifts | Public |
| `PUT` | `/doctor/{id}/schedule` | Update doctor schedule | Doctor/Admin |
| `GET` | `/doctors/{id}/slots` | Get real-time dynamic slots & lock status | Optional |
| `POST` | `/slots/lock` | Acquire distributed lock on slot | Patient |
| `POST` | `/slots/unlock` | Release distributed lock on slot | Patient |
| `POST` | `/appointment` | Book appointment with lock verification | Patient |
| `GET` | `/appointments` | List patient appointment history | Patient |
| `GET` | `/appointments/{id}` | Get appointment details | Patient/Doctor/Admin |
| `POST` | `/appointments/{id}/cancel` | Cancel an appointment | Patient/Doctor/Admin |
| `POST` | `/appointments/{id}/reschedule` | Reschedule an appointment | Patient/Admin |
| `PATCH` | `/appointments/{id}/status` | Update appointment state | Doctor/Admin |
| `POST` | `/payment/create-order` | Create Razorpay premium order | Patient |
| `POST` | `/payment/verify` | Verify payment signature | Patient |
| `POST` | `/payment/webhook` | Razorpay webhook callback | Public (HMAC Verified) |
| `POST` | `/premium/symptom-checker` | AI Symptom analysis | Premium Patient |

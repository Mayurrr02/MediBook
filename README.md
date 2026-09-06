# MediBook: Intelligent Healthcare Appointment & Scheduling Platform

MediBook is a production-oriented healthcare appointment scheduling platform built on a high-throughput, distributed architecture with FastAPI, Redis, Celery, MongoDB, React, and an AI-Assisted Patient Intake & Doctor Matching Engine.

> [!NOTE]
> **Safety & Medical Notice**: MediBook is an engineering showcase and scheduling platform. It does not provide medical diagnoses or claim HIPAA compliance.

---

## 🛠️ Tech Stack & Architecture

- **Backend**: Python 3.9+, FastAPI (Async REST API), Motor (Async MongoDB Driver)
- **AI Triage & Intake**: Google GenAI (Gemini) + Deterministic Emergency Scanner & Heuristic Engine
- **Distributed Caching & Locking**: Redis 7 (Atomic `SET NX EX` distributed slot locks, Lua script token release, AI rate limiting)
- **Background Workers & Scheduling**: Celery + Celery Beat (Periodic 24h/1h reminders, automated waitlist claim expiration)
- **Database**: MongoDB (Flexible document store with compound indexes)
- **Frontend**: React 18, Vite, React Router, Axios (MediBook AI Assistant, Slot Hold Countdowns, Dynamic Calendar, Waitlists)
- **Containerization**: Docker & Docker Compose (FastAPI, React + Nginx, MongoDB, Redis, Celery Worker, Celery Beat)
- **Payments**: Razorpay (Order creation + signature verification + webhook)
- **Testing**: Pytest & pytest-asyncio automated test suites (31/31 passing)

```
                              ┌──────────────────────────────────┐
                              │     React + Vite Frontend        │
                              │ (AI Assistant / Holds / Booking) │
                              └─────────────────┬────────────────┘
                                                │ REST API
                                                ▼
                              ┌──────────────────────────────────┐
                              │       FastAPI Application        │
                              │ ┌──────────────────────────────┐ │
                              │ │  Deterministic Emergency     │ │
                              │ │  Scanner (Pre & Post Filter) │ │
                              │ └──────────────┬───────────────┘ │
                              │ ┌──────────────▼───────────────┐ │
                              │ │  Structured LLM Intake /     │ │
                              │ │  Heuristic Fallback Engine   │ │
                              │ └──────────────┬───────────────┘ │
                              │ ┌──────────────▼───────────────┐ │
                              │ │  Doctor Matching Engine      │ │
                              │ │  (Transparent Multi-Factor)  │ │
                              │ └──────────────┬───────────────┘ │
                              │ ┌──────────────▼───────────────┐ │
                              │ │  Scheduling & Locking Engine │ │
                              │ └──────────────────────────────┘ │
                              └─────┬──────────────┬─────────────┘
                                    │              │
                   Distributed Lock │              │ Data Persistence
                   & Task Broker    │              │
                                    ▼              ▼
                     ┌──────────────────┐  ┌──────────────────┐
                     │   Redis Server   │  │  MongoDB Server  │
                     │  (SET NX Locks)  │  │ (Appointments /  │
                     └────────┬─────────┘  │  Waitlists / DB) │
                              │            └────────┬─────────┘
                 Async Tasks  │                     │
                              ▼                     │
               ┌──────────────────────────────┐     │
               │   Celery Worker & Beat       │◄────┘
               │  - 24h & 1h Reminders        │
               │  - Stale Waitlist Sweeper    │
               │  - Notification Dispatcher   │
               └──────────────────────────────┘
```

---

## 🤖 AI-Assisted Patient Intake & Doctor Matching (Phase 3)

MediBook features a cautious, non-diagnostic AI intake workflow that extracts structured clinical symptoms, enforces medical safety boundaries, maps to controlled specialties, and computes transparent match scores for doctors.

### 1. Medical Safety & Non-Diagnostic Rule
- The AI **MUST NOT** diagnose illnesses or prescribe medication.
- It provides specialty navigation (e.g. *"Based on the information provided, a General Physician may be an appropriate specialty to consult."*).

### 2. Deterministic Emergency Safety Layer
Independently of LLM inference, a rule-based deterministic scanner screens for life-threatening acute red flags (e.g., crushing chest pain, acute respiratory distress, FAST stroke criteria, altered consciousness, severe hemorrhage, anaphylaxis).
- **Trigger Behavior**: Instantly overrides urgency to `EMERGENCY` and prioritizes an emergency banner directing the user to dial **112 / 911 / 102** or visit the nearest Emergency Department.

### 3. Controlled Specialties Taxonomy
Specialty recommendations are strictly validated against a closed taxonomy:
`General Physician` | `Cardiologist` | `Dermatologist` | `Pediatrician` | `Orthopedic` | `Neurologist` | `ENT` | `Dentist` | `Gynecologist`.

### 4. Transparent Doctor Matching Scoring
Matched doctors are ranked using a multi-factor transparent formula (0–100 score):
$$\text{Match Score} = S_{\text{specialty}} + S_{\text{availability}} + S_{\text{rating}} + S_{\text{experience}} + S_{\text{fee}}$$
- **Specialty Match ($S_{\text{specialty}}$, Max 40 pts)**: Exact match = 40 pts; General medicine fallback = 20 pts.
- **Dynamic Availability ($S_{\text{availability}}$, Max 25 pts)**: Slots today = 25 pts; Next 3 days = 18 pts; This week = 10 pts.
- **Patient Rating ($S_{\text{rating}}$, Max 15 pts)**: $(Rating / 5.0) \times 15$.
- **Experience ($S_{\text{experience}}$, Max 10 pts)**: Normalized clinical experience.
- **Affordability ($S_{\text{fee}}$, Max 10 pts)**: Fee reasonableness index.

### 5. 1-Click Slot Recommendation Integration
Matched doctors display their top 3 next available slots generated live via the Phase 1 scheduling engine. Patients can click any slot to prefill doctor, date, slot time, and intake symptoms directly into the booking flow.

### 6. Resilience & Heuristic Fallback
If external AI providers experience timeouts, missing API keys, or rate limits, MediBook automatically fails over to an internal heuristic regex and keyword engine, guaranteeing 100% uptime.

---

## 🔒 Concurrency & Distributed Slot Locking (Phase 2)

1. **Atomic Redis Locking**:
   - Key: `appointment_lock:{doctor_id}:{date}:{time}`
   - Operation: `SET key json_payload NX EX 300` (5-minute TTL).
2. **Safe Release via Lua Script**: Verifies cryptographic token ownership before deleting locks.
3. **Double Verification**: Validates lock ownership + MongoDB state before creating confirmed bookings.
4. **Stress Tested**: Tested with **100 concurrent simultaneous requests** on the exact same slot; strictly 1 succeeds with 99 rejected (`409 Conflict`).

---

## ⏳ FIFO Waitlist Management Engine (Phase 2)

- Patients join FIFO waitlists for fully booked slots.
- Cancellation/rescheduling auto-promotes the first candidate (`WAITING` ➔ `NOTIFIED`), holds the slot for 15 minutes, and dispatches a notification.
- Celery Beat automatically sweeps and expires unclaimed slots every minute.

---

## ⏰ Background Tasks & Celery Workers (Phase 2)

- **24-Hour Reminders** (`tasks.reminders.send_24h_reminders_task`): Daily at 08:00 UTC.
- **1-Hour Reminders** (`tasks.reminders.send_1h_reminders_task`): Every 15 minutes.
- **Waitlist Expiration Sweeper** (`tasks.waitlist_tasks.expire_stale_waitlists_task`): Every minute.
- **Slot Lock Sweeper** (`tasks.cleanup_tasks.cleanup_slot_locks_task`): Every 5 minutes.

---

## 📖 API Endpoints Reference

### AI Intake & Doctor Matching (Phase 3)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/v1/ai/intake` | Analyze symptoms, detect red-flags, match doctors & slots | Optional (Public/Patient) |
| `GET` | `/api/v1/ai/specialties` | List controlled medical specialties taxonomy | Public |
| `GET` | `/api/v1/ai/intakes/me` | List patient's past intake evaluations | Patient |

### Health Check
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/health` | Health check verifying Database & Redis connectivity | Public |

### Slot Holds & Concurrency (Phase 2)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/v1/appointments/hold-slot` | Acquire temporary 5-min slot hold lock | Patient |
| `POST` | `/api/v1/appointments/release-slot` | Manually release slot hold lock | Patient |

### Waitlists (Phase 2)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/v1/waitlists` | Join FIFO waitlist for fully booked slots | Patient |
| `GET` | `/api/v1/waitlists/me` | List current patient's active/past waitlists | Patient |
| `POST` | `/api/v1/waitlists/{id}/claim` | Claim offered slot within 15-min window | Patient |
| `POST` | `/api/v1/waitlists/{id}/cancel` | Cancel waitlist queue position | Patient |

### Appointment Scheduling & Lifecycle (Phase 1)
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/v1/appointments/available-slots` | Dynamic available & booked slots | Public |
| `POST` | `/api/v1/appointments` | Book appointment with distributed lock & conflict checks | Patient |
| `GET` | `/api/v1/appointments` | List patient appointment history | Patient |
| `POST` | `/api/v1/appointments/{id}/cancel` | Cancel appointment (triggers waitlist promotion) | Patient/Doctor/Admin |
| `POST` | `/api/v1/appointments/{id}/reschedule` | Reschedule appointment to new slot | Patient/Admin |
| `PATCH` | `/api/v1/appointments/{id}/status` | Update state (`COMPLETED`, `NO_SHOW`) | Doctor/Admin |

### Doctor Availability & Leave Management
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/v1/doctors` | List doctors with availability summary | Public |
| `GET` | `/api/v1/doctors/{id}` | Get doctor profile and shifts | Public |
| `GET` | `/api/v1/doctors/{id}/availability` | Get working hours, shifts, breaks | Public |
| `PUT` | `/api/v1/doctors/{id}/availability` | Update doctor availability schedule | Doctor/Admin |
| `GET` | `/api/v1/doctors/{id}/leaves` | List doctor leave dates | Public |
| `POST` | `/api/v1/doctors/{id}/leaves` | Schedule leave / time off | Doctor/Admin |
| `DELETE` | `/api/v1/doctors/{id}/leaves/{leave_id}` | Cancel/delete leave record | Doctor/Admin |

---

## 🐳 Docker Deployment

```bash
# Build and start all 6 services
docker compose up --build -d

# View service logs
docker compose logs -f

# Check container status
docker compose ps
```

---

## 🧪 Running Automated Tests

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt

# Run complete automated test suite (31 tests)
pytest backend/tests -v
```

```bash
cd ../frontend
npm run build
```

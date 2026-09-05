# MediBook: Intelligent Healthcare Appointment & Scheduling Platform

MediBook is a production-oriented healthcare appointment scheduling platform built on a modular architecture with FastAPI, MongoDB, and React.

> [!NOTE]
> **Safety & Medical Notice**: MediBook is an engineering showcase and scheduling platform. It does not provide medical diagnoses or claim HIPAA compliance.

---

## 🛠️ Tech Stack
- **Backend**: Python 3.9+, FastAPI, Motor (Async MongoDB Driver)
- **Frontend**: React 18, Vite, React Router, Axios
- **Payments**: Razorpay (Order creation + signature verification + webhook)
- **AI Symptom Intake**: Google GenAI (Gemini) triage with emergency guardrails
- **Testing**: Pytest & pytest-asyncio automated test suites

---

## 📅 Scheduling Engine Architecture (Phase 1)

### 1. Dynamic Doctor Availability & Working Shifts
Doctors configure their availability via `DoctorAvailability` and `DoctorLeave` models:
- **Working Days**: e.g., Monday through Friday (`0` to `4`)
- **Working Shifts**: Multiple daily time intervals (e.g., `09:00 - 13:00` and `14:00 - 18:00`)
- **Break Periods**: Dedicated break blocks (e.g., `13:00 - 14:00` Lunch Break)
- **Appointment Duration**: Configurable duration per consultation (e.g., `30` minutes)
- **Buffer Time**: Automatic gap between back-to-back appointments (e.g., `10` minutes)
- **Leaves & Holidays**: Date-range leaves with reasons (e.g., annual conference, vacation)
- **Emergency Slots**: Configurable priority reserve slots

### 2. Real-Time Slot Calculation Logic
Available slots are calculated **dynamically on demand** rather than statically pre-allocated in the database:
$$\text{Next Slot Start} = \text{Slot Start} + \text{Duration} + \text{Buffer}$$

1. Checks if the requested date falls within doctor leave dates or non-working days.
2. Iterates over shifts, generating slots of duration $D$ followed by buffer $B$.
3. Checks for break overlaps and skips break intervals.
4. Checks existing active bookings (`CONFIRMED`, `HELD`) and excludes booked intervals.
5. Excludes past times for current-day queries.
6. Returns `available_slots`, `booked_slots`, and `unavailable_periods`.

---

## 🔄 Appointment Lifecycle State Machine

Appointments transition strictly according to the following validated lifecycle:

```
                  ┌──────────────────────┐
                  │      AVAILABLE       │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │      CONFIRMED       │◄─────────────┐ (Rescheduled To)
                  └──────────┬───────────┘              │
                             │                          │
         ┌───────────────────┼───────────────────┐      │
         │                   │                   │      │
         ▼                   ▼                   ▼      │
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│    COMPLETED    │ │    CANCELLED    │ │     NO_SHOW     │
│ (Terminal State)│ │ (Terminal State)│ │ (Terminal State)│
└─────────────────┘ └────────┬────────┘ └─────────────────┘
                             │
                             └────────────► [Linked to New Appointment on Reschedule]
```

- Invalid transitions (e.g. `CANCELLED ➔ COMPLETED` or `COMPLETED ➔ CANCELLED`) are strictly rejected with `400 Bad Request`.
- Cancellation is soft and non-destructive: records `cancelled_by`, `cancelled_at`, and `cancellation_reason`.
- Rescheduling marks the previous appointment as `CANCELLED` and reserves the new slot with `CONFIRMED`, preserving bidirectional audit history (`rescheduled_from`, `rescheduled_to`).

---

## 📖 API Endpoints (Phase 1)

### Appointment Scheduling
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/v1/appointments/available-slots` | Dynamic available & booked slots | Public |
| `POST` | `/api/v1/appointments` | Book appointment with conflict checks | Patient |
| `GET` | `/api/v1/appointments` | List patient appointment history | Patient |
| `POST` | `/api/v1/appointments/{id}/cancel` | Cancel an appointment with reason | Patient/Doctor/Admin |
| `POST` | `/api/v1/appointments/{id}/reschedule` | Reschedule appointment to new slot | Patient/Admin |
| `PATCH` | `/api/v1/appointments/{id}/status` | Update lifecycle state (`COMPLETED`, `NO_SHOW`) | Doctor/Admin |

### Doctor Availability & Leave Management
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/v1/doctors` | List doctors | Public |
| `GET` | `/api/v1/doctors/{id}` | Get doctor details | Public |
| `GET` | `/api/v1/doctors/{id}/availability` | Get working hours, shifts, breaks | Public |
| `PUT` | `/api/v1/doctors/{id}/availability` | Update doctor availability | Doctor/Admin |
| `GET` | `/api/v1/doctors/{id}/leaves` | List approved leave dates | Public |
| `POST` | `/api/v1/doctors/{id}/leaves` | Add leave period | Doctor/Admin |
| `DELETE` | `/api/v1/doctors/{id}/leaves/{leave_id}` | Cancel/delete leave record | Doctor/Admin |

---

## 📋 Example Booking Flow

### 1. Query Dynamic Available Slots
`GET /api/v1/appointments/available-slots?doctor_id=60c72b2f9b1d8b2bad000001&date=2026-10-12&appointment_type=IN_PERSON`

**Response (`200 OK`)**:
```json
{
  "doctor_id": "60c72b2f9b1d8b2bad000001",
  "doctor_name": "Dr. Sarah Jenkins",
  "specialization": "Cardiology",
  "date": "2026-10-12",
  "duration_minutes": 30,
  "buffer_minutes": 10,
  "consultation_type": "IN_PERSON",
  "is_on_leave": false,
  "total_available": 10,
  "total_booked": 1,
  "available_slots": [
    { "time": "09:00", "end_time": "09:30", "status": "AVAILABLE", "is_emergency": false, "consultation_type": "IN_PERSON" },
    { "time": "09:40", "end_time": "10:10", "status": "AVAILABLE", "is_emergency": false, "consultation_type": "IN_PERSON" }
  ],
  "booked_slots": [
    { "time": "10:20", "end_time": "10:50", "status": "CONFIRMED", "is_emergency": false, "consultation_type": "IN_PERSON" }
  ],
  "unavailable_periods": [
    { "start_time": "13:00", "end_time": "14:00", "reason": "Lunch Break" }
  ]
}
```

### 2. Confirm Booking
`POST /api/v1/appointments`  
Header: `Authorization: Bearer <jwt_token>`

**Request**:
```json
{
  "doctor_id": "60c72b2f9b1d8b2bad000001",
  "date": "2026-10-12",
  "time": "09:00",
  "consultation_type": "IN_PERSON",
  "reason": "Routine Cardiology Examination",
  "patient_notes": "Mild fatigue in the mornings"
}
```

**Response (`201 Created`)**:
```json
{
  "id": "66da9bc72b2f9b1d8b200001",
  "message": "Appointment confirmed successfully",
  "status": "CONFIRMED",
  "doctor_id": "60c72b2f9b1d8b2bad000001",
  "doctor_name": "Dr. Sarah Jenkins",
  "specialization": "Cardiology",
  "patient_id": "60c72b2f9b1d8b2bad000099",
  "patient_name": "John Doe",
  "date": "2026-10-12",
  "time": "09:00",
  "end_time": "09:30",
  "duration_minutes": 30,
  "consultation_type": "IN_PERSON",
  "reason": "Routine Cardiology Examination"
}
```

---

## 🧪 Running Tests & Build

```bash
# Run backend test suite (17/17 tests)
cd backend
source venv/bin/activate
pytest backend/tests -v

# Run frontend build
cd ../frontend
npm run build
```

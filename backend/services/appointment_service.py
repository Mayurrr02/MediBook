import datetime
from typing import Optional, List, Dict, Any
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

from database import db
from models import (
    AppointmentStatus,
    Appointment,
    AppointmentResponse,
    CancelAppointmentRequest,
    RescheduleAppointmentRequest,
)
from services.lock_service import (
    acquire_slot_lock,
    verify_slot_lock,
    release_slot_lock,
    force_release_slot_lock,
)

VALID_TRANSITIONS: Dict[AppointmentStatus, set] = {
    AppointmentStatus.PENDING_CONFIRMATION: {
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.CANCELLED,
    },
    AppointmentStatus.CONFIRMED: {
        AppointmentStatus.IN_PROGRESS,
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.RESCHEDULED,
        AppointmentStatus.NO_SHOW,
    },
    AppointmentStatus.IN_PROGRESS: {
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
    },
    AppointmentStatus.COMPLETED: set(),
    AppointmentStatus.CANCELLED: set(),
    AppointmentStatus.RESCHEDULED: set(),
    AppointmentStatus.NO_SHOW: set(),
}

ACTIVE_STATUSES = [
    AppointmentStatus.CONFIRMED.value,
    AppointmentStatus.PENDING_CONFIRMATION.value,
    AppointmentStatus.IN_PROGRESS.value,
    "confirmed",
    "pending",
    "booked",
]


def _validate_transition(current: AppointmentStatus, target: AppointmentStatus):
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid state transition: Cannot change appointment status from {current.value} to {target.value}"
        )


async def book_appointment(
    doctor_id: str,
    date: str,
    time_slot: str,
    user: dict,
    lock_token: Optional[str] = None,
    reason: Optional[str] = None,
    patient_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a new appointment with distributed locking and clash prevention.
    """
    user_id = str(user["_id"])
    doctor_id = str(doctor_id).strip()
    date = str(date).strip()
    time_slot = str(time_slot).strip()

    # 1. Past date validation
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    if date < today_str:
        raise HTTPException(status_code=400, detail="Cannot book an appointment in the past.")

    # 2. Verify doctor exists
    try:
        doctor = await db.doctors.find_one({"_id": ObjectId(doctor_id)})
    except (InvalidId, Exception):
        doctor = None

    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # 3. Lock acquisition / verification
    acquired_new_lock = False
    active_token = lock_token

    if lock_token:
        is_valid_lock = await verify_slot_lock(doctor_id, date, time_slot, user_id, lock_token)
        if not is_valid_lock:
            # Try to acquire lock directly if previous expired but slot might still be free
            ok, token, _, msg = await acquire_slot_lock(doctor_id, date, time_slot, user_id, ttl_seconds=60)
            if not ok:
                raise HTTPException(status_code=409, detail="Your slot hold expired and the slot is no longer available.")
            acquired_new_lock = True
            active_token = token
    else:
        # Acquire short atomic lock for immediate booking
        ok, token, _, msg = await acquire_slot_lock(doctor_id, date, time_slot, user_id, ttl_seconds=60)
        if not ok:
            raise HTTPException(status_code=409, detail=f"Slot is currently held or unavailable: {msg}")
        acquired_new_lock = True
        active_token = token

    try:
        # 4. Check database for existing active appointment
        clash = await db.appointments.find_one({
            "doctor_id": doctor_id,
            "date": date,
            "time": time_slot,
            "status": {"$in": ACTIVE_STATUSES}
        })

        if clash:
            raise HTTPException(
                status_code=409,
                detail="This slot is already booked by another patient. Please pick another time."
            )

        # 5. Insert appointment record
        now_iso = datetime.datetime.utcnow().isoformat()
        appointment_doc = {
            "doctor_id": doctor_id,
            "doctor_name": doctor.get("name", "Doctor"),
            "specialization": doctor.get("specialization", "General"),
            "user_id": user_id,
            "user_name": user.get("name", "Patient"),
            "user_email": user.get("email", ""),
            "date": date,
            "time": time_slot,
            "status": AppointmentStatus.CONFIRMED.value,
            "reason": reason or "Consultation",
            "patient_notes": patient_notes,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        result = await db.appointments.insert_one(appointment_doc)
        appointment_id = str(result.inserted_id)

        # 6. Release lock now that DB record is safely committed
        if active_token:
            await release_slot_lock(doctor_id, date, time_slot, user_id, active_token)

        return {
            "id": appointment_id,
            "message": "Appointment confirmed successfully",
            "status": AppointmentStatus.CONFIRMED.value,
            "doctor_id": doctor_id,
            "doctor_name": doctor.get("name", "Doctor"),
            "specialization": doctor.get("specialization", "General"),
            "date": date,
            "time": time_slot,
        }

    except HTTPException:
        # Clean up lock on HTTP error
        if active_token:
            await release_slot_lock(doctor_id, date, time_slot, user_id, active_token)
        raise
    except Exception as e:
        if active_token:
            await release_slot_lock(doctor_id, date, time_slot, user_id, active_token)
        raise HTTPException(status_code=500, detail=f"Booking failed: {str(e)}")


async def cancel_appointment(
    appointment_id: str,
    user: dict,
    reason: str = "Patient requested cancellation"
) -> Dict[str, Any]:
    """
    Cancels an existing appointment, validates state transitions and authorization.
    """
    try:
        appt = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
    except (InvalidId, Exception):
        appt = None

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Verify authorization
    user_id = str(user["_id"])
    is_admin = bool(user.get("is_admin"))
    is_owner = str(appt.get("user_id")) == user_id

    # Check if user is the assigned doctor
    is_doctor = False
    if user.get("role") == "DOCTOR":
        doctor_record = await db.doctors.find_one({"user_id": user_id})
        if doctor_record and str(doctor_record["_id"]) == str(appt.get("doctor_id")):
            is_doctor = True

    if not (is_owner or is_admin or is_doctor):
        raise HTTPException(status_code=403, detail="You do not have permission to cancel this appointment")

    # Current status
    current_status_str = appt.get("status", AppointmentStatus.CONFIRMED.value).upper()
    try:
        current_status = AppointmentStatus(current_status_str)
    except ValueError:
        current_status = AppointmentStatus.CONFIRMED

    _validate_transition(current_status, AppointmentStatus.CANCELLED)

    now_iso = datetime.datetime.utcnow().isoformat()
    await db.appointments.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": {
            "status": AppointmentStatus.CANCELLED.value,
            "cancelled_at": now_iso,
            "cancelled_by": user_id,
            "cancellation_reason": reason,
            "updated_at": now_iso,
        }}
    )

    # Clear any residual lock just in case
    await force_release_slot_lock(appt["doctor_id"], appt["date"], appt["time"])

    return {
        "id": appointment_id,
        "message": "Appointment cancelled successfully",
        "status": AppointmentStatus.CANCELLED.value,
        "cancelled_at": now_iso,
    }


async def reschedule_appointment(
    appointment_id: str,
    new_date: str,
    new_time: str,
    user: dict,
    new_lock_token: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reschedules an existing appointment to a new date and time slot.
    """
    try:
        appt = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
    except (InvalidId, Exception):
        appt = None

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    user_id = str(user["_id"])
    if str(appt.get("user_id")) != user_id and not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Not authorized to reschedule this appointment")

    current_status_str = appt.get("status", AppointmentStatus.CONFIRMED.value).upper()
    try:
        current_status = AppointmentStatus(current_status_str)
    except ValueError:
        current_status = AppointmentStatus.CONFIRMED

    _validate_transition(current_status, AppointmentStatus.RESCHEDULED)

    doctor_id = str(appt["doctor_id"])

    # Book new appointment first
    new_appt_result = await book_appointment(
        doctor_id=doctor_id,
        date=new_date,
        time_slot=new_time,
        user=user,
        lock_token=new_lock_token,
        reason=reason or f"Rescheduled from {appt.get('date')} {appt.get('time')}",
    )

    now_iso = datetime.datetime.utcnow().isoformat()
    # Mark old appointment as RESCHEDULED
    await db.appointments.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": {
            "status": AppointmentStatus.RESCHEDULED.value,
            "rescheduled_to": new_appt_result["id"],
            "rescheduled_at": now_iso,
            "updated_at": now_iso,
        }}
    )

    return {
        "message": "Appointment rescheduled successfully",
        "old_appointment_id": appointment_id,
        "new_appointment": new_appt_result,
    }


async def update_appointment_status(
    appointment_id: str,
    target_status: AppointmentStatus,
    user: dict,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Updates appointment status (Doctor / Admin action).
    """
    try:
        appt = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
    except (InvalidId, Exception):
        appt = None

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    current_status_str = appt.get("status", AppointmentStatus.CONFIRMED.value).upper()
    try:
        current_status = AppointmentStatus(current_status_str)
    except ValueError:
        current_status = AppointmentStatus.CONFIRMED

    _validate_transition(current_status, target_status)

    now_iso = datetime.datetime.utcnow().isoformat()
    update_fields: Dict[str, Any] = {
        "status": target_status.value,
        "updated_at": now_iso,
    }
    if notes:
        update_fields["status_notes"] = notes

    await db.appointments.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": update_fields}
    )

    return {
        "id": appointment_id,
        "status": target_status.value,
        "message": f"Appointment status updated to {target_status.value}"
    }


async def list_user_appointments(user_id: str) -> List[Dict[str, Any]]:
    """
    Returns full appointment history for a patient with enriched doctor details.
    """
    results = []
    cursor = db.appointments.find({"user_id": str(user_id)}).sort("date", -1)

    async for a in cursor:
        doctor_id = a.get("doctor_id")
        doctor = None
        if doctor_id:
            try:
                doctor = await db.doctors.find_one({"_id": ObjectId(doctor_id)})
            except (InvalidId, Exception):
                doctor = None

        doc_name = a.get("doctor_name") or (doctor["name"] if doctor else "Unknown Doctor")
        spec = a.get("specialization") or (doctor["specialization"] if doctor else "General")

        status_val = a.get("status", AppointmentStatus.CONFIRMED.value)

        results.append({
            "_id": str(a["_id"]),
            "doctor_id": doctor_id,
            "doctor_name": doc_name,
            "specialization": spec,
            "date": a.get("date"),
            "time": a.get("time", "Not set"),
            "status": status_val,
            "reason": a.get("reason"),
            "created_at": a.get("created_at"),
            "cancelled_at": a.get("cancelled_at"),
            "cancellation_reason": a.get("cancellation_reason"),
        })

    return results

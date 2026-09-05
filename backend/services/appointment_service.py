import datetime
import logging
from typing import Optional, List, Dict, Any
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

from database import db
from models import (
    AppointmentStatus,
    ConsultationType,
    BookAppointmentRequest,
    CancelAppointmentRequest,
    RescheduleAppointmentRequest,
    UpdateAppointmentStatusRequest,
    AppointmentResponse,
)
from services.scheduling_service import (
    parse_time,
    format_time_24,
    add_minutes,
    is_overlapping,
    get_doctor_availability,
    check_doctor_leave,
)
from services.lock_service import (
    acquire_slot_lock,
    verify_slot_lock,
    release_slot_lock,
    force_release_slot_lock,
)
from services.notification_service import NotificationService

logger = logging.getLogger("medibook.appointment_service")

# Strict Lifecycle Transition Rules
VALID_TRANSITIONS: Dict[AppointmentStatus, set] = {
    AppointmentStatus.HELD: {
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.EXPIRED,
    },
    AppointmentStatus.CONFIRMED: {
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.NO_SHOW,
    },
    AppointmentStatus.COMPLETED: set(),  # Terminal state
    AppointmentStatus.CANCELLED: set(),  # Terminal state
    AppointmentStatus.NO_SHOW: set(),    # Terminal state
    AppointmentStatus.EXPIRED: set(),    # Terminal state
    AppointmentStatus.AVAILABLE: {
        AppointmentStatus.HELD,
        AppointmentStatus.CONFIRMED,
    },
}

ACTIVE_STATUSES = [
    AppointmentStatus.CONFIRMED.value,
    AppointmentStatus.HELD.value,
    "confirmed",
    "pending",
    "booked",
]


def validate_state_transition(current: AppointmentStatus, target: AppointmentStatus):
    """Ensures state transitions strictly adhere to lifecycle rules."""
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid state transition: Cannot change appointment status from {current.value} to {target.value}"
        )


def _validate_transition(current: AppointmentStatus, target: AppointmentStatus):
    validate_state_transition(current, target)


async def book_appointment(
    doctor_id: str,
    date: str,
    time_slot: str,
    user: dict,
    consultation_type: ConsultationType = ConsultationType.IN_PERSON,
    reason: Optional[str] = "General Consultation",
    patient_notes: Optional[str] = None,
    lock_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Atomic appointment booking flow:
    Request -> Validate appointment -> Acquire Redis lock -> Verify database state -> Create appointment -> Confirm booking -> Release lock.
    """
    user_id = str(user.get("_id") or user.get("id"))
    doctor_id = str(doctor_id).strip()
    date_str = str(date).strip()
    time_str = str(time_slot).strip()

    # 1. Validate Date & Time Format
    try:
        req_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")

    try:
        slot_time = parse_time(time_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time format: {time_str}")

    # 2. Prevent Past Appointments
    now = datetime.datetime.now()
    today = now.date()
    if req_date < today:
        raise HTTPException(status_code=400, detail="Cannot book an appointment in the past.")
    if req_date == today and slot_time <= now.time():
        raise HTTPException(status_code=400, detail="Cannot book a time slot that has already passed.")

    # 3. Verify Doctor Exists
    try:
        doctor = await db.doctors.find_one({"_id": ObjectId(doctor_id)})
    except Exception:
        doctor = None

    if not doctor:
        raise HTTPException(status_code=404, detail=f"Doctor with ID {doctor_id} not found.")

    # 4. Verify Patient Exists
    try:
        patient = await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        patient = None

    if not patient and not user.get("email"):
        raise HTTPException(status_code=404, detail=f"Patient user not found.")

    patient_name = patient.get("name") if patient else user.get("name", "Patient")
    patient_email = patient.get("email") if patient else user.get("email", "")

    # 5. Check Doctor Availability & Leave
    leave = await check_doctor_leave(doctor_id, date_str)
    if leave:
        raise HTTPException(
            status_code=409,
            detail=f"Doctor is unavailable on {date_str} due to leave: {leave.reason}"
        )

    avail = await get_doctor_availability(doctor_id)
    if req_date.weekday() not in avail.working_days:
        raise HTTPException(
            status_code=400,
            detail=f"Doctor is not available on {req_date.strftime('%A')}s."
        )

    duration = avail.duration_minutes
    slot_end_time = add_minutes(slot_time, duration)

    # Check Breaks Overlap
    for b in avail.breaks:
        try:
            b_start = parse_time(b.start_time)
            b_end = parse_time(b.end_time)
            if is_overlapping(slot_time, slot_end_time, b_start, b_end):
                raise HTTPException(
                    status_code=409,
                    detail=f"Requested slot overlaps with doctor's scheduled break ({b.title}: {b.start_time} - {b.end_time})."
                )
        except HTTPException:
            raise
        except Exception:
            pass

    # 6. Atomic Distributed Redis Lock
    acquired_lock = False
    active_token = lock_token

    if lock_token:
        # Verify existing hold
        is_valid = await verify_slot_lock(doctor_id, date_str, time_str, user_id, lock_token)
        if not is_valid:
            # Attempt to re-acquire
            ok, token, _, msg = await acquire_slot_lock(doctor_id, date_str, time_str, user_id, ttl_seconds=60)
            if not ok:
                raise HTTPException(status_code=409, detail=f"Slot hold expired or unavailable: {msg}")
            acquired_lock = True
            active_token = token
    else:
        # Acquire fresh mutex lock for the booking duration
        ok, token, _, msg = await acquire_slot_lock(doctor_id, date_str, time_str, user_id, ttl_seconds=60)
        if not ok:
            raise HTTPException(status_code=409, detail=f"Slot is currently on hold or unavailable: {msg}")
        acquired_lock = True
        active_token = token

    try:
        # 7. Verify Database State (Clash check)
        existing_cursor = db.appointments.find({
            "doctor_id": doctor_id,
            "date": date_str,
            "status": {"$in": ACTIVE_STATUSES}
        })

        async for appt in existing_cursor:
            try:
                ex_start = parse_time(appt.get("time", ""))
                ex_dur = appt.get("duration_minutes", duration)
                ex_end = add_minutes(ex_start, ex_dur)
                if is_overlapping(slot_time, slot_end_time, ex_start, ex_end):
                    raise HTTPException(
                        status_code=409,
                        detail="This appointment slot is already booked. Please choose another available slot."
                    )
            except HTTPException:
                raise
            except Exception:
                pass

        # 8. Insert Appointment Record
        now_iso = datetime.datetime.utcnow().isoformat()
        c_val = consultation_type.value if hasattr(consultation_type, "value") else str(consultation_type)
        appointment_doc = {
            "doctor_id": doctor_id,
            "doctor_name": doctor.get("name", "Doctor"),
            "specialization": doctor.get("specialization", "General Medicine"),
            "patient_id": user_id,
            "user_id": user_id,
            "patient_name": patient_name,
            "patient_email": patient_email,
            "date": date_str,
            "time": format_time_24(slot_time),
            "end_time": format_time_24(slot_end_time),
            "duration_minutes": duration,
            "consultation_type": c_val,
            "status": AppointmentStatus.CONFIRMED.value,
            "reason": reason or "General Consultation",
            "patient_notes": patient_notes,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        result = await db.appointments.insert_one(appointment_doc)
        appointment_id = str(result.inserted_id)

        # 9. Release Redis Lock now that DB transaction is persisted
        if active_token:
            await release_slot_lock(doctor_id, date_str, time_str, user_id, active_token)

        # 10. Send Confirmation Notification (Non-blocking)
        try:
            NotificationService.notify_appointment_confirmation(
                patient_email=patient_email,
                patient_name=patient_name,
                doctor_name=doctor.get("name", "Doctor"),
                date=date_str,
                time=format_time_24(slot_time),
                consultation_type=c_val,
                appointment_id=appointment_id,
            )
        except Exception as e:
            logger.warning(f"Error sending confirmation notification: {e}")

        return {
            "id": appointment_id,
            "_id": appointment_id,
            "message": "Appointment confirmed successfully",
            "status": AppointmentStatus.CONFIRMED.value,
            "doctor_id": doctor_id,
            "doctor_name": doctor.get("name", "Doctor"),
            "specialization": doctor.get("specialization", "General Medicine"),
            "patient_id": user_id,
            "patient_name": patient_name,
            "date": date_str,
            "time": format_time_24(slot_time),
            "end_time": format_time_24(slot_end_time),
            "duration_minutes": duration,
            "consultation_type": c_val,
            "reason": appointment_doc["reason"],
        }

    except Exception as e:
        # Always release lock on failure/rollback
        if active_token:
            await release_slot_lock(doctor_id, date_str, time_str, user_id, active_token)
        raise


async def cancel_appointment(
    appointment_id: str,
    user: dict,
    reason: str = "Patient requested cancellation"
) -> Dict[str, Any]:
    """
    Cancels an existing appointment, triggers automated waitlist promotion,
    and dispatches cancellation notification without physical deletion.
    """
    try:
        appt = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
    except (InvalidId, Exception):
        appt = None

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    user_id = str(user.get("_id") or user.get("id"))
    is_admin = bool(user.get("is_admin"))
    is_owner = (str(appt.get("patient_id")) == user_id or str(appt.get("user_id")) == user_id)

    is_doctor = False
    if user.get("role") == "DOCTOR":
        doctor_record = await db.doctors.find_one({"user_id": user_id})
        if doctor_record and str(doctor_record["_id"]) == str(appt.get("doctor_id")):
            is_doctor = True

    if not (is_owner or is_admin or is_doctor):
        raise HTTPException(status_code=403, detail="You do not have permission to cancel this appointment.")

    current_status_str = appt.get("status", AppointmentStatus.CONFIRMED.value).upper()
    try:
        current_status = AppointmentStatus(current_status_str)
    except ValueError:
        current_status = AppointmentStatus.CONFIRMED

    validate_state_transition(current_status, AppointmentStatus.CANCELLED)

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

    doctor_id = str(appt["doctor_id"])
    date_str = str(appt["date"])
    time_str = str(appt["time"])

    # Force release any stale lock
    await force_release_slot_lock(doctor_id, date_str, time_str)

    # AUTOMATIC WAITLIST PROCESSING: Promote next waitlist candidate
    try:
        from services.waitlist_service import process_waitlist_on_cancellation
        await process_waitlist_on_cancellation(doctor_id, date_str, time_str)
    except Exception as e:
        logger.warning(f"Error during automatic waitlist processing on cancellation: {e}")

    # Dispatch cancellation notice
    try:
        NotificationService.notify_cancellation(
            patient_email=appt.get("patient_email", ""),
            patient_name=appt.get("patient_name", "Patient"),
            doctor_name=appt.get("doctor_name", "Doctor"),
            date=date_str,
            time=time_str,
            reason=reason,
        )
    except Exception as e:
        logger.warning(f"Error sending cancellation notification: {e}")

    return {
        "id": appointment_id,
        "message": "Appointment cancelled successfully.",
        "status": AppointmentStatus.CANCELLED.value,
        "cancelled_at": now_iso,
        "cancelled_by": user_id,
        "cancellation_reason": reason,
    }


async def reschedule_appointment(
    appointment_id: str,
    new_date: str,
    new_time: str,
    user: dict,
    new_consultation_type: Optional[ConsultationType] = None,
    new_lock_token: Optional[str] = None,
    reason: Optional[str] = "Patient rescheduled appointment",
) -> Dict[str, Any]:
    """
    Reschedules an appointment by booking new slot with lock, releasing old slot,
    and preserving bidirectional history.
    """
    try:
        appt = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
    except (InvalidId, Exception):
        appt = None

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    user_id = str(user.get("_id") or user.get("id"))
    is_admin = bool(user.get("is_admin"))
    is_owner = (str(appt.get("patient_id")) == user_id or str(appt.get("user_id")) == user_id)

    if not (is_owner or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to reschedule this appointment.")

    current_status_str = appt.get("status", AppointmentStatus.CONFIRMED.value).upper()
    try:
        current_status = AppointmentStatus(current_status_str)
    except ValueError:
        current_status = AppointmentStatus.CONFIRMED

    if current_status != AppointmentStatus.CONFIRMED and current_status != AppointmentStatus.HELD:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reschedule an appointment with status {current_status.value}."
        )

    doctor_id = str(appt["doctor_id"])
    c_type = new_consultation_type or ConsultationType(appt.get("consultation_type", ConsultationType.IN_PERSON.value))

    # 1. Book the new appointment first
    new_appt_result = await book_appointment(
        doctor_id=doctor_id,
        date=new_date,
        time_slot=new_time,
        user=user,
        consultation_type=c_type,
        reason=reason or f"Rescheduled from {appt.get('date')} {appt.get('time')}",
        patient_notes=appt.get("patient_notes"),
        lock_token=new_lock_token,
    )

    # 2. Cancel old appointment and link history
    now_iso = datetime.datetime.utcnow().isoformat()
    await db.appointments.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": {
            "status": AppointmentStatus.CANCELLED.value,
            "rescheduled_to": new_appt_result["id"],
            "cancelled_at": now_iso,
            "cancelled_by": user_id,
            "cancellation_reason": f"Rescheduled to {new_date} at {new_time}",
            "updated_at": now_iso,
        }}
    )

    # 3. Link new appointment back to old
    await db.appointments.update_one(
        {"_id": ObjectId(new_appt_result["id"])},
        {"$set": {
            "rescheduled_from": appointment_id,
            "updated_at": now_iso,
        }}
    )

    # Auto-promote waitlist on old slot
    try:
        from services.waitlist_service import process_waitlist_on_cancellation
        await process_waitlist_on_cancellation(doctor_id, appt["date"], appt["time"])
    except Exception as e:
        logger.warning(f"Waitlist promotion error on reschedule: {e}")

    return {
        "message": "Appointment rescheduled successfully.",
        "previous_appointment_id": appointment_id,
        "new_appointment": new_appt_result,
    }


async def update_appointment_status(
    appointment_id: str,
    target_status: AppointmentStatus,
    user: dict,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Updates appointment lifecycle status (Admin / Doctor).
    """
    try:
        appt = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
    except (InvalidId, Exception):
        appt = None

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    current_status_str = appt.get("status", AppointmentStatus.CONFIRMED.value).upper()
    try:
        current_status = AppointmentStatus(current_status_str)
    except ValueError:
        current_status = AppointmentStatus.CONFIRMED

    validate_state_transition(current_status, target_status)

    now_iso = datetime.datetime.utcnow().isoformat()
    update_data: Dict[str, Any] = {
        "status": target_status.value,
        "updated_at": now_iso,
    }
    if notes:
        update_data["status_notes"] = notes

    await db.appointments.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": update_data}
    )

    return {
        "id": appointment_id,
        "status": target_status.value,
        "message": f"Appointment status updated to {target_status.value}."
    }


async def list_user_appointments(user_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves appointment history for a user sorted chronologically.
    """
    results = []
    cursor = db.appointments.find({
        "$or": [{"patient_id": str(user_id)}, {"user_id": str(user_id)}]
    }).sort("date", -1)

    async for a in cursor:
        doctor_id = a.get("doctor_id")
        doctor = None
        if doctor_id:
            try:
                doctor = await db.doctors.find_one({"_id": ObjectId(doctor_id)})
            except Exception:
                pass

        doc_name = a.get("doctor_name") or (doctor["name"] if doctor else "Unknown Doctor")
        spec = a.get("specialization") or (doctor["specialization"] if doctor else "General Medicine")

        results.append({
            "_id": str(a["_id"]),
            "id": str(a["_id"]),
            "doctor_id": doctor_id,
            "doctor_name": doc_name,
            "specialization": spec,
            "date": a.get("date"),
            "time": a.get("time", "09:00"),
            "end_time": a.get("end_time"),
            "duration_minutes": a.get("duration_minutes", 30),
            "consultation_type": a.get("consultation_type", "IN_PERSON"),
            "status": a.get("status", AppointmentStatus.CONFIRMED.value),
            "reason": a.get("reason"),
            "patient_notes": a.get("patient_notes"),
            "created_at": a.get("created_at"),
            "cancelled_at": a.get("cancelled_at"),
            "cancellation_reason": a.get("cancellation_reason"),
            "rescheduled_to": a.get("rescheduled_to"),
            "rescheduled_from": a.get("rescheduled_from"),
        })

    return results

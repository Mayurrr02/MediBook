from typing import List, Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models import (
    Appointment,
    CancelAppointmentRequest,
    RescheduleAppointmentRequest,
    UpdateAppointmentStatusRequest,
    AppointmentResponse,
    AppointmentStatus,
)
from dependencies import get_current_user
from services.appointment_service import (
    book_appointment as service_book_appointment,
    cancel_appointment as service_cancel_appointment,
    reschedule_appointment as service_reschedule_appointment,
    update_appointment_status as service_update_appointment_status,
    list_user_appointments,
)

router = APIRouter(tags=["appointments"])


@router.post("/appointment")
async def book_appointment(appo: Appointment, user: dict = Depends(get_current_user)):
    """
    Books an appointment for the authenticated patient with distributed locking
    and double-booking prevention.
    """
    res = await service_book_appointment(
        doctor_id=appo.doctor_id,
        date=appo.date,
        time_slot=appo.time,
        user=user,
        lock_token=appo.lock_token,
        reason=appo.reason,
        patient_notes=appo.patient_notes,
    )
    return {
        "message": "appointment created",
        "id": res["id"],
        "status": res.get("status", AppointmentStatus.CONFIRMED.value),
        "doctor_name": res.get("doctor_name"),
        "date": res.get("date"),
        "time": res.get("time"),
    }


@router.get("/appointments")
async def get_appointments(user: dict = Depends(get_current_user)):
    """
    Retrieves all appointments booked by the authenticated user.
    """
    return await list_user_appointments(user["_id"])


@router.get("/appointments/{appointment_id}")
async def get_appointment_by_id(appointment_id: str, user: dict = Depends(get_current_user)):
    """
    Retrieves a single appointment by ID with permission check.
    """
    try:
        appt = await db.appointments.find_one({"_id": ObjectId(appointment_id)})
    except (InvalidId, Exception):
        appt = None

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    user_id = str(user["_id"])
    is_owner = str(appt.get("user_id")) == user_id
    is_admin = bool(user.get("is_admin"))

    if not (is_owner or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to view this appointment")

    doctor = None
    if appt.get("doctor_id"):
        try:
            doctor = await db.doctors.find_one({"_id": ObjectId(appt["doctor_id"])})
        except Exception:
            pass

    return {
        "_id": str(appt["_id"]),
        "doctor_id": appt.get("doctor_id"),
        "doctor_name": appt.get("doctor_name") or (doctor["name"] if doctor else "Unknown Doctor"),
        "specialization": appt.get("specialization") or (doctor["specialization"] if doctor else "General"),
        "date": appt.get("date"),
        "time": appt.get("time"),
        "status": appt.get("status", AppointmentStatus.CONFIRMED.value),
        "reason": appt.get("reason"),
        "patient_notes": appt.get("patient_notes"),
        "created_at": appt.get("created_at"),
        "cancelled_at": appt.get("cancelled_at"),
        "cancellation_reason": appt.get("cancellation_reason"),
    }


@router.post("/appointments/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: str,
    req: CancelAppointmentRequest = CancelAppointmentRequest(),
    user: dict = Depends(get_current_user)
):
    """
    Cancels an existing appointment.
    """
    return await service_cancel_appointment(
        appointment_id=appointment_id,
        user=user,
        reason=req.reason or "Patient requested cancellation"
    )


@router.post("/appointments/{appointment_id}/reschedule")
async def reschedule_appointment(
    appointment_id: str,
    req: RescheduleAppointmentRequest,
    user: dict = Depends(get_current_user)
):
    """
    Reschedules an existing appointment to a new date/time slot.
    """
    return await service_reschedule_appointment(
        appointment_id=appointment_id,
        new_date=req.new_date,
        new_time=req.new_time,
        user=user,
        new_lock_token=req.new_lock_token,
        reason=req.reason,
    )


@router.patch("/appointments/{appointment_id}/status")
async def update_status(
    appointment_id: str,
    req: UpdateAppointmentStatusRequest,
    user: dict = Depends(get_current_user)
):
    """
    Updates the lifecycle status of an appointment (Doctor / Admin).
    """
    return await service_update_appointment_status(
        appointment_id=appointment_id,
        target_status=req.status,
        user=user,
        notes=req.notes
    )

import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from models import (
    AvailableSlotsResponse,
    BookAppointmentRequest,
    Appointment,
    CancelAppointmentRequest,
    RescheduleAppointmentRequest,
    UpdateAppointmentStatusRequest,
    SlotHoldRequest,
    SlotHoldResponse,
    SlotReleaseRequest,
    ConsultationType,
)
from dependencies import get_current_user
from services.scheduling_service import calculate_available_slots
from services.appointment_service import (
    book_appointment as service_book_appointment,
    cancel_appointment as service_cancel_appointment,
    reschedule_appointment as service_reschedule_appointment,
    update_appointment_status as service_update_appointment_status,
    list_user_appointments,
)
from services.lock_service import (
    acquire_slot_lock,
    release_slot_lock,
)

router = APIRouter(tags=["appointments"])


# --- Slot Generation Endpoint ---
@router.get("/api/v1/appointments/available-slots", response_model=AvailableSlotsResponse)
@router.get("/appointments/available-slots", response_model=AvailableSlotsResponse)
async def get_available_slots(
    doctor_id: str = Query(..., description="ID of the doctor"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (defaults to today)"),
    appointment_type: Optional[str] = Query(None, description="IN_PERSON or VIDEO"),
):
    """
    Dynamically generates and returns available appointment slots, booked slots,
    and unavailable periods (breaks, leaves, off-hours) for a doctor on a specific date.
    """
    if not date:
        date = datetime.date.today().strftime("%Y-%m-%d")

    c_type_enum = None
    if appointment_type:
        try:
            c_type_enum = ConsultationType(appointment_type.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid appointment_type: {appointment_type}. Must be IN_PERSON or VIDEO.")

    try:
        return await calculate_available_slots(
            doctor_id=doctor_id,
            date_str=date,
            appointment_type=c_type_enum,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate slots: {str(e)}")


# --- Distributed Slot Locking (Temporary Hold) ---
@router.post("/api/v1/appointments/hold-slot", response_model=SlotHoldResponse)
@router.post("/api/v1/slots/hold", response_model=SlotHoldResponse)
async def hold_slot_endpoint(
    req: SlotHoldRequest,
    user: dict = Depends(get_current_user)
):
    """
    Acquires an atomic distributed lock on an appointment slot for 5 minutes (TTL),
    preventing other users from taking the slot during checkout.
    """
    user_id = str(user.get("_id") or user.get("id"))
    success, lock_token, expires_in, msg = await acquire_slot_lock(
        doctor_id=req.doctor_id,
        date=req.date,
        time_slot=req.time,
        user_id=user_id,
        ttl_seconds=req.ttl_seconds or 300,
    )

    if not success:
        raise HTTPException(status_code=409, detail=msg)

    return SlotHoldResponse(
        success=True,
        lock_token=lock_token,
        doctor_id=req.doctor_id,
        date=req.date,
        time=req.time,
        expires_in_seconds=expires_in,
        message=msg,
    )


@router.post("/api/v1/appointments/release-slot")
@router.post("/api/v1/slots/release")
async def release_slot_endpoint(
    req: SlotReleaseRequest,
    user: dict = Depends(get_current_user)
):
    """
    Releases a held slot lock early if patient closes modal or deselects slot.
    """
    user_id = str(user.get("_id") or user.get("id"))
    released = await release_slot_lock(
        doctor_id=req.doctor_id,
        date=req.date,
        time_slot=req.time,
        user_id=user_id,
        lock_token=req.lock_token,
    )
    if not released:
        raise HTTPException(status_code=400, detail="Unable to release lock (expired or invalid token).")
    return {"status": "released", "message": "Slot lock released successfully."}


# --- Booking Endpoints ---
@router.post("/api/v1/appointments", status_code=201)
@router.post("/appointment", status_code=201)
@router.post("/appointments", status_code=201)
async def book_new_appointment(
    req: BookAppointmentRequest,
    user: dict = Depends(get_current_user)
):
    """
    Validates availability, ensures no conflict, and books a new appointment.
    """
    return await service_book_appointment(
        doctor_id=req.doctor_id,
        date=req.date,
        time_slot=req.time,
        user=user,
        consultation_type=req.consultation_type,
        reason=req.reason,
        patient_notes=req.patient_notes,
        lock_token=req.lock_token,
    )


# --- User Appointments History ---
@router.get("/api/v1/appointments")
@router.get("/appointments")
async def get_my_appointments(user: dict = Depends(get_current_user)):
    """
    Returns all appointments booked by the current authenticated user.
    """
    return await list_user_appointments(user.get("_id") or user.get("id"))


# --- Cancellation ---
@router.post("/api/v1/appointments/{appointment_id}/cancel")
@router.post("/appointments/{appointment_id}/cancel")
async def cancel_appointment_endpoint(
    appointment_id: str,
    req: CancelAppointmentRequest = CancelAppointmentRequest(),
    user: dict = Depends(get_current_user)
):
    """
    Cancels an appointment, recording audit information without deleting the record.
    """
    return await service_cancel_appointment(
        appointment_id=appointment_id,
        user=user,
        reason=req.reason
    )


# --- Rescheduling ---
@router.post("/api/v1/appointments/{appointment_id}/reschedule")
@router.post("/appointments/{appointment_id}/reschedule")
@router.patch("/api/v1/appointments/{appointment_id}/reschedule")
async def reschedule_appointment_endpoint(
    appointment_id: str,
    req: RescheduleAppointmentRequest,
    user: dict = Depends(get_current_user)
):
    """
    Reschedules an appointment to a new date and time slot, preserving appointment history.
    """
    return await service_reschedule_appointment(
        appointment_id=appointment_id,
        new_date=req.new_date,
        new_time=req.new_time,
        user=user,
        new_consultation_type=req.new_consultation_type,
        new_lock_token=req.new_lock_token,
        reason=req.reason,
    )


# --- Status Update (Doctor / Admin) ---
@router.patch("/api/v1/appointments/{appointment_id}/status")
@router.patch("/appointments/{appointment_id}/status")
async def update_status_endpoint(
    appointment_id: str,
    req: UpdateAppointmentStatusRequest,
    user: dict = Depends(get_current_user)
):
    """
    Transitions appointment lifecycle state (e.g. COMPLETED, NO_SHOW).
    """
    return await service_update_appointment_status(
        appointment_id=appointment_id,
        target_status=req.status,
        user=user,
        notes=req.notes
    )

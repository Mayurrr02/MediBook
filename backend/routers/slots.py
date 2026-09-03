import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from jose import JWTError

from auth import decode_token
from dependencies import get_current_user
from models import (
    DoctorSlotsResponse,
    LockSlotRequest,
    LockSlotResponse,
    UnlockSlotRequest,
)
from services.scheduling_service import compute_doctor_slots
from services.lock_service import acquire_slot_lock, release_slot_lock

router = APIRouter(tags=["slots"])


async def get_optional_user_id(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Helper to extract user ID if Bearer token is provided, without forcing 401."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split("Bearer ")[1]
    try:
        payload = decode_token(token)
        return payload.get("id")
    except JWTError:
        return None


@router.get("/doctors/{doctor_id}/slots", response_model=DoctorSlotsResponse)
async def get_doctor_slots(
    doctor_id: str,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Returns real-time dynamic slot availability for a doctor on a specific date.
    Reflects working hours, breaks, existing bookings, and active distributed locks.
    """
    if not date:
        date = datetime.date.today().strftime("%Y-%m-%d")

    try:
        slots_response = await compute_doctor_slots(
            doctor_id=doctor_id,
            date_str=date,
            current_user_id=user_id
        )
        return slots_response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch slots: {str(e)}")


@router.post("/slots/lock", response_model=LockSlotResponse)
async def lock_slot(
    req: LockSlotRequest,
    user: dict = Depends(get_current_user),
):
    """
    Acquires an atomic distributed lock on a slot for 5 minutes (or custom TTL),
    preventing double booking while patient completes booking/checkout.
    """
    user_id = str(user["_id"])
    success, lock_token, expires_in, message = await acquire_slot_lock(
        doctor_id=req.doctor_id,
        date=req.date,
        time_slot=req.time,
        user_id=user_id,
        ttl_seconds=req.ttl_seconds or 300,
    )

    if not success:
        raise HTTPException(
            status_code=409,
            detail=message
        )

    return LockSlotResponse(
        success=True,
        lock_token=lock_token,
        doctor_id=req.doctor_id,
        date=req.date,
        time=req.time,
        expires_in_seconds=expires_in,
        message=message,
    )


@router.post("/slots/unlock")
async def unlock_slot(
    req: UnlockSlotRequest,
    user: dict = Depends(get_current_user),
):
    """
    Releases a held slot lock early if patient cancels or closes modal.
    """
    user_id = str(user["_id"])
    released = await release_slot_lock(
        doctor_id=req.doctor_id,
        date=req.date,
        time_slot=req.time,
        user_id=user_id,
        lock_token=req.lock_token,
    )

    if not released:
        raise HTTPException(
            status_code=400,
            detail="Lock could not be released (either expired or token invalid)"
        )

    return {"status": "unlocked", "message": "Slot lock released successfully"}

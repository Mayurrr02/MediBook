from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from models import WaitlistCreateRequest, WaitlistResponse
from dependencies import get_current_user
from services.waitlist_service import (
    join_waitlist as service_join_waitlist,
    list_patient_waitlists,
    cancel_waitlist_entry as service_cancel_waitlist,
    claim_waitlist_slot as service_claim_waitlist,
)

router = APIRouter(prefix="/api/v1/waitlists", tags=["waitlists"])


@router.post("", status_code=201)
async def join_waitlist_endpoint(
    req: WaitlistCreateRequest,
    user: dict = Depends(get_current_user)
):
    """
    Adds patient to the waitlist for a fully-booked doctor and date.
    """
    return await service_join_waitlist(req, user)


@router.get("/me")
async def get_my_waitlist(user: dict = Depends(get_current_user)):
    """
    Returns all active and historical waitlist requests for the logged-in patient.
    """
    user_id = str(user.get("_id") or user.get("id"))
    return await list_patient_waitlists(user_id)


@router.post("/{waitlist_id}/cancel")
async def cancel_waitlist_endpoint(
    waitlist_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Cancels a pending waitlist entry.
    """
    return await service_cancel_waitlist(waitlist_id, user)


@router.post("/{waitlist_id}/claim")
async def claim_waitlist_endpoint(
    waitlist_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Claims an offered slot before the claim deadline expires.
    """
    return await service_claim_waitlist(waitlist_id, user)

import datetime
import logging
from typing import Optional, List, Dict, Any
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

from database import db
from models import (
    WaitlistStatus,
    WaitlistCreateRequest,
    WaitlistResponse,
    ConsultationType,
    AppointmentStatus,
)
from config import WAITLIST_CLAIM_WINDOW_MINUTES
from services.lock_service import acquire_slot_lock, release_slot_lock
from services.notification_service import NotificationService

logger = logging.getLogger("medibook.waitlist")


async def join_waitlist(
    req: WaitlistCreateRequest,
    user: dict
) -> Dict[str, Any]:
    """
    Adds a patient to the FIFO waitlist for a specific doctor, date, and preferred slot.
    """
    user_id = str(user.get("_id") or user.get("id"))
    doctor_id = str(req.doctor_id).strip()

    # 1. Verify doctor exists
    try:
        doctor = await db.doctors.find_one({"_id": ObjectId(doctor_id)})
    except Exception:
        doctor = None

    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found.")

    # 2. Prevent duplicate active waitlist entry for the same user, doctor, and date
    existing = await db.waitlists.find_one({
        "patient_id": user_id,
        "doctor_id": doctor_id,
        "preferred_date": req.preferred_date,
        "status": {"$in": [WaitlistStatus.WAITING.value, WaitlistStatus.NOTIFIED.value]}
    })
    if existing:
        raise HTTPException(
            status_code=409,
            detail="You are already on the active waitlist for this doctor and date."
        )

    now_iso = datetime.datetime.utcnow().isoformat()
    waitlist_doc = {
        "patient_id": user_id,
        "patient_name": user.get("name", "Patient"),
        "patient_email": user.get("email", ""),
        "doctor_id": doctor_id,
        "doctor_name": doctor.get("name", "Doctor"),
        "specialization": doctor.get("specialization", "General Medicine"),
        "preferred_date": req.preferred_date,
        "preferred_time": req.preferred_time,
        "consultation_type": req.consultation_type.value if hasattr(req.consultation_type, "value") else str(req.consultation_type),
        "status": WaitlistStatus.WAITING.value,
        "notes": req.notes,
        "created_at": now_iso,
        "updated_at": now_iso,
        "notified_at": None,
        "claim_deadline": None,
    }

    result = await db.waitlists.insert_one(waitlist_doc)
    waitlist_id = str(result.inserted_id)

    return {
        "id": waitlist_id,
        "message": "Successfully joined the waitlist.",
        "status": WaitlistStatus.WAITING.value,
        "doctor_name": doctor.get("name", "Doctor"),
        "preferred_date": req.preferred_date,
        "preferred_time": req.preferred_time,
    }


async def list_patient_waitlists(patient_id: str) -> List[Dict[str, Any]]:
    """
    Retrieves all waitlist entries for the authenticated patient.
    """
    results = []
    cursor = db.waitlists.find({"patient_id": str(patient_id)}).sort("created_at", -1)
    async for w in cursor:
        results.append({
            "id": str(w["_id"]),
            "_id": str(w["_id"]),
            "patient_id": str(patient_id),
            "patient_name": w.get("patient_name"),
            "doctor_id": w.get("doctor_id"),
            "doctor_name": w.get("doctor_name", "Doctor"),
            "specialization": w.get("specialization", "General Medicine"),
            "preferred_date": w.get("preferred_date"),
            "preferred_time": w.get("preferred_time"),
            "consultation_type": w.get("consultation_type", "IN_PERSON"),
            "status": w.get("status", WaitlistStatus.WAITING.value),
            "created_at": w.get("created_at"),
            "notified_at": w.get("notified_at"),
            "claim_deadline": w.get("claim_deadline"),
            "notes": w.get("notes"),
        })
    return results


async def cancel_waitlist_entry(waitlist_id: str, user: dict) -> Dict[str, Any]:
    """
    Cancels a waitlist entry.
    """
    user_id = str(user.get("_id") or user.get("id"))
    is_admin = bool(user.get("is_admin"))

    try:
        w_entry = await db.waitlists.find_one({"_id": ObjectId(waitlist_id)})
    except Exception:
        w_entry = None

    if not w_entry:
        raise HTTPException(status_code=404, detail="Waitlist entry not found.")

    if str(w_entry.get("patient_id")) != user_id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this waitlist entry.")

    now_iso = datetime.datetime.utcnow().isoformat()
    await db.waitlists.update_one(
        {"_id": ObjectId(waitlist_id)},
        {"$set": {
            "status": WaitlistStatus.CANCELLED.value,
            "updated_at": now_iso,
        }}
    )

    return {"id": waitlist_id, "message": "Waitlist entry cancelled successfully."}


async def process_waitlist_on_cancellation(
    doctor_id: str,
    date_str: str,
    time_slot: str
) -> Optional[Dict[str, Any]]:
    """
    FIFO queue processing: Called when an appointment is cancelled.
    Finds the next eligible patient in the waitlist, marks them NOTIFIED, holds the slot,
    and sends a notification with a claim window deadline.
    """
    # Find matching waiting patients in FIFO order (oldest created_at first)
    query = {
        "doctor_id": str(doctor_id),
        "preferred_date": date_str,
        "$or": [
            {"preferred_time": time_slot},
            {"preferred_time": None},
            {"preferred_time": ""},
        ],
        "status": WaitlistStatus.WAITING.value,
    }

    next_candidate = await db.waitlists.find_one(query)
    if not next_candidate:
        logger.info(f"No waitlisted patients for doctor {doctor_id} on {date_str} at {time_slot}.")
        return None

    waitlist_id = str(next_candidate["_id"])
    patient_id = str(next_candidate["patient_id"])
    patient_email = next_candidate.get("patient_email")
    patient_name = next_candidate.get("patient_name", "Patient")
    doctor_name = next_candidate.get("doctor_name", "Doctor")

    # Set claim deadline (e.g. 15 minutes from now)
    now = datetime.datetime.utcnow()
    deadline = now + datetime.timedelta(minutes=WAITLIST_CLAIM_WINDOW_MINUTES)
    deadline_iso = deadline.isoformat()
    now_iso = now.isoformat()

    # Acquire temporary slot hold in Redis for this candidate
    ttl_seconds = WAITLIST_CLAIM_WINDOW_MINUTES * 60
    ok, lock_token, _, _ = await acquire_slot_lock(
        doctor_id=doctor_id,
        date=date_str,
        time_slot=time_slot,
        user_id=patient_id,
        ttl_seconds=ttl_seconds
    )

    # Update waitlist status to NOTIFIED
    await db.waitlists.update_one(
        {"_id": ObjectId(waitlist_id)},
        {"$set": {
            "status": WaitlistStatus.NOTIFIED.value,
            "notified_at": now_iso,
            "claim_deadline": deadline_iso,
            "lock_token": lock_token,
            "assigned_time": time_slot,
            "updated_at": now_iso,
        }}
    )

    # Dispatch notification
    NotificationService.notify_waitlist_promoted(
        patient_email=patient_email,
        patient_name=patient_name,
        doctor_name=doctor_name,
        date=date_str,
        time=time_slot,
        claim_deadline=deadline.strftime("%H:%M UTC"),
    )

    logger.info(f"Promoted waitlist patient {patient_name} ({patient_id}) for slot {date_str} {time_slot}. Deadline: {deadline_iso}")

    return {
        "waitlist_id": waitlist_id,
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "date": date_str,
        "time": time_slot,
        "claim_deadline": deadline_iso,
    }


async def claim_waitlist_slot(
    waitlist_id: str,
    user: dict,
    reason: Optional[str] = "Claimed from Waitlist"
) -> Dict[str, Any]:
    """
    Patient claims an offered waitlist slot before the deadline expires.
    """
    from services.appointment_service import book_appointment

    user_id = str(user.get("_id") or user.get("id"))
    try:
        w_entry = await db.waitlists.find_one({"_id": ObjectId(waitlist_id)})
    except Exception:
        w_entry = None

    if not w_entry:
        raise HTTPException(status_code=404, detail="Waitlist entry not found.")

    if str(w_entry.get("patient_id")) != user_id:
        raise HTTPException(status_code=403, detail="You can only claim your own waitlist slot.")

    if w_entry.get("status") != WaitlistStatus.NOTIFIED.value:
        raise HTTPException(status_code=400, detail=f"Waitlist status is {w_entry.get('status')}; only NOTIFIED slots can be claimed.")

    # Check deadline
    deadline_str = w_entry.get("claim_deadline")
    if deadline_str:
        deadline = datetime.datetime.fromisoformat(deadline_str)
        if datetime.datetime.utcnow() > deadline:
            await db.waitlists.update_one(
                {"_id": ObjectId(waitlist_id)},
                {"$set": {"status": WaitlistStatus.EXPIRED.value}}
            )
            raise HTTPException(status_code=400, detail="Your claim window for this slot has expired.")

    # Book the appointment
    doctor_id = w_entry["doctor_id"]
    date_str = w_entry["preferred_date"]
    time_str = w_entry.get("assigned_time") or w_entry.get("preferred_time") or "09:00"
    c_type_val = w_entry.get("consultation_type", ConsultationType.IN_PERSON.value)
    c_type = ConsultationType(c_type_val)

    booked_appt = await book_appointment(
        doctor_id=doctor_id,
        date=date_str,
        time_slot=time_str,
        user=user,
        consultation_type=c_type,
        reason=reason or "Claimed from Waitlist",
        lock_token=w_entry.get("lock_token"),
    )

    # Mark waitlist as BOOKED
    now_iso = datetime.datetime.utcnow().isoformat()
    await db.waitlists.update_one(
        {"_id": ObjectId(waitlist_id)},
        {"$set": {
            "status": WaitlistStatus.BOOKED.value,
            "appointment_id": booked_appt["id"],
            "updated_at": now_iso,
        }}
    )

    return {
        "message": "Waitlist slot claimed and confirmed successfully!",
        "appointment": booked_appt,
    }


async def expire_stale_waitlist_claims():
    """
    Background worker task: Finds expired waitlist notifications, marks them EXPIRED,
    and automatically triggers promotion for the next waitlist candidate in line.
    """
    now_iso = datetime.datetime.utcnow().isoformat()
    expired_cursor = db.waitlists.find({
        "status": WaitlistStatus.NOTIFIED.value,
        "claim_deadline": {"$lt": now_iso}
    })

    expired_list = []
    async for w in expired_cursor:
        expired_list.append(w)

    for w in expired_list:
        w_id = str(w["_id"])
        doc_id = w["doctor_id"]
        d_str = w["preferred_date"]
        t_str = w.get("assigned_time") or w.get("preferred_time")

        await db.waitlists.update_one(
            {"_id": ObjectId(w_id)},
            {"$set": {"status": WaitlistStatus.EXPIRED.value, "updated_at": now_iso}}
        )
        logger.info(f"Waitlist claim expired for waitlist ID {w_id}.")

        # Auto-promote next candidate
        if t_str:
            await process_waitlist_on_cancellation(doc_id, d_str, t_str)

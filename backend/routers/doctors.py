import datetime
from typing import List
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models import Doctor, DoctorAvailability, DoctorLeave
from dependencies import require_admin, get_current_user
from services.scheduling_service import (
    get_doctor_availability,
    save_doctor_availability,
)

router = APIRouter(tags=["doctors"])


# --- Doctor Profile Endpoints ---
@router.post("/api/v1/doctors", status_code=201)
@router.post("/doctor", status_code=201)
async def add_doctor(doc: Doctor, admin=Depends(require_admin)):
    """Creates a new doctor record (Admin only)."""
    doc_dict = doc.dict(exclude={"availability"})
    result = await db.doctors.insert_one(doc_dict)
    doctor_id = str(result.inserted_id)

    # If availability config provided, save it
    if doc.availability:
        doc.availability.doctor_id = doctor_id
        await save_doctor_availability(doctor_id, doc.availability)

    return {"id": doctor_id, "message": "Doctor created successfully"}


@router.get("/api/v1/doctors", response_model=List[dict])
@router.get("/doctors", response_model=List[dict])
async def get_doctors():
    """Returns list of all active doctors with availability details."""
    docs = []
    async for d in db.doctors.find():
        d["_id"] = str(d["_id"])
        d["id"] = d["_id"]
        docs.append(d)
    return docs


@router.get("/api/v1/doctors/{doctor_id}")
@router.get("/doctor/{doctor_id}")
async def get_doctor(doctor_id: str):
    """Retrieves a single doctor by ID."""
    try:
        doc = await db.doctors.find_one({"_id": ObjectId(doctor_id)})
    except (InvalidId, Exception):
        doc = None

    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")

    doc["_id"] = str(doc["_id"])
    doc["id"] = doc["_id"]
    return doc


# --- Doctor Availability Endpoints ---
@router.get("/api/v1/doctors/{doctor_id}/availability", response_model=DoctorAvailability)
@router.get("/doctor/{doctor_id}/availability", response_model=DoctorAvailability)
async def get_availability(doctor_id: str):
    """Gets working days, shifts, breaks, duration, and buffer for a doctor."""
    return await get_doctor_availability(doctor_id)


@router.put("/api/v1/doctors/{doctor_id}/availability", response_model=DoctorAvailability)
@router.put("/doctor/{doctor_id}/availability", response_model=DoctorAvailability)
async def update_availability(
    doctor_id: str,
    avail: DoctorAvailability,
    user: dict = Depends(get_current_user)
):
    """Updates doctor availability configuration (Doctor or Admin)."""
    is_admin = bool(user.get("is_admin"))
    user_id = str(user.get("_id") or user.get("id"))
    is_doctor = False

    if user.get("role") == "DOCTOR":
        doc_record = await db.doctors.find_one({"_id": ObjectId(doctor_id), "user_id": user_id})
        if doc_record:
            is_doctor = True

    if not (is_admin or is_doctor):
        raise HTTPException(status_code=403, detail="Admin or Doctor credentials required to edit availability")

    avail.doctor_id = doctor_id
    return await save_doctor_availability(doctor_id, avail)


# --- Doctor Leave Management Endpoints ---
@router.get("/api/v1/doctors/{doctor_id}/leaves")
@router.get("/doctor/{doctor_id}/leaves")
async def get_doctor_leaves(doctor_id: str):
    """Lists all approved leave dates for a doctor."""
    leaves = []
    async for l in db.doctor_leaves.find({"doctor_id": str(doctor_id)}):
        leaves.append({
            "id": str(l["_id"]),
            "_id": str(l["_id"]),
            "doctor_id": str(doctor_id),
            "start_date": l.get("start_date"),
            "end_date": l.get("end_date"),
            "reason": l.get("reason"),
            "created_at": l.get("created_at"),
        })
    return leaves


@router.post("/api/v1/doctors/{doctor_id}/leaves", status_code=201)
@router.post("/doctor/{doctor_id}/leaves", status_code=201)
async def add_doctor_leave(
    doctor_id: str,
    leave: DoctorLeave,
    user: dict = Depends(get_current_user)
):
    """Adds a leave period for a doctor (Admin or Doctor)."""
    is_admin = bool(user.get("is_admin"))
    user_id = str(user.get("_id") or user.get("id"))
    is_doctor = False

    if user.get("role") == "DOCTOR":
        doc_record = await db.doctors.find_one({"_id": ObjectId(doctor_id), "user_id": user_id})
        if doc_record:
            is_doctor = True

    if not (is_admin or is_doctor):
        raise HTTPException(status_code=403, detail="Admin or Doctor credentials required to record leaves")

    now_iso = datetime.datetime.utcnow().isoformat()
    leave_doc = {
        "doctor_id": str(doctor_id),
        "start_date": leave.start_date,
        "end_date": leave.end_date,
        "reason": leave.reason or "Doctor Leave",
        "created_at": now_iso,
    }
    result = await db.doctor_leaves.insert_one(leave_doc)
    return {
        "id": str(result.inserted_id),
        "message": "Leave recorded successfully",
        **leave_doc
    }


@router.delete("/api/v1/doctors/{doctor_id}/leaves/{leave_id}")
@router.delete("/doctor/{doctor_id}/leaves/{leave_id}")
async def delete_doctor_leave(
    doctor_id: str,
    leave_id: str,
    user: dict = Depends(get_current_user)
):
    """Deletes/cancels a doctor's leave period."""
    is_admin = bool(user.get("is_admin"))
    user_id = str(user.get("_id") or user.get("id"))
    is_doctor = False

    if user.get("role") == "DOCTOR":
        doc_record = await db.doctors.find_one({"_id": ObjectId(doctor_id), "user_id": user_id})
        if doc_record:
            is_doctor = True

    if not (is_admin or is_doctor):
        raise HTTPException(status_code=403, detail="Not authorized to delete leaves")

    res = await db.doctor_leaves.delete_one({"_id": ObjectId(leave_id), "doctor_id": str(doctor_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Leave record not found")

    return {"message": "Leave removed successfully"}

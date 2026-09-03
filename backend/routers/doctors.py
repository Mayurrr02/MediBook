from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models import Doctor, DoctorScheduleConfig
from dependencies import require_admin, get_current_user
from services.scheduling_service import (
    get_doctor_schedule_config,
    save_doctor_schedule_config,
)

router = APIRouter(tags=["doctors"])


@router.post("/doctor")
async def add_doctor(doc: Doctor, admin=Depends(require_admin)):
    """Creates a new doctor record (Admin only)."""
    doc_dict = doc.dict(exclude={"schedule"})
    result = await db.doctors.insert_one(doc_dict)
    doctor_id = str(result.inserted_id)

    # If schedule config provided, save it
    if doc.schedule:
        doc.schedule.doctor_id = doctor_id
        await save_doctor_schedule_config(doctor_id, doc.schedule)

    return {"id": doctor_id, "message": "Doctor added successfully"}


@router.get("/doctors")
async def get_doctors():
    """Returns list of all active doctors."""
    docs = []
    async for d in db.doctors.find():
        d["_id"] = str(d["_id"])
        docs.append(d)
    return docs


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
    return doc


@router.get("/doctor/{doctor_id}/schedule", response_model=DoctorScheduleConfig)
async def get_schedule(doctor_id: str):
    """Gets schedule and shift configuration for a doctor."""
    return await get_doctor_schedule_config(doctor_id)


@router.put("/doctor/{doctor_id}/schedule", response_model=DoctorScheduleConfig)
async def update_schedule(
    doctor_id: str,
    config: DoctorScheduleConfig,
    user: dict = Depends(get_current_user)
):
    """Updates doctor working schedule (Admin or assigned doctor)."""
    is_admin = bool(user.get("is_admin"))
    is_assigned_doctor = False
    if user.get("role") == "DOCTOR":
        doc_record = await db.doctors.find_one({"_id": ObjectId(doctor_id), "user_id": str(user["_id"])})
        if doc_record:
            is_assigned_doctor = True

    if not (is_admin or is_assigned_doctor):
        raise HTTPException(status_code=403, detail="Admin or Doctor credentials required to edit schedule")

    return await save_doctor_schedule_config(doctor_id, config)

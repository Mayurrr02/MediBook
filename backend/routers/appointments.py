from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

from database import db
from models import Appointment
from dependencies import get_current_user

router = APIRouter(tags=["appointments"])


@router.post("/appointment")
async def book_appointment(appo: Appointment, user: dict = Depends(get_current_user)):
    # Prevent double-booking: same doctor, same date, same slot.
    clash = await db.appointments.find_one({
        "doctor_id": appo.doctor_id,
        "date": appo.date,
        "time": appo.time,
    })
    if clash:
        raise HTTPException(409, "This slot is already booked. Please pick another.")

    data = appo.dict()
    data["user_id"] = user["_id"]

    result = await db.appointments.insert_one(data)
    return {"message": "appointment created", "id": str(result.inserted_id)}


@router.get("/appointments")
async def get_appointments(user: dict = Depends(get_current_user)):
    result_list = []

    async for a in db.appointments.find({"user_id": user["_id"]}):
        doctor_id = a.get("doctor_id")
        doctor = None
        try:
            doctor = await db.doctors.find_one({"_id": ObjectId(doctor_id)})
        except InvalidId:
            doctor = None

        result_list.append({
            "_id": str(a["_id"]),
            "doctor_id": doctor_id,
            "doctor_name": doctor["name"] if doctor else "Unknown Doctor",
            "specialization": doctor["specialization"] if doctor else "N/A",
            "date": a.get("date"),
            "time": a.get("time", "Not set"),
        })

    return result_list
